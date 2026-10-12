#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Software-Controller / Controller Simulator の本体の色(ボタンを除く背景の色)

- 色はコントローラーの種類ごとに持つ(同じ種類の小さいレイアウトと大きいレイアウトで共通)
- スティックの土台の色は変えない(レイアウトごとの固定の灰色)。GameCubeのみ、本体の色から決める
- 事前に用意した色(プリセット)と、ファイルに書き出した自分の色(ControllerColors フォルダ)から選べる
"""
from __future__ import annotations

import json
import os
import re

# 自分の色を書き出すフォルダ(ここにあるファイルは、設定画面のPresetの一覧にも並ぶ)
USER_PRESET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ControllerColors")

SWITCH_JOYCON = "Switch (Joy-Con)"
SWITCH_PRO = "Switch (Pro Controller)"
N3DS = "3DS"
NDS = "DS"
GAMECUBE = "GameCube"

# 種類ごとの、設定ファイルでのキー / 色の項目(キー, 表示名) / プリセット(名前, 色)。プリセットの先頭が初期値
CONTROLLER_TYPES = {
    SWITCH_JOYCON: {
        "id": "switch_joycon",
        "keys": (("left", "Left"), ("right", "Right")),
        "presets": (
            ("Default", {"left": "#56CCF2", "right": "#E9514E"}),
            ("Neon Blue / Neon Red", {"left": "#0AB9E6", "right": "#FF3C28"}),
            ("Gray", {"left": "#828282", "right": "#828282"}),
            ("Neon Yellow", {"left": "#E6FF00", "right": "#E6FF00"}),
            ("Neon Green / Neon Pink", {"left": "#1EDC00", "right": "#FF3278"}),
            ("Neon Purple / Neon Orange", {"left": "#B400E6", "right": "#FAA005"}),
            ("Blue / Neon Yellow", {"left": "#4655F5", "right": "#E6FF00"}),
            ("Pastel Pink / Pastel Yellow", {"left": "#FFAFAF", "right": "#F5FF82"}),
            ("Pastel Purple / Pastel Green", {"left": "#F0CBEB", "right": "#BCFFC8"}),
            ("Brown / Yellow", {"left": "#C88D32", "right": "#FFDC00"}),
        ),
    },
    SWITCH_PRO: {
        "id": "switch_pro",
        "keys": (("body", "Body"),),
        "presets": (
            ("Gray", {"body": "#868E96"}),
            ("Black", {"body": "#3C3C3C"}),
        ),
    },
    N3DS: {
        "id": "3ds",
        "keys": (("body", "Body"),),
        "presets": (
            ("Light Gray", {"body": "#C9D6DF"}),
            ("Aqua Blue", {"body": "#27A6C4"}),
            ("Cosmo Black", {"body": "#2B2B33"}),
            ("Flame Red", {"body": "#C8102E"}),
            ("Misty Pink", {"body": "#F2B8C6"}),
            ("Ice White", {"body": "#F2F4F5"}),
            ("Cobalt Blue", {"body": "#1F4E9E"}),
            ("Metallic Red", {"body": "#9E1B32"}),
        ),
    },
    NDS: {
        "id": "ds",
        "keys": (("body", "Body"),),
        "presets": (
            ("Crystal White", {"body": "#DFE3E8"}),
            ("Platinum Silver", {"body": "#B8BCC2"}),
            ("Ice Blue", {"body": "#A9D4EC"}),
            ("Enamel Navy", {"body": "#1B2A4A"}),
            ("Noble Pink", {"body": "#F3A7C0"}),
            ("Jet Black", {"body": "#1E1E22"}),
            ("Crimson Red", {"body": "#A31621"}),
            ("Metallic Rose", {"body": "#D0607F"}),
        ),
    },
    GAMECUBE: {
        "id": "gamecube",
        "keys": (("body", "Body"),),
        "presets": (
            ("Violet", {"body": "#6A5ACD"}),
            ("Black", {"body": "#2A2A2E"}),
            ("Orange", {"body": "#F28C28"}),
            ("Silver", {"body": "#B4B8BF"}),
            ("Emerald Blue", {"body": "#0E8C8C"}),
            ("Symphonic Green", {"body": "#8FCFB4"}),
            ("White", {"body": "#ECECEC"}),
        ),
    },
}

_COLOR_PATTERN = re.compile(r"#[0-9A-Fa-f]{6}")


def normalize_color(text: object) -> str | None:
    """
    "#RRGGBB" の形にそろえて返す(色として読めない場合はNone)
    """
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not text.startswith("#"):
        text = "#" + text
    return text.upper() if _COLOR_PATTERN.fullmatch(text) else None


def color_keys(controller_type: str) -> tuple[str, ...]:
    """その種類の色の項目のキーを返す(例: ("left", "right")、("body",))"""
    return tuple(key for key, _ in CONTROLLER_TYPES[controller_type]["keys"])


def default_colors(controller_type: str) -> dict[str, str]:
    """その種類の初期値の色(プリセットの先頭)を返す"""
    return dict(CONTROLLER_TYPES[controller_type]["presets"][0][1])


def complete_colors(controller_type: str, colors: object) -> dict[str, str]:
    """
    その種類に必要な色をすべて持つ辞書にして返す(足りない色・読めない色は初期値にする)
    colors: 色の項目 -> 色 の辞書(ファイルから読んだ内容も渡されるため、辞書でない場合は、すべて初期値にする)
    """
    result = default_colors(controller_type)
    if isinstance(colors, dict):
        for key in result:
            color = normalize_color(colors.get(key))
            if color is not None:
                result[key] = color
    return result


def stick_base_color(body: str) -> str:
    """
    スティックの土台の色を、本体の色から決める(少し暗い色。本体が暗い場合は、見分けられるよう少し明るい色)
    """
    r, g, b = (int(body[i : i + 2], 16) for i in (1, 3, 5))
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    if luminance < 0.2:
        r, g, b = (round(v + (255 - v) * 0.25) for v in (r, g, b))
    else:
        r, g, b = (round(v * 0.82) for v in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


# ---------- 今の色(アプリ全体で共通) ----------
_current = {controller_type: default_colors(controller_type) for controller_type in CONTROLLER_TYPES}


def get_colors(controller_type: str) -> dict[str, str]:
    """その種類の今の色(色の項目 -> "#RRGGBB")を返す(コピーを返すので、書き換えても今の色は変わらない)"""
    return dict(_current[controller_type])


def set_colors(controller_type: str, colors: object) -> None:
    """その種類の今の色を変える(足りない色・読めない色は初期値にする)"""
    _current[controller_type] = complete_colors(controller_type, colors)


# ---------- 設定ファイル(settings.ini)との受け渡し ----------
def colors_to_text(colors: dict[str, str]) -> str:
    """色を、設定ファイルに保存する文字("left:#56CCF2,right:#E9514E" の形)にする"""
    return ",".join(f"{key}:{color}" for key, color in colors.items())


def colors_from_text(controller_type: str, text: str) -> dict[str, str]:
    """colors_to_text で作った文字を、色の辞書に戻す(足りない色・読めない色は初期値にする)"""
    colors = {}
    for item in text.split(","):
        key, _, color = item.partition(":")
        colors[key.strip()] = color
    return complete_colors(controller_type, colors)


def load_settings(texts: dict[str, str]) -> None:
    """
    設定ファイルの内容(種類のキー -> 文字列)を、今の色にする
    """
    for controller_type, info in CONTROLLER_TYPES.items():
        if info["id"] in texts:
            _current[controller_type] = colors_from_text(controller_type, texts[info["id"]])


def settings_texts() -> dict[str, str]:
    """
    今の色を、設定ファイルに保存する形(種類のキー -> 文字列)で返す
    """
    return {info["id"]: colors_to_text(_current[controller_type]) for controller_type, info in CONTROLLER_TYPES.items()}


# ---------- 書き出し・読み込み ----------
def save_preset_file(path: str, controller_type: str, colors: dict[str, str]) -> None:
    """
    1つの種類の色をファイル(JSON)に書き出す
    """
    with open(path, "w", encoding="utf-8") as file:
        json.dump(
            {"controller": controller_type, "colors": complete_colors(controller_type, colors)},
            file,
            ensure_ascii=False,
            indent=2,
        )


def load_preset_file(path: str) -> tuple[str, dict[str, str]]:
    """
    save_preset_fileで書き出したファイルを読み、(種類, 色) を返す(内容が正しくない場合はValueError)
    """
    try:
        with open(path, encoding="utf-8-sig") as file:
            data = json.load(file)
        controller_type = data["controller"]
        colors = data["colors"]
    except (KeyError, TypeError, json.JSONDecodeError) as e:
        raise ValueError(f"invalid controller color file: {e!r}") from e
    if controller_type not in CONTROLLER_TYPES:
        raise ValueError(f"unknown controller: {controller_type}")
    if not isinstance(colors, dict):
        raise ValueError("invalid controller color file: colors")
    for key in color_keys(controller_type):
        if normalize_color(colors.get(key)) is None:
            raise ValueError(f"invalid color: {key}")
    return controller_type, complete_colors(controller_type, colors)


def list_user_presets(controller_type: str) -> list[tuple[str, dict[str, str]]]:
    """
    書き出し先のフォルダにある、その種類の色の一覧(名前=ファイル名, 色)を名前順で返す
    """
    presets = []
    try:
        names = sorted(os.listdir(USER_PRESET_DIR), key=str.lower)
    except OSError:
        return presets
    for name in names:
        if not name.lower().endswith(".json"):
            continue
        try:
            file_type, colors = load_preset_file(os.path.join(USER_PRESET_DIR, name))
        except (OSError, ValueError):
            continue
        if file_type == controller_type:
            presets.append((os.path.splitext(name)[0], colors))
    return presets
