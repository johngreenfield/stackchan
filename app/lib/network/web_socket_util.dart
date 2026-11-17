/*
SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
SPDX-License-Identifier: MIT
*/

import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:cupertino_ui/cupertino_ui.dart';

// Project-specific imports.
import '../app_state.dart';
import '../model/msg_type.dart';
import '../util/value_constant.dart';

class WebSocketUtil {
  WebSocketUtil._internal();

  static final WebSocketUtil shared = WebSocketUtil._internal();

  WebSocket? _socket;
  StreamSubscription? _subscription;

  // Track the connection state so reconnect logs are not repeated.
  bool _isConnected = false;
  bool _isReconnecting = false;
  bool _manuallyDisconnected = false;
  int _reconnectAttempts = 0;
  Timer? _reconnectTimer;

  Function()? connectionSuccessful;

  final Map<String, void Function(dynamic)> _observers = {};
  final Map<Object, void Function()> _connectionObservers = {};

  String _urlString = '';

  /* =======================
   * Connect
   * ======================= */
  Future<void> connect(String urlString) async {
    // Disconnect any existing connection first.
    if (_socket != null) {
      disconnect();
    }

    _manuallyDisconnected = false;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _isReconnecting = false;
    _urlString = urlString;

    final devId = AppState.shared.deviceMac.isNotEmpty
        ? AppState.shared.deviceMac
        : AppState.shared.deviceId;
    if (devId.isEmpty) {
      debugPrint(' WebSocket ConnectFailed:DeviceId/MAC is null/empty');
      return;
    }

    // Log the start of the connection attempt.
    debugPrint('🔌 StartConnect WebSocket: $urlString');

    try {
      final savedToken = await AppState.asyncPrefs.getString(
        ValueConstant.token,
      );
      final bearer = (savedToken != null && savedToken.isNotEmpty)
          ? savedToken
          : ValueConstant.bridgeToken;

      final headers = <String, dynamic>{
        if (bearer.isNotEmpty) ValueConstant.authorization: 'Bearer $bearer',
        ValueConstant.deviceIdHeader: devId,
      };
      _socket = await WebSocket.connect(urlString, headers: headers);

      // Log successful connection details (time and URL).
      _isConnected = true;
      _reconnectAttempts = 0;
      final connectTime = DateTime.now().toString().split('.').first;
      debugPrint(' WebSocket ConnectSuccess [$connectTime]');
      debugPrint('   ConnectAddress: $urlString');
      debugPrint('   ConnectState: ${_socket?.readyState} (OPEN)');

      _subscription = _socket!.listen(
        _handleMessage,
        onError: _handleError,
        onDone: _handleDone,
        cancelOnError: true,
      );

      if (connectionSuccessful != null) {
        connectionSuccessful!();
      }
      for (final observer in List.of(_connectionObservers.values)) {
        observer();
      }
    } catch (e) {
      _isConnected = false;
      // Log the failure with the specific error.
      final errorTime = DateTime.now().toString().split('.').first;
      debugPrint(' WebSocket ConnectFailed [$errorTime]');
      debugPrint('   ConnectAddress: $urlString');
      debugPrint('   Error原Because: $e');
      _scheduleReconnect();
    }
  }

  /* =======================
   * Message Handling
   * ======================= */
  void _handleMessage(dynamic message) {
    final isPing = replyPong(message);
    if (!isPing) {
      _notifyObservers(message);
    }
  }

  void _handleError(Object error) {
    // Log runtime errors separately from connection errors.
    debugPrint(' WebSocket Running / RuntimeWhenError: $error');
    _isConnected = false;
    _scheduleReconnect();
  }

  void _handleDone() {
    // Log the close event and its reason.
    _isConnected = false;
    final closeTime = DateTime.now().toString().split('.').first;
    debugPrint(' WebSocket ConnectAlready关闭 [$closeTime]');
    debugPrint('   关闭Address: $_urlString');
    debugPrint('   关闭State: ${_socket?.closeCode} - ${_socket?.closeReason}');
    _scheduleReconnect();
  }

  bool replyPong(dynamic message) {
    if (message is Uint8List) {
      final result = AppState.shared.parseMessage(message);
      final msgType = result.$1;

      if (msgType != null) {
        switch (msgType) {
          case MsgType.ping:
            AppState.shared.sendWebSocketMessage(.pong);
            return true;
          default:
            return false;
        }
      }
    }
    return false;
  }

  /* =======================
   * Send
   * ======================= */
  void sendString(String message) {
    if (_socket == null) {
      debugPrint(' 发送StringMessageFailed:WebSocket Disconnected');
      return;
    }

    debugPrint('📤 发送StringMessage: $message');
    try {
      _socket!.add(message);
    } catch (e) {
      debugPrint(' 发送StringMessageFailed: $e');
      _isConnected = false;
      _scheduleReconnect();
    }
  }

  void send(Uint8List data) {
    if (_socket == null) {
      debugPrint(' 发送2BaseMessageFailed:WebSocket Disconnected');
      return;
    }

    //debugPrint('📤 send2Basemessage: length=${data.length} Byte');
    try {
      _socket!.add(data);
    } catch (e) {
      debugPrint(' 发送2BaseMessageFailed: $e');
      _isConnected = false;
      _scheduleReconnect();
    }
  }

  /* =======================
   * Reconnect
   * ======================= */
  void _scheduleReconnect() {
    if (_manuallyDisconnected ||
        _urlString.isEmpty ||
        _isReconnecting ||
        _isConnected) {
      return;
    }

    _isReconnecting = true;
    final delaySeconds = (1 << _reconnectAttempts.clamp(0, 4)).clamp(1, 30);
    _reconnectAttempts++;

    debugPrint('🔄 Reconnecting WebSocket in ${delaySeconds}s: $_urlString');
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(Duration(seconds: delaySeconds), () {
      _isReconnecting = false;
      if (!_manuallyDisconnected && _urlString.isNotEmpty) {
        connect(_urlString);
      }
    });
  }

  /* =======================
   * Disconnect
   * ======================= */
  void disconnect() {
    _manuallyDisconnected = true;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _isReconnecting = false;
    _reconnectAttempts = 0;
    _subscription?.cancel();
    _subscription = null;
    _socket?.close(WebSocketStatus.goingAway, '主动断开连接');
    _isConnected = false;
    _socket = null;
    debugPrint('🔌 WebSocket AlreadyProactiveDisconnectConnect');
  }

  /* =======================
   * Observer
   * ======================= */
  void addObserver(String key, void Function(dynamic message) observer) {
    _observers[key] = observer;
  }

  void removeObserver(String key) {
    _observers.remove(key);
  }

  /// Pages subscribe individually so a shared reconnect callback cannot overwrite another handler or outlive its page.
  void addConnectionObserver(Object key, void Function() observer) {
    _connectionObservers[key] = observer;
  }

  void removeConnectionObserver(Object key) {
    _connectionObservers.remove(key);
  }

  void removeAllObservers() {
    _observers.clear();
  }

  void _notifyObservers(dynamic message) {
    for (final observer in List.of(_observers.values)) {
      observer(message);
    }
  }

  // Current connection state, exposed for external checks.
  bool get isConnected => _isConnected && _socket?.readyState == WebSocket.open;
}
