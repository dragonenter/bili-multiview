import asyncio
import re
from typing import Any

import httpx


class RoomIdError(ValueError):
    """非法的房间号或链接。"""


class BiliApiError(Exception):
    """B 站接口返回错误码或结构异常。"""


class StreamNotLiveError(Exception):
    """主播未开播。"""


_URL_RE = re.compile(r"https?://live\.bilibili\.com/(\d+)")
_NUMBER_RE = re.compile(r"^\d+$")

_PLAYINFO_URL = "https://api.live.bilibili.com/xlive/web-room/v2/index/getRoomPlayInfo"
_ROOMINFO_URL = "https://api.live.bilibili.com/xlive/web-room/v1/index/getInfoByRoom"

_HEADERS = {
    "Referer": "https://live.bilibili.com",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
}


def parse_room_id(text: str) -> str:
    """从用户输入提取真实房间号字符串。

    支持：
    - 完整链接 https://live.bilibili.com/12345 (可带 query/尾斜杠)
    - 纯数字字符串 12345
    """
    if not text or not text.strip():
        raise RoomIdError("输入为空")
    text = text.strip()
    m = _URL_RE.search(text)
    if m:
        rid = m.group(1)
    elif _NUMBER_RE.match(text):
        rid = text
    else:
        raise RoomIdError(f"无法识别的房间号或链接：{text!r}")
    if int(rid) <= 0:
        raise RoomIdError(f"无效房间号：{rid}")
    return rid


async def _fetch_json(client: httpx.AsyncClient, url: str, params: dict) -> dict:
    try:
        resp = await client.get(url, params=params, headers=_HEADERS, timeout=8.0)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise BiliApiError(
            f"B 站接口返回 HTTP {e.response.status_code}：{url}"
        ) from e
    except httpx.RequestError as e:
        raise BiliApiError(f"B 站接口请求失败：{e}") from e
    return resp.json()


async def get_stream_info(room_id: str, qn: int = 250) -> dict[str, Any]:
    """并行调用 B 站接口，返回汇总流信息。"""
    play_params = {
        "room_id": room_id,
        "protocol": "0,1",
        "format": "0,1,2",
        "codec": "0,1",
        "qn": qn,
        "platform": "web",
        "ptype": 8,
    }
    info_params = {"room_id": room_id}

    async with httpx.AsyncClient(trust_env=False) as client:
        play_json, info_json = await asyncio.gather(
            _fetch_json(client, _PLAYINFO_URL, play_params),
            _fetch_json(client, _ROOMINFO_URL, info_params),
        )

    if play_json.get("code") != 0:
        raise BiliApiError(
            f"getRoomPlayInfo code={play_json.get('code')} msg={play_json.get('message')}"
        )

    pdata = play_json.get("data") or {}
    live_status = pdata.get("live_status", 0)
    real_room_id = pdata.get("room_id", int(room_id))

    title = "未知标题"
    uname = "未知主播"
    if info_json.get("code") == 0:
        idata = info_json.get("data") or {}
        title = (idata.get("room_info") or {}).get("title") or title
        uname = ((idata.get("anchor_info") or {}).get("base_info") or {}).get("uname") or uname

    if live_status != 1 or not pdata.get("playurl_info"):
        raise StreamNotLiveError(
            f"主播未开播（room_id={real_room_id}, status={live_status}）"
        )

    try:
        codec = pdata["playurl_info"]["playurl"]["stream"][0]["format"][0]["codec"][0]
        url_info = codec["url_info"][0]
        stream_url = url_info["host"] + codec["base_url"] + url_info["extra"]
        current_qn = codec["current_qn"]
        accept_qn = codec["accept_qn"]
        fmt = pdata["playurl_info"]["playurl"]["stream"][0]["format"][0]["format_name"]
    except (KeyError, IndexError, TypeError) as e:
        raise BiliApiError(f"playurl 结构解析失败: {e}")

    return {
        "room_id": int(room_id),
        "real_room_id": real_room_id,
        "live_status": live_status,
        "title": title,
        "uname": uname,
        "qn": current_qn,
        "accept_qn": accept_qn,
        "stream_url": stream_url,
        "format": fmt,
    }
