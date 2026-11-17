/*
SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
SPDX-License-Identifier: MIT
*/

import 'package:cupertino_ui/cupertino_ui.dart';
import 'package:stack_chan/app_state.dart';
import 'package:stack_chan/network/urls.dart';
import 'package:stack_chan/util/value_constant.dart';
import 'package:stack_chan/view/popup/device_wifi_config.dart';
import 'package:stack_chan/view/util/theme_setting.dart';

class ServerConfigPage extends StatefulWidget {
  const ServerConfigPage({super.key, this.isWelCome = false});

  final bool isWelCome;

  @override
  State<ServerConfigPage> createState() => _ServerConfigPageState();
}

class _ServerConfigPageState extends State<ServerConfigPage> {
  late final TextEditingController _publicHostController;
  late final TextEditingController _lanHostController;
  late final TextEditingController _tokenController;
  bool _useLan = false;
  bool _obscureToken = true;
  bool _isSaving = false;

  @override
  void initState() {
    super.initState();
    _publicHostController = TextEditingController(text: Urls.rawPublicHost);
    _lanHostController = TextEditingController(text: Urls.rawLanHost);
    _tokenController = TextEditingController();
    _useLan = Urls.useLanFallback;
    _loadSavedValues();
  }

  Future<void> _loadSavedValues() async {
    await Urls.loadFromPrefs();
    final savedToken = await AppState.asyncPrefs.getString(ValueConstant.token);
    if (!mounted) return;
    setState(() {
      _publicHostController.text = Urls.rawPublicHost;
      _lanHostController.text = Urls.rawLanHost;
      _useLan = Urls.useLanFallback;
      _tokenController.text =
          (savedToken != null && savedToken.isNotEmpty)
              ? savedToken
              : ValueConstant.bridgeToken;
    });
  }

  @override
  void dispose() {
    _publicHostController.dispose();
    _lanHostController.dispose();
    _tokenController.dispose();
    super.dispose();
  }

  Future<void> _saveAndContinue() async {
    if (_isSaving) return;
    FocusManager.instance.primaryFocus?.unfocus();

    setState(() => _isSaving = true);
    try {
      await Urls.saveConfig(
        publicHost: _publicHostController.text,
        lanHost: _lanHostController.text,
        useLan: _useLan,
      );

      final nextToken = _tokenController.text.trim();
      if (nextToken.isEmpty) {
        await AppState.asyncPrefs.remove(ValueConstant.token);
      } else {
        await AppState.asyncPrefs.setString(ValueConstant.token, nextToken);
      }

      AppState.shared.connectWebSocket();

      if (!mounted) return;
      if (widget.isWelCome) {
        Navigator.of(context).push(
          CupertinoPageRoute(
            builder: (context) => const DeviceWifiConfig(isWelCome: true),
          ),
        );
      } else {
        AppState.shared.showToast("Server & bridge configuration saved");
        Navigator.maybePop(context);
      }
    } finally {
      if (mounted) {
        setState(() => _isSaving = false);
      }
    }
  }

  void _skipOnboarding() {
    FocusManager.instance.primaryFocus?.unfocus();
    Navigator.of(context).push(
      CupertinoPageRoute(
        builder: (context) => const DeviceWifiConfig(isWelCome: true),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final padding = MediaQuery.paddingOf(context);

    return CupertinoPageScaffold(
      backgroundColor: CupertinoColors.systemGroupedBackground.resolveFrom(
        context,
      ),
      child: Column(
        children: [
          Expanded(
            child: CustomScrollView(
              slivers: [
                CupertinoSliverNavigationBar(
                  backgroundColor:
                      ThemeSetting.cupertinoNavigationBarBackgroundColor(
                        context,
                      ),
                  border: ThemeSetting.cupertinoNavigationBarBorder(context),
                  padding: ThemeSetting.navigationBarPadding,
                  stretch: true,
                  largeTitle: const Text("Server & Bridge"),
                ),
                SliverPadding(
                  padding: EdgeInsets.only(
                    left: padding.left,
                    right: padding.right,
                  ),
                  sliver: SliverList.list(
                    children: [
                      const SizedBox(height: 12),
                      CupertinoListSection.insetGrouped(
                        header: const Text("PUBLIC SERVER HOST / URL"),
                        footer: const Text(
                          "Used over HTTPS/WSS when not in LAN mode. Leave blank if using LAN only.",
                        ),
                        children: [
                          CupertinoTextField(
                            controller: _publicHostController,
                            padding: const EdgeInsets.all(12),
                            decoration: const BoxDecoration(),
                            placeholder: "e.g. stackchan.example.com",
                            keyboardType: TextInputType.url,
                            autocorrect: false,
                            clearButtonMode: OverlayVisibilityMode.editing,
                          ),
                        ],
                      ),
                      CupertinoListSection.insetGrouped(
                        header: const Text("LAN SERVER HOST / URL"),
                        footer: const Text(
                          "Local bridge address (host:port) used over HTTP/WS on your home network.",
                        ),
                        children: [
                          CupertinoTextField(
                            controller: _lanHostController,
                            padding: const EdgeInsets.all(12),
                            decoration: const BoxDecoration(),
                            placeholder: "e.g. 192.168.1.100:8765",
                            keyboardType: TextInputType.url,
                            autocorrect: false,
                            clearButtonMode: OverlayVisibilityMode.editing,
                          ),
                          CupertinoListTile(
                            title: const Text("Use LAN Server"),
                            trailing: CupertinoSwitch(
                              value: _useLan,
                              onChanged: (value) {
                                setState(() => _useLan = value);
                              },
                            ),
                          ),
                        ],
                      ),
                      CupertinoListSection.insetGrouped(
                        header: const Text("BRIDGE TOKEN"),
                        footer: Text(
                          ValueConstant.bridgeToken.isNotEmpty
                              ? "Leave blank to fall back to the build-time STACKCHAN_BRIDGE_TOKEN."
                              : "Matches STACKCHAN_BRIDGE_TOKEN on your server-openclaw instance.",
                        ),
                        children: [
                          CupertinoTextField(
                            controller: _tokenController,
                            padding: const EdgeInsets.all(12),
                            decoration: const BoxDecoration(),
                            placeholder: "Enter bridge token",
                            obscureText: _obscureToken,
                            autocorrect: false,
                            suffix: CupertinoButton(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 10,
                              ),
                              minimumSize: Size.zero,
                              onPressed: () {
                                setState(() => _obscureToken = !_obscureToken);
                              },
                              child: Icon(
                                _obscureToken
                                    ? CupertinoIcons.eye
                                    : CupertinoIcons.eye_slash,
                                size: 20,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: EdgeInsets.only(
              left: 20 + padding.left,
              right: 20 + padding.right,
              top: 16,
              bottom: padding.bottom + 20,
            ),
            child: Row(
              spacing: 15,
              children: [
                if (widget.isWelCome)
                  Expanded(
                    child: CupertinoButton.tinted(
                      onPressed: _skipOnboarding,
                      child: Center(
                        child: Text(
                          "Skip",
                          style: TextStyle(
                            color: CupertinoTheme.of(context).primaryColor,
                          ),
                        ),
                      ),
                    ),
                  ),
                Expanded(
                  child: CupertinoButton.filled(
                    onPressed: _isSaving ? null : _saveAndContinue,
                    child: Center(
                      child: _isSaving
                          ? const CupertinoActivityIndicator(
                              color: CupertinoColors.white,
                            )
                          : Text(
                              widget.isWelCome ? "Continue" : "Save",
                              style: const TextStyle(
                                color: CupertinoColors.white,
                              ),
                            ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
