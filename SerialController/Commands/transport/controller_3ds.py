#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
3DS Controller: 3DS 用の自動化基板へ、11 バイトで送る(タッチスクリーンあり)。
ファームウェアの版で、スティックの値の表し方が違う
"""
from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

from Commands.Keys import conversion_3ds_controller_button
from Commands.transport.base import Transport

if TYPE_CHECKING:
    from Commands.Keys import SendFormat


class Controller3dsTransport(Transport):
    """3DS Controller の送信方式(ファームウェアの版ごとに、名前と mode を変えて登録する)"""

    baud_rate = 115200
    button_conversion = conversion_3ds_controller_button
    has_touchscreen = True

    def __init__(self, name: str, mode: int) -> None:
        """
        name: 形式の名前(画面の Data Format に表示する)
        mode: 0 (FW:-x.3) / 1 (FW:x.4-)
        """
        self.name = name
        self.mode = mode

    def encode(self, state: OrderedDict, last_sent: dict | None, encoder: SendFormat, port: object) -> list[int]:
        """合成した入力を、11 バイトの数値のリストにする(スティックの値の表し方は mode で決まる)"""
        encoder.format = OrderedDict(state)
        return encoder.convert2list2(mode=self.mode)
