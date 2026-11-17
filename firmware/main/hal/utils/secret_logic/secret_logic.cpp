/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#include "secret_logic.h"
#include "stackchan_config.h"
#include <esp_log.h>
#include <sdkconfig.h>

namespace secret_logic {

__attribute__((weak)) std::string get_server_url()
{
    return STACKCHAN_SERVER_HTTP_URL;
}

__attribute__((weak)) std::string generate_auth_token()
{
    std::string token = STACKCHAN_AUTH_TOKEN;
    if (token.empty()) {
        ESP_LOGW("secret_logic", "STACKCHAN_AUTH_TOKEN is unset; returning empty token");
        return "";
    }
    return token;
}

__attribute__((weak)) std::string generate_handshake_token(std::string_view data)
{
    (void)data;
    return generate_auth_token();
}

}  // namespace secret_logic
