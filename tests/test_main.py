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


# ---------------- /api/room ----------------

_ROOM_META_RESP = {
    "code": 0,
    "data": {
        "room_info": {
            "title": "t", "uid": 99, "room_id": 67890, "live_status": 1,
            "online": 1234, "area_name": "电竞", "parent_area_name": "网游",
            "live_start_time": 1700000000,
        },
        "anchor_info": {
            "base_info": {"uname": "u", "face": "https://i0.hdslb.com/x.jpg"},
        },
    },
}


@respx.mock
def test_api_room_success():
    respx.get("https://api.live.bilibili.com/xlive/web-room/v1/index/getInfoByRoom").mock(
        return_value=httpx.Response(200, json=_ROOM_META_RESP))
    client = TestClient(app)
    r = client.get("/api/room", params={"room_id": "12345"})
    assert r.status_code == 200
    j = r.json()
    assert j["uid"] == 99
    assert j["uname"] == "u"
    assert j["live_status"] == 1
    assert j["area_name"] == "电竞"


def test_api_room_bad_input():
    client = TestClient(app)
    r = client.get("/api/room", params={"room_id": "nope"})
    assert r.status_code == 400


# ---------------- /api/status ----------------

@respx.mock
def test_api_status_success():
    respx.post("https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids").mock(
        return_value=httpx.Response(200, json={
            "code": 0,
            "data": {
                "123": {"room_id": 1, "title": "t1", "uname": "a", "live_status": 1, "online": 100},
                "456": {"room_id": 2, "title": "t2", "uname": "b", "live_status": 1, "online": 200},
            },
        }))
    client = TestClient(app)
    r = client.post("/api/status", json={"uids": [123, 456, 789]})
    assert r.status_code == 200
    j = r.json()
    assert "123" in j and j["123"]["live_status"] == 1
    assert "789" not in j


def test_api_status_empty_uids():
    client = TestClient(app)
    r = client.post("/api/status", json={"uids": []})
    assert r.status_code == 200
    assert r.json() == {}


def test_api_status_too_many():
    client = TestClient(app)
    r = client.post("/api/status", json={"uids": list(range(201))})
    assert r.status_code == 400


def test_api_status_bad_payload():
    client = TestClient(app)
    r = client.post("/api/status", json={"uids": "nope"})
    assert r.status_code == 400
