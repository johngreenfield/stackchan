import asyncio
import json
import logging
import struct
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Awaitable, Callable, Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger("stackchan.avatar")


class DataType(IntEnum):
    OPUS = 0x01
    JPEG = 0x02
    CONTROL_AVATAR = 0x03
    CONTROL_MOTION = 0x04
    START_CAMERA_STREAM = 0x05
    STOP_CAMERA_STREAM = 0x06
    TEXT_MESSAGE = 0x07
    REQUEST_CALL = 0x09
    DECLINE_CALL = 0x0A
    ACCEPT_CALL = 0x0B
    END_CALL = 0x0C
    SET_DEVICE_NAME = 0x0D
    GET_DEVICE_NAME = 0x0E
    HEARTBEAT_PING = 0x10
    HEARTBEAT_PONG = 0x11
    VIDEO_MODE_ON = 0x12
    VIDEO_MODE_OFF = 0x13
    DANCE_SEQUENCE = 0x14
    GET_AVATAR_POSTURE = 0x15
    DEVICE_OFFLINE = 0x16
    DEVICE_ONLINE = 0x17
    START_AUDIO_STREAM = 0x18
    STOP_AUDIO_STREAM = 0x19
    AIMED_TAKE_PHOTO = 0x1A
    APP_LAN_ADDRESS = 0x1B


# Avatar feature presets for ControlAvatar (0x03) over /stackChan/ws
AVATAR_EMOTION_PRESETS: Dict[str, Dict[str, Any]] = {
    "neutral": {
        "leftEye": {"x": 0, "y": 0, "rotation": 0, "weight": 100, "size": 100},
        "rightEye": {"x": 0, "y": 0, "rotation": 0, "weight": 100, "size": 100},
        "mouth": {"x": 0, "y": 0, "rotation": 0, "weight": 35, "size": 100},
    },
    "happy": {
        "leftEye": {"x": 0, "y": -4, "rotation": 0, "weight": 45, "size": 110},
        "rightEye": {"x": 0, "y": -4, "rotation": 0, "weight": 45, "size": 110},
        "mouth": {"x": 0, "y": 2, "rotation": 0, "weight": 95, "size": 115},
    },
    "laughing": {
        "leftEye": {"x": 0, "y": -6, "rotation": 0, "weight": 30, "size": 115},
        "rightEye": {"x": 0, "y": -6, "rotation": 0, "weight": 30, "size": 115},
        "mouth": {"x": 0, "y": 4, "rotation": 0, "weight": 115, "size": 125},
    },
    "sad": {
        "leftEye": {"x": 0, "y": 5, "rotation": -15, "weight": 75, "size": 95},
        "rightEye": {"x": 0, "y": 5, "rotation": 15, "weight": 75, "size": 95},
        "mouth": {"x": 0, "y": 10, "rotation": 180, "weight": 40, "size": 85},
    },
    "angry": {
        "leftEye": {"x": 0, "y": 2, "rotation": 22, "weight": 80, "size": 95},
        "rightEye": {"x": 0, "y": 2, "rotation": -22, "weight": 80, "size": 95},
        "mouth": {"x": 0, "y": 8, "rotation": 180, "weight": 55, "size": 95},
    },
    "surprised": {
        "leftEye": {"x": 0, "y": -4, "rotation": 0, "weight": 120, "size": 125},
        "rightEye": {"x": 0, "y": -4, "rotation": 0, "weight": 120, "size": 125},
        "mouth": {"x": 0, "y": 4, "rotation": 0, "weight": 110, "size": 75},
    },
    "thinking": {
        "leftEye": {"x": -4, "y": -4, "rotation": 0, "weight": 85, "size": 95},
        "rightEye": {"x": -4, "y": -6, "rotation": 10, "weight": 65, "size": 95},
        "mouth": {"x": 6, "y": 4, "rotation": -8, "weight": 25, "size": 70},
    },
    "sleepy": {
        "leftEye": {"x": 0, "y": 6, "rotation": 0, "weight": 15, "size": 100},
        "rightEye": {"x": 0, "y": 6, "rotation": 0, "weight": 15, "size": 100},
        "mouth": {"x": 0, "y": 4, "rotation": 0, "weight": 20, "size": 65},
    },
    "doubtful": {
        "leftEye": {"x": 0, "y": -3, "rotation": -12, "weight": 95, "size": 105},
        "rightEye": {"x": 0, "y": 2, "rotation": 0, "weight": 55, "size": 95},
        "mouth": {"x": 4, "y": 4, "rotation": -10, "weight": 30, "size": 80},
    },
}


def pack_frame(msg_type: int, payload: bytes = b"") -> bytes:
    return struct.pack(">BI", int(msg_type) & 0xFF, len(payload)) + payload


def unpack_frame(data: bytes) -> Optional[tuple[int, bytes]]:
    if len(data) < 5:
        return None
    msg_type, length = struct.unpack(">BI", data[:5])
    payload = data[5 : 5 + length]
    return msg_type, payload


@dataclass
class StackChanDeviceConn:
    device_id: str
    websocket: WebSocket
    connected_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    name: str = "Stack-chan"


class StackChanHub:
    def __init__(self) -> None:
        self.devices: Dict[str, StackChanDeviceConn] = {}
        self.remotes: Set[WebSocket] = set()
        self.latest_jpeg: Optional[bytes] = None
        self.latest_jpeg_at: Optional[float] = None
        self.device_name: str = "Stack-chan"
        self.camera_streaming: bool = False
        self.last_emotion: str = "neutral"
        self._status_provider: Optional[Callable[[], Dict[str, Any]]] = None
        self._chat_handler: Optional[Callable[[str, str], Awaitable[Dict[str, Any]]]] = None
        self._keepalive_task: Optional[asyncio.Task] = None

    def _ensure_keepalive_task(self) -> None:
        if self._keepalive_task is None or self._keepalive_task.done():
            self._keepalive_task = asyncio.create_task(self._keepalive_loop(), name="stackchan-keepalive")

    async def _keepalive_loop(self) -> None:
        try:
            while self.devices:
                await asyncio.sleep(4.0)
                if self.devices:
                    await self.send_binary_to_devices(DataType.HEARTBEAT_PONG)
        except asyncio.CancelledError:
            pass
        finally:
            self._keepalive_task = None

    def set_status_provider(self, fn: Callable[[], Dict[str, Any]]) -> None:
        self._status_provider = fn

    def set_chat_handler(self, fn: Callable[[str, str], Awaitable[Dict[str, Any]]]) -> None:
        self._chat_handler = fn

    @property
    def device_count(self) -> int:
        return len(self.devices)

    @property
    def remote_count(self) -> int:
        return len(self.remotes)

    async def broadcast_json_to_remotes(self, payload: Dict[str, Any]) -> None:
        if not self.remotes:
            return
        text = json.dumps(payload)
        dead = []
        for ws in list(self.remotes):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.remotes.discard(ws)

    async def broadcast_binary_to_remotes(self, frame: bytes) -> None:
        if not self.remotes:
            return
        dead = []
        for ws in list(self.remotes):
            try:
                await ws.send_bytes(frame)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.remotes.discard(ws)

    async def send_binary_to_devices(self, msg_type: int, payload: bytes = b"") -> int:
        if not self.devices:
            return 0
        frame = pack_frame(msg_type, payload)
        sent = 0
        dead = []
        for dev_id, conn in list(self.devices.items()):
            try:
                await conn.websocket.send_bytes(frame)
                sent += 1
            except Exception:
                dead.append(dev_id)
        for dev_id in dead:
            self.devices.pop(dev_id, None)
        return sent

    async def send_motion(
        self,
        yaw_deg: Optional[int] = None,
        pitch_deg: Optional[int] = None,
        speed: int = 150,
    ) -> int:
        body: Dict[str, Any] = {}
        if yaw_deg is not None:
            body["yawServo"] = {"angle": int(yaw_deg) * 10, "speed": int(speed)}
        if pitch_deg is not None:
            body["pitchServo"] = {"angle": int(pitch_deg) * 10, "speed": int(speed)}
        if not body:
            return 0
        return await self.send_binary_to_devices(DataType.CONTROL_MOTION, json.dumps(body).encode("utf-8"))

    async def send_avatar_emotion(self, emotion: str) -> int:
        emo = emotion.strip().lower()
        self.last_emotion = emo
        preset = AVATAR_EMOTION_PRESETS.get(emo, AVATAR_EMOTION_PRESETS["neutral"])
        return await self.send_binary_to_devices(DataType.CONTROL_AVATAR, json.dumps(preset).encode("utf-8"))

    async def send_led_color(self, r: int, g: int, b: int) -> int:
        # Scale 0..168 -> 0..255 hex for DanceSequence RGB keyframes
        r_hex = max(0, min(255, int(round(r * 255 / 168)))) if r <= 168 else max(0, min(255, int(r)))
        g_hex = max(0, min(255, int(round(g * 255 / 168)))) if g <= 168 else max(0, min(255, int(g)))
        b_hex = max(0, min(255, int(round(b * 255 / 168)))) if b <= 168 else max(0, min(255, int(b)))
        color = f"#{r_hex:02X}{g_hex:02X}{b_hex:02X}"
        seq = [{"leftRgbColor": color, "rightRgbColor": color, "durationMs": 500}]
        return await self.send_binary_to_devices(DataType.DANCE_SEQUENCE, json.dumps(seq).encode("utf-8"))

    async def _push_status_to_remotes(self) -> None:
        if self._status_provider:
            await self.broadcast_json_to_remotes({"type": "status", "data": self._status_provider()})

    async def handle_websocket(self, websocket: WebSocket, device_type: str, device_id: str) -> None:
        await websocket.accept()
        kind = (device_type or "WebRemote").strip()
        if kind == "StackChan":
            await self._handle_stackchan_device(websocket, device_id)
        else:
            await self._handle_remote_client(websocket, kind)

    async def _handle_stackchan_device(self, websocket: WebSocket, device_id: str) -> None:
        existing = self.devices.get(device_id)
        if existing is not None and existing.websocket is not websocket:
            try:
                await existing.websocket.close(code=1000, reason="Replaced by new connection")
            except Exception:
                pass
        conn = StackChanDeviceConn(device_id=device_id, websocket=websocket, name=self.device_name)
        self.devices[device_id] = conn
        self._ensure_keepalive_task()
        logger.info("StackChan Avatar WS connected: %s", device_id)

        await self.broadcast_binary_to_remotes(pack_frame(DataType.DEVICE_ONLINE, device_id.encode("utf-8")))
        await self._push_status_to_remotes()

        # Request device name on connect
        try:
            await websocket.send_bytes(pack_frame(DataType.GET_DEVICE_NAME))
        except Exception:
            pass

        try:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                conn.last_seen = time.time()

                if msg.get("bytes") is not None:
                    raw = msg["bytes"]
                    parsed = unpack_frame(raw)
                    if not parsed:
                        continue
                    msg_type, payload = parsed
                    if msg_type == DataType.HEARTBEAT_PING:
                        await websocket.send_bytes(pack_frame(DataType.HEARTBEAT_PONG))
                    elif msg_type == DataType.HEARTBEAT_PONG:
                        pass
                    elif msg_type == DataType.JPEG:
                        self.latest_jpeg = payload
                        self.latest_jpeg_at = time.time()
                        await self.broadcast_binary_to_remotes(raw)
                    elif msg_type == DataType.GET_DEVICE_NAME:
                        name = payload.decode("utf-8", errors="replace").strip()
                        if name:
                            conn.name = name
                            self.device_name = name
                        await self.broadcast_binary_to_remotes(raw)
                        await self._push_status_to_remotes()
                    elif msg_type == DataType.TEXT_MESSAGE:
                        await self.broadcast_binary_to_remotes(raw)
                        try:
                            txt_obj = json.loads(payload.decode("utf-8", errors="replace"))
                            await self.broadcast_json_to_remotes({"type": "device_text", "data": txt_obj})
                        except Exception:
                            pass
                    else:
                        await self.broadcast_binary_to_remotes(raw)
                elif msg.get("text") is not None:
                    logger.debug("StackChan text frame (%s): %s", device_id, msg["text"][:200])
        except Exception as exc:
            logger.info("StackChan Avatar WS closed (%s): %s", device_id, exc)
        finally:
            if self.devices.get(device_id) is conn:
                self.devices.pop(device_id, None)
            if not self.devices:
                self.camera_streaming = False
            await self.broadcast_binary_to_remotes(pack_frame(DataType.DEVICE_OFFLINE, device_id.encode("utf-8")))
            await self._push_status_to_remotes()

    async def _handle_remote_client(self, websocket: WebSocket, kind: str) -> None:
        self.remotes.add(websocket)
        logger.info("StackChan %s WS connected (total remotes=%d)", kind, len(self.remotes))

        try:
            if self.devices:
                await websocket.send_bytes(
                    pack_frame(DataType.DEVICE_ONLINE, next(iter(self.devices.keys())).encode("utf-8"))
                )
            else:
                await websocket.send_bytes(pack_frame(DataType.DEVICE_OFFLINE))

            if self.latest_jpeg:
                await websocket.send_bytes(pack_frame(DataType.JPEG, self.latest_jpeg))

            if self._status_provider:
                await websocket.send_text(json.dumps({"type": "status", "data": self._status_provider()}))

            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break

                if msg.get("bytes") is not None:
                    raw = msg["bytes"]
                    parsed = unpack_frame(raw)
                    if not parsed:
                        continue
                    msg_type, payload = parsed
                    if msg_type == DataType.HEARTBEAT_PING:
                        await websocket.send_bytes(pack_frame(DataType.HEARTBEAT_PONG))
                    elif msg_type == DataType.START_CAMERA_STREAM:
                        self.camera_streaming = True
                        await self.send_binary_to_devices(msg_type, payload)
                        await self._push_status_to_remotes()
                    elif msg_type == DataType.STOP_CAMERA_STREAM:
                        self.camera_streaming = False
                        await self.send_binary_to_devices(msg_type, payload)
                        await self._push_status_to_remotes()
                    elif msg_type == DataType.SET_DEVICE_NAME:
                        name = payload.decode("utf-8", errors="replace").strip()
                        if name:
                            self.device_name = name
                        await self.send_binary_to_devices(msg_type, payload)
                    else:
                        await self.send_binary_to_devices(msg_type, payload)
                elif msg.get("text") is not None:
                    await self._handle_remote_json(websocket, msg["text"])
        except Exception as exc:
            logger.info("StackChan %s WS closed: %s", kind, exc)
        finally:
            self.remotes.discard(websocket)

    async def _handle_remote_json(self, websocket: WebSocket, raw_text: str) -> None:
        try:
            data = json.loads(raw_text)
        except Exception:
            return
        if not isinstance(data, dict):
            return
        cmd = data.get("type")
        if cmd == "ping":
            await websocket.send_text(json.dumps({"type": "pong", "ts": time.time()}))
        elif cmd == "get_status" and self._status_provider:
            await websocket.send_text(json.dumps({"type": "status", "data": self._status_provider()}))
        elif cmd == "chat" and self._chat_handler:
            text = str(data.get("text", "")).strip()
            if text:
                asyncio.create_task(self._chat_handler(text, "web-remote"))
