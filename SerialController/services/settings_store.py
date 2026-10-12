#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
設定ファイル(プロファイルの settings.ini)の読み込みと保存

画面(tkinter)には触れない。設定値は、このクラスの属性として、ふつうの値(数値・文字列・真偽値など)で持つ。
tkinter の画面は、Settings.GuiSettings(このクラスを継承し、一部の属性を tkinter の変数にしたもの)を使う。
"""
from __future__ import annotations

import configparser
import os
from logging import getLogger
from typing import Any

import Profile
from services import notification_image

GENERAL = "General Setting"

# General Setting の項目のうち、画面の部品と結び付けるもの: (属性名, 型, 設定ファイルに無い場合の値)
# (型が int / bool の項目は、設定ファイルに無い場合 0 / False になる)
GENERAL_FIELDS = (
    ("camera_id", int, 0),
    # カメラの代わりに取り込むウィンドウの識別名(空ならカメラを使う)
    ("capture_window", str, ""),
    # 他のアプリケーションのウィンドウを、Deviceの候補に出すか
    ("is_show_windows", bool, False),
    ("com_port", int, 0),
    ("com_port_name", str, ""),
    ("baud_rate", int, 0),
    ("fps", str, "45"),
    ("show_size", str, ""),
    ("capture_size", str, "1280x720"),
    ("controller_device", str, "Auto"),
    # 音声(Audioタブ)
    ("is_use_audio", bool, False),
    ("audio_device", str, ""),
    ("audio_output_device", str, ""),
    ("is_audio_playback", bool, True),
    ("audio_volume", int, 100),
    ("software_controller_layout", str, "Switch (Joy-Con)"),
    ("controller_layout", str, "Switch (Joy-Con)"),
    ("is_use_mjpg", bool, False),
    ("is_show_realtime", bool, False),
    ("is_show_value", bool, False),
    ("is_show_guide", bool, False),
    ("is_show_serial", bool, False),
    ("is_use_keyboard", bool, False),
    ("serial_data_format_name", str, "Default"),
)
# Notification の項目(すべて真偽値。設定ファイルに無い場合は False)
NOTIFICATION_FIELDS = (
    "is_win_notification_start",
    "is_win_notification_end",
    "is_line_notification_start",
    "is_line_notification_end",
    "is_discord_notification_start",
    "is_discord_notification_end",
)
# 画面の部品と結び付ける項目の、属性名と型(Settings.GuiSettings が、tkinter の変数にする)
VARIABLE_FIELDS = (
    tuple((name, kind) for name, kind, _ in GENERAL_FIELDS)
    + tuple((name, bool) for name in NOTIFICATION_FIELDS)
)


class AppSettings:
    """
    設定ファイル(settings.ini)の内容を、属性として持つ。
    SETTING_PATH: 設定ファイルの場所(プロファイルを切り替えるときに、クラスの値を書き換える)
    """

    SETTING_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles", "default", "settings.ini")
    SHORTCUT_NUM = 12
    HISTORY_MAX = 10

    def __init__(self):
        """設定ファイルを読み込む(無い場合は、既定の内容で作ってから読み込む)"""
        self._logger = getLogger("Settings")
        self.setting = configparser.ConfigParser()
        self.setting.optionxform = str

        if not os.path.exists(self.SETTING_PATH):
            self._logger.debug("Setting file does not exists.")
            self.generate()
            self.load()
            self._logger.debug("Settings file has been generated.")
        else:
            self._logger.debug("Setting file exists.")
            self.load()
            self._logger.debug("Settings file has been loaded.")
        self._read_values()

    def _read_values(self) -> None:
        """
        読み込んだ設定ファイルの内容を、属性に入れる
        """
        general = self.setting[GENERAL]
        for name, kind, default in GENERAL_FIELDS:
            if kind is int:
                value = general.getint(name, fallback=default)
            elif kind is bool:
                value = general.getboolean(name, fallback=default)
            else:
                value = general.get(name, fallback=default)
            # 項目はあるが値が無い場合
            setattr(self, name, kind() if value is None else value)
        # プレビューの明るさ(表示だけ): ゲイン(%)とガンマ
        try:
            self.preview_gain = general.getint("preview_gain", fallback=100)
            self.preview_gamma = general.getfloat("preview_gamma", fallback=1.0)
        except ValueError:
            self.preview_gain, self.preview_gamma = 100, 1.0
        # タッチスクリーンの範囲(プレビュー上の座標)
        for name, default in (
            ("touchscreen_start_x", 1),
            ("touchscreen_start_y", 1),
            ("touchscreen_end_x", 320),
            ("touchscreen_end_y", 240),
        ):
            try:
                setattr(self, name, int(general[name]))
            except Exception:
                setattr(self, name, default)
        # Touch Screenタブの座標を、取り込みサイズ上の値で表示・入力するか
        self.is_touchscreen_capture_size = general.getboolean("is_touchscreen_capture_size", fallback=False)
        # タッチスクリーンの範囲の、取り込み画像に対する割合("start_x,start_y,end_x,end_y"。無ければ空)
        # (プレビュー上の座標は整数に丸めるので、取り込みサイズ上の値を正確に保つために保存する)
        self.touchscreen_ratio = general.get("touchscreen_ratio", fallback="")
        # Shortcut用の設定
        self.command_class_dict = {}
        self.command_name_dict = {}
        for i in range(1, self.SHORTCUT_NUM + 1):  # Update直後のError回避策
            try:
                self.command_class_dict[str(i)] = self.setting["Shortcut"][f"command_class_{i}"]
                self.command_name_dict[str(i)] = self.setting["Shortcut"][f"command_name_{i}"]
            except Exception:
                self.command_class_dict[str(i)] = "None"
                self.command_name_dict[str(i)] = "(empty)"
        # History用の設定 (新しい順)
        self.command_history = []
        if self.setting.has_section("History"):
            for i in range(1, self.HISTORY_MAX + 1):
                command_class = self.setting["History"].get(f"command_class_{i}", fallback="None")
                command_name = self.setting["History"].get(f"command_name_{i}", fallback="")
                last_run = self.setting["History"].get(f"last_run_{i}", fallback="")
                if command_class == "None" or command_name == "":
                    continue
                self.command_history.append({"class": command_class, "name": command_name, "last_run": last_run})
        # Notification用の設定
        for name in NOTIFICATION_FIELDS:
            try:
                value = self.setting["Notification"].getboolean(name)
            except Exception:
                value = False
            setattr(self, name, bool(value))
        # Discord の通知に付ける画像(画面 / ウィンドウ全体)
        try:
            kind = self.setting["Notification"].get(notification_image.SETTING_NAME, fallback=notification_image.DEFAULT)
        except Exception:
            kind = notification_image.DEFAULT
        self.discord_notification_image = notification_image.normalize(kind)
        # 目隠し(Maskタブ)。masksは "図形,x1,y1,x2,y2,色,有効" の文字列のリスト
        self.is_show_mask = True
        self.is_mask_apply_to_capture = False
        self.masks = []
        if self.setting.has_section("Mask"):
            section = self.setting["Mask"]
            self.is_show_mask = section.getboolean("is_show_mask", fallback=True)
            self.is_mask_apply_to_capture = section.getboolean("is_apply_to_capture", fallback=False)
            index = 1
            while f"mask_{index}" in section:
                self.masks.append(section[f"mask_{index}"])
                index += 1
        # コントローラーの本体の色(種類のキー -> "項目:色,..." の文字列。ControllerColorsを参照)
        self.controller_colors = {}
        if self.setting.has_section("ControllerColor"):
            self.controller_colors = dict(self.setting["ControllerColor"])
        # Output Area用の設定
        output = self.setting["Output"]
        # 右側のパネル(Output・Software-Controller)を隠すか
        self.is_side_panel_hidden = output.getboolean("side_panel_hidden", fallback=False)
        # 右側のパネル(Output・Software-Controller)の位置: "right"(右) / "bottom"(下) / "hidden"(表示しない)
        # 通常の画面とミニ画面で別々に持つ。以前の設定(side_panel_hidden)からも読み替える
        self.side_panel_position = output.get(
            "side_panel_position", fallback="hidden" if self.is_side_panel_hidden else "right"
        )
        self.mini_side_panel_position = output.get("mini_side_panel_position", fallback="bottom")
        # 通常の画面のウィンドウの大きさ("幅x高さ"。空なら中身に合わせる)と、仕切り線の位置の比率(JSON)
        self.window_size = output.get("window_size", fallback="")
        self.pane_ratios = output.get("pane_ratios", fallback="")
        # ミニ画面で起動するか
        self.is_mini = output.getboolean("mini", fallback=False)
        # テーマ(配色)。Theme.THEMES の ID
        self.theme = output.get("theme", fallback="default")
        self.area_size = output["area_size"]
        self.stdout_destination = output["stdout_destination"]
        # ミニ画面でのWidget Mode(通常画面とは別に持つ)
        self.mini_widget_mode = output.get("mini_widget_mode", fallback="ALL (default)")
        # Log タブで表示するレベル("debug" / "info" / "warning" / "error"。そのレベル以上を表示する)
        self.log_level = output.get("log_level", fallback="debug")
        self.right_frame_widget_mode = output.get("widget_mode", fallback="ALL (default)")
        self.pos_software_controller = output.get("software_controller_position", fallback="2")
        self.pos_dialogue_buttons = output.get("dialogue_buttons_position", fallback="2")

    @classmethod
    def readTheme(cls, path: str | None = None) -> str:
        """
        設定ファイルから、テーマ(配色)だけを読む(画面の部品を作る前にテーマを当てるため)
        path: 読む設定ファイル(省略すると SETTING_PATH。ファイルがなければ "default")
        """
        setting = configparser.ConfigParser()
        try:
            setting.read(path or cls.SETTING_PATH, encoding="utf-8")
            return setting.get("Output", "theme", fallback="default")
        except (configparser.Error, OSError, UnicodeDecodeError):
            return "default"

    def load(self) -> None:
        """設定ファイルを読み込む(self.setting に入れるだけ。属性には入れない。ファイルが無ければ何もしない)"""
        if os.path.isfile(self.SETTING_PATH):
            self.setting.read(self.SETTING_PATH, encoding="utf-8")

    def generate(self) -> None:
        """既定の内容の設定ファイルを作る(今のファイルは上書きする)"""
        # logger.info('Create Default setting file.')
        # default
        self.setting[GENERAL] = {
            "camera_id": 0,
            "capture_window": "",
            "is_show_windows": False,
            "com_port": 0,
            "com_port_name": "",
            "baud_rate": 9600,
            "fps": 45,
            "show_size": "640x360",
            "capture_size": "1280x720",
            "controller_device": "Auto",
            "controller_layout": "Switch (Joy-Con)",
            "software_controller_layout": "Switch (Joy-Con)",
            "is_use_audio": False,
            "audio_device": "",
            "audio_output_device": "",
            "is_audio_playback": True,
            "audio_volume": 100,
            "is_use_mjpg": False,
            "is_show_realtime": True,
            "is_show_value": False,
            "is_show_guide": False,
            "is_show_serial": False,
            "is_use_keyboard": True,
            "serial_data_format_name": "Default",
            "touchscreen_start_x": 1,
            "touchscreen_start_y": 1,
            "touchscreen_end_x": 320,
            "touchscreen_end_y": 240,
            "is_touchscreen_capture_size": False,
            "touchscreen_ratio": "",
        }
        # keyconfig
        self.setting["KeyMap-Button"] = {
            "Button.Y": "y",
            "Button.B": "b",
            "Button.X": "x",
            "Button.A": "a",
            "Button.L": "l",
            "Button.R": "r",
            "Button.ZL": "k",
            "Button.ZR": "e",
            "Button.MINUS": "m",
            "Button.PLUS": "p",
            "Button.LCLICK": "q",
            "Button.RCLICK": "w",
            "Button.HOME": "h",
            "Button.CAPTURE": "c",
        }
        self.setting["KeyMap-Direction"] = {
            "Direction.UP": "Key.up",
            "Direction.RIGHT": "Key.right",
            "Direction.DOWN": "Key.down",
            "Direction.LEFT": "Key.left",
            "Direction.UP_RIGHT": "20001",
            "Direction.DOWN_RIGHT": "20002",
            "Direction.DOWN_LEFT": "20010",
            "Direction.UP_LEFT": "20011",
        }
        self.setting["KeyMap-Hat"] = {
            "Hat.TOP": "10000",
            "Hat.TOP_RIGHT": "10001",
            "Hat.RIGHT": "10010",
            "Hat.BTM_RIGHT": "10011",
            "Hat.BTM": "10100",
            "Hat.BTM_LEFT": "10101",
            "Hat.LEFT": "10110",
            "Hat.TOP_LEFT": "10111",
            "Hat.CENTER": "11000",
        }
        self.setting["Shortcut"] = {}
        for i in range(1, self.SHORTCUT_NUM + 1):
            self.setting["Shortcut"][f"command_class_{i}"] = "None"
            self.setting["Shortcut"][f"command_name_{i}"] = "(empty)"
        self.setting["History"] = {}
        self.setting["Notification"] = {name: False for name in NOTIFICATION_FIELDS}
        self.setting["Notification"][notification_image.SETTING_NAME] = notification_image.DEFAULT
        self.setting["Output"] = {
            "area_size": "20",
            "stdout_destination": "1",
            "widget_mode": "ALL (default)",
            "software_controller_position": "2",
            "dialogue_buttons_position": "2",
            "side_panel_hidden": False,
            "mini": False,
        }
        with open(self.SETTING_PATH, "w", encoding="utf-8") as file:
            self.setting.write(file)
        os.chmod(path=self.SETTING_PATH, mode=0o777)

    def _value(self, name: str) -> Any:
        """
        保存する値(属性の値)。Settings.GuiSettings では、tkinter の変数から値を取り出す
        """
        return getattr(self, name)

    def _shortcut_name(self, number: str) -> str:
        """ショートカットのコマンド名(number: "1"～)。Settings.GuiSettings では、tkinter の変数から取り出す"""
        return self.command_name_dict[number]

    def save(self, path: str | None = None) -> None:
        """
        属性の値を、設定ファイル(SETTING_PATH)に保存する。
        同じプロファイルで 2 つ目以降に起動した場合(読み取り専用)は、保存しない。
        path: 使っていない(以前の呼び出し方との互換のために残している。保存先は、いつも SETTING_PATH)
        """
        if Profile.is_read_only():
            # 同じプロファイルで2つ目以降に起動した場合は保存しない
            return
        # キーの対応(キーコンフィグ)は、キーコンフィグの画面が設定ファイルに直接保存している。
        # 起動時に読んだ古い内容で上書きしないよう、保存の前にファイルから読み直す
        current = configparser.ConfigParser()
        current.optionxform = str
        try:
            current.read(self.SETTING_PATH, encoding="utf-8")
        except (OSError, configparser.Error):
            pass
        for section in current.sections():
            if section.startswith("KeyMap-"):
                self.setting[section] = dict(current[section])
        value = self._value
        self.setting[GENERAL] = {
            "camera_id": value("camera_id"),
            # "%"は設定ファイルの書式で特別な意味を持つので、重ねて書く
            "capture_window": value("capture_window").replace("%", "%%"),
            "is_show_windows": value("is_show_windows"),
            "com_port": value("com_port"),
            "com_port_name": value("com_port_name"),
            "baud_rate": value("baud_rate"),
            "fps": value("fps"),
            "show_size": value("show_size"),
            "capture_size": value("capture_size"),
            "controller_device": value("controller_device"),
            "controller_layout": value("controller_layout"),
            "software_controller_layout": value("software_controller_layout"),
            "is_use_audio": value("is_use_audio"),
            "audio_device": value("audio_device"),
            "audio_output_device": value("audio_output_device"),
            "is_audio_playback": value("is_audio_playback"),
            "audio_volume": value("audio_volume"),
            "is_use_mjpg": value("is_use_mjpg"),
            "preview_gain": self.preview_gain,
            "preview_gamma": self.preview_gamma,
            "is_show_realtime": value("is_show_realtime"),
            "is_show_value": value("is_show_value"),
            "is_show_guide": value("is_show_guide"),
            "is_show_serial": value("is_show_serial"),
            "is_use_keyboard": value("is_use_keyboard"),
            "serial_data_format_name": value("serial_data_format_name"),
            "touchscreen_start_x": self.touchscreen_start_x,
            "touchscreen_start_y": self.touchscreen_start_y,
            "touchscreen_end_x": self.touchscreen_end_x,
            "touchscreen_end_y": self.touchscreen_end_y,
            "is_touchscreen_capture_size": self.is_touchscreen_capture_size,
            "touchscreen_ratio": self.touchscreen_ratio,
        }
        # 以前の版にあった Pokemon Home 連携の設定は、使わないので消す
        self.setting.remove_section("Pokemon Home")
        # ショートカット用の設定
        shortcut = {}
        for i in range(1, self.SHORTCUT_NUM + 1):
            shortcut[f"command_class_{i}"] = self.command_class_dict[str(i)]
            shortcut[f"command_name_{i}"] = self._shortcut_name(str(i))
        self.setting["Shortcut"] = shortcut
        # 実行履歴用の設定
        history = {}
        for i, entry in enumerate(self.command_history[: self.HISTORY_MAX], start=1):
            history[f"command_class_{i}"] = entry["class"]
            history[f"command_name_{i}"] = entry["name"]
            history[f"last_run_{i}"] = entry["last_run"]
        self.setting["History"] = history
        self.setting["Notification"] = {name: value(name) for name in NOTIFICATION_FIELDS}
        self.setting["Notification"][notification_image.SETTING_NAME] = notification_image.normalize(
            getattr(self, "discord_notification_image", notification_image.DEFAULT)
        )
        mask_section = {
            "is_show_mask": self.is_show_mask,
            "is_apply_to_capture": self.is_mask_apply_to_capture,
        }
        for index, text in enumerate(self.masks, start=1):
            mask_section[f"mask_{index}"] = text
        self.setting["Mask"] = mask_section
        self.setting["ControllerColor"] = dict(self.controller_colors)
        self.setting["Output"] = {
            "area_size": self.area_size,
            "stdout_destination": self.stdout_destination,
            "widget_mode": self.right_frame_widget_mode,
            "software_controller_position": self.pos_software_controller,
            "dialogue_buttons_position": self.pos_dialogue_buttons,
            "side_panel_hidden": self.side_panel_position == "hidden",
            "side_panel_position": self.side_panel_position,
            "mini_side_panel_position": self.mini_side_panel_position,
            "window_size": self.window_size,
            "pane_ratios": self.pane_ratios,
            "mini": self.is_mini,
            "mini_widget_mode": self.mini_widget_mode,
            "log_level": self.log_level,
            "theme": self.theme,
        }
        with open(self.SETTING_PATH, "w", encoding="utf-8") as file:
            self.setting.write(file)
        os.chmod(path=self.SETTING_PATH, mode=0o777)
        self._logger.debug("Settings file has been saved.")
