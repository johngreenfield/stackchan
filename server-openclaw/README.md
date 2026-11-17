# server-openclaw (StackChan Self-Hosted Bridge)

Self-hosted Python/FastAPI bridge connecting **StackChan CoreS3** (XiaoZhi Voice WS + Avatar/Control WS), the **OpenClaw Gateway**, and the **Flutter / Web Remote UI**.

## Features

- **Voice & Embodied AI Turn Pipeline:** Receives Opus audio over `/xiaozhi/ws`, transcribes with `faster-whisper`, forwards turns to OpenClaw Gateway, parses `[[stackchan:{...}]]` emotion/servo/LED directives, and streams Piper TTS Opus audio back to the CoreS3.
- **Avatar & Camera Relay (`/stackChan/ws`):** Relays live JPEG camera frames, servo motion, avatar expressions, and LED commands between CoreS3, the Flutter app, and the built-in Web Remote UI.
- **Built-in Web Remote UI (`/`, `/remote/`):** Browser control panel (`static/index.html`) with pan/tilt sliders, expressions, RGB LEDs, live camera view, and OpenClaw chat log.
- **Keepalive & Auth Hardening:** Sends 4-second `HEARTBEAT_PONG` keepalives to connected devices, enforces `STACKCHAN_BRIDGE_TOKEN` across `/api/*`, `/stackChan/device/*`, and WebSocket endpoints, and gates `X-Forwarded-For` behind `TRUST_PROXY_HEADERS`.

## Environment Setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` and set your tokens and hostnames:
   ```dotenv
   OPENCLAW_GATEWAY_URL=ws://host.docker.internal:18789
   OPENCLAW_GATEWAY_TOKEN=replace-with-openclaw-gateway-token
   STACKCHAN_BRIDGE_TOKEN=replace-with-stackchan-bridge-token
   PUBLIC_DOMAIN=stackchan.example.com
   LAN_HOST=192.168.1.100
   PORT=8765
   WHISPER_MODEL=base.en
   PIPER_VOICE=en_US-lessac-medium
   ALLOW_LAN_BYPASS=true
   TRUST_PROXY_HEADERS=false
   ```

## Running the Bridge

### Docker Compose (Recommended)

```bash
cd server-openclaw
docker compose up -d --build
```

### Local Uvicorn (Development)

```bash
cd server-openclaw
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8765
```

## Key Endpoints

| Endpoint | Protocol | Description |
| --- | --- | --- |
| `/health` | HTTP GET | Bridge, OpenClaw, and connected client status |
| `/`, `/remote/` | HTTP GET | Built-in Web Remote UI (`static/index.html`) |
| `/xiaozhi/ota` | HTTP GET/POST | Returns WebSocket URL and server time for CoreS3 |
| `/xiaozhi/ws` | WebSocket | XiaoZhi Opus voice + MCP hardware tool channel |
| `/stackChan/ws` | WebSocket | Binary Avatar/Motion/Camera relay (`StackChan` / `App` / `WebRemote`) |
| `/api/status`, `/api/chat`, `/api/motion`, `/api/avatar`, `/api/led`, `/api/camera/*` | HTTP | Authenticated REST control endpoints (`Authorization: Bearer <token>`) |
