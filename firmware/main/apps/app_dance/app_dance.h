/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <mooncake.h>
#include <memory>
#include <mutex>
#include <queue>
#include <string>

/**
 * @brief
 *
 */
class AppDance : public mooncake::AppAbility {
public:
    AppDance();

    void onCreate() override;
    void onOpen() override;
    void onRunning() override;
    void onClose() override;

private:
    std::mutex _mutex;

    std::queue<std::string> _ble_avatar_queue;
    std::queue<std::string> _ble_motion_queue;
    std::queue<std::string> _ble_rgb_queue;

    uint32_t _last_motion_cmd_tick = 0;

    void check_auto_angle_sync_mode();
};
