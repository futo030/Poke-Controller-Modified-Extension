#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qingpi: 3DS 用の自動化基板へ、11 バイトで送る(タッチスクリーンあり)
"""
from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

from Commands.transport.base import Transport

if TYPE_CHECKING:
    from Commands.Keys import SendFormat


class QingpiTransport(Transport):
    """Qingpi の送信方式"""

    name = "Qingpi"
    has_touchscreen = True

    def encode(self, state: OrderedDict, last_sent: dict | None, encoder: SendFormat, port: object) -> list[int]:
        """合成した入力を、11 バイトの数値のリストにする(右スティックは送らず、中央のまま)"""
        encoder.format = OrderedDict(state)
        return encoder.convert2list()
