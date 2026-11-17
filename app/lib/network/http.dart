/*
SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
SPDX-License-Identifier: MIT
*/

import 'package:dio/dio.dart';
import 'package:cupertino_ui/cupertino_ui.dart';
import 'package:stack_chan/app_state.dart';
import 'package:stack_chan/network/urls.dart';

import '../util/value_constant.dart';

void logPrint(Object? object) {
  if (object == null) return;
  String log = object.toString();
  const int chunkSize = 800; // Print at most 800 characters at a time to stay under the system log limit.
  // Print short logs directly.
  if (log.length <= chunkSize) {
    debugPrint(log);
    return;
  }

  // Print long logs in chunks.
  for (int i = 0; i < log.length; i += chunkSize) {
    int end = i + chunkSize;
    if (end > log.length) end = log.length;
    // Prefer debugPrint: it is more reliable than print and supports longer output.
    debugPrint(log.substring(i, end));
  }
}

class Http {
  static final Http instance = Http._init();

  late final Dio _dio;

  late final BaseOptions _baseOptions;

  final List<Interceptor> _interceptors = [
    LogInterceptor(responseBody: true, logPrint: logPrint),
    InterceptorsWrapper(
      onRequest:
          (RequestOptions options, RequestInterceptorHandler handler) async {
            options.baseUrl = Urls.getBaseUrl();
            // Bridge Bearer token (from SharedPreferences or --dart-define)
            final savedBridgeToken = await AppState.asyncPrefs.getString(
              ValueConstant.token,
            );
            final bearer =
                (savedBridgeToken != null && savedBridgeToken.isNotEmpty)
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

            /// App version header.
            String? version = AppState.shared.packageInfo?.version;
            if (version != null) {
              options.headers[ValueConstant.appVersion] = version;
            }
            return handler.next(options);
          },
      onResponse:
          (Response response, ResponseInterceptorHandler handler) async {
            if (response.statusCode == 401) {
              AppState.shared.showToast(
                "Authentication failed (401). Check STACKCHAN_BRIDGE_TOKEN in Settings.",
              );
            }
            return handler.next(response);
          },
      onError: (DioException error, ErrorInterceptorHandler handler) async {
        if (error.response?.statusCode == 401) {
          AppState.shared.showToast(
            "Authentication failed (401). Check STACKCHAN_BRIDGE_TOKEN in Settings.",
          );
        }
        return handler.next(error);
      },
    ),
  ];

  Http._init() {
    _baseOptions = BaseOptions(
      baseUrl: Urls.getBaseUrl(),
      connectTimeout: const Duration(seconds: 30),
      receiveTimeout: const Duration(seconds: 30),
      sendTimeout: const Duration(seconds: 30),
    );
    _dio = Dio(_baseOptions);
    _dio.interceptors.addAll(_interceptors);
  }

  Future<Response> get(
    String pathUrl, {
    dynamic data,
    Options? options,
    String? baseUrlString,
  }) async {
    if (baseUrlString != null) {
      _dio.options.baseUrl = baseUrlString;
    }
    return await _dio.get(pathUrl, queryParameters: data, options: options);
  }

  Future<Response> post(
    String pathUrl, {
    dynamic data,
    Options? options,
    String? baseUrlString,
  }) async {
    if (baseUrlString != null) {
      _dio.options.baseUrl = baseUrlString;
    }
    return await _dio.post(pathUrl, data: data, options: options);
  }

  Future<Response> put(
    String pathUrl, {
    dynamic data,
    Options? options,
    String? baseUrlString,
  }) async {
    if (baseUrlString != null) {
      _dio.options.baseUrl = baseUrlString;
    }
    return await _dio.put(pathUrl, data: data, options: options);
  }

  Future<Response> delete(
    String pathUrl, {
    dynamic data,
    Options? options,
    String? baseUrlString,
  }) async {
    if (baseUrlString != null) {
      _dio.options.baseUrl = baseUrlString;
    }
    return await _dio.delete(pathUrl, data: data, options: options);
  }

  Future<Response> postFormData(
    String pathUrl,
    FormData data, {
    Options? options,
    String? baseUrlString,
  }) async {
    if (baseUrlString != null) {
      _dio.options.baseUrl = baseUrlString;
    }
    return await _dio.post(pathUrl, data: data, options: options);
  }
}
