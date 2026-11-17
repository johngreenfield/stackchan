# StackChan CoreS3 Firmware

ESP32-S3 firmware for the M5Stack CoreS3 + StackChan robot body, adapted for self-hosted OpenClaw bridge deployments.

## Hardware Specs

- **Controller:** M5Stack CoreS3 (ESP32-S3 dual-core 240 MHz, 16MB Flash, 8MB PSRAM, Wi-Fi, BLE, 2.0" touch display, 0.3MP camera, 9-axis IMU, speaker, dual microphones)
- **Robot Body:** Pan/tilt feedback servos, 12 RGB LEDs, IR TX/RX, 3-zone head touch panel, NFC module, 550 mAh battery

## Build Requirements

- **ESP-IDF:** v6.1.x (tested on **v6.1.1**)
- **Windows Git Line Endings:** Before fetching dependencies on Windows, ensure LF line endings are preserved so upstream patches apply cleanly:
  ```bash
  git config core.autocrlf false
  ```

### 1. Fetch & Patch Dependencies

```bash
python fetch_repos.py
```

### 2. Configure Self-Hosted Server & Secrets

1. Copy `main/stackchan_config.h.example` to `main/stackchan_config.h` (gitignored) and set your self-hosted bridge URLs (`https://stackchan.example.com` or `http://192.168.1.100:8765`).
2. Create `sdkconfig.defaults.local` (gitignored) to override Kconfig defaults without modifying tracked files:
   ```ini
   CONFIG_STACKCHAN_USE_WSS=y
   CONFIG_STACKCHAN_SERVER_URL="https://stackchan.example.com"
   CONFIG_OTA_URL="https://stackchan.example.com/xiaozhi/ota/"
   CONFIG_STACKCHAN_AUTH_TOKEN="your-stackchan-bridge-token"
   ```

### 3. Build & Flash

```bash
idf.py build
idf.py -p PORT flash
```

### Host-Side Tests

The motion coordinate helpers can be tested without ESP-IDF hardware:

```bash
cmake -S tests -B build-host-tests
cmake --build build-host-tests
ctest --test-dir build-host-tests --output-on-failure
```

## Fork Changes & Fixes

- **Removed Cloud Bloat:** Removed `APP.CENTER` ("App Store") and `EZDATA` launcher registrations from `main/main.cpp`, `main/apps/apps.h`, and `main/hal/hal_toggles.h`.
- **Removed Insecure Fallback Token:** Removed the `"hi-stack-chan"` fallback from `secret_logic::generate_auth_token()` (returns `""` with a warning log when `STACKCHAN_AUTH_TOKEN` is unset).
- **WebSocket Heartbeat & Shutdown Stability:** `WebSocketAvatar::update()` now closes the stale socket and triggers reconnection on >10s heartbeat timeout; `stopRemoteTask()` closes `_websocket` before waiting with a bounded 3s timeout (`pdMS_TO_TICKS(3000)`) to avoid Task Watchdog trips.
- **BLE & Cross-Task Thread Safety:** Replaced shared `const char*` BLE payload caches with mutex-protected `std::queue<std::string>` in `AppAvatar` and `AppDance`, fixed BLE battery reporting to return `GetHAL().getBatteryLevel()`, cleared missing signals on `onClose()`, and converted modifier event flags (`head_pet.h`, `imu.h`) to `std::atomic<bool>`.

## Credits

Based on the upstream open-source StackChan firmware by M5Stack Technology CO LTD and the StackChan community (Shinya Ishikawa / `@stack_chan`, Takao Akaki / `@mongonta555`).
