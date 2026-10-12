#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
プロファイルごとの設定ファイルの場所の切り替え

画面(tkinter)には触れない。画面だけが使う設定(キーコンフィグの画面など)の場所は、画面側で切り替える。
"""
from __future__ import annotations

import os
from logging import getLogger, DEBUG, NullHandler

import Profile
from DiscordNotify import Discord_Notify
from ExternalTools import MQTTCommunications, SocketCommunications
from Keyboard import SwitchKeyboardController
from LineNotify import Line_Notify
from services.settings_store import AppSettings

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

SERIAL_CONTROLLER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PROFILE = "default"


def profile_file(profile: str, filename: str) -> str:
    """そのプロファイルのフォルダー(profiles/プロファイル名)にあるファイルの、絶対パスを返す"""
    return os.path.join(SERIAL_CONTROLLER_DIR, "profiles", profile, filename)


def apply_profile(profile: str) -> str | None:
    """
    そのプロファイルの設定ファイルを使うようにする(フォルダが無い場合は作る)。
    設定ファイル(settings.ini)の場所を返す(default の場合は、初めから default を指しているので None)
    """
    profile_dirname = os.path.join("profiles", profile)
    if not os.path.isdir(profile_dirname):
        os.makedirs(profile_dirname)
        # 新しく作ったプロファイルは、--auto で起動するときの優先度を最も低くする
        Profile.add_profile_priority(profile)
        _logger.debug(f"mkdir: '{profile_dirname}'")
    if profile == DEFAULT_PROFILE:
        return None
    setting_path = profile_file(profile, "settings.ini")
    AppSettings.SETTING_PATH = setting_path
    Line_Notify.LINE_TOKEN_PATH = profile_file(profile, "line_token.ini")
    Discord_Notify.DISCORD_SETTING_PATH = profile_file(profile, "discord_token.ini")
    token_path = profile_file(profile, "external_token.ini")
    SocketCommunications.SOCKET_TOKEN_PATH = token_path
    MQTTCommunications.MQTT_TOKEN_PATH = token_path
    SwitchKeyboardController.SETTING_PATH = setting_path
    _logger.debug(f"Use Profile: '{setting_path}'")
    return setting_path
