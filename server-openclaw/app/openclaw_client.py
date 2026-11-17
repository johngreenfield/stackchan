import asyncio
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import websockets

from app.config import Settings

logger = logging.getLogger("stackchan.openclaw")

DIRECTIVE_RE = re.compile(r"\[\[stackchan\s*:\s*(\{.*?\})\s*\]\]", re.DOTALL | re.IGNORECASE)

VALID_EMOTIONS = {
    "neutral",
    "happy",
    "laughing",
    "angry",
    "sad",
    "crying",
    "sleepy",
    "doubtful",
    "surprised",
    "thinking",
}

EMOTION_EMOJIS = {
    "neutral": "🙂",
    "happy": "😄",
    "laughing": "😆",
    "angry": "😠",
    "sad": "😢",
    "crying": "😭",
    "sleepy": "😴",
    "doubtful": "🤨",
    "surprised": "😮",
    "thinking": "🤔",
}


def clamp(val: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, val))


def parse_stackchan_directive(raw_text: str) -> Tuple[str, Dict[str, Any]]:
    directive: Dict[str, Any] = {"emotion": "neutral"}
    matches = DIRECTIVE_RE.findall(raw_text or "")
    for m in matches:
        try:
            obj = json.loads(m)
            if not isinstance(obj, dict):
                continue
            emo = str(obj.get("emotion", directive["emotion"])).strip().lower()
            if emo in VALID_EMOTIONS:
                directive["emotion"] = emo
            if "yaw" in obj and obj["yaw"] is not None:
                directive["yaw"] = clamp(int(round(float(obj["yaw"]))), -128, 128)
            if "pitch" in obj and obj["pitch"] is not None:
                directive["pitch"] = clamp(int(round(float(obj["pitch"]))), 0, 90)
            if "speed" in obj and obj["speed"] is not None:
                directive["speed"] = clamp(int(round(float(obj["speed"]))), 100, 1000)
            if "led" in obj and isinstance(obj["led"], (list, tuple)) and len(obj["led"]) == 3:
                rgb = [int(round(float(x))) for x in obj["led"]]
                max_ch = max(rgb)
                if max_ch > 168:
                    # Scale 0..255 down cleanly into Stack-chan's safe 0..168 range
                    rgb = [clamp(int(round(c * 168 / 255)), 0, 168) for c in rgb]
                else:
                    rgb = [clamp(c, 0, 168) for c in rgb]
                directive["led"] = rgb
        except Exception:
            continue

    cleaned = DIRECTIVE_RE.sub("", raw_text or "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, directive


def _extract_message_text(message_obj: Any) -> str:
    if isinstance(message_obj, str):
        return message_obj.strip()
    if not isinstance(message_obj, dict):
        return ""
    content = message_obj.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                txt = block.get("text")
                if isinstance(txt, str) and txt:
                    parts.append(txt)
        return "\n".join(parts).strip()
    txt = message_obj.get("text")
    return txt.strip() if isinstance(txt, str) else ""


@dataclass
class PendingChatTurn:
    idempotency_key: str
    session_key: str
    future: asyncio.Future
    run_id: Optional[str] = None
    accumulated_text: str = ""
    created_at: float = field(default_factory=time.time)


class OpenClawClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.ws: Optional[Any] = None
        self.connected = False
        self.session_key: Optional[str] = None
        self.last_error: Optional[str] = None
        self.last_turn_at: Optional[float] = None

        self._stop = False
        self._runner_task: Optional[asyncio.Task] = None
        self._ready_event = asyncio.Event()
        self._pending_rpc: Dict[str, asyncio.Future] = {}
        self._pending_turns: Dict[str, PendingChatTurn] = {}
        self._turn_lock = asyncio.Lock()
        self._session_file = os.path.join(self.settings.data_dir, "openclaw_session.json")

    def start(self) -> None:
        if self._runner_task is None:
            self._stop = False
            self._runner_task = asyncio.create_task(self._connection_loop(), name="openclaw-ws-loop")

    async def stop(self) -> None:
        self._stop = True
        if self._runner_task:
            self._runner_task.cancel()
            try:
                await self._runner_task
            except asyncio.CancelledError:
                pass
            self._runner_task = None
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None
        self.connected = False
        self._ready_event.clear()

    def _load_saved_session_key(self) -> Optional[str]:
        try:
            if os.path.exists(self._session_file):
                with open(self._session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    key = data.get("sessionKey")
                    if isinstance(key, str) and key.strip():
                        return key.strip()
        except Exception:
            pass
        return None

    def _save_session_key(self, key: str) -> None:
        try:
            os.makedirs(self.settings.data_dir, exist_ok=True)
            with open(self._session_file, "w", encoding="utf-8") as f:
                json.dump({"sessionKey": key, "updatedAt": time.time()}, f)
        except Exception as exc:
            logger.warning("Could not persist session key: %s", exc)

    async def _connection_loop(self) -> None:
        backoff = 1.0
        while not self._stop:
            try:
                await self._connect_and_serve()
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = str(exc)
                logger.warning("OpenClaw Gateway connection error: %s (retrying in %.1fs)", exc, backoff)
            finally:
                self.ws = None
                self.connected = False
                self._ready_event.clear()
                self._fail_pending_requests("OpenClaw Gateway disconnected")
            if not self._stop:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 20.0)

    def _fail_pending_requests(self, reason: str) -> None:
        for req_id, fut in list(self._pending_rpc.items()):
            if not fut.done():
                fut.set_exception(RuntimeError(reason))
        self._pending_rpc.clear()

        for key, turn in list(self._pending_turns.items()):
            if not turn.future.done():
                turn.future.set_exception(RuntimeError(reason))
        self._pending_turns.clear()

    async def _connect_and_serve(self) -> None:
        url = self.settings.openclaw_gateway_url
        logger.info("Connecting to OpenClaw Gateway at %s", url)
        async with websockets.connect(
            url,
            ping_interval=25,
            ping_timeout=25,
            max_size=4 * 1024 * 1024,
        ) as ws:
            self.ws = ws

            # Wait for connect.challenge
            challenge_deadline = time.monotonic() + 10.0
            while True:
                remaining = challenge_deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Timed out waiting for OpenClaw connect.challenge")
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if isinstance(msg, dict) and msg.get("type") == "event" and msg.get("event") == "connect.challenge":
                    break

            connect_id = str(uuid.uuid4())
            connect_req = {
                "type": "req",
                "id": connect_id,
                "method": "connect",
                "params": {
                    "minProtocol": 4,
                    "maxProtocol": 4,
                    "client": {
                        "id": "gateway-client",
                        "version": "1.0.0",
                        "platform": "linux",
                        "mode": "backend",
                    },
                    "role": "operator",
                    "scopes": ["operator.read", "operator.write"],
                    "auth": {
                        "token": self.settings.openclaw_gateway_token,
                    },
                },
            }
            await ws.send(json.dumps(connect_req))

            # Wait for connect response
            hello_deadline = time.monotonic() + 10.0
            while True:
                remaining = hello_deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Timed out waiting for OpenClaw connect response")
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if isinstance(msg, dict) and msg.get("type") == "res" and msg.get("id") == connect_id:
                    if not msg.get("ok"):
                        err = msg.get("error", {})
                        raise RuntimeError(f"OpenClaw connect failed: {err}")
                    break

            self.connected = True
            self.last_error = None
            logger.info("Authenticated with OpenClaw Gateway (protocol v4)")

            reader_task = asyncio.create_task(self._reader_loop(ws), name="openclaw-reader")
            try:
                await self._ensure_session()
                self._ready_event.set()
                await reader_task
            finally:
                reader_task.cancel()
                try:
                    await reader_task
                except asyncio.CancelledError:
                    pass

    async def _reader_loop(self, ws: Any) -> None:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                continue

            msg_type = msg.get("type")
            if msg_type == "res":
                req_id = msg.get("id")
                fut = self._pending_rpc.pop(req_id, None)
                if fut and not fut.done():
                    if msg.get("ok"):
                        fut.set_result(msg.get("payload"))
                    else:
                        err = msg.get("error") or {}
                        err_msg = err.get("message") if isinstance(err, dict) else str(err)
                        fut.set_exception(RuntimeError(err_msg or "OpenClaw RPC error"))
            elif msg_type == "event":
                await self._handle_event(msg)

    async def _handle_event(self, evt: Dict[str, Any]) -> None:
        if evt.get("event") != "chat":
            return
        payload = evt.get("payload")
        if not isinstance(payload, dict):
            return

        state = payload.get("state")
        session_key = payload.get("sessionKey")
        run_id = payload.get("runId")

        turn = None
        if run_id and run_id in self._pending_turns:
            turn = self._pending_turns[run_id]
        elif session_key:
            for candidate in self._pending_turns.values():
                if candidate.session_key == session_key:
                    turn = candidate
                    break
        if not turn or turn.future.done():
            return

        if state == "delta":
            delta_text = payload.get("deltaText")
            if isinstance(delta_text, str):
                if payload.get("replace"):
                    turn.accumulated_text = delta_text
                else:
                    turn.accumulated_text += delta_text
            else:
                extracted = _extract_message_text(payload.get("message"))
                if extracted:
                    turn.accumulated_text = extracted
        elif state == "final":
            final_text = _extract_message_text(payload.get("message")) or turn.accumulated_text
            turn.future.set_result(final_text)
        elif state == "aborted":
            err_msg = payload.get("errorMessage") or "Response aborted"
            if turn.accumulated_text.strip():
                turn.future.set_result(turn.accumulated_text.strip())
            else:
                turn.future.set_exception(RuntimeError(err_msg))
        elif state == "error":
            err_msg = payload.get("errorMessage") or "OpenClaw chat error"
            turn.future.set_exception(RuntimeError(err_msg))

    async def _rpc(self, method: str, params: Dict[str, Any], timeout: float = 20.0) -> Any:
        if not self.ws or not self.connected:
            raise RuntimeError("OpenClaw Gateway is not connected")
        req_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending_rpc[req_id] = fut
        try:
            await self.ws.send(json.dumps({"type": "req", "id": req_id, "method": method, "params": params}))
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending_rpc.pop(req_id, None)

    async def _ensure_session(self, force_create: bool = False) -> str:
        if not force_create:
            saved = self._load_saved_session_key()
            if saved:
                try:
                    desc = await self._rpc("sessions.describe", {"key": saved}, timeout=10.0)
                    if isinstance(desc, dict) and (desc.get("session") or desc.get("key")):
                        self.session_key = saved
                        logger.info("Reusing dedicated Stack-chan session: %s", saved)
                        return saved
                except Exception:
                    logger.info("Saved session %s unavailable; creating a new one", saved)

        res = await self._rpc(
            "sessions.create",
            {"agentId": "main", "displayName": "Stack-chan"},
            timeout=15.0,
        )
        key = None
        if isinstance(res, dict):
            key = res.get("key") or res.get("sessionKey") or (res.get("entry") or {}).get("key")
        if not key:
            raise RuntimeError(f"sessions.create did not return a session key: {res}")
        self.session_key = str(key)
        self._save_session_key(self.session_key)
        logger.info("Created dedicated Stack-chan session: %s", self.session_key)
        return self.session_key

    async def send_turn(self, user_text: str, source: str = "voice", timeout: float = 90.0) -> Tuple[str, Dict[str, Any]]:
        await asyncio.wait_for(self._ready_event.wait(), timeout=20.0)

        async with self._turn_lock:
            if not self.session_key:
                await self._ensure_session()

            wrapped = (
                "[Stack-chan Robot Context]\n"
                "You are embodying Stack-chan, a friendly physical desktop robot with a 320x240 animated face, "
                "pan/tilt head servos (yaw -45..45 deg, pitch 0..60 deg), and internal RGB LEDs.\n"
                "Keep your spoken reply concise, warm, and conversational plain text suitable for TTS "
                "(no markdown, bullet lists, or code blocks).\n"
                "You may optionally include one embodied control directive anywhere in your reply:\n"
                '[[stackchan:{"emotion":"happy|sad|angry|surprised|neutral|thinking|laughing|sleepy|doubtful",'
                '"yaw":0,"pitch":15,"speed":150,"led":[0,120,168]}]]\n'
                "The bridge parses and strips [[stackchan:...]] before speaking.\n\n"
                f"User ({source}): {user_text}"
            )

            for attempt in range(2):
                idem_key = str(uuid.uuid4())
                loop = asyncio.get_running_loop()
                fut = loop.create_future()
                turn = PendingChatTurn(
                    idempotency_key=idem_key,
                    session_key=self.session_key,
                    future=fut,
                )
                self._pending_turns[idem_key] = turn

                try:
                    ack = await self._rpc(
                        "chat.send",
                        {
                            "sessionKey": self.session_key,
                            "message": wrapped,
                            "idempotencyKey": idem_key,
                        },
                        timeout=30.0,
                    )
                    if isinstance(ack, dict) and ack.get("runId"):
                        run_id = str(ack["runId"])
                        turn.run_id = run_id
                        if run_id != idem_key:
                            self._pending_turns[run_id] = turn

                    raw_reply = await asyncio.wait_for(fut, timeout=timeout)
                    self.last_turn_at = time.time()
                    spoken_text, directive = parse_stackchan_directive(raw_reply)
                    if not spoken_text:
                        spoken_text = "Okay!"
                    return spoken_text, directive
                except RuntimeError as exc:
                    # If session became stale/unknown, recreate once and retry
                    if (
                        attempt == 0
                        and "session" in str(exc).lower()
                        and "not found" in str(exc).lower()
                    ):
                        await self._ensure_session(force_create=True)
                        continue
                    raise
                finally:
                    self._pending_turns.pop(idem_key, None)
                    if turn.run_id:
                        self._pending_turns.pop(turn.run_id, None)
