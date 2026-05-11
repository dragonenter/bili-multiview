# B站多路直播分屏观看器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个可公网访问的 web 服务，最多同屏播放 9 路 B 站直播，单击任一路放大并自动升原画。

**Architecture:** FastAPI 后端代理 B 站 `getRoomPlayInfo` API（自带 Referer 绕开反爬）→ 返回真实 FLV 流地址 → 浏览器 flv.js 直连 B 站 CDN 拉流。前端纯 HTML/JS，网格 ⇄ 焦点布局切换，画质随焦点联动。

**Tech Stack:** Python 3.10+ / FastAPI / uvicorn / httpx / respx (tests) / flv.js 1.6.2 / 原生 HTML+JS（无构建）

**Spec:** [`docs/superpowers/specs/2026-05-11-bili-multiview-design.md`](../specs/2026-05-11-bili-multiview-design.md)

**文件所有权（File Registry）：** 每个源文件归属唯一 task。

| 文件 | 所属 Task |
|------|----------|
| `requirements.txt` `requirements-dev.txt` `.gitignore` `pyproject.toml` `tests/__init__.py` | Task 1 |
| `bili_api.py` `tests/test_bili_api.py` | Task 2 |
| `main.py` `tests/test_main.py` `static/index.html` | Task 3 |
| `static/flv.min.js` | Task 4 |
| `static/style.css` | Task 5 |
| `static/player.js` | Task 6 |
| `static/app.js` | Task 7 |
| `start.sh` `stop.sh` `README.md` | Task 8 |

---

## Task 1: 项目骨架

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `tests/__init__.py`

- [ ] **Step 1: 创建依赖与配置文件**

`requirements.txt`：
```
fastapi==0.115.0
uvicorn[standard]==0.32.0
httpx==0.27.2
```

`requirements-dev.txt`：
```
-r requirements.txt
pytest==8.3.3
pytest-asyncio==0.24.0
respx==0.21.1
```

`.gitignore`：
```
__pycache__/
*.pyc
.venv/
venv/
.pytest_cache/
nohup.out
*.log
.idea/
.vscode/
.pid
```

`pyproject.toml`：
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

`tests/__init__.py`：空文件

- [ ] **Step 2: 初始化 git 仓库 + 提交**

```bash
cd /data/codes/lilong/bili-multiview
git init
git add requirements.txt requirements-dev.txt .gitignore pyproject.toml tests/__init__.py docs/
git commit -m "chore: init bili-multiview project skeleton"
```

- [ ] **Step 3: 安装依赖（验证）**

```bash
cd /data/codes/lilong/bili-multiview
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

Expected: 全部包安装成功，无报错。后续步骤直接用 `.venv/bin/python` / `.venv/bin/pytest`。

---

## Task 2: bili_api.py — 房间号解析 + B 站 API 调用（TDD）

**Files:**
- Create: `bili_api.py`
- Create: `tests/test_bili_api.py`

**Interface Contract（供 Task 3 import）：**
- `parse_room_id(text: str) -> str`：抛 `RoomIdError`
- `async get_stream_info(room_id: str, qn: int = 250) -> dict`：抛 `StreamNotLiveError` / `BiliApiError`
  - 返回字段：`room_id, real_room_id, live_status, title, uname, qn, accept_qn, stream_url, format`

- [ ] **Step 1: 写解析器的失败测试**

`tests/test_bili_api.py`：
```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/bin/pytest tests/test_bili_api.py -v
```
Expected: `ModuleNotFoundError: No module named 'bili_api'`。

- [ ] **Step 3: 实现 bili_api.py**

`bili_api.py`：
```python
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
    if not text:
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
    resp = await client.get(url, params=params, headers=_HEADERS, timeout=8.0)
    resp.raise_for_status()
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

    async with httpx.AsyncClient() as client:
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/bin/pytest tests/test_bili_api.py -v
```
Expected: 12 passed。

- [ ] **Step 5: Commit**

```bash
git add bili_api.py tests/test_bili_api.py
git commit -m "feat(bili-api): add room id parser and async stream info fetcher"
```

---

## Task 3: main.py — FastAPI 应用 + `/api/stream` + 静态资源挂载（TDD）

**Files:**
- Create: `main.py`
- Create: `tests/test_main.py`
- Create: `static/index.html`

**Imports from previous tasks:**
- `bili_api.parse_room_id`、`bili_api.get_stream_info`、`bili_api.RoomIdError`、`bili_api.StreamNotLiveError`、`bili_api.BiliApiError`

- [ ] **Step 1: 写失败的测试**

`tests/test_main.py`：
```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/bin/pytest tests/test_main.py -v
```
Expected: `ModuleNotFoundError: No module named 'main'`。

- [ ] **Step 3: 实现 static/index.html**

`static/index.html`：
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8" />
    <title>B站多路直播分屏 - bili-multiview</title>
    <link rel="stylesheet" href="/static/style.css" />
</head>
<body>
    <header class="toolbar">
        <textarea id="urls" placeholder="一行一个 B 站直播链接或房间号&#10;https://live.bilibili.com/12345&#10;67890"></textarea>
        <div class="buttons">
            <button id="btn-start">开始观看</button>
            <button id="btn-clear">清空</button>
            <button id="btn-exit-focus" hidden>退出焦点</button>
        </div>
    </header>
    <main id="stage" class="grid"></main>
    <script src="/static/flv.min.js"></script>
    <script src="/static/player.js"></script>
    <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 4: 实现 main.py**

`main.py`：
```python
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from bili_api import (
    parse_room_id,
    get_stream_info,
    RoomIdError,
    StreamNotLiveError,
    BiliApiError,
)


app = FastAPI(title="bili-multiview")

_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(_STATIC_DIR / "index.html")


@app.get("/api/stream")
async def api_stream(
    room_id: str = Query(..., description="房间号或完整直播链接"),
    qn: int = Query(250, description="画质：80/150/250/400/10000"),
):
    try:
        rid = parse_room_id(room_id)
    except RoomIdError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        info = await get_stream_info(rid, qn=qn)
    except StreamNotLiveError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except BiliApiError as e:
        raise HTTPException(status_code=502, detail=f"B站接口异常：{e}")

    return info
```

- [ ] **Step 5: 运行测试确认通过**

```bash
.venv/bin/pytest tests/test_main.py -v
```
Expected: 5 passed。

- [ ] **Step 6: 手动验证服务可启动**

```bash
.venv/bin/python -m uvicorn main:app --port 8765 &
sleep 2
curl -s -o /dev/null -w "/  -> %{http_code}\n" http://localhost:8765/
curl -s -o /dev/null -w "/static/index.html -> %{http_code}\n" http://localhost:8765/static/index.html
pkill -f "uvicorn main:app"
```
Expected: 两行均 `200`。

- [ ] **Step 7: Commit**

```bash
git add main.py tests/test_main.py static/index.html
git commit -m "feat(api): add /api/stream endpoint and static frontend mount"
```

---

## Task 4: 引入 flv.js

**Files:**
- Create: `static/flv.min.js`

- [ ] **Step 1: 下载 flv.js 1.6.2**

```bash
cd /data/codes/lilong/bili-multiview
curl -L -o static/flv.min.js https://cdn.jsdelivr.net/npm/flv.js@1.6.2/dist/flv.min.js
ls -lh static/flv.min.js
head -c 100 static/flv.min.js
```
Expected: 文件大小约 150-200KB，开头是 `!function` 等 UMD 包装。

如果 jsdelivr 不可达，备选：
```bash
curl -L -o static/flv.min.js https://unpkg.com/flv.js@1.6.2/dist/flv.min.js
```

- [ ] **Step 2: Commit**

```bash
git add static/flv.min.js
git commit -m "chore(web): vendor flv.js 1.6.2"
```

---

## Task 5: 前端样式 — 网格 & 焦点布局

**Files:**
- Create: `static/style.css`

- [ ] **Step 1: 写 CSS**

`static/style.css`：
```css
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; height: 100%; background: #111; color: #eee; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif; }

.toolbar {
    display: flex; gap: 8px; padding: 8px;
    background: #1c1c1c; border-bottom: 1px solid #333;
}
.toolbar textarea {
    flex: 1; height: 56px; resize: vertical;
    background: #222; color: #eee; border: 1px solid #444; border-radius: 4px;
    padding: 6px 8px; font-family: monospace; font-size: 13px;
}
.toolbar .buttons { display: flex; flex-direction: column; gap: 4px; }
.toolbar button {
    padding: 6px 14px; background: #2a6cf0; color: #fff;
    border: none; border-radius: 4px; cursor: pointer; font-size: 13px;
}
.toolbar button:hover { background: #1f54c4; }
#btn-clear { background: #555; }
#btn-clear:hover { background: #444; }
#btn-exit-focus { background: #d9534f; }

#stage {
    width: 100%; height: calc(100vh - 72px);
    padding: 4px; gap: 4px;
}

/* 网格模式 */
#stage.grid { display: grid; }
#stage.grid.count-1 { grid-template-columns: 1fr; grid-template-rows: 1fr; }
#stage.grid.count-2 { grid-template-columns: 1fr 1fr; grid-template-rows: 1fr; }
#stage.grid.count-3, #stage.grid.count-4 { grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; }
#stage.grid.count-5, #stage.grid.count-6 { grid-template-columns: repeat(3, 1fr); grid-template-rows: repeat(2, 1fr); }
#stage.grid.count-7, #stage.grid.count-8, #stage.grid.count-9 { grid-template-columns: repeat(3, 1fr); grid-template-rows: repeat(3, 1fr); }

/* 焦点模式 */
#stage.focus {
    display: grid;
    grid-template-columns: 1fr 220px;
    grid-template-rows: 1fr;
}
#stage.focus > .tile.is-focus {
    grid-column: 1; grid-row: 1;
}
#stage.focus > .sidebar {
    grid-column: 2; grid-row: 1;
    display: flex; flex-direction: column; gap: 4px;
    overflow-y: auto;
}
#stage.focus > .sidebar > .tile {
    flex: 0 0 130px;
    cursor: pointer;
}

.tile {
    position: relative; background: #000;
    border: 1px solid #333; border-radius: 4px; overflow: hidden;
    min-width: 0; min-height: 0;
}
.tile video {
    width: 100%; height: 100%; object-fit: contain; background: #000;
    display: block;
}
.tile .tile-label {
    position: absolute; top: 0; left: 0;
    padding: 2px 8px; font-size: 12px;
    background: rgba(0,0,0,0.6); color: #fff;
    border-bottom-right-radius: 4px;
    max-width: 80%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.tile .tile-qn {
    position: absolute; top: 0; right: 0;
    padding: 2px 8px; font-size: 11px;
    background: rgba(42,108,240,0.7); color: #fff;
    border-bottom-left-radius: 4px;
}
.tile.is-error, .tile.is-offline {
    display: flex; align-items: center; justify-content: center;
}
.tile.is-error .placeholder,
.tile.is-offline .placeholder {
    color: #aaa; font-size: 13px; text-align: center; padding: 8px; white-space: pre-line;
}
.tile.is-error .placeholder { color: #f88; }
```

- [ ] **Step 2: 手动验证**

```bash
.venv/bin/python -m uvicorn main:app --port 8765 &
sleep 2
```
浏览器打开 `http://localhost:8765/`，确认：
- 顶部输入栏 + 三个按钮可见
- 暂无视频内容时下方区域是深色空白
- "退出焦点"按钮 hidden 状态不显示

```bash
pkill -f "uvicorn main:app"
```

- [ ] **Step 3: Commit**

```bash
git add static/style.css
git commit -m "feat(web): add grid and focus layout styles"
```

---

## Task 6: 前端 Player 封装

**Files:**
- Create: `static/player.js`

**Interface Contract（供 Task 7 使用，挂在 `window.Player`）：**
- `new Player(roomInput: string, initialQn: number)` 构造
- 实例方法：`mount(container: HTMLElement)`、`async load()`、`async switchQuality(newQn: number)`、`destroy()`
- 实例字段：`onClick: (player: Player) => void`（由 app.js 注入）

- [ ] **Step 1: 写 Player 类**

`static/player.js`：
```javascript
/* global flvjs */
const QN_LABEL = {
    80: "流畅", 150: "高清", 250: "超清", 400: "蓝光", 10000: "原画"
};

class Player {
    constructor(roomInput, initialQn = 250) {
        this.roomInput = roomInput;      // 原始输入（链接或数字）
        this.qn = initialQn;
        this.realRoomId = null;
        this.title = "";
        this.uname = "";
        this.flvPlayer = null;
        this.videoEl = null;
        this.container = null;
        this.label = null;
        this.qnBadge = null;
        this.onClick = null;             // 由 app.js 注入
    }

    mount(container) {
        this.container = container;
        container.classList.add("tile");
        container.classList.remove("is-error", "is-offline", "is-focus");
        container.innerHTML = "";

        this.videoEl = document.createElement("video");
        this.videoEl.muted = true;
        this.videoEl.autoplay = true;
        this.videoEl.playsInline = true;
        container.appendChild(this.videoEl);

        this.label = document.createElement("div");
        this.label.className = "tile-label";
        this.label.textContent = `加载中 (${this.roomInput})`;
        container.appendChild(this.label);

        this.qnBadge = document.createElement("div");
        this.qnBadge.className = "tile-qn";
        this.qnBadge.textContent = QN_LABEL[this.qn] || `qn=${this.qn}`;
        container.appendChild(this.qnBadge);

        container.addEventListener("click", () => {
            if (this.onClick) this.onClick(this);
        });
    }

    async load() {
        try {
            const params = new URLSearchParams({
                room_id: this.roomInput,
                qn: String(this.qn),
            });
            const r = await fetch(`/api/stream?${params}`);
            if (!r.ok) {
                const err = await r.json().catch(() => ({}));
                this._showPlaceholder(
                    r.status === 503 ? "主播未开播" : (err.detail || `加载失败 (${r.status})`),
                    r.status === 503 ? "is-offline" : "is-error",
                );
                return;
            }
            const info = await r.json();
            this.realRoomId = info.real_room_id;
            this.title = info.title;
            this.uname = info.uname;
            this.qn = info.qn;
            if (this.label) this.label.textContent = `${this.uname} · ${this.title}`;
            if (this.qnBadge) this.qnBadge.textContent = QN_LABEL[this.qn] || `qn=${this.qn}`;
            this._attachFlv(info.stream_url);
        } catch (e) {
            this._showPlaceholder(`错误: ${e.message}`, "is-error");
        }
    }

    _attachFlv(streamUrl) {
        if (!window.flvjs || !flvjs.isSupported()) {
            this._showPlaceholder("浏览器不支持 flv.js", "is-error");
            return;
        }
        this._destroyFlv();
        if (!this.videoEl) return;
        const player = flvjs.createPlayer({
            type: "flv",
            url: streamUrl,
            isLive: true,
            hasAudio: true,
            hasVideo: true,
        }, {
            enableWorker: false,
            enableStashBuffer: false,
            stashInitialSize: 128,
        });
        player.attachMediaElement(this.videoEl);
        player.load();
        player.play().catch(() => { /* autoplay 被拦截时静音重试 */ });
        this.flvPlayer = player;
    }

    async switchQuality(newQn) {
        if (newQn === this.qn) return;
        this.qn = newQn;
        if (this.qnBadge) this.qnBadge.textContent = QN_LABEL[newQn] || `qn=${newQn}`;
        // 重新 mount 一遍，确保 placeholder 状态被清掉、video 元素就位
        if (this.container) this.mount(this.container);
        await this.load();
    }

    _showPlaceholder(text, cls) {
        this._destroyFlv();
        if (!this.container) return;
        this.container.classList.remove("is-error", "is-offline");
        this.container.classList.add(cls);
        if (this.videoEl) { this.videoEl.remove(); this.videoEl = null; }
        const p = document.createElement("div");
        p.className = "placeholder";
        p.textContent = `${this.roomInput}\n${text}`;
        this.container.appendChild(p);
    }

    _destroyFlv() {
        if (this.flvPlayer) {
            try {
                this.flvPlayer.pause();
                this.flvPlayer.unload();
                this.flvPlayer.detachMediaElement();
                this.flvPlayer.destroy();
            } catch (_) { /* ignore */ }
            this.flvPlayer = null;
        }
    }

    destroy() {
        this._destroyFlv();
        if (this.container) this.container.innerHTML = "";
    }
}

window.Player = Player;
window.QN_LABEL = QN_LABEL;
```

- [ ] **Step 2: Commit**

```bash
git add static/player.js
git commit -m "feat(web): add Player class wrapping flv.js with quality switching"
```

---

## Task 7: 前端 app.js — 链接解析、网格渲染、焦点切换、画质联动

**Files:**
- Create: `static/app.js`

**Imports (browser globals from previous tasks):**
- `window.Player` (from Task 6)

- [ ] **Step 1: 写 app.js**

`static/app.js`：
```javascript
/* global Player */

const stage = document.getElementById("stage");
const btnStart = document.getElementById("btn-start");
const btnClear = document.getElementById("btn-clear");
const btnExitFocus = document.getElementById("btn-exit-focus");
const urlsEl = document.getElementById("urls");

const QN_GRID = 250;       // 网格态默认超清
const QN_FOCUS_MAIN = 10000;
const QN_FOCUS_OTHER = 80;
const MAX_STREAMS = 9;

let players = [];          // Player[]
let focusedIdx = -1;       // -1 表示网格态

function parseLines(text) {
    return text.split(/\r?\n/).map(s => s.trim()).filter(Boolean).slice(0, MAX_STREAMS);
}

function clearStage() {
    players.forEach(p => p.destroy());
    players = [];
    focusedIdx = -1;
    stage.className = "grid";
    stage.innerHTML = "";
    btnExitFocus.hidden = true;
}

function renderGrid() {
    stage.className = `grid count-${players.length}`;
    stage.innerHTML = "";
    players.forEach((p) => {
        const tile = document.createElement("div");
        stage.appendChild(tile);
        p.mount(tile);
        p.onClick = () => enterFocus(players.indexOf(p));
        p.load();
    });
    btnExitFocus.hidden = true;
}

function enterFocus(idx) {
    if (idx < 0 || idx >= players.length) return;
    focusedIdx = idx;

    stage.className = "focus";
    stage.innerHTML = "";

    const focusTile = document.createElement("div");
    stage.appendChild(focusTile);

    const sidebar = document.createElement("div");
    sidebar.className = "sidebar";
    stage.appendChild(sidebar);

    players.forEach((p, i) => {
        if (i === idx) {
            p.mount(focusTile);
            focusTile.classList.add("is-focus");
            p.onClick = null;
        } else {
            const tile = document.createElement("div");
            sidebar.appendChild(tile);
            p.mount(tile);
            p.onClick = () => enterFocus(players.indexOf(p));
        }
    });

    players.forEach((p, i) => {
        const target = (i === idx) ? QN_FOCUS_MAIN : QN_FOCUS_OTHER;
        p.switchQuality(target);
    });

    btnExitFocus.hidden = false;
}

function exitFocus() {
    if (focusedIdx === -1) return;
    focusedIdx = -1;
    renderGrid();
    players.forEach(p => p.switchQuality(QN_GRID));
}

async function startWatch() {
    const inputs = parseLines(urlsEl.value);
    if (inputs.length === 0) {
        alert("请至少输入一个直播链接或房间号");
        return;
    }
    clearStage();
    players = inputs.map(input => new Player(input, QN_GRID));
    renderGrid();
}

btnStart.addEventListener("click", startWatch);
btnClear.addEventListener("click", () => { urlsEl.value = ""; clearStage(); });
btnExitFocus.addEventListener("click", exitFocus);
```

- [ ] **Step 2: 手动冒烟测试**

```bash
.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8765 &
sleep 2
```

浏览器打开 `http://localhost:8765/`，到 https://live.bilibili.com/ 主页挑 2-3 个正在直播的房间号，粘贴进 textarea（一行一个）→ 点"开始观看"。

逐项确认：

- [ ] 网格态：按数量自适应布局（2 路 → 1×2，3-4 路 → 2×2）
- [ ] 每 tile 左上显示"主播名 · 标题"，右上显示"超清"徽章
- [ ] 单击任一路 → 焦点模式：该路占左侧大区，其他缩侧栏
- [ ] 焦点路徽章 1-2 秒后变为"原画"，侧栏路变为"流畅"
- [ ] 单击侧栏任意一路 → 焦点切换 + 画质联动
- [ ] 顶部"退出焦点" → 回到网格 + 所有路恢复"超清"
- [ ] 故意加一个未开播房间号 → 该 tile 显示"主播未开播"占位
- [ ] 故意加一个非法字符串 → 该 tile 显示错误提示

测试完成后：
```bash
pkill -f "uvicorn main:app"
```

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat(web): add link parser, grid render, focus mode with quality auto-switching"
```

---

## Task 8: 启动脚本、README、部署验收

**Files:**
- Create: `start.sh`
- Create: `stop.sh`
- Create: `README.md`

- [ ] **Step 1: 创建启动脚本**

`start.sh`：
```bash
#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi
PORT=${PORT:-8765}
nohup .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port "$PORT" > nohup.out 2>&1 &
echo $! > .pid
sleep 1
echo "bili-multiview started on port $PORT, pid $(cat .pid)"
echo "log: $(pwd)/nohup.out"
```

`stop.sh`：
```bash
#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ -f ".pid" ]; then
    PID=$(cat .pid)
    if kill "$PID" 2>/dev/null; then
        echo "stopped pid $PID"
    else
        echo "pid $PID not running"
    fi
    rm -f .pid
else
    pkill -f "uvicorn main:app" && echo "killed via pkill" || echo "no process found"
fi
```

```bash
chmod +x start.sh stop.sh
```

- [ ] **Step 2: 创建 README.md**

`README.md`：
````markdown
# bili-multiview · B站多路直播分屏观看器

最多 9 路 B 站直播同屏观看；点击任意一路最大化并自动升原画，其余路自动降为流畅。

## 快速开始

```bash
cd /data/codes/lilong/bili-multiview
bash start.sh             # 默认 8765 端口
# 或自定义端口：
PORT=9000 bash start.sh
```

浏览器访问：`http://<服务器IP>:8765/`

停止：
```bash
bash stop.sh
```

## 使用方法

1. 在顶部 textarea 一行粘贴一个 B 站直播链接或房间号，最多 9 行：
   ```
   https://live.bilibili.com/12345
   67890
   ```
2. 点"开始观看" → 视频按数量自适应网格播放（1/2/4/6/9 格）
3. 单击任一路 → 切换到焦点模式，该路放大并升原画，其余路缩侧栏并降流畅
4. 焦点模式下点 sidebar 任一路 → 焦点切换
5. 顶部"退出焦点" → 回到网格

## 画质联动策略

| 状态 | 焦点路 | 其他路 |
|------|--------|--------|
| 网格态 | 超清 (qn=250) | 超清 (qn=250) |
| 焦点态 | 原画 (qn=10000) | 流畅 (qn=80) |

切换画质时会有 1-2 秒黑屏，属于正常重连。

## 技术架构

- 后端 FastAPI 代理 B 站 `getRoomPlayInfo` 接口（自带 Referer 绕开校验），返回真实 CDN FLV 流地址
- 浏览器 flv.js 直接拉 CDN 流，服务器不中转视频流量
- 9 路 flv.js 实例约占用浏览器 400MB 内存

## API

- `GET /api/stream?room_id=<id>&qn=<qn>` → JSON
  - 200：`{stream_url, real_room_id, title, uname, qn, accept_qn, format, ...}`
  - 400：链接无法解析
  - 503：主播未开播
  - 502：B 站接口异常

## 开发与测试

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -v
```

## 已知限制

- 不支持 `b23.tv` 短链，请使用完整 `live.bilibili.com` 链接或房间号
- 不支持登录态弹幕、礼物互动、录播下载（本期范围外）
- 同时 9 路对带宽和浏览器内存有要求，画质过高可能卡顿

## 故障排查

- 服务起不来：查看 `nohup.out`
- 公网打不开：检查服务器防火墙是否开放对应端口
- 视频不播放：右键 inspect → console 看 flv.js 报错；可能是 B 站 CDN 偶发 403，刷新页面或换房间重试
````

- [ ] **Step 3: 部署冒烟测试**

```bash
cd /data/codes/lilong/bili-multiview
bash stop.sh 2>/dev/null || true
bash start.sh
sleep 2

# 1. 本地访问
curl -s -o /dev/null -w "local /  -> %{http_code}\n" http://localhost:8765/
curl -s -o /dev/null -w "local /static/index.html -> %{http_code}\n" http://localhost:8765/static/index.html

# 2. /api/stream 接通 B 站接口（用任一真实在线房间号验证）
# 把 <在线房间号> 换成 https://live.bilibili.com/ 上挑的一个真实在线 ID
curl -s "http://localhost:8765/api/stream?room_id=<在线房间号>&qn=250" | python3 -m json.tool | head -20
```

期望：
- 本地 / 和 /static/index.html 均返回 200
- /api/stream 返回的 JSON 中 `stream_url` 是 `https://...bilivideo.com/.../live_xxx.flv?...`

- [ ] **Step 4: 完整自测清单（逐项打勾）**

后端：
- [ ] `/api/stream?room_id=<在线>` 返回 200 + 合法 stream_url
- [ ] `/api/stream?room_id=invalid` 返回 400
- [ ] `/api/stream?room_id=<未开播房间>` 返回 503

前端（浏览器）：
- [ ] 粘贴 1 个链接 → 单路全屏播放
- [ ] 粘贴 2 个 → 1×2 布局
- [ ] 粘贴 4 个 → 2×2 布局
- [ ] 粘贴 9 个 → 3×3 布局
- [ ] 单击任一路 → 进入焦点 + 升原画 + 其余降流畅
- [ ] 焦点态点 sidebar 切焦点 → 画质联动
- [ ] 退出焦点 → 回到网格 + 所有恢复超清
- [ ] 未开播房间显示"主播未开播"占位
- [ ] 非法字符串显示错误占位

部署：
- [ ] **从外部公网 IP 访问 `http://<server-ip>:8765/` 可正常使用**（必须用另一台机器或手机移动网络验证）
- [ ] `bash stop.sh && bash start.sh` 重启无残留进程

- [ ] **Step 5: Commit**

```bash
git add start.sh stop.sh README.md
git commit -m "docs: add start/stop scripts and README"
```

- [ ] **Step 6: 推送到 GitHub（如用户提供仓库地址）**

```bash
# git remote add origin <仓库地址>
# git push -u origin main
```

如果用户未提供仓库，跳过此步。

---

## Plan-Guard 自审总结

**File Ownership（Phase 1）：**
- ✅ 每个源文件归属唯一 task（见顶部 File Registry）
- ✅ `bili_api.py` / `main.py` / `static/app.js` 由单一 task 完整创建（不再有"先创建后修改"的跨 task 冲突）

**Task Order：**
- ✅ Task 2 (bili_api) → Task 3 (main.py import bili_api) → Task 5/6 (frontend deps) → Task 7 (app.js use Player) → Task 8 (deploy)

**Task Count：**
- ✅ 8 tasks（5-10 区间内）

**Interface Contracts：**
- ✅ Task 2 顶部明确列出 `parse_room_id`、`get_stream_info` 签名与异常类型
- ✅ Task 6 顶部明确列出 `Player` 类接口供 Task 7 使用

**Spec Coverage：**
- ✅ 房间号解析、API 代理、Referer 绕过、网格 1/2/4/6/9 布局、焦点切换 + sidebar、画质联动（10000/80/250）、nohup 后台部署、外网访问验证、完整自测清单 — 全部覆盖
