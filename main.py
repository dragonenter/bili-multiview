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
