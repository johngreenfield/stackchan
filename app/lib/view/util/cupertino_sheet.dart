/*
SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
SPDX-License-Identifier: MIT
*/

import 'dart:math';

import 'package:cupertino_ui/cupertino_ui.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

import '../popup/cupertino_popup_windows.dart';

class CupertinoSheet extends StatelessWidget {
  const CupertinoSheet({
    super.key,
    required this.builder,
    this.backgroundColor = CupertinoColors.transparent,
    this.sheetSize = .medium,
  });

  final WidgetBuilder builder;
  final Color backgroundColor;
  final SheetSize sheetSize;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: MediaQuery.of(context).padding,
      child: LayoutBuilder(
        builder: (context, constraints) {
          double height;
          switch (sheetSize) {
            case SheetSize.medium:
              height = constraints.maxHeight / 2 * 1;
            case SheetSize.large:
              height = constraints.maxHeight;
          }
          return SizedBox(
            height: height,
            child: Padding(
              padding: const .all(10),
              child: AdaptiveGlass(
                shape: const LiquidRoundedSuperellipse(borderRadius: 25),
                settings: const LiquidGlassSettings(lightAngle: 0.25 * pi),
                child: GlassGlow(child: builder(context)),
              ),
            ),
          );
        },
      ),
    );
  }
}
