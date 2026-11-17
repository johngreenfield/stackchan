/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#include "app_dance.h"
#include <hal/hal.h>
#include <mooncake.h>
#include <mooncake_log.h>
#include <stackchan/stackchan.h>
#include <apps/common/common.h>
#include <assets/assets.h>

using namespace mooncake;
using namespace stackchan;

AppDance::AppDance()
{
    // 配置 App 名
    setAppInfo().name = "DANCE";
    // 配置 App 图标
    static auto icon  = assets::get_image("icon_dance.bin");
    setAppInfo().icon = (void*)&icon;
    // 配置 App 主题颜色
    static uint32_t theme_color = 0xB77BFF;
    setAppInfo().userData       = (void*)&theme_color;
}

// App 被安装时会被调用
void AppDance::onCreate()
{
    mclog::tagInfo(getAppInfo().name, "on create");
}

void AppDance::onOpen()
{
    mclog::tagInfo(getAppInfo().name, "on open");

    // Create loading page
    std::unique_ptr<view::LoadingPage> loading_page;
    {
        LvglLockGuard lock;
        loading_page = std::make_unique<view::LoadingPage>(0xB77BFF, 0x422268);
        loading_page->setMessage("Starting\n BLE server...");
    }

    // Start BLE service
    GetHAL().startBleServer();

    LvglLockGuard lock;

    // Destroy loading page
    loading_page.reset();

    // Create default avatar
    auto avatar = std::make_unique<avatar::DefaultAvatar>();
    avatar->init(lv_screen_active());
    GetStackChan().attachAvatar(std::move(avatar));

    /* ------------------------------- BLE events ------------------------------- */
    GetHAL().onBleAvatarData.connect([&](const char* data) {
        if (!data) return;
        std::lock_guard<std::mutex> lock(_mutex);
        _ble_avatar_queue.emplace(data);
    });

    GetHAL().onBleMotionData.connect([&](const char* data) {
        if (!data) return;
        std::lock_guard<std::mutex> lock(_mutex);
        _ble_motion_queue.emplace(data);
    });

    GetHAL().onBleRgbData.connect([&](const char* data) {
        if (!data) return;
        std::lock_guard<std::mutex> lock(_mutex);
        _ble_rgb_queue.emplace(data);
    });

    /* ----------------------------- Common widgets ----------------------------- */
    view::create_home_indicator([&]() { close(); }, 0xB77BFF, 0x422268);
    view::create_status_bar(0xB77BFF, 0x422268);
}

void AppDance::onRunning()
{
    std::queue<std::string> avatar_msgs;
    std::queue<std::string> motion_msgs;
    std::queue<std::string> rgb_msgs;
    {
        std::lock_guard<std::mutex> lock(_mutex);
        avatar_msgs.swap(_ble_avatar_queue);
        motion_msgs.swap(_ble_motion_queue);
        rgb_msgs.swap(_ble_rgb_queue);
    }

    LvglLockGuard lvgl_lock;

    while (!avatar_msgs.empty()) {
        GetStackChan().updateAvatarFromJson(avatar_msgs.front().c_str());
        avatar_msgs.pop();
    }

    while (!motion_msgs.empty()) {
        check_auto_angle_sync_mode();
        GetStackChan().updateMotionFromJson(motion_msgs.front().c_str());
        motion_msgs.pop();
    }

    while (!rgb_msgs.empty()) {
        GetStackChan().updateNeonLightFromJson(rgb_msgs.front().c_str());
        rgb_msgs.pop();
    }

    GetStackChan().update();

    view::update_home_indicator();
    view::update_status_bar();
}

void AppDance::onClose()
{
    mclog::tagInfo(getAppInfo().name, "on close");

    {
        LvglLockGuard lock;

        GetStackChan().resetAvatar();

        GetHAL().onBleAvatarData.clear();
        GetHAL().onBleMotionData.clear();
        GetHAL().onBleRgbData.clear();

        view::destroy_home_indicator();
        view::destroy_status_bar();
    }

    GetHAL().requestWarmReboot(5);
}

void AppDance::check_auto_angle_sync_mode()
{
    auto& motion = GetStackChan().motion();

    // If far from last command, enable auto angle sync
    if (GetHAL().millis() - _last_motion_cmd_tick > 2000) {
        motion.setAutoAngleSyncEnabled(true);
    } else {
        motion.setAutoAngleSyncEnabled(false);
    }

    _last_motion_cmd_tick = GetHAL().millis();
}
