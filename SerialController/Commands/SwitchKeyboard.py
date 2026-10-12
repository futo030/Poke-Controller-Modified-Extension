#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Switchへのキーボード入力(マイコンをキーボードとしても認識させて、文字やキーを打つ)

キーボード機能に対応したファームウェアが必要。
    Arduino Leonardo: Poke-ControllerForLeonardo v04 以降
    CH552-SERIAL    : CH55xSwitchSerialControl v2.4 以上(それより前の版では、Enter・矢印キーなどを送れない)
Data Format が Default の場合は、マイコンに次の行を送る(通常の操作と同じテキストの行)。
NX の場合は、キーの操作を 11 バイトのデータで送る(Commands/transport/nx_macro.py)。
    "abc"       引用符の中の半角文字を、1文字ずつキーボードで打つ
    Key 40      キーを1回押して離す
    Press 42    キーを押したままにする
    Release 42  キーを離す

送れるのは半角の文字(キーに対応する英字・数字・記号)だけ。かなを入力する場合は、
Switch側をローマ字入力のモードにして、ローマ字を送る(モードの切り替えも、キーを送って行う)。

このモジュールは送る行を作るだけで、送信は行わない(送信と待ち時間は PythonCommand が行う)。
"""
from __future__ import annotations

from enum import IntEnum


class KEY(IntEnum):
    """
    TypeKey / PressKey / ReleaseKey に渡すキー(値は、マイコンに送る数値。SPACE 以外はUSBキーボードのキーコード)。
    ファームウェアは、ここにあるキーコードはそのまま送り、それ以外の数値は文字コードとして扱う
    """

    SPACE = 32
    ENTER = 40
    BACKSPACE = 42
    DELETE = 76
    RIGHT_ARROW = 79
    LEFT_ARROW = 80
    DOWN_ARROW = 81
    UP_ARROW = 82
    JP_HANZEN = 0x35  # 半角/全角
    JP_BACKSLASH = 0x87
    JP_HIRAGANA = 0x88  # ひらがな/カタカナ
    JP_HENKAN = 0x8A  # 変換


# 1行で送る文字数の上限。
# ファームウェアは行の先頭の語を16バイトの領域に読み込むので、引用符2つと終端を含めて収まる長さにする
MAX_TEXT_LENGTH = 13
# ファームウェアが1文字を打つのに掛ける時間(押す30ms + 離す30ms)
SECONDS_PER_CHARACTER = 0.06
# ファームウェアがキーを押す・離すのに掛ける時間
SECONDS_PER_KEY_ACTION = 0.03
# 行を送ってから、ファームウェアが打ち終わるまでの余裕(通信と、打った後のコントローラーの状態の送信)
SECONDS_MARGIN = 0.1

# Switchでは入力できないとされている文字(送ることはできるので、警告だけ行う)
UNSUPPORTED_ON_SWITCH = "@"


def is_text_format(serial_data_format_name: str) -> bool:
    """
    テキストの行を送れるData Formatか(バイナリで送る形式・FTDI直結の形式では使えない)
    """
    from Commands.transport import get_transport

    return get_transport(serial_data_format_name).supports_text


def find_invalid_characters(text: str) -> list[str]:
    """
    半角の文字(スペース〜「~」)以外の文字を、出てきた順に重複なく返す(無ければ空)
    """
    invalid = []
    for character in text:
        if not (0x20 <= ord(character) <= 0x7E) and character not in invalid:
            invalid.append(character)
    return invalid


def split_text(text: str) -> list[str]:
    """
    文字列を、1行で送れる長さに分ける
    """
    return [text[i : i + MAX_TEXT_LENGTH] for i in range(0, len(text), MAX_TEXT_LENGTH)]


def text_row(text: str) -> str:
    """
    文字列を打つ行(text は split_text で分けたもの)
    """
    return f'"{text}"'


def text_seconds(text: str) -> float:
    """
    文字列を打つ行を送ってから、次の行を送るまでに待つ時間
    """
    return len(text) * SECONDS_PER_CHARACTER + SECONDS_MARGIN


def key_row(action: str, key: int) -> str:
    """
    キーを操作する行。action: "Key"(押して離す) / "Press"(押したまま) / "Release"(離す)
    """
    return f"{action} {int(key)}"


def key_seconds(action: str) -> float:
    """
    キーを操作する行を送ってから、次の行を送るまでに待つ時間
    """
    actions = 2 if action == "Key" else 1
    return actions * SECONDS_PER_KEY_ACTION + SECONDS_MARGIN


def key_name(key: int) -> str:
    """
    表示用のキーの名前(数値で指定された場合は数値のまま)
    """
    return key.name if isinstance(key, KEY) else str(int(key))
