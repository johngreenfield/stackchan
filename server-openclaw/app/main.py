import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.audio_pipeline import AudioPipeline
from app.config import Settings, is_authorized, load_settings
from app.openclaw_client import EMOTION_EMOJIS, OpenClawClient, clamp
from app.stackchan_protocol import DataType, StackChanHub
from app.xiaozhi_protocol import XiaoZhiManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("stackchan.main")

settings: Settings = load_settings()
openclaw_client = OpenClawClient(settings)
audio_pipeline = AudioPipeline(settings)
avatar_hub = StackChanHub()
xiaozhi_mgr = XiaoZhiManager(openclaw=openclaw_client, audio=audio_pipeline, avatar_hub=avatar_hub)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")


def build_status_snapshot() -> Dict[str, Any]:
    return {
        "status": "ok",
        "openclaw_connected": openclaw_client.connected,
        "session_key": openclaw_client.session_key,
        "openclaw_error": openclaw_client.last_error,
        "xiaozhi_clients": xiaozhi_mgr.client_count,
        "stackchan_clients": avatar_hub.device_count,
        "webremote_clients": avatar_hub.remote_count,
        "device_name": avatar_hub.device_name,
        "camera_streaming": avatar_hub.camera_streaming,
        "last_emotion": avatar_hub.last_emotion,
        "has_latest_jpeg": avatar_hub.latest_jpeg is not None,
        "whisper_model": settings.whisper_model,
        "piper_voice": os.path.basename(settings.piper_model_path),
    }


avatar_hub.set_status_provider(build_status_snapshot)
avatar_hub.set_chat_handler(lambda text, source: xiaozhi_mgr.run_embodied_turn(text, source=source))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await asyncio.to_thread(audio_pipeline.load_models)
    openclaw_client.start()
    yield
    await openclaw_client.stop()


app = FastAPI(title="Stack-chan OpenClaw Bridge", version="1.0.0", lifespan=lifespan)

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _check_ws_auth(websocket: WebSocket, token: Optional[str]) -> bool:
    auth_header = websocket.headers.get("authorization")
    xff = websocket.headers.get("x-forwarded-for")
    client_host = websocket.client.host if websocket.client else None
    return is_authorized(settings, auth_header, token, client_host, xff)


def _check_http_auth(request: Request) -> bool:
    auth_header = request.headers.get("authorization")
    xff = request.headers.get("x-forwarded-for")
    client_host = request.client.host if request.client else None
    token = request.query_params.get("token")
    return is_authorized(settings, auth_header, token, client_host, xff)


@app.get("/health")
async def health() -> Dict[str, Any]:
    return build_status_snapshot()


@app.get("/")
@app.get("/remote")
@app.get("/remote/")
async def serve_remote_ui() -> FileResponse:
    index_path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="Web Remote UI not found")
    return FileResponse(index_path, media_type="text/html")


@app.api_route("/xiaozhi/ota/", methods=["GET", "POST"])
@app.api_route("/xiaozhi/ota", methods=["GET", "POST"])
async def xiaozhi_ota(request: Request, scheme: Optional[str] = Query(default=None)) -> JSONResponse:
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "http").split(",")[0].strip().lower()
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()

    forced = scheme.strip().lower() if scheme else ""
    if forced == "ws":
        target_host = host or f"{settings.lan_host}:{settings.port}"
        ws_url = f"ws://{target_host}/xiaozhi/ws"
    elif forced == "wss":
        target_host = host or settings.public_domain
        ws_url = f"wss://{target_host}/xiaozhi/ws"
    elif proto == "https" or (host and host.split(":")[0].lower() == settings.public_domain.lower()):
        target_host = host or settings.public_domain
        ws_url = f"wss://{target_host}/xiaozhi/ws"
    elif host:
        ws_url = f"ws://{host}/xiaozhi/ws"
    else:
        ws_url = f"ws://{settings.lan_host}:{settings.port}/xiaozhi/ws"

    payload = {
        "server_time": {
            "timestamp": int(time.time() * 1000),
            "timezone_offset": 0,
        },
        "websocket": {
            "url": ws_url,
            "token": "",
            "version": 1,
        },
        "firmware": {
            "version": "1.6.2",
            "url": "",
        },
    }
    return JSONResponse(content=payload)


@app.websocket("/xiaozhi/ws")
async def xiaozhi_websocket(websocket: WebSocket, token: Optional[str] = Query(default=None)) -> None:
    if not _check_ws_auth(websocket, token):
        await websocket.close(code=1008, reason="Unauthorized")
        return
    device_id = (
        websocket.headers.get("device-id")
        or websocket.query_params.get("deviceId")
        or (websocket.client.host if websocket.client else "stackchan-device")
    )
    await xiaozhi_mgr.handle_websocket(websocket, device_id=device_id)


@app.websocket("/stackChan/ws")
async def stackchan_websocket(
    websocket: WebSocket,
    deviceType: str = Query(default="WebRemote"),
    deviceId: Optional[str] = Query(default=None),
    token: Optional[str] = Query(default=None),
) -> None:
    if not _check_ws_auth(websocket, token):
        await websocket.close(code=1008, reason="Unauthorized")
        return
    resolved_id = (
        deviceId
        or websocket.headers.get("device-id")
        or (websocket.client.host if websocket.client else "stackchan-avatar")
    )
    await avatar_hub.handle_websocket(websocket, device_type=deviceType, device_id=resolved_id)


# Minimal Stack-chan device/account HTTP endpoints expected by firmware
@app.get("/stackChan/device/user")
async def stackchan_device_user(request: Request) -> Dict[str, Any]:
    if not _check_http_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"code": 0, "message": "ok", "data": {"username": "OpenClaw"}}


@app.get("/stackChan/device/info")
async def stackchan_device_info(request: Request) -> Dict[str, Any]:
    if not _check_http_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "name": avatar_hub.device_name,
            "deviceId": next(iter(avatar_hub.devices.keys()), "stackchan-openclaw"),
        },
    }


@app.post("/stackChan/device/unbind")
async def stackchan_device_unbind(request: Request) -> Dict[str, Any]:
    if not _check_http_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"code": 0, "message": "ok", "data": {}}


@app.get("/stackChan/apps")
async def stackchan_apps() -> Dict[str, Any]:
    return {"code": 0, "message": "ok", "data": []}


# Web Remote Control REST APIs
class ChatRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class MotionRequest(BaseModel):
    yaw: Optional[int] = Field(default=None, ge=-128, le=128)
    pitch: Optional[int] = Field(default=None, ge=0, le=90)
    speed: int = Field(default=150, ge=100, le=1000)


class AvatarRequest(BaseModel):
    emotion: str = Field(default="neutral")


class LedRequest(BaseModel):
    r: int = Field(default=0, ge=0, le=255)
    g: int = Field(default=0, ge=0, le=255)
    b: int = Field(default=0, ge=0, le=255)


def _require_http_auth(request: Request) -> None:
    if not _check_http_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/api/status")
async def api_status(request: Request) -> Dict[str, Any]:
    _require_http_auth(request)
    return build_status_snapshot()


@app.post("/api/chat")
async def api_chat(request: Request, req: ChatRequest) -> Dict[str, Any]:
    _require_http_auth(request)
    try:
        return await xiaozhi_mgr.run_embodied_turn(req.text.strip(), source="web-remote")
    except Exception as exc:
        logger.exception("Web Remote chat turn failed: %s", exc)
        raise HTTPException(status_code=502, detail="Chat turn failed")


@app.post("/api/motion")
async def api_motion(request: Request, req: MotionRequest) -> Dict[str, Any]:
    _require_http_auth(request)
    avatar_sent = await avatar_hub.send_motion(yaw_deg=req.yaw, pitch_deg=req.pitch, speed=req.speed)
    xz_session = xiaozhi_mgr.get_primary_session()
    mcp_result = None
    if xz_session is not None:
        args: Dict[str, Any] = {"speed": req.speed}
        if req.yaw is not None:
            args["yaw"] = req.yaw
        if req.pitch is not None:
            args["pitch"] = req.pitch
        mcp_result = await xiaozhi_mgr.call_mcp_tool(xz_session, "self.robot.set_head_angles", args)
    return {
        "ok": True,
        "yaw": req.yaw,
        "pitch": req.pitch,
        "speed": req.speed,
        "avatar_sent": avatar_sent,
        "mcp_called": xz_session is not None,
        "mcp_result": mcp_result,
    }


@app.post("/api/avatar")
async def api_avatar(request: Request, req: AvatarRequest) -> Dict[str, Any]:
    _require_http_auth(request)
    emo = req.emotion.strip().lower()
    avatar_sent = await avatar_hub.send_avatar_emotion(emo)
    xz_session = xiaozhi_mgr.get_primary_session()
    if xz_session is not None:
        await xiaozhi_mgr._send_json(
            xz_session,
            {
                "session_id": xz_session.session_id,
                "type": "llm",
                "emotion": emo,
                "text": EMOTION_EMOJIS.get(emo, "🙂"),
            },
        )
    return {
        "ok": True,
        "emotion": emo,
        "avatar_sent": avatar_sent,
        "xiaozhi_sent": xz_session is not None,
    }


@app.post("/api/led")
async def api_led(request: Request, req: LedRequest) -> Dict[str, Any]:
    _require_http_auth(request)
    # Scale 0..255 -> 0..168 if needed for Stack-chan MCP tool safety
    r = clamp(int(round(req.r * 168 / 255)) if max(req.r, req.g, req.b) > 168 else req.r, 0, 168)
    g = clamp(int(round(req.g * 168 / 255)) if max(req.r, req.g, req.b) > 168 else req.g, 0, 168)
    b = clamp(int(round(req.b * 168 / 255)) if max(req.r, req.g, req.b) > 168 else req.b, 0, 168)

    avatar_sent = await avatar_hub.send_led_color(r, g, b)
    xz_session = xiaozhi_mgr.get_primary_session()
    mcp_result = None
    if xz_session is not None:
        mcp_result = await xiaozhi_mgr.call_mcp_tool(
            xz_session,
            "self.robot.set_led_color",
            {"red": r, "green": g, "blue": b},
        )
    return {
        "ok": True,
        "led": [r, g, b],
        "avatar_sent": avatar_sent,
        "mcp_called": xz_session is not None,
        "mcp_result": mcp_result,
    }


@app.post("/api/camera/start")
async def api_camera_start(request: Request) -> Dict[str, Any]:
    _require_http_auth(request)
    avatar_hub.camera_streaming = True
    sent = await avatar_hub.send_binary_to_devices(DataType.START_CAMERA_STREAM)
    return {"ok": True, "camera_streaming": True, "devices_notified": sent}


@app.post("/api/camera/stop")
async def api_camera_stop(request: Request) -> Dict[str, Any]:
    _require_http_auth(request)
    avatar_hub.camera_streaming = False
    sent = await avatar_hub.send_binary_to_devices(DataType.STOP_CAMERA_STREAM)
    return {"ok": True, "camera_streaming": False, "devices_notified": sent}


@app.get("/api/camera/latest.jpg")
async def api_camera_latest(request: Request) -> Response:
    _require_http_auth(request)
    if not avatar_hub.latest_jpeg:
        return Response(status_code=204)
    return Response(content=avatar_hub.latest_jpeg, media_type="image/jpeg")
