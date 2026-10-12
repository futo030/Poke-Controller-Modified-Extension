#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DS FT: FTDI の GPIO に DS のボタンを直結した基板へ、ピンの状態を送る。
COM ポートではなく FTDI のデバイス(FtdiPort)を開く。文字列を送ると MPSSE のコマンドとして解釈され、
意図しないピンが動くので、入力の合成を経由しない送信は行わない

使えるのは、ftd2xx が入っていて、起動時に --ds_ft を付けた場合のみ(それ以外では、Data Format の一覧に出さない)
"""
from __future__ import annotations

import re
from collections import OrderedDict
from typing import TYPE_CHECKING

from Commands import FtdiPort as ftdi
from Commands.transport.base import Transport

if TYPE_CHECKING:
    from Commands.Keys import SendFormat
    from Commands.Sender import Sender


# 起動時のオプション(Window.py が、--ds_ft が付いている場合に set_enabled(True) を呼ぶ)
OPTION = "--ds_ft"
_enabled = False


def set_enabled(enabled: bool) -> None:
    """この形式を使うかを切り替える(起動時に --ds_ft を付けた場合に有効にする)"""
    global _enabled
    _enabled = bool(enabled)


def is_enabled() -> bool:
    """この形式を使う設定になっているか(set_enabled で切り替えた値)"""
    return _enabled


class DsFtTransport(Transport):
    """DS FT の送信方式(基板のリビジョンごとに、名前を変えて登録する)"""

    baud_rate = None
    allows_raw_write = False
    raw_write_message = "FTDI: このData Formatでは、Mcuコマンドやシリアルコマンドの直接送信は行いません。"
    raw_write_log = "Raw serial write is blocked in the FTDI data format."
    skip_unchanged = True

    def __init__(self, name: str) -> None:
        """name: 形式の名前(FtdiPort.FTDI_FORMATS のキー。ピンの割り当てを決める)"""
        self.name = name

    def is_available(self) -> bool:
        """起動時に --ds_ft を付けていて、ftd2xx が入っている場合のみ True"""
        return _enabled and ftdi.FTDI_AVAILABLE

    def unavailable_message(self) -> str:
        """使えない理由(オプションなし、または ftd2xx なし)を表す文"""
        if not _enabled:
            return f"Data Format '{self.name}' は、起動時に {OPTION} を付けた場合のみ使えます。"
        return f"Data Format '{self.name}' は ftd2xx が無いため使えません。(pip install ftd2xx) "

    def open(self, sender: Sender, port_num: int, port_name: str = "", baudrate: int = 9600) -> bool:
        """
        COMポートに対応するFTDIデバイスを、MPSSEモードで開く

        port_name に "COM数字" があればその番号を、なければ port_num を使う。baudrate は使わない。
        開けたかを返す(開けなかった場合は sender.ser を None にする)
        """
        m = re.search(r"COM(\d+)", port_name or "")
        com_port = int(m.group(1)) if m else int(port_num)
        print(f"connecting to FTDI device on COM{com_port} ({self.name})")
        sender._logger.info(f"connecting to FTDI device on COM{com_port} ({self.name})")
        # 開けなかった場合に、前のポートへ送らないようにする
        sender.ser = None
        try:
            sender.ser = ftdi.open_ftdi_port(com_port, self.name)
        except ftdi.FtdiError as e:
            print(f"FTDI: {e}")
            sender._logger.error(f"FTDI: {e}")
            return False
        print(f"FTDI: {sender.ser.description} をMPSSEモードで開きました")
        sender._logger.info(f"FTDI device opened: {sender.ser.description}")
        return True

    def encode(self, state: OrderedDict, last_sent: dict | None, encoder: SendFormat, port: object) -> bytes | None:
        """合成した入力を、ピンの状態を表すデータにする(port が FtdiPort でなければ None を返し、送らない)"""
        if not isinstance(port, ftdi.FtdiPort):
            # この形式なのにデバイスを開けていない(COMポートのデバイスには送らない)
            return None
        # ボタンのビットを変換しない形式なので、Buttonのビット配置のまま渡す
        return ftdi.encode_pin_states(state["btn"], state["hat"], port.pin_map)
