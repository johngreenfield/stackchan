/*
SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
SPDX-License-Identifier: MIT
*/

import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:stack_chan/app_state.dart';
import 'package:stack_chan/network/http.dart';
import 'package:stack_chan/network/urls.dart';
import 'package:stack_chan/util/mac_address_validator.dart';
import 'package:stack_chan/util/value_constant.dart';

import '../model/XiaoZhi/XiaoZhi_model.dart';
import '../model/XiaoZhi/agent.dart';
import '../model/XiaoZhi/agent_create.dart';
import '../model/XiaoZhi/agent_template.dart';
import '../model/XiaoZhi/common_mcp_tool.dart';
import '../model/XiaoZhi/conversation.dart';
import '../model/XiaoZhi/conversation_message_data.dart';
import '../model/XiaoZhi/device.dart';
import '../model/XiaoZhi/endpoints_response.dart';
import '../model/XiaoZhi/mcp_endpoints.dart';
import '../model/XiaoZhi/pagination.dart';
import '../model/XiaoZhi/tts_list.dart';

/// OpenClaw self-hosted stub for legacy XiaoZhi cloud API calls.
///
/// The OpenClaw bridge (`server-openclaw`) runs the agent, STT, and TTS locally
/// without external `xiaozhi.me` accounts or token brokers.
class XiaoZhiUtil {
  static final XiaoZhiUtil shared = XiaoZhiUtil._internal();

  XiaoZhiUtil._internal() {
    _dio.options.baseUrl = Urls.getFileUrl();
    _dio.options.connectTimeout = const Duration(seconds: 10);
    _dio.options.receiveTimeout = const Duration(seconds: 10);
    _dio.options.validateStatus = (state) {
      return state != null && state >= 200 && state < 500;
    };
    _dio.interceptors.add(
      LogInterceptor(responseBody: true, logPrint: logPrint),
    );
  }

  final Dio _dio = Dio();

  Future<String?> getToken() async {
    final savedToken = await AppState.asyncPrefs.getString(ValueConstant.token);
    if (savedToken != null && savedToken.isNotEmpty) {
      return savedToken;
    }
    return ValueConstant.bridgeToken;
  }

  Future<String?> getTokenFromServer() async => await getToken();

  /// Refresh the bridge access token (no-op in self-hosted OpenClaw mode).
  Future<String?> refreshXiaoZhiToken() async => await getToken();

  /// Get the agent template list (managed by OpenClaw).
  Future<List<AgentTemplate>> agentTemplatesList(int page, int pageSize) async {
    return [];
  }

  /// Get device list stub for the given MAC address.
  Future<List<Device>> getDevice(String macAddress) async {
    final formattedMac =
        MacAddressValidator.formatMac(macAddress) ?? macAddress;
    return [
      Device(
        deviceId: 1,
        macAddress: formattedMac,
        agentId: 1,
        alias: "OpenClaw",
      ),
    ];
  }

  Future<List<Device>> getCapitalLettersMacDevice(String macAddress) async {
    return await getDevice(macAddress);
  }

  /// Get voice list (managed by OpenClaw).
  Future<TTsList?> getTtsList() async => null;

  /// Get model list (managed by OpenClaw).
  Future<List<ModelData>> getModelList() async => [];

  /// Get official MCP tools (managed by OpenClaw).
  Future<List<CommonMcpTool>> getCommonMcpTool() async => [];

  /// Create agent (no-op in self-hosted OpenClaw mode).
  Future<int?> createAgent(AgentCreate agentParams) async => 1;

  /// Get agent list.
  Future<List<Agent>> getAgents({
    int page = 1,
    int pageSize = 24,
    String? keyword,
  }) async {
    return [Agent(id: 1, agentName: "OpenClaw")];
  }

  /// Get agent details (read-only OpenClaw stub).
  Future<Agent?> getAgentDetail(int agentId) async {
    return Agent(id: agentId, agentName: "OpenClaw");
  }

  /// Update agent (no-op in self-hosted OpenClaw mode).
  Future<bool> updateAgent(int agentId, AgentCreate agentParams) async => true;

  /// Bind a device to an agent (no-op in self-hosted OpenClaw mode).
  Future<bool> bindDeviceToAgent(int agentId, String verificationCode) async =>
      true;

  /// Update device alias in agent settings (no-op).
  Future<bool> updateAgentDeviceAlias({
    required int agentId,
    required String macAddress,
    required String alias,
  }) async => true;

  /// Enable/disable OTA auto-update for a device (no-op).
  Future<bool> updateAgentDeviceAutoUpdate({
    required int agentId,
    required String macAddress,
    required bool enabled,
  }) async => true;

  /// Unbind device (no-op).
  Future<bool> unbindDevice(int deviceId) async => true;

  /// Get MCP endpoint list.
  Future<List<McpEndpoints>> mcpEndpoints() async => [];

  /// Create an MCP endpoint (no-op).
  Future<bool> createMcpEndpoints(
    String name,
    String description,
    bool enabled,
  ) async => true;

  /// Generate an MCP endpoint token for an agent.
  Future<String?> generateMcpEndpointToken(int id) async => await getToken();

  /// Generate a token for an MCP endpoint.
  Future<String?> getEndpointToken(int id) async => await getToken();

  Future<EndpointsResponse?> endpointsList(int agentId) async => null;

  /// Edit MCP endpoint information (no-op).
  Future<bool> editEndpoints(
    int id, {
    String? name,
    String? description,
    bool? enabled,
  }) async => true;

  /// Delete MCP endpoint (no-op).
  Future<bool> deleteEndpoints(int id) async => true;

  Future<List<Conversation>> getConversationList({
    required String startDate,
    String? endDate,
    int? deviceId,
    int? page,
    int? pageSize,
    int? agentId,
    int? chatId,
  }) async => [];

  /// Delete conversation (no-op).
  Future<bool> deleteConversation(int agentId, int id) async => true;

  /// Get message list.
  Future<List<ConversationMessageData>> getChatsMessages({
    required String startDate,
    String? endDate,
    int? chatId,
    int? page,
    int? pageSize,
  }) async => [];
}

class XiaozhiResponse<T> {
  bool success = false;
  T? data;
  String? message;
  Pagination? pagination;
  String? token;

  XiaozhiResponse({
    required this.success,
    this.data,
    this.message,
    this.pagination,
    this.token,
  });

  XiaozhiResponse.fromJson(
    Map<String, dynamic> map, {
    T Function(dynamic)? factory,
  }) {
    if (map["data"] != null && map["data"] != "null" && factory != null) {
      data = factory(map["data"]);
    } else {
      data = map["data"];
    }
    if (map["message"] != null && map["message"] != "null") {
      message = map["message"];
    }
    if (map["success"] != null && map["success"] != "null") {
      success = map["success"];
    }
    if (map["pagination"] != null && map["pagination"] != "null") {
      pagination = Pagination.fromJson(map["pagination"]);
    }
    if (map["token"] != null && map["token"] != "null") {
      token = map["token"];
    }
  }

  XiaozhiResponse.fromJsonT(dynamic data, {T Function(dynamic)? factory})
    : this.fromJson(data is String ? jsonDecode(data) : data, factory: factory);

  XiaozhiResponse.fromJsonString(
    String? jsonString, {
    T Function(dynamic)? factory,
  }) : this.fromJson(jsonDecode(jsonString ?? ""), factory: factory);
}

class ListData<T> {
  List<T> list;
  Pagination? pagination;

  // Use a generic list instead of a fixed Device type
  ListData({required this.list, this.pagination});

  // Generic factory: parses a list of any type
  factory ListData.fromJson(
    Map<String, dynamic> json,
    T Function(Map<String, dynamic>) fromJsonT, // Item converter
  ) {
    return ListData<T>(
      list: json['list'] != null
          ? List<T>.from(
              (json['list'] as List).map(
                (x) => fromJsonT(x as Map<String, dynamic>),
              ),
            )
          : [],
      pagination: json['pagination'] != null
          ? Pagination.fromJson(json['pagination'] as Map<String, dynamic>)
          : null,
    );
  }

  // Serialize to JSON for any generic type
  Map<String, dynamic> toJson(dynamic Function(T) toJsonT) {
    final Map<String, dynamic> data = <String, dynamic>{};
    data['list'] = list.map((v) => toJsonT(v)).toList();
    if (pagination != null) {
      data['pagination'] = pagination!.toJson();
    }
    return data;
  }
}
