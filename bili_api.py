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
_STATUS_BY_UIDS_URL = "https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids"

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


async def get_room_meta(room_id: str) -> dict[str, Any]:
    """只调 getInfoByRoom 拿房间元信息（不要求开播，用于加入关注列表）。

    返回字段包含 uid（关键，是后续批量查在播状态的入口）。
    """
    async with httpx.AsyncClient(trust_env=False) as client:
        info_json = await _fetch_json(client, _ROOMINFO_URL, {"room_id": room_id})
    if info_json.get("code") != 0:
        raise BiliApiError(
            f"getInfoByRoom code={info_json.get('code')} msg={info_json.get('message')}"
        )
    idata = info_json.get("data") or {}
    rinfo = idata.get("room_info") or {}
    ainfo = idata.get("anchor_info") or {}
    base = ainfo.get("base_info") or {}
    return {
        "room_id": int(room_id),
        "real_room_id": rinfo.get("room_id") or int(room_id),
        "uid": rinfo.get("uid") or 0,
        "uname": base.get("uname") or "",
        "face": base.get("face") or "",
        "title": rinfo.get("title") or "",
        "area_name": rinfo.get("area_name") or "",
        "parent_area_name": rinfo.get("parent_area_name") or "",
        "live_status": rinfo.get("live_status", 0),
        "online": rinfo.get("online") or 0,
        "live_start_time": rinfo.get("live_start_time") or 0,
    }


async def get_status_by_uids(uids: list[int]) -> dict[str, Any]:
    """批量查多个主播的当前直播状态。

    B 站接口：POST /room/v1/Room/get_status_info_by_uids，body {"uids": [int,...]}
    返回 {str_uid: {room_id, title, live_status, online, ...}}；
    未开播 / 没直播间的 UID 通常不在返回里。
    """
    if not uids:
        return {}
    async with httpx.AsyncClient(trust_env=False) as client:
        try:
            resp = await client.post(
                _STATUS_BY_UIDS_URL,
                json={"uids": list(uids)},
                headers=_HEADERS,
                timeout=8.0,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise BiliApiError(
                f"get_status_info_by_uids HTTP {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            raise BiliApiError(f"get_status_info_by_uids request failed: {e}") from e
        j = resp.json()
    if j.get("code") != 0:
        raise BiliApiError(
            f"get_status_info_by_uids code={j.get('code')} msg={j.get('message')}"
        )
    return j.get("data") or {}


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
    uid = 0
    face = ""
    online = 0
    live_start_time = 0
    area_name = ""
    parent_area_name = ""
    tags = ""
    fans = 0
    if info_json.get("code") == 0:
        idata = info_json.get("data") or {}
        rinfo = idata.get("room_info") or {}
        ainfo = idata.get("anchor_info") or {}
        ainfo_base = ainfo.get("base_info") or {}
        ainfo_rel = ainfo.get("relation_info") or {}

        title = rinfo.get("title") or title
        uid = rinfo.get("uid") or 0
        online = rinfo.get("online") or 0
        live_start_time = rinfo.get("live_start_time") or 0
        area_name = rinfo.get("area_name") or ""
        parent_area_name = rinfo.get("parent_area_name") or ""
        tags = rinfo.get("tags") or ""

        uname = ainfo_base.get("uname") or uname
        face = ainfo_base.get("face") or ""
        fans = ainfo_rel.get("attention") or rinfo.get("attention") or 0

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
        "uid": uid,
        "face": face,
        "online": online,
        "live_start_time": live_start_time,
        "area_name": area_name,
        "parent_area_name": parent_area_name,
        "tags": tags,
        "fans": fans,
        "qn": current_qn,
        "accept_qn": accept_qn,
        "stream_url": stream_url,
        "format": fmt,
    }
