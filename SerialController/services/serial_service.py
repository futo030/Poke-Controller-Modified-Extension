#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
シリアルの接続の管理(ポートの一覧、接続と切断、送るデータの形式)

画面(tkinter)には触れない。送信そのものは Commands/Sender.py の Sender が行う。
"""
from __future__ import annotations

import re
from logging import getLogger, DEBUG, NullHandler

from typing import TYPE_CHECKING

from serial.tools import list_ports

from Commands.Keys import InputSource, KeyPress
from Commands.transport import get_transport

if TYPE_CHECKING:
    from Commands.Sender import Sender

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# 送るデータの形式で決まるボーレート(形式ごとの値は、送信方式(Commands/transport)が持つ)
BAUD_RATE_3DS_CONTROLLER = get_transport("3DS Controller(FW:x.4-)").baud_rate
BAUD_RATE_DEFAULT = get_transport("Default").baud_rate


def port_number(description: str) -> int:
    """
    ポートの説明(例: "USB-SERIAL CH340 (COM9)")から、ポートの番号を取り出す
    説明に "COM番号" が無い場合は AttributeError
    """
    return int(re.search(r"COM(\d+)", description).groups()[0])


def forced_baud_rate(format_name: str) -> int | None:
    """
    送るデータの形式で決まるボーレート(FTDI直結の基板はボーレートを使わないのでNone)
    """
    return get_transport(format_name).baud_rate


class SerialService:
    """シリアルのポートの一覧、接続と切断、送るデータの形式の切り替え"""

    def __init__(self, sender: Sender):
        """
        sender: 送信に使う Sender
        """
        self.sender = sender
        # キーボードでの手動操作の入力先(接続していない間はNone)
        self.key_press = None

    def list_port_descriptions(self) -> list:
        """
        接続されているポートの説明の一覧(ポートの番号順。説明に "COM番号" が無いポートは、その後ろに、見つかった順で並べる)
        """

        def order(description: str) -> tuple[int, int]:
            """並べ替えの基準: (番号があるか, 番号)"""
            try:
                return 0, port_number(description)
            except (AttributeError, ValueError):
                return 1, 0

        descriptions = [port.description for port in list_ports.comports()]
        return sorted(descriptions, key=order)

    @staticmethod
    def find_description(descriptions: list, number: int) -> str | None:
        """
        一覧から、その番号のポートの説明を探す(無ければNone。説明に "COM番号" が無いポートは、飛ばす)
        """
        for description in descriptions:
            try:
                if int(number) == port_number(description):
                    return description
            except (AttributeError, ValueError):
                continue
        return None

    def set_data_format(self, format_name: str) -> int | None:
        """
        送るデータの形式を切り替える。その形式で決まるボーレート(決まらない形式はNone)を返す
        """
        KeyPress.serial_data_format_name = format_name
        return forced_baud_rate(format_name)

    def is_connected(self) -> bool:
        """ポートに接続しているか"""
        return self.sender.isOpened()

    def connect(self, number: int, name: str, baud_rate: int) -> bool:
        """
        ポートに接続する(接続中の場合は、切断してから接続し直す)。接続できたかを返す
        """
        self.disconnect()
        if not self.sender.openSerial(number, name, baud_rate):
            return False
        print("COM Port " + str(number) + " connected successfully")
        _logger.debug("COM Port " + str(number) + " connected successfully")
        self.key_press = KeyPress(self.sender, source=InputSource.KEYBOARD)
        return True

    def disconnect(self) -> None:
        """接続中のポートを閉じる(接続していなければ何もしない)"""
        if self.sender.isOpened():
            print("Port is already opened and being closed.")
            self.sender.closeSerial()
            self.key_press = None
