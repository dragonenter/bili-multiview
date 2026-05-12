import asyncio
import json
import logging
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from bili_api import (
    parse_room_id,
    get_stream_info,
    get_room_meta,
    get_status_by_uids,
    RoomIdError,
    StreamNotLiveError,
    BiliApiError,
)
from danmaku import subscribe as danmaku_subscribe, DanmakuError

logging.basicConfig(level=logging.INFO)


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


@app.get("/api/room")
async def api_room(room_id: str = Query(..., description="房间号或完整直播链接")):
    """轻量元信息：不要求开播，用于加入关注列表/校验房间号。"""
    try:
        rid = parse_room_id(room_id)
    except RoomIdError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        return await get_room_meta(rid)
    except BiliApiError as e:
        raise HTTPException(status_code=502, detail=f"B站接口异常：{e}")


@app.post("/api/status")
async def api_status(payload: dict = Body(...)):
    """批量查 UID 列表的当前直播状态。body: {"uids": [int,...]}"""
    uids = payload.get("uids") or []
    if not isinstance(uids, list):
        raise HTTPException(status_code=400, detail="uids 必须是数组")
    if len(uids) == 0:
        return {}
    if len(uids) > 200:
        raise HTTPException(status_code=400, detail="uids 数量上限 200")
    try:
        clean = [int(u) for u in uids if u]
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="uids 中存在非整数")
    try:
        return await get_status_by_uids(clean)
    except BiliApiError as e:
        raise HTTPException(status_code=502, detail=f"B站接口异常：{e}")


@app.get("/api/danmaku/{room_id}")
async def api_danmaku(room_id: int):
    """SSE 推送指定房间的弹幕。客户端用 EventSource 订阅。"""

    async def event_stream():
        yield ": connected\n\n"
        # 长时间无弹幕时给 SSE 发 keepalive 注释行避免 proxy 断开
        q: asyncio.Queue = asyncio.Queue()

        async def producer():
            try:
                async for msg in danmaku_subscribe(room_id):
                    await q.put(("msg", msg))
            except DanmakuError as e:
                await q.put(("err", str(e)))
            except Exception as e:
                logging.warning("danmaku stream error room=%s: %s", room_id, e)
                await q.put(("err", str(e)))
            await q.put(("end", None))

        task = asyncio.create_task(producer())
        try:
            while True:
                try:
                    kind, payload = await asyncio.wait_for(q.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if kind == "msg":
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                elif kind == "err":
                    yield f"event: error\ndata: {json.dumps({'error': payload})}\n\n"
                    break
                elif kind == "end":
                    break
        finally:
            task.cancel()
            try:
                await task
            except BaseException:
                pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
