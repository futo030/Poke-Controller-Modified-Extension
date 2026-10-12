#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import TYPE_CHECKING, Callable

from Commands import CommandBase

if TYPE_CHECKING:
    from Commands.Sender import Sender


# MCU command
class McuCommand(CommandBase.Command):
    """マイコンに書き込んである処理を、名前の行を送って始めさせるコマンド(Mcu コマンド)の基底クラス"""

    def __init__(self, sync_name: str) -> None:
        """sync_name: 開始するときにマイコンへ送る行(ファームウェアが、この名前で処理を見分ける)"""
        super(McuCommand, self).__init__()
        self.sync_name = sync_name
        self.postProcess = None

    def start(self, ser: Sender, postProcess: Callable[[], None] | None) -> None:
        """
        sync_name の行を送って、マイコンの処理を始める

        postProcess: end で呼ぶ関数(画面の Start ボタンを戻す処理など。None: 呼ばない)
        """
        ser.writeRow(self.sync_name)
        self.isRunning = True
        self.postProcess = postProcess

    def end(self, ser: Sender) -> None:
        """"end" の行を送ってマイコンの処理を止め、start で受け取った postProcess を呼ぶ"""
        ser.writeRow("end")
        self.isRunning = False
        if self.postProcess:
            self.postProcess()
