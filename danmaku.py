"""B 站直播弹幕协议客户端。

数据流：
1. `get_danmu_info(room_id)` HTTP 拉 WS 连接 token + 服务器列表
2. `subscribe(room_id, real_room_id)` 建 WS 连接，返回 async iterator 推送解析后的消息

帧格式（大端）：
  offset 0,  4 bytes: packet length (整包，含头)
  offset 4,  2 bytes: header length (16)
  offset 6,  2 bytes: protocol version (0=raw JSON, 2=zlib, 3=brotli)
  offset 8,  4 bytes: operation (2=heartbeat, 3=heartbeat reply, 5=notification, 7=auth, 8=auth reply)
  offset 12, 4 bytes: sequence

操作码常用：2/3/5/7/8。protover 用 2（zlib），避开 brotli 第三方依赖。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import struct
import time
import zlib
from typing import AsyncIterator
from urllib.parse import urlencode

import httpx
import websockets

log = logging.getLogger("danmaku")

# WBI 签名重排表（B 站固定常量，社区已知）
_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]
_NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
_WBI_CACHE: dict[str, tuple[str, float]] = {}  # mixin_key 缓存（含过期）

_DANMU_INFO_URL = "https://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo"
_BASE_HEADERS = {
    "Referer": "https://live.bilibili.com",
    "Origin": "https://live.bilibili.com",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
}
_FINGER_SPI_URL = "https://api.bilibili.com/x/frontend/finger/spi"
_BUVID_CACHE: dict[str, str] = {}  # 进程级缓存


async def _get_buvid(client: httpx.AsyncClient) -> str:
    """从 B 站接口拉真 buvid3（反爬必备）。进程级缓存。"""
    if "b3" in _BUVID_CACHE:
        return _BUVID_CACHE["b3"]
    try:
        r = await client.get(_FINGER_SPI_URL, headers=_BASE_HEADERS, timeout=6.0)
        r.raise_for_status()
        j = r.json()
        b3 = (j.get("data") or {}).get("b_3") or ""
        if b3:
            _BUVID_CACHE["b3"] = b3
            return b3
    except Exception as e:
        log.warning("finger/spi failed: %s", e)
    # 兜底
    return "A1B2C3D4-E5F6-7890-ABCD-EF1234567890infoc"


async def _headers_with_buvid(client: httpx.AsyncClient) -> dict:
    b3 = await _get_buvid(client)
    return {**_BASE_HEADERS, "Cookie": f"buvid3={b3}"}


async def _get_mixin_key(client: httpx.AsyncClient) -> str:
    """从 /nav 拉 wbi keys；缓存 10 分钟。"""
    now = time.time()
    cached = _WBI_CACHE.get("mixin")
    if cached and now - cached[1] < 600:
        return cached[0]
    try:
        headers = await _headers_with_buvid(client)
        r = await client.get(_NAV_URL, headers=headers, timeout=6.0)
        r.raise_for_status()
        wbi = ((r.json().get("data") or {}).get("wbi_img") or {})
        img_url = wbi.get("img_url") or ""
        sub_url = wbi.get("sub_url") or ""
        img_key = img_url.rsplit("/", 1)[-1].split(".", 1)[0]
        sub_key = sub_url.rsplit("/", 1)[-1].split(".", 1)[0]
        if not img_key or not sub_key:
            raise DanmakuError("nav: empty wbi keys")
        raw = img_key + sub_key
        mixin = "".join(raw[i] for i in _MIXIN_KEY_ENC_TAB if i < len(raw))[:32]
        _WBI_CACHE["mixin"] = (mixin, now)
        return mixin
    except Exception as e:
        log.warning("get_mixin_key failed: %s", e)
        raise


def _sign_wbi(params: dict, mixin_key: str) -> dict:
    """给 params 加上 wts + w_rid 签名。"""
    signed = {**params, "wts": int(time.time())}
    # 按 key 字母序排序；值过滤 !'()* （B 站官方 sample 行为）
    sorted_items = sorted(signed.items())
    cleaned = {k: str(v).translate(str.maketrans("", "", "!'()*")) for k, v in sorted_items}
    q = urlencode(cleaned)
    w_rid = hashlib.md5((q + mixin_key).encode("utf-8")).hexdigest()
    cleaned["w_rid"] = w_rid
    return cleaned

OP_HEARTBEAT = 2
OP_HEARTBEAT_REPLY = 3
OP_NOTIFICATION = 5
OP_AUTH = 7
OP_AUTH_REPLY = 8

HEADER_LEN = 16
HEARTBEAT_INTERVAL = 30  # 秒


class DanmakuError(Exception):
    pass


async def get_danmu_info(room_id: int) -> dict:
    """拉 WS 连接配置（token + host_list）。需要 wbi 签名。"""
    async with httpx.AsyncClient(trust_env=False) as client:
        headers = await _headers_with_buvid(client)
        mixin_key = await _get_mixin_key(client)
        params = _sign_wbi({"id": room_id, "type": 0}, mixin_key)
        resp = await client.get(
            _DANMU_INFO_URL,
            params=params,
            headers=headers,
            timeout=8.0,
        )
        resp.raise_for_status()
        j = resp.json()
    if j.get("code") != 0:
        raise DanmakuError(f"getDanmuInfo code={j.get('code')} msg={j.get('message')}")
    return j["data"]


def _pack_packet(op: int, body: bytes, protover: int = 1) -> bytes:
    total = HEADER_LEN + len(body)
    header = struct.pack(">IHHII", total, HEADER_LEN, protover, op, 1)
    return header + body


def _parse_packets(buf: bytes) -> list[tuple[int, int, bytes]]:
    """从一个 buffer 里解析出多个 (op, protover, body)。

    顶层 packet 可能是 protover=2 的 zlib 压缩载荷，解压后是嵌套多个 packet——递归解开。
    """
    out: list[tuple[int, int, bytes]] = []
    i = 0
    n = len(buf)
    while i + HEADER_LEN <= n:
        total, hlen, protover, op, _seq = struct.unpack(">IHHII", buf[i:i + HEADER_LEN])
        if total <= 0 or i + total > n:
            break
        body = buf[i + hlen:i + total]
        if protover == 2 and op == OP_NOTIFICATION:
            try:
                inner = zlib.decompress(body)
                out.extend(_parse_packets(inner))
            except zlib.error as e:
                log.warning("zlib decompress failed: %s", e)
        else:
            out.append((op, protover, body))
        i += total
    return out


def _parse_business_msg(raw_body: bytes) -> dict | None:
    """把单条业务消息 body 解成 dict；返回 None 表示不感兴趣。"""
    try:
        j = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    cmd = j.get("cmd") or ""
    # 兼容 `DANMU_MSG:4:0:2:2:2:0` 这种带后缀的命令
    cmd_base = cmd.split(":")[0]
    if cmd_base == "DANMU_MSG":
        info = j.get("info") or []
        try:
            text = info[1]
            uname = info[2][1]
            color = info[0][3] if len(info[0]) > 3 else 0xFFFFFF
            return {"type": "danmu", "text": text, "uname": uname, "color": color}
        except (IndexError, TypeError):
            return None
    if cmd_base == "SEND_GIFT":
        d = j.get("data") or {}
        return {
            "type": "gift",
            "uname": d.get("uname", ""),
            "gift_name": d.get("giftName", ""),
            "num": d.get("num", 1),
        }
    if cmd_base == "SUPER_CHAT_MESSAGE":
        d = j.get("data") or {}
        return {
            "type": "sc",
            "uname": (d.get("user_info") or {}).get("uname", ""),
            "text": d.get("message", ""),
            "price": d.get("price", 0),
        }
    if cmd_base == "INTERACT_WORD":
        d = j.get("data") or {}
        if d.get("msg_type") == 1:  # 进入直播间
            return {"type": "enter", "uname": d.get("uname", "")}
    return None


async def subscribe(room_id: int) -> AsyncIterator[dict]:
    """订阅指定房间的弹幕流，async 生成器，逐条 yield 解析后的 dict。

    使用 protover=2（zlib），不依赖 brotli。
    """
    cfg = await get_danmu_info(room_id)
    token = cfg.get("token") or ""
    hosts = cfg.get("host_list") or []
    if not hosts:
        raise DanmakuError("no host_list in getDanmuInfo response")
    host = hosts[0]
    wss_url = f"wss://{host['host']}:{host.get('wss_port', 443)}/sub"
    log.info("danmaku connect %s for room %s", wss_url, room_id)

    auth_body = json.dumps({
        "uid": 0,
        "roomid": int(room_id),
        "protover": 2,  # 用 zlib，避开 brotli
        "platform": "web",
        "type": 2,
        "key": token,
    }, separators=(",", ":")).encode("utf-8")

    async with websockets.connect(wss_url, max_size=2 ** 23, open_timeout=10) as ws:
        await ws.send(_pack_packet(OP_AUTH, auth_body, protover=1))
        log.info("danmaku auth sent for room %s", room_id)

        async def heartbeat_loop():
            try:
                while True:
                    await asyncio.sleep(HEARTBEAT_INTERVAL)
                    await ws.send(_pack_packet(OP_HEARTBEAT, b"", protover=1))
            except (asyncio.CancelledError, websockets.exceptions.ConnectionClosed):
                pass

        hb_task = asyncio.create_task(heartbeat_loop())
        try:
            async for raw in ws:
                if isinstance(raw, str):
                    raw = raw.encode("utf-8")
                packets = _parse_packets(raw)
                for op, _ver, body in packets:
                    if op == OP_AUTH_REPLY:
                        try:
                            reply = json.loads(body.decode("utf-8"))
                            log.info("auth reply room=%s code=%s", room_id, reply.get("code"))
                        except Exception:
                            log.info("auth reply (unparseable) room=%s len=%d", room_id, len(body))
                        continue
                    if op == OP_HEARTBEAT_REPLY:
                        continue
                    if op == OP_NOTIFICATION:
                        msg = _parse_business_msg(body)
                        if msg:
                            yield msg
        finally:
            hb_task.cancel()
            try:
                await hb_task
            except (asyncio.CancelledError, BaseException):
                pass
