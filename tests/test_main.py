import pytest
import respx
import httpx
from fastapi.testclient import TestClient

from main import app


SAMPLE_PLAYINFO = {
    "code": 0,
    "data": {
        "room_id": 67890,
        "live_status": 1,
        "playurl_info": {
            "playurl": {
                "stream": [{"protocol_name": "http_stream", "format": [{
                    "format_name": "flv",
                    "codec": [{
                        "codec_name": "avc",
                        "current_qn": 250,
                        "accept_qn": [80, 150, 250, 400, 10000],
                        "base_url": "/live-bvc/x/x.flv?e=1",
                        "url_info": [{"host": "https://cdn.bilivideo.com", "extra": "&t=a"}],
                    }],
                }]}]
            }
        },
    },
}

SAMPLE_ROOMINFO = {
    "code": 0,
    "data": {
        "room_info": {"title": "t"},
        "anchor_info": {"base_info": {"uname": "u"}},
    },
}


@respx.mock
def test_api_stream_success():
    respx.get("https://api.live.bilibili.com/xlive/web-room/v2/index/getRoomPlayInfo").mock(
        return_value=httpx.Response(200, json=SAMPLE_PLAYINFO))
    respx.get("https://api.live.bilibili.com/xlive/web-room/v1/index/getInfoByRoom").mock(
        return_value=httpx.Response(200, json=SAMPLE_ROOMINFO))

    client = TestClient(app)
    r = client.get("/api/stream", params={"room_id": "12345", "qn": 250})
    assert r.status_code == 200
    j = r.json()
    assert j["real_room_id"] == 67890
    assert j["stream_url"].startswith("https://cdn.bilivideo.com/")
    assert j["format"] == "flv"


@respx.mock
def test_api_stream_full_url_input():
    respx.get("https://api.live.bilibili.com/xlive/web-room/v2/index/getRoomPlayInfo").mock(
        return_value=httpx.Response(200, json=SAMPLE_PLAYINFO))
    respx.get("https://api.live.bilibili.com/xlive/web-room/v1/index/getInfoByRoom").mock(
        return_value=httpx.Response(200, json=SAMPLE_ROOMINFO))

    client = TestClient(app)
    r = client.get("/api/stream", params={"room_id": "https://live.bilibili.com/12345"})
    assert r.status_code == 200


def test_api_stream_bad_input():
    client = TestClient(app)
    r = client.get("/api/stream", params={"room_id": "not-a-room"})
    assert r.status_code == 400
    assert "无法识别" in r.json()["detail"]


@respx.mock
def test_api_stream_not_live():
    not_live = {**SAMPLE_PLAYINFO}
    not_live["data"] = {**SAMPLE_PLAYINFO["data"], "live_status": 0, "playurl_info": None}
    respx.get("https://api.live.bilibili.com/xlive/web-room/v2/index/getRoomPlayInfo").mock(
        return_value=httpx.Response(200, json=not_live))
    respx.get("https://api.live.bilibili.com/xlive/web-room/v1/index/getInfoByRoom").mock(
        return_value=httpx.Response(200, json=SAMPLE_ROOMINFO))

    client = TestClient(app)
    r = client.get("/api/stream", params={"room_id": "12345"})
    assert r.status_code == 503
    assert "未开播" in r.json()["detail"]


def test_index_html_served():
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "<!DOCTYPE html>" in r.text
