# Stack-chan × OpenClaw Architecture & Protocol Specification

> **Branch:** `feat/openclaw-integration`  
> **Scope:** Technical audit of `https://github.com/m5stack/StackChan` (`firmware/`, `server/`, `remote/`, `app/`) and integration architecture for self-hosted OpenClaw operation.

---

## 1. Repository Overview & Key Clarifications

| Directory | Actual Contents & Role | Notes for Integration |
| :--- | :--- | :--- |
| `firmware/` | **ESP-IDF v6.1** C++23 firmware for the **M5Stack Kickstarter Stack-chan** (CoreS3 / ESP32-S3 based). Integrates `xiaozhi-esp32` (v2.5.2 + local patch) for AI voice agent mode alongside Mooncake apps (`AI.AGENT`, `AVATAR`, `DANCE`, `ESPNOW.REMOTE`, `APP.CENTER`, `SETUP`). | Not PlatformIO; builds with ESP-IDF `>=6.1.0,<6.2.0` (`idf.py build`). `fetch_repos.py` clones 6 dependencies and applies `patches/xiaozhi-esp32.patch`. |
| `server/` | **GoFrame v2 / Go 1.26** backend (`:12800`) providing REST APIs (`/stackChan/*`, `/stackChan/v2/*`), MySQL persistence, RSA-OAEP auth, XiaoZhi cloud API proxy (`https://xiaozhi.me/`), and binary WebSocket relay (`/stackChan/ws`). | `server/resource/public/` only contains `.gitkeep` placeholders (no web remote UI is included upstream). |
| `remote/` | **Hardware ESP-NOW Remote Controller firmware** (`StackChan-RemoteControl-ESPNow`, ESP-IDF C++ for M5Stack remote hardware) using local ESP-NOW packets—**not** a web UI. | No cloud URLs or WebSocket endpoints exist in `remote/`. A dedicated **Web Remote UI** will be served by `server-openclaw/` for browser/control access. |
| `app/` | **Flutter** mobile app (`StackChan World`) targeting Android & iOS. Handles BLE Wi-Fi provisioning, RSA-encrypted auth, XiaoZhi agent setup (`https://xiaozhi.me/`), LAN direct control, and remote WebSocket avatar/camera/dance control. | Documented in Phase 4 (`APP_MIGRATION_SPEC.md`) for external update in Antigravity on Windows. |

---

## 2. Firmware Architecture & Build System (`firmware/`)

### 2.1 Framework, Toolchain & Dependencies
- **Framework:** Espressif **ESP-IDF** (`idf >=6.1.0,<6.2.0` in `firmware/main/idf_component.yml`, `firmware/README.md`).
- **Project Version:** `1.6.2` (`firmware/CMakeLists.txt`).
- **C++ Standard:** `cxx_std_23` (`-std=gnu++23`, exceptions + RTTI enabled).
- **Local Config Overlay:** `firmware/CMakeLists.txt` auto-detects `sdkconfig.defaults.local` and appends it to `SDKCONFIG_DEFAULTS`.
- **Vendored Dependencies (`firmware/repos.json`, fetched via `firmware/fetch_repos.py`):**
  - `components/mooncake` (`v2.3.3`)
  - `components/mooncake_log` (`v1.5.0`)
  - `components/smooth_ui_toolkit` (`v2.12.0`)
  - `components/ArduinoJson` (`v7.4.2`)
  - `components/esp-now` (`c3b5f9be245f1a80db9cb938600566aa6a8dd1e5`)
  - `xiaozhi-esp32` (`v2.5.2`, patched with `firmware/patches/xiaozhi-esp32.patch`)
- **Managed IDF Components (`firmware/main/idf_component.yml`):** Includes `lvgl/lvgl` (`~9.5.0`), `esp_lvgl_port` (`~2.9.0`), `espressif/esp-sr` (`==2.4.7`), `78/esp-wifi-connect` (`~3.3.1`), `78/xiaozhi-fonts` (`~2.0.0`), `espressif/esp_codec_dev`, `espressif/esp32-camera`, `espressif/esp_video`, `espressif/bmi270_sensor`, `espressif/led_strip`, etc.

### 2.2 Target MCU, Hardware & SDK Flags (`firmware/sdkconfig.defaults` & `main/hal/board/config.h`)
- **Target:** `CONFIG_IDF_TARGET="esp32s3"` (`240 MHz` CPU).
- **Board:** `CONFIG_BOARD_TYPE_M5STACK_STACK_CHAN=y`.
- **Flash:** `16 MB` QIO (`CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y`, `CONFIG_ESPTOOLPY_FLASHMODE_QIO=y`).
- **PSRAM:** Enabled at `80 MHz` (`CONFIG_SPIRAM=y`, `CONFIG_SPIRAM_SPEED_80M=y`, `CONFIG_SPIRAM_MALLOC_RESERVE_INTERNAL=65536`).
- **Display:** `320×240` ILI9342E LCD + FT6336 capacitive touch (`LVGL` RGB565).
- **Audio Codec:** Duplex I2S TDM (AW88298 speaker amp + ES7210 mic ADC via I2C `SDA=12, SCL=11`), `AUDIO_INPUT_SAMPLE_RATE = 24000`, `AUDIO_OUTPUT_SAMPLE_RATE = 24000`, `AUDIO_INPUT_REFERENCE = true` (AEC reference).
- **Camera:** GC0308 DVP (`YUV422 320×240 20fps`).
- **Servos:** Feetech SCS serial bus servos (`FTServo_Arduino/SCSCL.h`):
  - **Yaw servo:** `angleLimit = [-1280, 1280]` (decidegrees = `-128.0°` to `+128.0°`), `rawPosLimit = [0, 1000]`.
  - **Pitch servo:** `angleLimit = [30, 870]` (decidegrees = `+3.0°` to `+87.0°`), `rawPosLimit = [0, 1000]`.
  - Conversion: `mapped_raw = zero_pos + angle_decideg * 16 / 50`.
- **Wake Word & AFE:** `CONFIG_USE_AFE_WAKE_WORD=y`, `CONFIG_SR_WN_WN9L_HISTACKCHAN_TTS3=y` (`"Hi Stack-chan"`), `CONFIG_SEND_WAKE_WORD_DATA=n`.
- **Bluetooth:** NimBLE enabled in PSRAM (`CONFIG_BT_NIMBLE_MEM_ALLOC_MODE_EXTERNAL=y`, `CONFIG_BT_NIMBLE_ATT_PREFERRED_MTU=512`).
- **Memory & TLS:** `CONFIG_MBEDTLS_EXTERNAL_MEM_ALLOC=y`, `CONFIG_MBEDTLS_DYNAMIC_BUFFER=y`, `CONFIG_MBEDTLS_DYNAMIC_FREE_CONFIG_DATA=y`.

### 2.3 Partition Table (`firmware/partitions.csv`)
| Partition | Type | SubType | Offset | Size | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `nvs` | `data` | `nvs` | `0x9000` | `0x4000` (16 KB) | Wi-Fi, WebSocket, device settings |
| `otadata` | `data` | `ota` | `0xd000` | `0x2000` (8 KB) | Active OTA slot selector |
| `phy_init` | `data` | `phy` | `0xf000` | `0x1000` (4 KB) | RF calibration |
| `ota_0` | `app` | `ota_0` | `0x20000` | `0x4f0000` (~4.94 MB) | Primary firmware image |
| `ota_1` | `app` | `ota_1` | `0x510000` | `0x4f0000` (~4.94 MB) | Secondary OTA slot |
| `assets` | `data` | `spiffs` | `0xA00000` | `0x400000` (4 MB) | `generated_assets.bin` (fonts, emojis, SR wake word model) |
| `coredump` | `data` | `coredump` | `0xE00000` | `0x10000` (64 KB) | Crash coredumps |

*(Note: Standard ESP32-S3 bootloader sits at `0x0`, partition table at `0x8000`, and `ota_data_initial.bin` at `0xd000`.)*

### 2.4 Wi-Fi & Server Provisioning Mechanism
1. **Upstream Defaults:** Hotspot (`CONFIG_USE_HOTSPOT_WIFI_PROVISIONING=n`) and BluFi (`CONFIG_USE_ESP_BLUFI_WIFI_PROVISIONING=n`) are disabled.
2. **BLE GATT Provisioning (`main/hal/hal_ble.cpp`, `main/hal/utils/bleprph/bleprph.h`):**
   - Service UUID (normal): `e2e5e5e0-1234-5678-1234-56789abcdef0`
   - Service UUID (setup/alt mode): `e2e5e5ff-1234-5678-1234-56789abcdef0`
   - Characteristics:
     - Motion: `e2e5e5e1-1234-5678-1234-56789abcdef0`
     - Avatar: `e2e5e5e2-1234-5678-1234-56789abcdef0`
     - Config: `e2e5e5e3-1234-5678-1234-56789abcdef0`
     - RGB: `e2e5e5e4-1234-5678-1234-56789abcdef0`
   - Large GATT packets (>MTU) use a 10-byte fragmentation header: `[0xAA, 0x55, 0xC3, 0x01, idx(2B BE), total_pkts(2B BE), total_len(2B BE)]`.
   - Config JSON commands: `{"cmd":"setWifi","data":{"ssid":"...","password":"...","frequency":2412,"currentNetwork":true}}`, `{"cmd":"getWifiStatus"}`, `{"cmd":"handshake","data":"..."}`.
3. **Boot-Time Setup Gate (`app_launcher.cpp` & `hal_app_setup.cpp`):**
   - NVS `app_config.is_configed` is checked on boot (`Hal::isAppConfiged()`). If `false`, Stack-chan forces the `app_setup` BLE provisioning flow.
   - `Application::CheckNewVersion()` (`xiaozhi-esp32.patch`) reboots into `app_setup` (`requestAppSetup()`) if OTA returns an `activation.code` (`RequiresAppBinding()`), or if `challenge_rounds > 3`.
   - **Self-Hosted Fix (Phase 3):** When `stackchan_config.h` supplies default Wi-Fi credentials or OpenClaw server settings, pre-populate `WifiManager`/`SsidManager` + `app_config.is_configed = true` + NVS `websocket.url`/`token` when unconfigured, and omit `activation` in the bridge's `/ota` JSON response so the device boots straight into normal operation.

### 2.5 TLS Root Certificate Handling
- `firmware/sdkconfig.defaults` enables PSRAM & dynamic mbedTLS buffers (`CONFIG_MBEDTLS_EXTERNAL_MEM_ALLOC=y`, `CONFIG_MBEDTLS_DYNAMIC_BUFFER=y`) but does **not** explicitly pin `CONFIG_MBEDTLS_CERTIFICATE_BUNDLE=y` / `CONFIG_MBEDTLS_CERTIFICATE_BUNDLE_DEFAULT_FULL=y`.
- `firmware/main/hal/utils/network_diagnostics/network_diagnostics.cpp:146` attaches `esp_crt_bundle_attach` only `#ifdef CONFIG_MBEDTLS_CERTIFICATE_BUNDLE`.
- `firmware/main/hal/utils/ota/ota.c:29` embeds a dummy self-signed cert (`Stackchan OTA Test Server` for `localhost`) with `CONFIG_EXAMPLE_USE_CERT_BUNDLE` commented out.
- `78/esp-wifi-connect` (used by `Board::GetNetwork()->CreateHttp()` and `CreateWebSocket()`) uses ESP-IDF `esp_crt_bundle_attach` when `CONFIG_MBEDTLS_CERTIFICATE_BUNDLE` is enabled.
- **Requirement for `wss://stackchan.example.com` (Phase 3):**
  1. Explicitly enable `CONFIG_MBEDTLS_CERTIFICATE_BUNDLE=y` and `CONFIG_MBEDTLS_CERTIFICATE_BUNDLE_DEFAULT_FULL=y` in `sdkconfig.defaults`.
  2. Also bundle the Let's Encrypt **ISRG Root X1** PEM certificate in `stackchan_config.h` and ensure SNTP time sync runs before TLS handshakes (already started in `Hal::startNetwork()` -> `startSntp()`) so X.509 validity checks succeed.

---

## 3. Wire Protocols

Stack-chan uses **two distinct WebSocket protocols** depending on the active subsystem:

### 3.1 Channel A — XiaoZhi AI Voice Agent Protocol (`AI.AGENT` / `xiaozhi-esp32`)

1. **OTA & WebSocket Discovery (`xiaozhi-esp32/main/ota.cc`):**
   - Device sends `POST <OTA_URL>` (default `CONFIG_OTA_URL = "https://api.tenclass.net/xiaozhi/ota/"`, overridable via NVS `wifi.ota_url`).
   - Headers: `Activation-Version: 1|2`, `Device-Id: <MAC>`, `Client-Id: <UUID>`, `User-Agent`, `Accept-Language: en-US`, `Content-Type: application/json`.
   - Body: `Board::GetSystemInfoJson()` (chip, flash, PSRAM, mac, version, etc.).
   - Server JSON Response:
     ```json
     {
       "server_time": { "timestamp": 1794680000000, "timezone_offset": 0 },
       "websocket": {
         "url": "wss://stackchan.example.com/xiaozhi/ws",
         "token": "<auth-token>",
         "version": 1
       },
       "firmware": { "version": "1.6.2", "url": "" }
     }
     ```
     *(Omitting `"activation"` prevents `RequiresAppBinding()` from rebooting into setup!)*

2. **WebSocket Handshake (`xiaozhi-esp32/main/protocols/websocket_protocol.cc`):**
   - Connects to NVS `websocket.url` with headers:
     - `Authorization: Bearer <token>`
     - `Protocol-Version: 1` (or `2` / `3`)
     - `Device-Id: <MAC>`
     - `Client-Id: <UUID>`
   - **Client `hello` (text JSON):**
     ```json
     {
       "type": "hello",
       "version": 1,
       "features": { "mcp": true },
       "transport": "websocket",
       "audio_params": {
         "format": "opus",
         "sample_rate": 16000,
         "channels": 1,
         "frame_duration": 60
       }
     }
     ```
   - **Server `hello` (text JSON, must arrive within 10s):**
     ```json
     {
       "type": "hello",
       "transport": "websocket",
       "session_id": "<uuid>",
       "audio_params": {
         "format": "opus",
         "sample_rate": 24000,
         "channels": 1,
         "frame_duration": 60
       }
     }
     ```

3. **Audio Format & Binary Framing:**
   - **Codec:** Raw **Opus** frames (`OPUS_FRAME_DURATION_MS = 60` ms, `channels = 1` mono).
   - **Uplink (Device -> Server):** `16000 Hz` mono Opus (60 ms = 960 samples/frame).
   - **Downlink (Server -> Device):** `24000 Hz` (or `16000 Hz`, matched to server `hello` `audio_params.sample_rate`) mono Opus (60 ms = 1440 samples/frame at 24 kHz; `AudioService` resamples if needed to `AUDIO_OUTPUT_SAMPLE_RATE=24000`).
   - **Framing (`version == 1`):** Raw Opus packet per WebSocket binary frame (no extra header). (`v2` adds 16-byte `BinaryProtocol2`; `v3` adds 4-byte `BinaryProtocol3`.)

4. **JSON Control Messages:**
   - **Device -> Server:**
     - `{"session_id":"...","type":"listen","state":"start"|"stop"|"detect","mode":"auto"|"manual"|"realtime","text":"..."}`
     - `{"session_id":"...","type":"abort","reason":"wake_word_detected"}`
     - `{"session_id":"...","type":"mcp","payload":{"jsonrpc":"2.0","id":1,"result":{...}}}`
   - **Server -> Device:**
     - `{"session_id":"...","type":"stt","text":"<user speech>"}`
     - `{"session_id":"...","type":"llm","emotion":"happy","text":"😀"}`
     - `{"session_id":"...","type":"tts","state":"start"|"sentence_start"|"stop","text":"..."}`
     - `{"session_id":"...","type":"mcp","payload":{"jsonrpc":"2.0","id":1,"method":"initialize"|"tools/list"|"tools/call","params":{...}}}`
     - `{"session_id":"...","type":"alert","status":"...","message":"...","emotion":"..."}`
     - `{"session_id":"...","type":"system","command":"reboot"}`

5. **Firmware Embodied MCP Tools (`firmware/main/hal/hal_mcp.cpp`):**
   - `self.robot.get_head_angles` -> returns `{"yaw": <deg>, "pitch": <deg>}`
   - `self.robot.set_head_angles` -> args `yaw` (`-128..128` deg), `pitch` (`0..90` deg), `speed` (`100..1000`, default `150`)
   - `self.robot.set_led_color` -> args `red`, `green`, `blue` (`0..168`)
   - `self.robot.create_reminder`, `self.robot.get_reminders`, `self.robot.stop_reminder`

6. **Supported Firmware Emotions (`main/hal/board/stackchan_display.cc:321`):**
   - Currently implemented: `"neutral"`, `"happy"`, `"laughing"`, `"angry"`, `"sad"`, `"crying"`, `"sleepy"`, `"doubtful"`.
   - **Gap identified:** `"surprised"` and `"thinking"` currently fall back to `Emotion::Neutral`! In Phase 3, `SetEmotion()` will be extended to handle `"surprised"` and `"thinking"` explicitly via custom avatar expressions/modifiers.

---

### 3.2 Channel B — Stack-chan Avatar & Device WebSocket (`hal_ws_avatar.cpp` <-> `server/`)

1. **Endpoint & Auth:**
   - Firmware connects to: `<STACKCHAN_SERVER_URL>/stackChan/ws?deviceType=StackChan` (`ws://` or `wss://`).
   - App connects to: `<STACKCHAN_SERVER_URL>/stackChan/ws?deviceType=App&deviceId=<uuid>`.
   - Header `Authorization`:
     - Upstream Go server (`server/internal/web_socket/web_socket.go:79`): expects `Base64(RSA-OAEP-SHA256("<mac>|<random>|<unix_sec>"))` decrypted with server private key (10s clock window).
     - Firmware stub (`secret_logic.cpp:22`): weak symbol returns `"<bridge-token>"` when proprietary key library is absent.
     - **Self-hosted bridge solution:** Support both token-based auth (e.g., `Bearer <token>` / shared bridge token + `Device-Id` header) and fallback MAC query/header identification cleanly.

2. **Binary Envelope (`[Type:1][Length:4 BE][Payload:Length]`):**
   - `0x01` `Opus` (audio)
   - `0x02` `Jpeg` (camera / phone screen video frame)
   - `0x03` `ControlAvatar` — JSON:
     ```json
     {
       "leftEye":  { "x": 0, "y": 0, "rotation": 0, "weight": 100, "size": 100 },
       "rightEye": { "x": 0, "y": 0, "rotation": 0, "weight": 100, "size": 100 },
       "mouth":    { "x": 0, "y": 0, "rotation": 0, "weight": 100, "size": 100 }
     }
     ```
   - `0x04` `ControlMotion` — JSON (angles in decidegrees, `10 = 1°`):
     ```json
     {
       "yawServo":   { "angle": 0, "speed": 150 },
       "pitchServo": { "angle": 300, "speed": 150 }
     }
     ```
     *(Supports `speed`, `spring: {stiffness, damping}`, or `rotate` velocity.)*
   - `0x05` / `0x06` `StartCameraStream` / `StopCameraStream`
   - `0x07` `TextMessage` (`{"name":"...","content":"..."}`)
   - `0x09`–`0x0C` `RequestCall`, `DeclineCall`, `AcceptCall`, `EndCall`
   - `0x0D` / `0x0E` `SetDeviceName` / `GetDeviceName`
   - `0x10` / `0x11` `HeartbeatPing` / `HeartbeatPong` (firmware warns after 10s silence)
   - `0x12` / `0x13` `VideoModeOn` / `VideoModeOff`
   - `0x14` `DanceSequence` — JSON array of keyframes (`leftEye`, `rightEye`, `mouth`, `yawServo`, `pitchServo`, `leftRgbColor`, `rightRgbColor`, `durationMs`)
   - `0x15` `GetAvatarPosture`, `0x16`/`0x17` `DeviceOffline`/`Online`, `0x18`/`0x19` `Start/StopAudioStream`, `0x1A` `AimedTakePhoto`, `0x1B` `AppLanAddress`

3. **LAN Direct Framing (`local_network_protocol.h`):**
   - 20-byte header: `['S', 'C', 0x01, type, 0, 0, session(8B BE), seq(4B BE), len(2B BE)]` + payload (with 12-char MAC prefix for types `0x02..0x06, 0x12, 0x13`).

---

## 4. Hardcoded URLs, Endpoints, Keys & Auth Audit

| Component | File & Line | Current Hardcoded Value / Behavior | Target Replacement |
| :--- | :--- | :--- | :--- |
| `firmware/` | `main/Kconfig.projbuild:4` | `CONFIG_STACKCHAN_SERVER_URL = "http://47.113.125.164:12800"` | `stackchan_config.h` (`wss://stackchan.example.com` / `ws://192.168.1.100:8765`) |
| `firmware/` | `main/Kconfig.projbuild:17` | `CONFIG_OTA_URL = "https://api.tenclass.net/xiaozhi/ota/"` | `https://stackchan.example.com/xiaozhi/ota/` / `http://192.168.1.100:8765/xiaozhi/ota/` |
| `firmware/` | `main/hal/utils/secret_logic/secret_logic.cpp:16,22,27` | Weak stubs: `"http://localhost:3000"`, token `"<bridge-token>"` | Read from `stackchan_config.h` (`STACKCHAN_BRIDGE_URL`, `STACKCHAN_AUTH_TOKEN`) |
| `firmware/` | `main/hal/hal_ws_avatar.cpp:74,119` | Connects to `<server_url>/stackChan/ws?deviceType=StackChan` with `Authorization` header | Point to self-hosted bridge + include `Device-Id` MAC header |
| `firmware/` | `main/hal/hal_account.cpp:19-30` | `/stackChan/device/user`, `/stackChan/device/info`, `/stackChan/device/unbind` | Implemented cleanly by `server-openclaw/` |
| `firmware/` | `main/hal/hal_app_center.cpp:18` | `GET <server_url>/stackChan/apps` | Implemented cleanly by `server-openclaw/` |
| `firmware/` | `main/hal/hal_ezdata.cpp:158` | `https://ezdata2.m5stack.com/api/v2/device/registerMac` (MQTT cloud telemetry) | Disable/guard behind config flag in OpenClaw build |
| `firmware/` | `main/hal/hal_network.cpp:36-38` | SNTP servers `pool.ntp.org`, `time.google.com`, `cn.pool.ntp.org` | Keep `pool.ntp.org` & `time.google.com` (needed for TLS) |
| `firmware/` | `main/hal/utils/ota/ota.c:29` | Hardcoded self-signed `localhost` PEM cert | Enable `CONFIG_MBEDTLS_CERTIFICATE_BUNDLE_DEFAULT_FULL=y` + bundle ISRG Root X1 |
| `server/` | `manifest/config/config.yaml:3` | `address: ":12800"`, empty MySQL/JWT/RSA/XiaoZhi fields | Superseded by `server-openclaw/` on `:8765` |
| `server/` | `internal/xiaozhi/xiaozhi.go:42` | `baseUrl = "https://xiaozhi.me/"` + `api/developers/*` | Replaced by OpenClaw Gateway RPC + local STT/TTS |
| `server/` | `internal/web_socket/web_socket.go:79` | RSA-OAEP-SHA256 `Authorization` header decryption (`server/utility/rsa.go`) | Bridge token + `Device-Id` auth in `server-openclaw/` |
| `remote/` | `code/main/*` | Pure ESP-NOW hardware remote (no cloud URLs) | Unchanged; Web Remote UI added in `server-openclaw/` |
| `app/` | `lib/network/urls.dart:21` | `static const String url = "api.example.com:8080/";`, hardcoded `http://` & `ws://` schemes | Update to `stackchan.example.com` (`https://` / `wss://`), documented in Phase 4 |
| `app/` | `lib/util/xiao_zhi_util.dart:32` & `XiaoZhi_util.dart:39` | `"https://xiaozhi.me/"` / `"https://XiaoZhi.me/"` | Bypass / route to `server-openclaw/` in Phase 4 |
| `app/` | `lib/util/value_constant.dart` & `rsa_util.dart` | Build-time `--dart-define` RSA keys (`serverPublicKey`, `clientPrivateKey`, `stackChanBluePrivateKey`) | Document token/auth simplification in Phase 4 |

---

## 5. Architecture Plan for Phases 2–4

1. **Unified Self-Hosted Bridge (`server-openclaw/` on port `8765`):**
   - **HTTP Endpoints:**
     - `GET /health` — Docker healthcheck & bridge readiness.
     - `POST/GET /xiaozhi/ota/` — Returns `websocket: { url, token, version: 1 }` pointing to `/xiaozhi/ws` (`wss://stackchan.example.com/xiaozhi/ws` or `ws://192.168.1.100:8765/xiaozhi/ws` based on `Host`/protocol or env), `server_time`, and **no** `activation` block.
     - `GET /stackChan/device/user`, `GET /stackChan/device/info`, `POST /stackChan/device/unbind`, `GET /stackChan/apps` — Minimal JSON responses (`{code:0, data:...}`) so firmware account/app-center views never error.
     - `GET /` & static assets — **Stack-chan Web Remote UI** (avatar expression buttons, pan/tilt joystick/sliders, TTS speak test, live camera JPEG viewer, text chat to OpenClaw, device connection status).
   - **WebSocket Endpoints:**
     - `/xiaozhi/ws` — Full XiaoZhi v1 protocol (hello, Opus 16kHz→PCM→STT, OpenClaw Gateway RPC chat turn, TTS→PCM→Opus 24kHz, MCP tool bridge for `self.robot.set_head_angles`, `self.robot.set_led_color`, plus `llm` emotion updates!).
     - `/stackChan/ws` — Binary protocol relay (`[Type:1][Len:4][Payload]`) supporting both `deviceType=StackChan` and `deviceType=WebRemote` / `App`, enabling real-time pan/tilt, avatar, LED, dance, and camera JPEG streaming, plus allowing OpenClaw voice turns to drive `ControlAvatar` / `ControlMotion` / `SetEmotion`.
   - **OpenClaw Connection:** Connects to `ws://host.docker.internal:18789` (OpenClaw Gateway RPC WebSocket, authenticated with `OPENCLAW_GATEWAY_TOKEN` from `.env`, zero changes to OpenClaw config!).
   - **Local Audio Pipeline inside Docker:** `faster-whisper` (STT) + `piper-tts` (TTS, offline, fast, zero external API keys) + `ffmpeg` / `opuslib` (`16 kHz` Opus decode → WAV/PCM → Whisper; TTS WAV → `24 kHz` mono `60 ms` Opus frames).
2. **Firmware Updates (`firmware/`):**
   - Add `main/stackchan_config.h` centralizing server URL, XiaoZhi OTA URL, auth token, and optional default Wi-Fi SSID/password.
   - Support both `wss://stackchan.example.com` (with `CONFIG_MBEDTLS_CERTIFICATE_BUNDLE=y` + `CONFIG_MBEDTLS_CERTIFICATE_BUNDLE_DEFAULT_FULL=y` + embedded ISRG Root X1 PEM) and `ws://192.168.1.100:8765` (`ws-lan` variant).
   - Extend `SetEmotion()` for `surprised` & `thinking`, and bypass mandatory mobile-app setup when `stackchan_config.h` provides Wi-Fi credentials.
