# StackChan Mobile App Migration Specification (`app/` → OpenClaw Self-Hosted Bridge)

> **Target Environment:** Flutter (`app/`) edited & built externally in **Antigravity on Windows** (Android / iOS).  
> **Backend Target:** `server-openclaw` (FastAPI bridge on `:8765`, reverse-proxied at `https://stackchan.example.com`).  
> **Scope:** Exact file-by-file changes required to migrate the Flutter app (`StackChan World`) from M5Stack's Go/MySQL cloud + RSA-OAEP + `https://xiaozhi.me/` architecture to the self-hosted OpenClaw bridge, while preserving all BLE Wi-Fi provisioning and `/stackChan/ws` binary avatar/motion/camera capabilities.

---

## 1. Summary of Required Changes

| Area | Upstream Behavior | Target OpenClaw Behavior |
| :--- | :--- | :--- |
| **Server URLs** (`urls.dart`) | `http://api.example.com:8080/stackChan/`, `ws://.../stackChan/ws` | `https://stackchan.example.com/stackChan/`, `wss://stackchan.example.com/stackChan/ws` (with optional LAN fallback `http://192.168.1.100:8765/` / `ws://192.168.1.100:8765/`) |
| **HTTP & Remote WS Auth** (`http.dart`, `web_socket_util.dart`, `rsa_util.dart`, `value_constant.dart`) | RSA-OAEP-SHA256 encrypted `<mac>\|<rand>\|<ts>` using `--dart-define` PEM keys | `Authorization: Bearer <STACKCHAN_BRIDGE_TOKEN>` + `Device-Id: <mac_or_uuid>` |
| **LAN Direct WS Auth** (`local_area_network_service.dart`) | Calls `RsaUtil.decryptStackChanBlue(Authorization)` and parses `<mac>\|<rand>\|<ts>` | Compares `Authorization` (raw or `Bearer <token>`) against `<STACKCHAN_BRIDGE_TOKEN>` (with optional `"<bridge-token>"` LAN fallback) |
| **XiaoZhi Cloud** (`xiao_zhi_util.dart`, `XiaoZhi_util.dart`, UI popups) | Direct REST calls to `https://xiaozhi.me/` / `https://api.xiaozhi.me/` + token proxy via StackChan server | Bypass/disable cloud XiaoZhi activation & agent CRUD (OpenClaw runs the agent in `server-openclaw`), or stub local responses |
| **BLE Provisioning** (`blue_util.dart`, `device_wifi_config.dart`, `select_blue_device.dart`) | Service `e2e5e5ff...` / `e2e5e5e0...`, `0xAA 0x55 0xC3 0x01` fragmentation, JSON `setWifi` / `getWifiStatus` / `handshake`, RSA decrypt of `notifyState` type `4` | Keep BLE UUIDs, fragmentation, and `setWifi` / `getWifiStatus` / `handshake` payloads **unchanged**; replace `RsaUtil.decryptStackChanBlue` in `select_blue_device.dart` with MAC extraction from BLE `manufacturerData` + token check |

---

## 2. File-by-File Migration Instructions

### 2.1 `app/lib/network/urls.dart` — Backend & WebSocket URLs

Update `Urls` to use HTTPS/WSS against `stackchan.example.com`, with a clean compile-time or runtime switch for the LAN fallback (`192.168.1.100:8765`):

```dart
class Urls {
  /// Toggle via --dart-define=STACKCHAN_USE_LAN=true for local-only testing
  static const bool useLanFallback =
      bool.fromEnvironment('STACKCHAN_USE_LAN', defaultValue: false);

  static const String publicHost = "stackchan.example.com/";
  static const String lanHost = "192.168.1.100:8765/";

  static String get url => useLanFallback ? lanHost : publicHost;
  static String get _httpScheme => useLanFallback ? "http" : "https";
  static String get _wsScheme => useLanFallback ? "ws" : "wss";

  /// Returns:
  /// - Public: `https://stackchan.example.com/stackChan/`
  /// - LAN:    `http://192.168.1.100:8765/stackChan/`
  static String getBaseUrl() {
    return "$_httpScheme://$url"
        "stackChan/";
  }

  /// Returns:
  /// - Public: `https://stackchan.example.com/`
  /// - LAN:    `http://192.168.1.100:8765/`
  static String getFileUrl() {
    return "$_httpScheme://$url";
  }

  /// Returns:
  /// - Public: `wss://stackchan.example.com/stackChan/ws`
  /// - LAN:    `ws://192.168.1.100:8765/stackChan/ws`
  static String getWebSocketUrl() {
    return "$_wsScheme://$url"
        "stackChan/ws";
  }
  // ... keep existing endpoint path constants ...
}
```

> **Note on runtime LAN fallback:** If you want automatic runtime fallback when off-LAN vs on-LAN (instead of `--dart-define=STACKCHAN_USE_LAN=true`), keep `publicHost` as the default and add a settings toggle in `SharedPreferencesAsync` that overrides `Urls.getBaseUrl()` / `Urls.getWebSocketUrl()` and re-initializes `Http.instance` Dio `baseUrl`.

---

### 2.2 `app/lib/util/value_constant.dart` — Replace RSA Keys with Bridge Token

1. **Remove** the three RSA PEM `--dart-define` constants (lines ~255–307):
   - `serverPublicKey` (`SERVER_PUBLIC_KEY`)
   - `clientPrivateKey` (`CLIENT_PRIVATE_KEY`)
   - `stackChanBluePrivateKey` (`STACKCHAN_BLE_PRIVATE_KEY`)
2. **Add** the bridge token constant & `Device-Id` header key:

```dart
  /// Header key for device MAC / client UUID identification
  static const String deviceIdHeader = "Device-Id";

  /// Shared bridge auth token (matches STACKCHAN_BRIDGE_TOKEN in server-openclaw/.env).
  /// Pass at build time:
  ///   flutter run --dart-define=STACKCHAN_BRIDGE_TOKEN=<your-token>
  static const String bridgeToken =
      String.fromEnvironment('STACKCHAN_BRIDGE_TOKEN', defaultValue: '');
```

> **Security:** Never hardcode the production `STACKCHAN_BRIDGE_TOKEN` in committed Dart source files. Inject it via `--dart-define=STACKCHAN_BRIDGE_TOKEN=...` in Windows/Antigravity launch configs, or enter it once in an in-app Settings screen persisted to `SharedPreferencesAsync`.

---

### 2.3 `app/lib/util/rsa_util.dart` — Remove Static RSA Key Parsing

Currently `RsaUtil._encrypter` parses `ValueConstant.serverPublicKey` and `ValueConstant.clientPrivateKey` in a `static final` initializer (`app/lib/util/rsa_util.dart:11-19`), which **throws a `FormatException` on first access** whenever `--dart-define` RSA PEMs are omitted.

Replace `rsa_util.dart` (or guard its methods) so no RSA PEM parsing occurs:

```dart
class RsaUtil {
  static String encrypt(String plainText) => plainText;
  static String decrypt(String cipherText) => cipherText;
  static String decryptStackChanBlue(String cipherText) => cipherText;
}
```

Once `http.dart`, `web_socket_util.dart`, `local_area_network_service.dart`, and `select_blue_device.dart` are updated as described below, `encrypt` / `pointycastle` imports in `rsa_util.dart` are no longer needed and can be removed cleanly.

---

### 2.4 `app/lib/network/http.dart` — Bearer Token + `Device-Id` Auth

In `Http._interceptors` (`app/lib/network/http.dart:44-76`):

1. Remove `import '../util/rsa_util.dart';` and `import 'package:stack_chan/network/web_socket_util.dart';` (no longer needed).
2. Replace the `onRequest` RSA logic with `Bearer` token + `Device-Id`:

```dart
      onRequest: (RequestOptions options, RequestInterceptorHandler handler) async {
        // Bridge Bearer token (from --dart-define or SharedPreferences)
        final savedBridgeToken = await AppState.asyncPrefs.getString(
          ValueConstant.token,
        );
        final bearer = (savedBridgeToken != null && savedBridgeToken.isNotEmpty)
            ? savedBridgeToken
            : ValueConstant.bridgeToken;

        if (bearer.isNotEmpty) {
          options.headers[ValueConstant.authorization] = 'Bearer $bearer';
        }

        // Device-Id header expected by server-openclaw
        final devId = AppState.shared.deviceMac.isNotEmpty
            ? AppState.shared.deviceMac
            : AppState.shared.deviceId;
        if (devId.isNotEmpty) {
          options.headers[ValueConstant.deviceIdHeader] = devId;
        }

        String? version = AppState.shared.packageInfo?.version;
        if (version != null) {
          options.headers[ValueConstant.appVersion] = version;
        }
        return handler.next(options);
      },
```

3. **Keep** `BaseOptions(baseUrl: Urls.getBaseUrl(), ...)` (now `https://stackchan.example.com/stackChan/`).
4. **401 Handling Caution:** `onResponse` / `onError` currently calls `await AppState.shared.logout()` on any `401`. Only trigger `logout()` if you keep multi-user login enabled; in single-user self-hosted mode, show a toast instructing the user to check `STACKCHAN_BRIDGE_TOKEN` rather than clearing `deviceMac`.

---

### 2.5 `app/lib/network/web_socket_util.dart` — Remote `/stackChan/ws` Auth

In `WebSocketUtil.connect(String urlString)` (`app/lib/network/web_socket_util.dart:54-80`):

1. Remove `import '../util/rsa_util.dart';`.
2. Note: `AppState.connectWebSocket()` (`app/lib/app_state.dart:330-334`) builds:
   ```
   wss://stackchan.example.com/stackChan/ws?deviceType=App&deviceId=<uuid>
   ```
   Wait: check `WebSocketUtil.connect()` lines 64–67:
   ```dart
   if (AppState.shared.deviceMac.isEmpty) {
     debugPrint(' WebSocket ConnectFailed:DeviceMACAddressIs null/empty');
     return;
   }
   ```
   If operating without cloud device binding (or before BLE binding), either pre-seed `deviceMac` or fall back to `AppState.shared.deviceId` so `/stackChan/ws` can still connect as `deviceType=App`.
3. Replace lines 73–76:
   ```dart
   final savedToken = await AppState.asyncPrefs.getString(ValueConstant.token);
   final bearer = (savedToken != null && savedToken.isNotEmpty)
       ? savedToken
       : ValueConstant.bridgeToken;

   final headers = <String, dynamic>{
     if (bearer.isNotEmpty) ValueConstant.authorization: 'Bearer $bearer',
     ValueConstant.deviceIdHeader: AppState.shared.deviceMac.isNotEmpty
         ? AppState.shared.deviceMac
         : AppState.shared.deviceId,
   };
   _socket = await WebSocket.connect(urlString, headers: headers);
   ```
   This matches `server-openclaw/app/config.py:is_authorized()` and `server-openclaw/app/main.py:stackchan_websocket()`.

---

### 2.6 `app/lib/network/local_area_network_service.dart` — Firmware-to-App LAN WebSocket Auth

How LAN direct mode works in the firmware (`firmware/main/hal/hal_ws_avatar.cpp:104-106` & `firmware/main/hal/utils/local_network/local_avatar_client.cpp:169-181`):
- The phone binds an ephemeral `HttpServer` (`ws://<phone-lan-ip>:<port>/ws`) and sends `AppLanAddress` (`0x1B`) over `/stackChan/ws`.
- The firmware connects directly to `ws://<phone-lan-ip>:<port>/ws` with header:
  ```
  Authorization: <STACKCHAN_AUTH_TOKEN>
  ```
  (where `secret_logic::generate_handshake_token("stackchan-lan-v1")` returns `STACKCHAN_AUTH_TOKEN`, or `"<bridge-token>"` if empty — **plaintext**, NOT RSA-encrypted `<mac>|<rand>|<ts>`).

Update `LocalAreaNetworkService._handleRequest()` (`app/lib/network/local_area_network_service.dart:356-411`):

1. Remove `RsaUtil.decryptStackChanBlue` from constructor (`LocalAreaNetworkService._()`).
2. Replace lines 373–391 (RSA decryption + `|` field splitting) with bridge token validation:

```dart
      final authorization = request.headers.value(
        HttpHeaders.authorizationHeader,
      )?.trim();

      String? provided = authorization;
      if (provided != null && provided.toLowerCase().startsWith('bearer ')) {
        provided = provided.substring(7).trim();
      }

      const expected = ValueConstant.bridgeToken;
      final bool tokenValid = expected.isEmpty
          ? (provided != null && provided.isNotEmpty)
          : (provided == expected || provided == '<bridge-token>');

      if (!tokenValid) {
        debugPrint('LAN WebSocket rejected status=401 target=$_runningTarget');
        await _reject(request, HttpStatus.unauthorized);
        return;
      }
```
3. Pass `provided ?? ''` as `key` to `_handleData(socket, data, key)`. Keep the 20-byte `'S','C',1` binary framing (`LocalAreaNetworkMessage`) completely untouched.

---

### 2.7 `app/lib/util/xiao_zhi_util.dart` & `app/lib/util/XiaoZhi_util.dart` — Replacing/Bypassing `https://xiaozhi.me/`

The upstream repo contains **two** nearly identical files (`xiao_zhi_util.dart` is the one imported by all active UI pages; `XiaoZhi_util.dart` is an unused/legacy uppercase duplicate referencing `https://XiaoZhi.me/` and `https://api.XiaoZhi.me/`).

**Active callers of `xiao_zhi_util.dart`:**
- `app/lib/view/popup/xiaozhi_welcome_page.dart` (setup wizard / agent config)
- `app/lib/view/popup/agent_configuration.dart` (agent template & device bind)
- `app/lib/view/popup/edit_agent.dart` (LLM/TTS/MCP agent editor)
- `app/lib/view/home/mcp_page.dart` (hardcodes `"wss://api.xiaozhi.me/mcp/?token=..."` at lines 290, 299, 309)
- `app/lib/view/home/conversation_page.dart` & `app/lib/view/popup/conversation_message_page.dart`

**Recommended Migration (Self-Hosted OpenClaw Mode):**
Because `server-openclaw` runs the OpenClaw Gateway RPC, `faster-whisper` STT, and `piper-tts` directly on the bridge (without `xiaozhi.me` accounts, device binding codes, or external MCP token brokers):

1. **Delete or archive `app/lib/util/XiaoZhi_util.dart`** (after verifying nothing imports it; current codebase imports `xiao_zhi_util.dart` everywhere).
2. **In `app/lib/util/xiao_zhi_util.dart`:**
   - Replace `_dio.options.baseUrl = "https://xiaozhi.me/";` (line 33) with `Urls.getFileUrl()` (`https://stackchan.example.com/`, or `http://192.168.1.100:8765/`).
   - Remove `_xiaozhiBaseHost = "api.xiaozhi.me"` (line 133) and `https://$_xiaozhiBaseHost/mcp/endpoints/list` (line 521).
   - Replace `getToken()` / `getTokenFromServer()` / `refreshXiaoZhiToken()` (lines 135–169) so they return `ValueConstant.bridgeToken` (no calls to `Urls.xiaozhiToken` / `Urls.xiaozhiTokenRefresh`).
   - Stub cloud-only agent management methods cleanly so existing UI pages degrade gracefully instead of failing against `xiaozhi.me`:
     - `getDevice(mac)` → returns `[Device(deviceId: mac, macAddress: mac, agentId: 1)]`
     - `getAgentDetail(1)` → returns a read-only OpenClaw stub `Agent(id: 1, agentName: "OpenClaw")`
     - `agentTemplatesList`, `getTtsList`, `getModelList`, `getCommonMcpTool`, `mcpEndpoints`, `endpointsList`, `getConversationList`, `getChatsMessages` → return empty lists / `null`
     - `bindDeviceToAgent`, `updateAgent`, `createAgent` → return `true` / `1` (no-op)
3. **In `app/lib/view/home/settings.dart` & `app/lib/view/home/mcp_page.dart`:**
   - Either hide or label the `"AI Agent Config"`, `"MCP"`, and `"Chat History"` tiles in `settings.dart:431-485` as managed by OpenClaw (`https://stackchan.example.com/`), and remove the hardcoded `wss://api.xiaozhi.me/mcp/?token=...` string in `mcp_page.dart:290-311`.

---

### 2.8 BLE Provisioning (`blue_util.dart`, `device_wifi_config.dart`, `select_blue_device.dart`)

#### What MUST Stay Intact (Firmware `hal_ble.cpp` & `bleprph.h` Compatibility)
Do **NOT** change any of the following in `app/lib/util/blue_util.dart` or `app/lib/view/popup/device_wifi_config.dart`:

- **GATT Service UUIDs:**
  - Normal / Dance mode: `e2e5e5e0-1234-5678-1234-56789abcdef0` (`BlueUtil.danceTargetServiceUUID`)
  - Setup / Wi-Fi pairing mode: `e2e5e5ff-1234-5678-1234-56789abcdef0` (`BlueUtil.targetServiceUUID`)
- **GATT Characteristic UUIDs:**
  - Motion (`writeMotionCharacteristic`): `e2e5e5e1-1234-5678-1234-56789abcdef0`
  - Avatar (`writeAvatarCharacteristic`): `e2e5e5e2-1234-5678-1234-56789abcdef0`
  - Config / Wi-Fi / Handshake (`writeWifiSetCharacteristic`, Write + Notify): `e2e5e5e3-1234-5678-1234-56789abcdef0`
  - RGB (`writeRGBCharacteristic`): `e2e5e5e4-1234-5678-1234-56789abcdef0`
  - Legacy BLE characteristics (`headCharacteristicUUID = 0000ffe1...`, `expressionCharacteristicUUID = 0000ffe3...`, `writeCharacteristicUUID = 0000ffe4...`)
- **Fragmentation Header (`blue_util.dart:59-64` & `hal_ble.cpp`):**
  - 10-byte header: `[0xAA, 0x55, 0xC3, 0x01, pkt_idx_hi, pkt_idx_lo, total_pkts_hi, total_pkts_lo, total_len_hi, total_len_lo]`
  - Negotiated MTU payload (`_requestedBleMtu = 247`, ATT overhead `3`, max chunk payload `mtuPayload - 10`).
- **Config JSON Payloads on `e2e5e5e3...`:**
  - `setWifi` (`device_wifi_config.dart:515-522`):
    ```json
    {
      "cmd": "setWifi",
      "data": {
        "ssid": "<ssid>",
        "password": "<password>",
        "currentNetwork": true,
        "frequency": 2412
      }
    }
    ```
  - `getWifiStatus`:
    ```json
    {"cmd": "getWifiStatus"}
    ```
  - `handshake` (`select_blue_device.dart:609-612`):
    ```json
    {"cmd": "handshake", "data": "<unix_ms>"}
    ```
  - Firmware `notifyState` responses (`hal_ble.cpp:536-560`):
    - `type: 0` → `wifiConnecting`
    - `type: 1` → `wifiConnected`
    - `type: 2` → `wifiConnectFailed` (with optional `errorCode`, `errorMessage`, `reason`, `sdkError`, `ssid`)
    - `type: 3` → `wifiDisconnected`
    - `type: 4` → handshake token (`state` = output of `secret_logic::generate_handshake_token`)

#### Required Change in `app/lib/view/popup/select_blue_device.dart` (`stackChanBluePrivateKey` Removal)
In upstream firmware, `secret_logic::generate_handshake_token()` returned an RSA-encrypted string starting with the 12-hex-char device MAC, which `select_blue_device.dart:351` decrypted with `RsaUtil.decryptStackChanBlue(data)`.

In our OpenClaw firmware (`firmware/main/hal/utils/secret_logic/secret_logic.cpp:26-30`), `generate_handshake_token()` returns `STACKCHAN_AUTH_TOKEN` (plaintext bridge token, or `"<bridge-token>"`). Calling `RsaUtil.decryptStackChanBlue(data)` will fail!

**Fix in `app/lib/view/popup/select_blue_device.dart`:**
1. Store the tapped `BlueDeviceInfo` (e.g., `_selectedDeviceInfo = deviceInfo;`) when the user selects a device in the list (`select_blue_device.dart:466`).
2. In `_handleNotification` when `model.cmd == "notifyState" && model.data?.type == 4` (around lines 336–375):
   - Remove `RsaUtil.decryptStackChanBlue(data)`.
   - Verify `data` is non-empty (and if `ValueConstant.bridgeToken` is configured, optionally accept `data == ValueConstant.bridgeToken || data == "<bridge-token>"`).
   - Extract the 12-hex-character MAC address from `_selectedDeviceInfo` using `_getDeviceId(_selectedDeviceInfo)` (already implemented at `select_blue_device.dart:49-60` from BLE `manufacturerData`, identical to `BlueUtil._getDeviceId`), or fall back to regex-matching a 12-hex-char MAC if present in `data`, or `deviceRemoteId`.
   - Call `await _activateAndBindDevice(macAddress);` as before.

---

### 2.9 `app/lib/app_state.dart` — Single-User Self-Hosted Flow (Optional Login Bypass)

Upstream gates device binding, BLE Wi-Fi auto-connect, and home tabs behind `AppState.shared.isLogin.value` (`app_state.dart:102`, `stack_chan.dart:37`, `settings.dart:40`, `blue_util.dart:565`).

Choose **one** of the two options below:
- **Option A (Recommended for single-user OpenClaw):** In `AppState.initData()` (`app/lib/app_state.dart:95-125`), default `isLogin.value = true;` whenever `ValueConstant.bridgeToken.isNotEmpty` (or unconditionally in self-hosted builds), and skip `Urls.user` / `Urls.login` unless the user explicitly opens profile settings. Also allow `WebSocketUtil.connect()` to use `deviceId` if `deviceMac` is not yet bound.
- **Option B (Keep Login/Device UI screens functional):** Implement the minimal `/stackChan/v2/*` endpoints in `server-openclaw/app/main.py` listed in Section 3 below.

---

## 3. Optional Additional Endpoints in `server-openclaw/`

`server-openclaw/app/main.py` **already implements** all core firmware & control endpoints:
- `GET /health`, `GET /`, `GET /remote/`
- `GET/POST /xiaozhi/ota/` & `/xiaozhi/ota`
- `WS /xiaozhi/ws`
- `WS /stackChan/ws` (`deviceType=StackChan` | `App` | `WebRemote`)
- `GET /stackChan/device/user`
- `GET /stackChan/device/info`
- `POST /stackChan/device/unbind`
- `GET /stackChan/apps`
- `GET /api/status`, `POST /api/chat`, `POST /api/motion`, `POST /api/avatar`, `POST /api/led`, `POST /api/camera/start`, `POST /api/camera/stop`, `GET /api/camera/latest.jpg`

If you choose **Option B** (keeping the Flutter app's upstream Login, Account, Device List, Binding, and Dance Library screens active without bypassing them), add these lightweight JSON endpoints to `server-openclaw/app/main.py` (all protected by `_check_http_auth(request)`, returning the `{"code": 0, "message": "ok", "data": ...}` envelope expected by `app/lib/model/model.dart`):

| Method & Path | Called By | Expected Response `data` |
| :--- | :--- | :--- |
| `POST /stackChan/v2/user/login` | `login_page.dart:101` (`Urls.login`) | `{"token": "<STACKCHAN_BRIDGE_TOKEN>"}` |
| `POST /stackChan/v2/user/registration` | `registration_page.dart:75` (`Urls.registration`) | `{"token": "<STACKCHAN_BRIDGE_TOKEN>"}` (or `403` if closed) |
| `GET /stackChan/v2/user` | `app_state.dart:229` (`Urls.user`) | `{"uid": 1, "username": "OpenClaw", "displayName": "OpenClaw"}` |
| `GET /stackChan/v2/devices` | `app_state.dart:471` (`Urls.devices`) | `[{"mac": "<bound_mac>", "name": "Stack-chan", "uid": 1}]` |
| `POST /stackChan/v2/device/activate_bind` | `app_state.dart:508` (`Urls.v2deviceActivateBind`) | `true` (persists `mac` in `/app/data/devices.json`) |
| `POST /stackChan/v2/device/unbind` | `app_state.dart:528` (`Urls.v2deviceUnbind`) | `true` (removes `mac` from `/app/data/devices.json`) |
| `PUT /stackChan/device/info` | `app_state.dart:366` (`Urls.deviceInfo`) | `"ok"` (updates `avatar_hub.device_name` from body `name`) |
| `GET /stackChan/dance` & `GET/POST/PUT/DELETE /stackChan/v2/dance` | `dance.dart:77,92`, `dance_list_page.dart:596,769,781` | `[]` / saved dance JSON list (only if mobile Dance Editor is used) |
| `POST /stackChan/uploadFile` | `add_music.dart:133` (`Urls.uploadFile`) | `{"path": "static/uploads/<uuid>.mp3"}` (only if custom MP3 upload is used) |

---

## 4. Android & iOS Network Security Notes

### Android (`app/android/app/src/main/AndroidManifest.xml`)
- Already sets `android:usesCleartextTraffic="true"`, which permits:
  - LAN fallback to `http://192.168.1.100:8765/` and `ws://192.168.1.100:8765/`
  - Firmware-to-phone LAN WebSocket (`ws://<phone-ip>:<port>/ws`)
- Already declares `INTERNET`, `ACCESS_NETWORK_STATE`, `ACCESS_WIFI_STATE`, `CHANGE_WIFI_STATE`, `RECORD_AUDIO`, `MODIFY_AUDIO_SETTINGS`, `BLUETOOTH_SCAN`, `BLUETOOTH_CONNECT`, `ACCESS_FINE_LOCATION`.
- **Hardening Recommendation (Optional):** Before distributing release APKs, replace global `usesCleartextTraffic="true"` with `android:networkSecurityConfig="@xml/network_security_config"` that enforces HTTPS/WSS for `stackchan.example.com` and permits cleartext only for `192.168.0.0/16` / `10.0.0.0/8` / `127.0.0.1`.

### iOS (`app/ios/Runner/Info.plist`)
- Already sets `NSAppTransportSecurity -> NSAllowsArbitraryLoads = true`, `NSBluetoothAlwaysUsageDescription`, `NSBluetoothPeripheralUsageDescription`, `NSLocationWhenInUseUsageDescription`, `NSMicrophoneUsageDescription`, `NSCameraUsageDescription`.
- **Required for iOS 14+ LAN Direct Mode (`LocalAreaNetworkService` & `192.168.1.100:8765`):** Add `NSLocalNetworkUsageDescription` so iOS presents the Local Network permission prompt instead of silently dropping local socket traffic:
  ```xml
  <key>NSLocalNetworkUsageDescription</key>
  <string>StackChan uses the local network to connect directly to your Stack-chan robot for low-latency avatar, motion, and camera streaming.</string>
  ```

---

## 5. Windows / Antigravity Verification Checklist

1. Build/run with bridge token injected (never committed):
   ```powershell
   flutter pub get
   flutter run --dart-define=STACKCHAN_BRIDGE_TOKEN=<STACKCHAN_BRIDGE_TOKEN>
   ```
   For LAN-only testing:
   ```powershell
   flutter run --dart-define=STACKCHAN_USE_LAN=true --dart-define=STACKCHAN_BRIDGE_TOKEN=<STACKCHAN_BRIDGE_TOKEN>
   ```
2. Verify `/stackChan/ws` connects to `wss://stackchan.example.com/stackChan/ws?deviceType=App&deviceId=<uuid>` and `server-openclaw` logs `Remote client connected`.
3. Verify BLE scan discovers `e2e5e5ff-1234-5678-1234-56789abcdef0`, `handshake` + `setWifi` work without RSA errors, and servo/avatar controls drive Stack-chan over both `/stackChan/ws` and LAN `LocalAreaNetworkService`.
