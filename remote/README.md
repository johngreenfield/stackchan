# StackChan-RemoteControl-ESPNow

ESP-NOW wireless remote controller firmware for StackChan (`remote/code/`), targeting **M5StickC Plus** / **M5StickC Plus2** with **Hat Mini JoyC**.

> **Web Remote UI:** A browser-based Stack-chan Remote Control UI is also included in [`server-openclaw/static/index.html`](../server-openclaw/static/index.html) and served by the self-hosted bridge at `/` and `/remote/` (port `8765` / `https://stackchan.example.com/`).

## Hardware Assembly & Pinout

- **Controller:** M5StickC Plus (ESP32) + Hat Mini JoyC
- **Hat Mini JoyC I2C Bus:** `SDA` = `GPIO0`, `SCL` = `GPIO26`, I2C Address = `0x54`

## Usage Instructions

- **Setup Screen (`MODE_SETUP`):**
  - Move the joystick **Up / Down** to change the selected Channel or Receiver ID.
  - Press **BtnB** to switch between Channel and Receiver ID fields.
  - **Click the joystick button** to open/confirm dropdown selections on the Setup screen.
  - Press **BtnA** to cycle between Setup, Running (`MODE_RUNNING`), and IMU (`MODE_IMU`) screens.
- **Running / IMU Screens:**
  - Broadcasts yaw, pitch, and button state over ESP-NOW to the configured Receiver ID (`0` = broadcast).

## Build & Flash Requirements

- **ESP-IDF:** v5.4.x (tested on **v5.4.4**, target `esp32`)
- **Flashing Baud Rate:** Flash at `115200` baud for reliable FTDI FT232R communication:
  ```bash
  cd remote/code
  idf.py build
  idf.py -p PORT -b 115200 flash
  ```

## Firmware Fixes in This Fork

- **I2C Driver Alignment (ESP-IDF v5.4+):** Aligned `M5Unified` (`0.2.29`), `M5GFX` (`0.3.0`), `espressif/i2c_bus` (`1.5.2`), and `joystick_handle` onto `esp_driver_i2c` to resolve startup I2C driver conflicts.
- **ESP-NOW Channel Reinit & Long-Range Mode:** Fixed `wifi_espnow_reinit()` to query the active channel via `esp_wifi_get_channel()` instead of comparing against uninitialized `0`, and re-applied `WIFI_PROTOCOL_LR` when `CONFIG_ESPNOW_ENABLE_LONG_RANGE` is enabled.
- **Non-Blocking ESP-NOW Sends:** Replaced blocking `portMAX_DELAY` and fatal `ESP_ERROR_CHECK` in `espnow_send_data()` with a bounded `pdMS_TO_TICKS(50)` timeout and `ESP_LOGW` error logging.
- **LVGL Thread Safety & Bounded Retries:** Added `lvgl_port_lock()` / `lvgl_port_unlock()` guards around screen transitions in `ui.c`, replaced unbounded `goto` retry loops with a 3-attempt bounded retry, unlocked the mutex on `create_running_screen()` failure, moved `vTaskDelay()` outside the LVGL lock in `ui_setup_screen.c`, and fixed the `"Bat: 100%%"` display typo to `"Bat: 100%"`.

## Credits

Original firmware by M5Stack Technology CO LTD (MIT License).
