#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Default: Poke-Controller 用のファームウェアへ、文字列の行で送る
"""
from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

from Commands import SwitchKeyboard
from Commands.transport.base import Transport

if TYPE_CHECKING:
    from Commands.Keys import SendFormat


class TextSerialTransport(Transport):
    """Default の送信方式(ボタン・十字キー・スティックを、1 行の文字列で送る)"""

    name = "Default"
    supports_text = True
    end_row = "end"

    def encode(self, state: OrderedDict, last_sent: dict | None, encoder: SendFormat, port: object) -> str:
        """合成した入力を、送る行の文字列にする(行末の改行は付けない)"""
        encoder.format = OrderedDict(state)
        # スティックは変化した場合のみ送る(送らなければ前回の値が維持される)
        encoder.L_stick_changed = last_sent is None or (state["lx"], state["ly"]) != (last_sent["lx"], last_sent["ly"])
        encoder.R_stick_changed = last_sent is None or (state["rx"], state["ry"]) != (last_sent["rx"], last_sent["ry"])
        return encoder.convert2str()

    def keyboard_steps(self, kind: str, value: str | int | None = None) -> list[tuple[str, float]]:
        """キーボード入力の手順を [(送る行, 送った後に待つ秒数), ...] で返す(kind と value は Transport と同じ)"""
        # キーボードの操作は、文字列の行で送る(行の作り方と、待つ時間は SwitchKeyboard.py)
        if kind == "init":
            return [("end", 0.05)]
        if kind == "text":
            return [
                (SwitchKeyboard.text_row(part), SwitchKeyboard.text_seconds(part))
                for part in SwitchKeyboard.split_text(value)
            ]
        return [(SwitchKeyboard.key_row(kind, int(value)), SwitchKeyboard.key_seconds(kind))]
