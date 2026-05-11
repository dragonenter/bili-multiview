import pytest
import httpx
import respx

from bili_api import (
    parse_room_id,
    RoomIdError,
    get_stream_info,
    StreamNotLiveError,
    BiliApiError,
)


class TestParseRoomId:
    def test_full_url(self):
        assert parse_room_id("https://live.bilibili.com/12345") == "12345"

    def test_full_url_with_query(self):
        assert parse_room_id("https://live.bilibili.com/12345?from=search") == "12345"

    def test_http_url(self):
        assert parse_room_id("http://live.bilibili.com/67890") == "67890"

    def test_url_trailing_slash(self):
        assert parse_room_id("https://live.bilibili.com/12345/") == "12345"

    def test_plain_number(self):
        assert parse_room_id("12345") == "12345"

    def test_plain_number_with_whitespace(self):
        assert parse_room_id("  12345  ") == "12345"

    def test_invalid_string_raises(self):
        with pytest.raises(RoomIdError):
            parse_room_id("not-a-room")

    def test_empty_raises(self):
        with pytest.raises(RoomIdError):
            parse_room_id("")

    def test_zero_raises(self):
        with pytest.raises(RoomIdError):
            parse_room_id("0")


SAMPLE_PLAYINFO = {
    "code": 0,
    "message": "0",
    "data": {
        "room_id": 67890,
        "short_id": 12345,
        "uid": 999,
        "live_status": 1,
        "playurl_info": {
            "playurl": {
                "stream": [{
                    "protocol_name": "http_stream",
                    "format": [{
                        "format_name": "flv",
                        "codec": [{
                            "codec_name": "avc",
                            "current_qn": 10000,
                            "accept_qn": [80, 150, 250, 400, 10000],
                            "base_url": "/live-bvc/123/live_999.flv?expires=1",
                            "url_info": [{
                                "host": "https://cn-cdn.bilivideo.com",
                                "extra": "&token=abc",
                                "stream_ttl": 3600,
                            }],
                        }],
                    }],
                }]
            }
        },
    },
}

SAMPLE_ROOMINFO = {
    "code": 0,
    "data": {
        "room_info": {"title": "测试直播间标题"},
        "anchor_info": {"base_info": {"uname": "测试主播"}},
    },
}


@respx.mock
async def test_get_stream_info_success():
    respx.get("https://api.live.bilibili.com/xlive/web-room/v2/index/getRoomPlayInfo").mock(
        return_value=httpx.Response(200, json=SAMPLE_PLAYINFO))
    respx.get("https://api.live.bilibili.com/xlive/web-room/v1/index/getInfoByRoom").mock(
        return_value=httpx.Response(200, json=SAMPLE_ROOMINFO))

    info = await get_stream_info("12345", qn=10000)

    assert info["real_room_id"] == 67890
    assert info["live_status"] == 1
    assert info["title"] == "测试直播间标题"
    assert info["uname"] == "测试主播"
    assert info["qn"] == 10000
    assert info["accept_qn"] == [80, 150, 250, 400, 10000]
    assert info["stream_url"] == (
        "https://cn-cdn.bilivideo.com/live-bvc/123/live_999.flv?expires=1&token=abc"
    )
    assert info["format"] == "flv"


@respx.mock
async def test_get_stream_info_not_live_raises():
    not_live = {
        "code": 0,
        "data": {**SAMPLE_PLAYINFO["data"], "live_status": 0, "playurl_info": None},
    }
    respx.get("https://api.live.bilibili.com/xlive/web-room/v2/index/getRoomPlayInfo").mock(
        return_value=httpx.Response(200, json=not_live))
    respx.get("https://api.live.bilibili.com/xlive/web-room/v1/index/getInfoByRoom").mock(
        return_value=httpx.Response(200, json=SAMPLE_ROOMINFO))

    with pytest.raises(StreamNotLiveError):
        await get_stream_info("12345")


@respx.mock
async def test_get_stream_info_api_error_raises():
    respx.get("https://api.live.bilibili.com/xlive/web-room/v2/index/getRoomPlayInfo").mock(
        return_value=httpx.Response(200, json={"code": 60004, "message": "房间不存在"}))
    respx.get("https://api.live.bilibili.com/xlive/web-room/v1/index/getInfoByRoom").mock(
        return_value=httpx.Response(200, json=SAMPLE_ROOMINFO))

    with pytest.raises(BiliApiError):
        await get_stream_info("12345")
