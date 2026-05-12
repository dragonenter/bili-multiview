from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
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
