# StackChan App

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Flutter](https://img.shields.io/badge/Flutter-3.0+-blue.svg)](https://flutter.dev/)
[![Dart](https://img.shields.io/badge/Dart-3.0+-blue.svg)](https://dart.dev/)

A Flutter companion application for controlling and interacting with the StackChan AI robot companion over a self-hosted OpenClaw bridge or local LAN WebSocket.

## Features

- 🤖 **Bluetooth Device Management** - Provision Wi-Fi and control StackChan robots via BLE
- 💬 **Self-Hosted OpenClaw Bridge** - Connect over HTTPS/WSS or local LAN HTTP/WS with bearer token authentication
- 🎭 **Facial Expression Rendering** - Real-time 3D face animation using Three.js
- 🎵 **Music & Dance** - Create and play dance choreographies with music
- 📷 **Camera Integration** - Live camera streaming and face detection

## System Requirements

- **Flutter SDK**: 3.0+
- **Dart SDK**: 3.0+
- **iOS**: 14.0+ (for iOS deployment)
- **Android**: API 21+ (for Android deployment)
- **macOS**: 11.0+ (for macOS deployment)

## Installation & Configuration

### 1. Install Dependencies

```bash
cd app
flutter pub get
```

### 2. Configure Self-Hosted Bridge URL & Token

This fork removes hardcoded personal domains, LAN IPs, and legacy XiaoZhi cloud onboarding screens.

- **Runtime Configuration (Recommended):**
  During device onboarding (`DeviceNamePage` -> **Server & Bridge**) or from **Settings -> Server & Bridge Config**, enter:
  - **Public Server Host / URL** (e.g., `stackchan.example.com`)
  - **LAN Server Host / URL** (e.g., `192.168.1.100:8765`) and **Use LAN Server** toggle
  - **Bridge Token** (matches `STACKCHAN_BRIDGE_TOKEN` in `server-openclaw/.env`)
  Values are persisted via `SharedPreferencesAsync` and update `Urls` and `Http` dynamically.

- **Compile-Time Defaults (`--dart-define`):**
  You can also bake default values into a build:
  ```bash
  flutter run \
    --dart-define=STACKCHAN_PUBLIC_HOST=stackchan.example.com \
    --dart-define=STACKCHAN_LAN_HOST=192.168.1.100:8765 \
    --dart-define=STACKCHAN_USE_LAN=false \
    --dart-define=STACKCHAN_BRIDGE_TOKEN=your-bridge-token
  ```

> **Security Note:** The legacy `"hi-stack-chan"` fallback token has been removed from both LAN WebSocket auth and BLE pairing handshakes. Ensure `STACKCHAN_BRIDGE_TOKEN` matches between `server-openclaw`, `firmware`, and the app when token auth is enabled.

## Building & Verification

```bash
# Static analysis
flutter analyze --no-pub

# Run on Android / iOS
flutter run -d android
flutter run -d ios
```

For Android release signing, configure `android/key.properties` and `android/app/release.jks` (both gitignored).

## License & Acknowledgments

The source code authored by M5Stack Technology CO LTD is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
Bundled assets and third-party dependencies may be covered by separate terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

- M5Stack Technology CO LTD for the StackChan hardware and upstream Flutter app
- Flutter team, Three.js, and all open-source contributors
