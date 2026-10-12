#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
キーボードのキーとコントローラーのボタンの対応(キーコンフィグ)の定義

- 対応はゲーム機(Switch / 3DS / DS / GameCube)ごとに持つ
- 設定ファイル(settings.ini)には、ゲーム機ごとの区分に「ボタンの名前 = キー」で保存する
  (Switchは以前からの区分 [KeyMap-Button] [KeyMap-Hat]、他は [KeyMap-Button-3DS] のようにゲーム機の名前を付ける)
- ボタンの名前は、どのゲーム機でも送信に使うSwitchのボタンの名前(Button.A、Hat.TOP など)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from configparser import ConfigParser

SWITCH = "Switch"
N3DS = "3DS"
NDS = "DS"
GAMECUBE = "GameCube"
CONSOLES = (SWITCH, N3DS, NDS, GAMECUBE)

_HATS = (("HAT UP", "Hat.TOP"), ("HAT LEFT", "Hat.LEFT"), ("HAT RIGHT", "Hat.RIGHT"), ("HAT DOWN", "Hat.BTM"))
# キーコンフィグの画面に並べるボタン: ゲーム機 -> (左の列, 右の列)。それぞれ (表示名, ボタンの名前)
BUTTONS = {
    SWITCH: (
        (("ZL", "Button.ZL"), ("L", "Button.L"), ("MINUS", "Button.MINUS"), *_HATS,
         ("CAPTURE", "Button.CAPTURE"), ("L CLICK", "Button.LCLICK")),
        (("ZR", "Button.ZR"), ("R", "Button.R"), ("PLUS", "Button.PLUS"), ("A", "Button.A"), ("B", "Button.B"),
         ("X", "Button.X"), ("Y", "Button.Y"), ("HOME", "Button.HOME"), ("R CLICK", "Button.RCLICK")),
    ),
    N3DS: (
        (("L", "Button.L"), *_HATS, ("SELECT", "Button.MINUS")),
        (("R", "Button.R"), ("A", "Button.A"), ("B", "Button.B"), ("X", "Button.X"), ("Y", "Button.Y"),
         ("START", "Button.PLUS"), ("HOME", "Button.HOME")),
    ),
    NDS: (
        (("L", "Button.L"), *_HATS, ("SELECT", "Button.MINUS")),
        (("R", "Button.R"), ("A", "Button.A"), ("B", "Button.B"), ("X", "Button.X"), ("Y", "Button.Y"),
         ("START", "Button.PLUS")),
    ),
    GAMECUBE: (
        (("L", "Button.ZL"), *_HATS),
        (("R", "Button.ZR"), ("Z", "Button.R"), ("A", "Button.A"), ("B", "Button.B"), ("X", "Button.X"),
         ("Y", "Button.Y"), ("START", "Button.PLUS")),
    ),
}  # fmt: skip

# 初期値。十字キーは、どのキーにも当たらない値(キーコンフィグで設定するまで、キーボードでは操作できない)
_HAT_DEFAULTS = {"Hat.TOP": "10000", "Hat.RIGHT": "10010", "Hat.BTM": "10100", "Hat.LEFT": "10110"}
DEFAULTS = {
    SWITCH: {
        "Button.Y": "y", "Button.B": "b", "Button.X": "x", "Button.A": "a", "Button.L": "l", "Button.R": "r",
        "Button.ZL": "k", "Button.ZR": "e", "Button.MINUS": "m", "Button.PLUS": "p", "Button.LCLICK": "q",
        "Button.RCLICK": "w", "Button.HOME": "h", "Button.CAPTURE": "c", **_HAT_DEFAULTS,
    },
    N3DS: {
        "Button.Y": "y", "Button.B": "b", "Button.X": "x", "Button.A": "a", "Button.L": "l", "Button.R": "r",
        "Button.MINUS": "m", "Button.PLUS": "p", "Button.HOME": "h", **_HAT_DEFAULTS,
    },
    NDS: {
        "Button.Y": "y", "Button.B": "b", "Button.X": "x", "Button.A": "a", "Button.L": "l", "Button.R": "r",
        "Button.MINUS": "m", "Button.PLUS": "p", **_HAT_DEFAULTS,
    },
    GAMECUBE: {
        "Button.Y": "y", "Button.B": "b", "Button.X": "x", "Button.A": "a", "Button.ZL": "l", "Button.ZR": "r",
        "Button.R": "z", "Button.PLUS": "p", **_HAT_DEFAULTS,
    },
}  # fmt: skip


def button_names(console: str) -> list[str]:
    """
    そのゲーム機でキーを割り当てるボタンの名前(画面に並べる順)
    """
    left, right = BUTTONS[console]
    return [name for _, name in (*left, *right)]


def section_name(console: str, name: str) -> str:
    """
    ボタンの名前を保存する、設定ファイルの区分の名前
    """
    kind = name.split(".")[0]
    return f"KeyMap-{kind}" if console == SWITCH else f"KeyMap-{kind}-{console}"


# 設定ファイルに保存せずに使う対応(ゲーム機 -> 対応)。同じプロファイルで2つ目以降に起動した、
# 設定を保存しないウィンドウで、キーコンフィグの変更をそのウィンドウの間だけ使うためのもの
_session_keymaps: dict[str, dict[str, str]] = {}


def set_session_keymap(console: str, keymap: dict[str, str]) -> None:
    """そのゲーム機の対応を、設定ファイルに保存せずに、起動している間だけ使うようにする"""
    _session_keymaps[console] = dict(keymap)


def load_keymap(setting: ConfigParser, console: str) -> dict[str, str]:
    """
    設定(configparser)から、そのゲーム機の対応(ボタンの名前 -> キー)を読む。保存されていないボタンは初期値
    (保存せずに使う対応がある場合は、そちらを使う)
    """
    if console in _session_keymaps:
        return dict(_session_keymaps[console])
    keymap = {}
    for name in button_names(console):
        section = section_name(console, name)
        value = None
        if setting.has_section(section):
            value = setting[section].get(name)
        keymap[name] = value if value else DEFAULTS[console][name]
    return keymap


def store_keymap(setting: ConfigParser, console: str, keymap: dict[str, str]) -> None:
    """
    そのゲーム機の対応を、設定(configparser)に入れる(区分にある他の項目は残す)
    keymap: ボタンの名前 -> キー(そのゲーム機のすべてのボタンが要る。足りないと KeyError)
    """
    for name in button_names(console):
        section = section_name(console, name)
        if not setting.has_section(section):
            setting.add_section(section)
        setting[section][name] = keymap[name]


def console_of_layout(layout_name: str) -> str:
    """
    Software-Controllerのレイアウトの名前から、ゲーム機を決める
    """
    for console in (N3DS, NDS, GAMECUBE):
        if layout_name.startswith(console):
            return console
    return SWITCH
