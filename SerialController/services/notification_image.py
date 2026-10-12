#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discord の通知に付ける画像の選び方(Notification タブの Discord Notification の設定)

画面(tkinter)には触れない。画像を取り出す処理は、呼び出し側が関数で渡す。
この設定が効くのは、Notification の Test・Start・End と、Main Panel の Discord ボタン。
スクリプトの discord_image が送る画像には、影響しない。
"""
from __future__ import annotations

from logging import getLogger, DEBUG, NullHandler
from typing import Any, Callable

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# 付ける画像の種類(設定ファイルに書く値)
CAMERA = "camera"  # 画面(カメラの今の画像)
WINDOW = "window"  # ウィンドウ全体(このアプリケーションのウィンドウ)
KINDS = (CAMERA, WINDOW)
DEFAULT = CAMERA
# 画面に表示する名前
LABELS = {CAMERA: "画面", WINDOW: "ウィンドウ全体"}
SETTING_NAME = "discord_notification_image"


def normalize(kind: object) -> str:
    """設定の値を、決まった値にそろえる(知らない値は、画面)"""
    text = str(kind).strip().lower()
    return text if text in KINDS else DEFAULT


def pick(kind: object, read_camera: Callable[[], Any], capture_window: Callable[[], Any] | None = None) -> Any:
    """
    通知に付ける画像を取り出す(取り出せなければ None)。
    kind: 画像の種類、read_camera: カメラの今の画像を返す関数、capture_window: ウィンドウ全体の画像を返す関数
    ウィンドウ全体を選んでいても、取り込めないとき(最小化している、Windows 以外など)は、カメラの画像にする
    """
    if normalize(kind) == WINDOW and capture_window is not None:
        try:
            image = capture_window()
        except Exception as e:
            _logger.warning(f"Failed to capture the window: {e}")
            image = None
        if image is not None:
            return image
    try:
        return read_camera()
    except Exception as e:
        _logger.warning(f"Failed to read the camera image: {e}")
        return None
