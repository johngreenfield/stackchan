import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fastapi import WebSocket

from app.audio_pipeline import AudioPipeline
from app.openclaw_client import EMOTION_EMOJIS, OpenClawClient
from app.stackchan_protocol import StackChanHub

logger = logging.getLogger("stackchan.xiaozhi")


@dataclass
class XiaoZhiSession:
    session_id: str
    device_id: str
    websocket: WebSocket
    listening: bool = False
    listen_mode: str = "auto"
    uplink_sample_rate: int = 16000
    uplink_frame_duration: int = 60
    downlink_sample_rate: int = 24000
    downlink_frame_duration: int = 60
    audio_buffer: List[bytes] = field(default_factory=list)
    last_audio_at: float = 0.0
    silence_task: Optional[asyncio.Task] = None
    tts_task: Optional[asyncio.Task] = None
    tts_abort_event: asyncio.Event = field(default_factory=asyncio.Event)
    turn_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    mcp_next_id: int = 1
    mcp_pending: Dict[int, asyncio.Future] = field(default_factory=dict)
    mcp_tools: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class XiaoZhiManager:
    def __init__(
        self,
        openclaw: OpenClawClient,
        audio: AudioPipeline,
        avatar_hub: StackChanHub,
    ) -> None:
        self.openclaw = openclaw
        self.audio = audio
        self.avatar_hub = avatar_hub
        self.sessions: Dict[str, XiaoZhiSession] = {}

    @property
    def client_count(self) -> int:
        return len(self.sessions)

    def get_primary_session(self) -> Optional[XiaoZhiSession]:
        if not self.sessions:
            return None
        return next(reversed(self.sessions.values()))

    async def _send_json(self, session: XiaoZhiSession, payload: Dict[str, Any]) -> None:
        await session.websocket.send_text(json.dumps(payload))

    async def call_mcp_tool(
        self,
        session: XiaoZhiSession,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: float = 5.0,
    ) -> Optional[Any]:
        rpc_id = session.mcp_next_id
        session.mcp_next_id += 1
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        session.mcp_pending[rpc_id] = fut

        msg = {
            "session_id": session.session_id,
            "type": "mcp",
            "payload": {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            },
        }
        try:
            await self._send_json(session, msg)
            return await asyncio.wait_for(fut, timeout=timeout)
        except Exception as exc:
            logger.warning("MCP tools/call %s failed or timed out: %s", tool_name, exc)
            return None
        finally:
            session.mcp_pending.pop(rpc_id, None)

    async def _send_mcp_rpc(
        self,
        session: XiaoZhiSession,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 5.0,
    ) -> Optional[Any]:
        rpc_id = session.mcp_next_id
        session.mcp_next_id += 1
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        session.mcp_pending[rpc_id] = fut
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
        if params is not None:
            payload["params"] = params
        try:
            await self._send_json(
                session,
                {"session_id": session.session_id, "type": "mcp", "payload": payload},
            )
            return await asyncio.wait_for(fut, timeout=timeout)
        except Exception as exc:
            logger.debug("MCP %s failed/timed out: %s", method, exc)
            return None
        finally:
            session.mcp_pending.pop(rpc_id, None)

    async def _init_mcp_discovery(self, session: XiaoZhiSession) -> None:
        init_res = await self._send_mcp_rpc(
            session,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "openclaw-stackchan-bridge", "version": "1.0.0"},
            },
            timeout=5.0,
        )
        if init_res is not None:
            logger.debug("MCP initialize result for %s: %s", session.device_id, init_res)
        tools_res = await self._send_mcp_rpc(session, "tools/list", {}, timeout=5.0)
        if isinstance(tools_res, dict):
            tools = tools_res.get("tools")
            if isinstance(tools, list):
                for tool in tools:
                    if isinstance(tool, dict) and tool.get("name"):
                        session.mcp_tools[str(tool["name"])] = tool
                logger.info(
                    "Discovered %d MCP tools from %s: %s",
                    len(session.mcp_tools),
                    session.device_id,
                    list(session.mcp_tools.keys()),
                )

    async def _abort_tts(self, session: XiaoZhiSession) -> None:
        session.tts_abort_event.set()
        task = session.tts_task
        if task and not task.done():
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except asyncio.TimeoutError:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            except Exception:
                pass

    async def _stream_tts(self, session: XiaoZhiSession, spoken_text: str) -> None:
        session.tts_abort_event.clear()
        frames = await self.audio.text_to_opus_frames(
            spoken_text,
            sample_rate=session.downlink_sample_rate,
            frame_duration_ms=session.downlink_frame_duration,
        )
        if session.tts_abort_event.is_set():
            return

        await self._send_json(session, {"session_id": session.session_id, "type": "tts", "state": "start"})
        await self._send_json(
            session,
            {
                "session_id": session.session_id,
                "type": "tts",
                "state": "sentence_start",
                "text": spoken_text,
            },
        )

        frame_sec = session.downlink_frame_duration / 1000.0
        start_time = time.monotonic()
        prebuffer_frames = 3
        try:
            for idx, frame in enumerate(frames):
                if session.tts_abort_event.is_set():
                    break
                await session.websocket.send_bytes(frame)
                if idx >= prebuffer_frames:
                    target = start_time + (idx - prebuffer_frames + 1) * frame_sec
                    delay = target - time.monotonic()
                    if delay > 0:
                        try:
                            await asyncio.wait_for(session.tts_abort_event.wait(), timeout=delay)
                            break
                        except asyncio.TimeoutError:
                            pass
        finally:
            try:
                await self._send_json(session, {"session_id": session.session_id, "type": "tts", "state": "stop"})
            except Exception:
                pass

    async def apply_directive(
        self,
        directive: Dict[str, Any],
        session: Optional[XiaoZhiSession] = None,
    ) -> None:
        emotion = str(directive.get("emotion", "neutral")).lower()

        # 1. XiaoZhi LLM emotion + MCP hardware tools
        if session is not None:
            emoji = EMOTION_EMOJIS.get(emotion, "🙂")
            try:
                await self._send_json(
                    session,
                    {
                        "session_id": session.session_id,
                        "type": "llm",
                        "emotion": emotion,
                        "text": emoji,
                    },
                )
            except Exception as exc:
                logger.warning("Failed to send llm emotion: %s", exc)

            if "yaw" in directive or "pitch" in directive:
                args: Dict[str, Any] = {"speed": int(directive.get("speed", 150))}
                if "yaw" in directive:
                    args["yaw"] = int(directive["yaw"])
                if "pitch" in directive:
                    args["pitch"] = int(directive["pitch"])
                await self.call_mcp_tool(session, "self.robot.set_head_angles", args)

            if "led" in directive and isinstance(directive["led"], list) and len(directive["led"]) == 3:
                r, g, b = [int(x) for x in directive["led"]]
                await self.call_mcp_tool(
                    session,
                    "self.robot.set_led_color",
                    {"red": r, "green": g, "blue": b},
                )

        # 2. Relay to Avatar WS (/stackChan/ws) if connected
        if self.avatar_hub.device_count > 0:
            await self.avatar_hub.send_avatar_emotion(emotion)
            if "yaw" in directive or "pitch" in directive:
                await self.avatar_hub.send_motion(
                    yaw_deg=directive.get("yaw"),
                    pitch_deg=directive.get("pitch"),
                    speed=int(directive.get("speed", 150)),
                )
            if "led" in directive and isinstance(directive["led"], list) and len(directive["led"]) == 3:
                r, g, b = [int(x) for x in directive["led"]]
                await self.avatar_hub.send_led_color(r, g, b)

    async def run_embodied_turn(
        self,
        user_text: str,
        source: str = "voice",
        session: Optional[XiaoZhiSession] = None,
    ) -> Dict[str, Any]:
        target_session = session or self.get_primary_session()
        if target_session is not None:
            async with target_session.turn_lock:
                return await self._run_embodied_turn_locked(user_text, source=source, target_session=target_session)
        return await self._run_embodied_turn_locked(user_text, source=source, target_session=None)

    async def _run_embodied_turn_locked(
        self,
        user_text: str,
        source: str = "voice",
        target_session: Optional[XiaoZhiSession] = None,
    ) -> Dict[str, Any]:
        if target_session is not None:
            await self._abort_tts(target_session)
            try:
                await self._send_json(
                    target_session,
                    {"session_id": target_session.session_id, "type": "stt", "text": user_text},
                )
            except Exception:
                pass

        spoken_text, directive = await self.openclaw.send_turn(user_text, source=source)
        await self.apply_directive(directive, session=target_session)

        audio_played = False
        if target_session is not None:
            target_session.tts_task = asyncio.create_task(
                self._stream_tts(target_session, spoken_text),
                name=f"tts-{target_session.session_id[:8]}",
            )
            await target_session.tts_task
            audio_played = True
        elif self.avatar_hub.device_count > 0:
            # Show text bubble if only Avatar WS is connected
            await self.avatar_hub.send_binary_to_devices(
                0x07,
                json.dumps({"name": "OpenClaw", "content": spoken_text}).encode("utf-8"),
            )

        result = {
            "user_text": user_text,
            "reply_text": spoken_text,
            "directive": directive,
            "audio_played_on_device": audio_played,
            "timestamp": time.time(),
        }
        await self.avatar_hub.broadcast_json_to_remotes({"type": "chat_log", "data": result})
        return result

    async def _process_audio_buffer(self, session: XiaoZhiSession) -> None:
        async with session.turn_lock:
            frames = list(session.audio_buffer)
            session.audio_buffer.clear()
            if not frames:
                return
            try:
                text = await self.audio.transcribe_opus_frames(frames, sample_rate=session.uplink_sample_rate)
            except Exception as exc:
                logger.exception("Whisper STT error: %s", exc)
                return

            if not text:
                logger.debug("Empty STT result from %d audio frames", len(frames))
                return

            logger.info("STT [%s]: %s", session.device_id, text)
            try:
                await self._run_embodied_turn_locked(text, source="voice", target_session=session)
            except Exception as exc:
                logger.exception("Embodied voice turn failed: %s", exc)
                try:
                    await self._send_json(
                        session,
                        {
                            "session_id": session.session_id,
                            "type": "llm",
                            "emotion": "sad",
                            "text": "😅",
                        },
                    )
                except Exception:
                    pass

    async def _silence_watchdog(self, session: XiaoZhiSession) -> None:
        try:
            while session.listening:
                await asyncio.sleep(0.25)
                if not session.listening:
                    break
                if session.audio_buffer and (time.monotonic() - session.last_audio_at) >= 1.2:
                    if len(session.audio_buffer) >= 3:
                        session.listening = False
                        asyncio.create_task(self._process_audio_buffer(session))
                    break
        except asyncio.CancelledError:
            pass

    def _cancel_silence_watchdog(self, session: XiaoZhiSession) -> None:
        if session.silence_task and not session.silence_task.done():
            session.silence_task.cancel()
        session.silence_task = None

    async def handle_websocket(self, websocket: WebSocket, device_id: str) -> None:
        await websocket.accept()
        session_id = str(uuid.uuid4())
        session = XiaoZhiSession(session_id=session_id, device_id=device_id, websocket=websocket)

        try:
            # Expect client hello within 10s
            raw_hello = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
            hello = json.loads(raw_hello)
            if hello.get("type") != "hello":
                await websocket.close(code=1008, reason="Expected hello")
                return

            audio_params = hello.get("audio_params") or {}
            session.uplink_sample_rate = int(audio_params.get("sample_rate") or 16000)
            session.uplink_frame_duration = int(audio_params.get("frame_duration") or 60)

            await self._send_json(
                session,
                {
                    "type": "hello",
                    "transport": "websocket",
                    "session_id": session_id,
                    "audio_params": {
                        "format": "opus",
                        "sample_rate": session.downlink_sample_rate,
                        "channels": 1,
                        "frame_duration": session.downlink_frame_duration,
                    },
                },
            )

            self.sessions[session_id] = session
            logger.info("XiaoZhi WS connected: device=%s session=%s", device_id, session_id)
            await self.avatar_hub._push_status_to_remotes()

            # Discover device MCP tools asynchronously if supported
            features = hello.get("features") or {}
            if features.get("mcp", True):
                asyncio.create_task(self._init_mcp_discovery(session))

            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break

                if msg.get("bytes") is not None:
                    if session.listening:
                        session.audio_buffer.append(msg["bytes"])
                        session.last_audio_at = time.monotonic()
                elif msg.get("text") is not None:
                    await self._handle_text_message(session, msg["text"])
        except Exception as exc:
            logger.info("XiaoZhi WS closed (%s): %s", session_id, exc)
        finally:
            self._cancel_silence_watchdog(session)
            await self._abort_tts(session)
            for fut in session.mcp_pending.values():
                if not fut.done():
                    fut.cancel()
            self.sessions.pop(session_id, None)
            await self.avatar_hub._push_status_to_remotes()

    async def _handle_text_message(self, session: XiaoZhiSession, raw_text: str) -> None:
        try:
            msg = json.loads(raw_text)
        except Exception:
            return
        if not isinstance(msg, dict):
            return

        msg_type = msg.get("type")
        if msg_type == "listen":
            state = msg.get("state")
            mode = str(msg.get("mode") or "auto")
            if state == "start":
                await self._abort_tts(session)
                self._cancel_silence_watchdog(session)
                session.audio_buffer.clear()
                session.listening = True
                session.listen_mode = mode
                session.last_audio_at = time.monotonic()
                if mode == "auto":
                    session.silence_task = asyncio.create_task(self._silence_watchdog(session))
            elif state == "stop":
                session.listening = False
                self._cancel_silence_watchdog(session)
                if session.audio_buffer:
                    asyncio.create_task(self._process_audio_buffer(session))
            elif state == "detect":
                # Wake word detected; clear stale audio and wait for listen start
                session.audio_buffer.clear()
                logger.info("Wake word detected [%s]: %s", session.device_id, msg.get("text", ""))
            elif state == "text":
                text = str(msg.get("text", "")).strip()
                if text:
                    asyncio.create_task(self.run_embodied_turn(text, source="voice-text", session=session))
        elif msg_type == "text":
            text = str(msg.get("text", "")).strip()
            if text:
                asyncio.create_task(self.run_embodied_turn(text, source="text", session=session))
        elif msg_type == "abort":
            session.listening = False
            self._cancel_silence_watchdog(session)
            await self._abort_tts(session)
        elif msg_type == "mcp":
            payload = msg.get("payload")
            if isinstance(payload, dict) and "id" in payload:
                rpc_id = payload["id"]
                fut = session.mcp_pending.pop(rpc_id, None)
                if fut and not fut.done():
                    if "error" in payload and payload["error"] is not None:
                        fut.set_exception(RuntimeError(str(payload["error"])))
                    else:
                        fut.set_result(payload.get("result"))
