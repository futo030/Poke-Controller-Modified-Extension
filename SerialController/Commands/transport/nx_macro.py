#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NX: NX Macro Controller の形式(11 バイト)で送る。CH552-SERIAL(CH55xSwitchSerialControl)などが対応している。

    0      0xAB
    1, 2   ボタン(16ビット、下位が先。並びは Default と同じ)
    3      十字キー(0: 上 から時計回りに 7: 左上、8: なし)
    4 - 7  左X、左Y、右X、右Y(中央は 0x80)
    8      キーボードの操作(0: なし、1: 文字のキーを押す、2: 文字のキーを離す、
           3: キーコードのキーを押す、4: キーコードのキーを離す、5: すべてのキーを離す)
    9      キー(8 が 1・2 のときは文字コード、3・4 のときは USB キーボードのキーコード)
    10     0

キーボードの操作も、コントローラーの状態と同じ 11 バイトで送る(そのとき押しているボタンは、押したままになる)。
ファームウェアは行の先頭で形式を見分けるので、文字列の行(Mcu コマンドなど)も、そのまま送れる
"""
from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

from Commands import SwitchKeyboard
from Commands.transport.base import Transport

if TYPE_CHECKING:
    from Commands.Keys import SendFormat

HEADER = 0xAB
KEYBOARD_NONE = 0
KEYBOARD_PRESS = 1
KEYBOARD_RELEASE = 2
KEYBOARD_PRESS_CODE = 3
KEYBOARD_RELEASE_CODE = 4
KEYBOARD_RELEASE_ALL = 5

# キーコードとして送るキー(これ以外の数値は、文字コードとして送る。Default の形式でのファームウェアの扱いと同じ)
KEY_CODES = frozenset(int(key) for key in SwitchKeyboard.KEY if key is not SwitchKeyboard.KEY.SPACE)


class NxMacroTransport(Transport):
    """NX(NX Macro Controller の 11 バイトの形式)の送信方式"""

    name = "NX"

    def encode(self, state: OrderedDict, last_sent: dict | None, encoder: SendFormat, port: object) -> bytes:
        """合成した入力を、11 バイトのデータにする(キーボードの操作は、なし)"""
        return self.packet(state)

    def encode_keyboard(self, state: OrderedDict, encoder: SendFormat, mode: int, key: int) -> bytes:
        """
        キーボードの操作を、今のコントローラーの状態と一緒に送るデータにする

        mode: キーボードの操作(KEYBOARD_PRESS など)
        key: 文字コード、または USB キーボードのキーコード
        """
        return self.packet(state, mode, key)

    @staticmethod
    def packet(state: dict, keyboard_mode: int = KEYBOARD_NONE, key: int = 0) -> bytes:
        """
        11 バイトのデータを作る(並びは、このファイルの先頭の説明のとおり)

        state: SendFormat.format と同じ形(btn、hat、lx、ly、rx、ry を使う)
        keyboard_mode: キーボードの操作(KEYBOARD_NONE など。0 - 5)
        key: 文字コード、または USB キーボードのキーコード(下位 8 ビットを送る)
        """
        buttons = int(state["btn"])
        return bytes(
            (
                HEADER,
                buttons & 0xFF,
                (buttons >> 8) & 0xFF,
                int(state["hat"]),
                int(state["lx"]),
                int(state["ly"]),
                int(state["rx"]),
                int(state["ry"]),
                keyboard_mode,
                int(key) & 0xFF,
                0,
            )
        )

    def keyboard_steps(self, kind: str, value: str | int | None = None) -> list[tuple[tuple[int, int], float]]:
        """
        キーボード入力の手順を [((キーボードの操作, キー), 送った後に待つ秒数), ...] で返す

        kind と value は Transport と同じ。知らない kind は ValueError
        (キーの操作で value が数値に直せない場合も、int() の ValueError / TypeError が出る)
        """
        wait = SwitchKeyboard.SECONDS_PER_KEY_ACTION
        if kind == "init":
            return [((KEYBOARD_RELEASE_ALL, 0), 0.05)]
        if kind == "text":
            steps = []
            for character in value:
                steps.append(((KEYBOARD_PRESS, ord(character)), wait))
                steps.append(((KEYBOARD_RELEASE, ord(character)), wait))
            return steps
        code = int(value)
        press, release = (
            (KEYBOARD_PRESS_CODE, KEYBOARD_RELEASE_CODE) if code in KEY_CODES else (KEYBOARD_PRESS, KEYBOARD_RELEASE)
        )
        if kind == "Key":
            return [((press, code), wait), ((release, code), wait)]
        if kind == "Press":
            return [((press, code), wait)]
        if kind == "Release":
            return [((release, code), wait)]
        raise ValueError(f"unknown keyboard action: {kind}")
