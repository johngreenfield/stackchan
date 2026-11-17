# StackChan Open-Source (Self-Hosted OpenClaw Fork)

<img src="https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1205/K151_stack_chan_main_pictures_01.webp" width="60%">

Open-source StackChan desktop robot ecosystem—including the ESP32-S3 CoreS3 firmware, self-hosted OpenClaw FastAPI/WebSocket bridge, M5StickC Plus / Plus2 ESP-NOW remote firmware, and Flutter companion mobile app.

----

<img src="https://cdn.shopify.com/s/files/1/0056/7689/2250/files/5a589623895f65487717894d9240f6b8.png" width="60%">

**StackChan is a super kawaii AI desktop robot co-created by M5Stack and the user community.** It uses the M5Stack **flagship IoT development kit [CoreS3](https://docs.m5stack.com/en/core/CoreS3)** as its main controller, powered by an ESP32-S3 SoC featuring a 240 MHz dual-core processor, with 16MB Flash and 8MB PSRAM onboard, and supporting Wi-Fi and BLE. The main unit also integrates a 2.0-inch capacitive touch display with a high-strength glass cover, a 0.3 MP camera, a proximity & ambient light sensor, a 9-axis IMU (accelerometer + gyroscope + magnetometer), a microSD card slot, a 1W speaker, dual microphones, and power/reset buttons.

The **robot body**, connected to the main unit, includes a USB-C interface for power and data, a 550 mAh battery, two feedback servos (360-degree continuous rotation on the horizontal axis and 90-degree movement on the vertical axis), two rows totaling 12 RGB LEDs, infrared transmitter and receiver, a three-zone touch panel, and a full-featured NFC module.

> ⚠️ Do not forcibly rotate any movable parts connected to the motors by hand when you are unsure whether the motors are powered and under control, as this may cause hardware damage.

## Fork Overview

This fork replaces proprietary M5Stack / XiaoZhi cloud dependencies with a **self-hosted OpenClaw bridge**, hardens the **ESP32-S3 CoreS3 firmware**, updates the **Flutter mobile app** for self-hosted deployments, and stabilizes the **M5StickC Plus / Plus2 ESP-NOW remote**.

### Added Features
- **Self-Hosted OpenClaw Bridge (`server-openclaw/`):** Python/FastAPI bridge providing Whisper STT, Piper TTS, XiaoZhi WebSocket (`/xiaozhi/ws`), Avatar/Remote WebSocket (`/stackChan/ws`), and a built-in Web Remote UI (`/`, `/remote/`).
- **Bearer Token Authentication:** Unified `STACKCHAN_BRIDGE_TOKEN` / `STACKCHAN_AUTH_TOKEN` bearer authentication across HTTP, WebSocket, and BLE pairing handshakes, plus `TRUST_PROXY_HEADERS` gating for reverse-proxied deployments.
- **WSS / HTTPS & Local Kconfig Overlays:** TLS support via `CONFIG_STACKCHAN_USE_WSS` and gitignored local secret overlays (`firmware/sdkconfig.defaults.local` and `firmware/main/stackchan_config.h`).
- **In-App Server & Bridge Setup:** Runtime configuration screen in the Flutter app for Public Server Host, LAN Server Host, LAN mode toggle, and Bridge Token.

### Removed Features
- **Proprietary Cloud Dependencies:** Disabled/removed M5Stack cloud telemetry (`EZDATA`), online `APP.CENTER` ("App Store"), and legacy XiaoZhi cloud onboarding/LLM configuration screens.
- **Insecure Fallback Tokens:** Removed all hardcoded `"hi-stack-chan"` fallback tokens and empty-token auth bypasses across firmware, bridge, and mobile app.

### Key Fixes
- **Heartbeat & Reconnection Stability:** Fixed CoreS3 WebSocket heartbeat timeout recovery, added bounded shutdown timeouts (`pdMS_TO_TICKS(3000)`) to prevent Task Watchdog trips, added 4-second bridge keepalive pings, and added single-flight exponential backoff in the Flutter WebSocket/BLE clients.
- **Thread Safety & Memory Cleanup:** Replaced unsafe BLE raw `const char*` payload caches with mutex-protected `std::queue<std::string>`, converted cross-task modifier flags to `std::atomic<bool>`, and fixed `cv.Mat` / stream subscription / `TextEditingController` leaks in the Flutter app.
- **Remote Firmware & Driver Alignment:** Aligned `M5Unified`, `M5GFX`, `espressif/i2c_bus`, and `joystick_handle` onto `esp_driver_i2c`; fixed `wifi_espnow_reinit()` channel detection and Long-Range re-apply; replaced blocking `portMAX_DELAY` + fatal `ESP_ERROR_CHECK` ESP-NOW sends with a 50ms timeout; added `lvgl_port_lock()/unlock()` guards and bounded screen-switch retries.

## Quick-Start Map

| Component | Path | Description |
| --- | --- | --- |
| **CoreS3 Firmware** | [`firmware/`](firmware/README.md) | ESP-IDF v6.1.x firmware for M5Stack CoreS3 + StackChan body |
| **OpenClaw Bridge** | [`server-openclaw/`](server-openclaw/README.md) | Self-hosted Python/FastAPI bridge, STT/TTS pipeline, and Web Remote UI |
| **Joystick Remote** | [`remote/`](remote/README.md) | ESP-IDF v5.4.x ESP-NOW remote firmware for M5StickC Plus / Hat Mini JoyC |
| **Mobile App** | [`app/`](app/README.md) | Flutter iOS/Android companion app |
| **Architecture Spec** | [`ARCHITECTURE_SPEC.md`](ARCHITECTURE_SPEC.md) | System architecture and protocol specification |
| **App Migration Spec** | [`APP_MIGRATION_SPEC.md`](APP_MIGRATION_SPEC.md) | Flutter app self-hosted migration notes |

## Upstream Resources & Credits

- Purchase link: [M5Stack Official Store](https://shop.m5stack.com/products/stackchan-kawaii-co-created-open-source-ai-desktop-robot) | [淘宝 Taobao](https://item.taobao.com/item.htm?id=1042238294510)
- Product document page: [English](https://docs.m5stack.com/en/StackChan) | [日本語](https://docs.m5stack.com/ja/StackChan) | [中文](https://docs.m5stack.com/zh_CN/StackChan)
- Board support package: https://github.com/m5stack/StackChan-BSP

Thank you to M5Stack and the contributors of the StackChan community, especially:

| ![](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1205/avatar_stack_chan.jpg) | ![](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1205/avatar_takao.jpg) |
| -------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| [@stack_chan](https://x.com/stack_chan)                                          | [@mongonta555](https://x.com/mongonta555)                                   |
| Shinya Ishikawa                                                                  | Takao Akaki                                                                 |
