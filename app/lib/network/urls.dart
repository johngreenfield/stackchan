/*
SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
SPDX-License-Identifier: MIT
*/

import 'package:stack_chan/app_state.dart';

/// API endpoint configuration for the StackChan backend server
///
/// This class contains all the base URL configurations and API endpoint paths
/// for communicating with the StackChan backend server.
///
/// Backend Configuration:
/// - Pass defaults at build time via `--dart-define`:
///   `STACKCHAN_PUBLIC_HOST`, `STACKCHAN_LAN_HOST`, `STACKCHAN_USE_LAN`
/// - Override at runtime via the Server & Bridge Setup screen (persisted in
///   `SharedPreferencesAsync`).
class Urls {
  static const String publicHostKey = 'stackchan_public_host';
  static const String lanHostKey = 'stackchan_lan_host';
  static const String useLanKey = 'stackchan_use_lan';

  /// Build-time defaults via --dart-define
  static const bool defaultUseLanFallback =
      bool.fromEnvironment('STACKCHAN_USE_LAN', defaultValue: false);
  static const String defaultPublicHost =
      String.fromEnvironment('STACKCHAN_PUBLIC_HOST', defaultValue: '');
  static const String defaultLanHost =
      String.fromEnvironment('STACKCHAN_LAN_HOST', defaultValue: '');

  static String _savedPublicHost = '';
  static String _savedLanHost = '';
  static bool? _savedUseLan;

  static bool get useLanFallback => _savedUseLan ?? defaultUseLanFallback;

  static String get rawPublicHost =>
      _savedPublicHost.isNotEmpty ? _savedPublicHost : defaultPublicHost;

  static String get rawLanHost =>
      _savedLanHost.isNotEmpty ? _savedLanHost : defaultLanHost;

  static Future<void> loadFromPrefs() async {
    _savedPublicHost =
        (await AppState.asyncPrefs.getString(publicHostKey))?.trim() ?? '';
    _savedLanHost =
        (await AppState.asyncPrefs.getString(lanHostKey))?.trim() ?? '';
    _savedUseLan = await AppState.asyncPrefs.getBool(useLanKey);
  }

  static Future<void> saveConfig({
    required String publicHost,
    required String lanHost,
    required bool useLan,
  }) async {
    final cleanPublic = _stripSchemeAndSlashes(publicHost);
    final cleanLan = _stripSchemeAndSlashes(lanHost);

    if (cleanPublic.isEmpty) {
      await AppState.asyncPrefs.remove(publicHostKey);
    } else {
      await AppState.asyncPrefs.setString(publicHostKey, cleanPublic);
    }

    if (cleanLan.isEmpty) {
      await AppState.asyncPrefs.remove(lanHostKey);
    } else {
      await AppState.asyncPrefs.setString(lanHostKey, cleanLan);
    }

    await AppState.asyncPrefs.setBool(useLanKey, useLan);

    _savedPublicHost = cleanPublic;
    _savedLanHost = cleanLan;
    _savedUseLan = useLan;
  }

  static String _stripSchemeAndSlashes(String raw) {
    var value = raw.trim();
    value = value.replaceFirst(RegExp(r'^https?://', caseSensitive: false), '');
    value = value.replaceFirst(RegExp(r'^wss?://', caseSensitive: false), '');
    value = value.replaceAll(RegExp(r'/+$'), '');
    return value;
  }

  static String _normalizeHostWithTrailingSlash(String raw, String fallback) {
    final clean = _stripSchemeAndSlashes(raw);
    if (clean.isEmpty) return fallback;
    return '$clean/';
  }

  static String get publicHost =>
      _normalizeHostWithTrailingSlash(rawPublicHost, '');
  static String get lanHost =>
      _normalizeHostWithTrailingSlash(rawLanHost, '');

  static String get url {
    if (useLanFallback) {
      return lanHost.isNotEmpty
          ? lanHost
          : (publicHost.isNotEmpty ? publicHost : 'localhost:8765/');
    }
    return publicHost.isNotEmpty
        ? publicHost
        : (lanHost.isNotEmpty ? lanHost : 'localhost:8765/');
  }

  static bool get _usingLanHost {
    if (useLanFallback) return lanHost.isNotEmpty || publicHost.isEmpty;
    return publicHost.isEmpty && lanHost.isNotEmpty;
  }

  static String get _httpScheme => _usingLanHost ? "http" : "https";
  static String get _wsScheme => _usingLanHost ? "ws" : "wss";

  /// Returns `<scheme>://<host>/stackChan/`
  static String getBaseUrl() {
    return "$_httpScheme://$url"
        "stackChan/";
  }

  /// Returns `<scheme>://<host>/`
  static String getFileUrl() {
    return "$_httpScheme://$url";
  }

  /// Returns `<ws-scheme>://<host>/stackChan/ws`
  static String getWebSocketUrl() {
    return "$_wsScheme://$url"
        "stackChan/ws";
  }

  // ===========================================================================
  // Device Management Endpoints
  // ===========================================================================

  /// Device registration endpoint
  /// Register a new device using its MAC address
  static const String registerMac = "api/v2/device/registerMac";

  /// Device information endpoint
  /// Retrieve device details and status
  static const String deviceInfo = "device/info";

  // ===========================================================================
  // Dance Choreography Endpoints
  // ===========================================================================

  /// Dance data endpoint (v1 legacy)
  static const String dance = "dance";

  /// Dance data endpoint (v2)
  /// Create, retrieve, update, and delete dance choreographies
  static const String v2dance = "v2/dance";

  // ===========================================================================
  // Social & Content Endpoints
  // ===========================================================================

  /// Get a random list of devices for discovery
  static const String deviceRandomList = "device/randomList";

  /// File upload endpoint for media (images, videos, dance files)
  static const String uploadFile = "uploadFile";

  /// Create a new social post
  static const String postAdd = "post/add";

  /// Retrieve post details
  static const String postGet = "post/get";

  /// Delete a social post
  static const String postDelete = "post/delete";

  /// Create a comment on a post
  static const String postCommentCreate = "post/comment/create";

  /// Delete a comment from a post
  static const String postCommentDelete = "post/comment/delete";

  /// Retrieve comments for a post
  static const String postCommentGet = "post/comment/get";

  /// Panoramic image or 360 view content endpoint
  static const String pano = "pano";

  // ===========================================================================
  // Authentication & User Endpoints
  // ===========================================================================

  /// User login endpoint
  static const String login = "v2/user/login";

  /// User profile management endpoint
  static const String user = "v2/user";

  /// User devices management endpoint
  static const String devices = "v2/devices";

  /// User registration endpoint
  static const String registration = "v2/user/registration";

  // ===========================================================================
  // Device-User Binding Endpoints
  // ===========================================================================

  /// Activate and bind a device to a user account
  static const String v2deviceActivateBind = "v2/device/activate_bind";

  /// Unbind a device from a user account
  static const String v2deviceUnbind = "v2/device/unbind";

  // ===========================================================================
  // XiaoZhi AI Service Endpoints
  // ===========================================================================

  /// XiaoZhi AI authentication token endpoint
  /// Retrieve a token for AI service access
  static const String xiaozhiToken = "xiaozhi/token";

  /// XiaoZhi AI token refresh endpoint
  /// Refresh expired authentication tokens
  static const String xiaozhiTokenRefresh = "xiaozhi/token/refresh";

  static const String privacyPolicyUrl =
      "https://policies.m5stack.com/stack-chan-privacy-policy";
}
