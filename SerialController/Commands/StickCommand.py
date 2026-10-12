#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from time import sleep
from typing import TYPE_CHECKING, Callable

from . import CommandBase
import numpy as np
from .Keys import KeyPress, Direction, Stick

from logging import getLogger  # , Formatter, handlers, StreamHandler, DEBUG

if TYPE_CHECKING:
    from .Keys import Button, Hat
    from .Sender import Sender

# Single button command


class StickCommand(CommandBase.Command):
    """
    スティックを倒すコマンドの基底クラス(画面のスティック操作のために作られたもの。
    今は、どこからも使われていない)
    """

    def __init__(self) -> None:
        """入力を送る KeyPress は、start で作る"""
        super().__init__()
        self.key = None
        self._logger = getLogger(__name__)

    def start(self, ser: Sender, postProcess: Callable[[], None] | None = None) -> None:
        """入力を送る KeyPress を作る(postProcess は使わない)"""
        self.isRunning = True
        self.key = KeyPress(ser)

    def end(self, ser: Sender) -> None:
        """終わった状態にして、KeyPress を作り直す(入力を離す処理は、子クラスが、この後に行う)"""
        self.isRunning = False
        self.key = KeyPress(ser)

    # do nothing at wait time(s)
    def wait(self, wait: float) -> None:
        """wait 秒、何もせずに待つ"""
        sleep(wait)

    def press(self, btn: Button | Hat | Direction) -> None:
        """btn を 0.1 秒押して離し、コマンドを終わった状態にする(KeyPress も手放す)"""
        self.key.input([btn])
        self.wait(0.1)
        self.key.inputEnd([btn])
        self.isRunning = False
        self.key = None

    # press button at duration times(s)
    def stick(self, stick: Direction, duration: float = 0.015, wait: float = 0) -> None:
        """スティックを stick の向きに倒し、duration + wait 秒待つ(倒したまま。離すのは stick_end)"""
        self.key.input(stick, ifPrint=False)
        # print(buttons)
        self.wait(duration)
        self.wait(wait)

    def stick_end(self, stick: Direction = Direction(Stick.LEFT, 0)) -> None:
        """stick と同じ側のスティックを、中央に戻す"""
        self.key.inputEnd(stick)


class StickLeft(StickCommand):
    """左スティックを、角度と倒す量で動かすコマンド"""

    def __init__(self, ser: Sender) -> None:
        """ser: LStick が行を送る相手"""
        super().__init__()
        self.ser = ser
        self.key = None
        self._logger = getLogger(__name__)

    def start(self, ser: Sender, postprocess: Callable[[], None] | None = None) -> None:
        """入力を送る KeyPress を作る(postprocess は使わない)"""
        super().start(ser)
        self.key = KeyPress(ser)
        self._logger.debug("Start LeftStick Serial Connection")

    def LStick(self, angle: float, r: float = 1.0, duration: float = 0.015) -> None:
        """
        左スティックを倒す行を、合成を経由せずに送り、duration 秒待つ(Default の形式の行。倒したまま戻る)

        angle: 角度(度。0 が右、90 が上)
        r: 倒す量(0.0 - 1.0)
        duration: 送った後に待つ時間(秒)
        """
        self.ser.writeRow(
            f"3 8 {hex(int(128 + r * 127.5 * np.cos(np.deg2rad(angle))))} {hex(int(128 - r * 127.5 * np.sin(np.deg2rad(angle))))} 80 80",
            is_show=False,
        )
        self.wait(duration)

    def end(self, ser: Sender) -> None:
        """左スティックを中央に戻す"""
        super().end(ser)
        self.stick_end(stick=Direction(Stick.LEFT, 0))


class StickRight(StickCommand):
    """右スティックを、角度と倒す量で動かすコマンド"""

    def __init__(self) -> None:
        """入力を送る KeyPress は、start で作る"""
        super().__init__()
        self.key = None
        self._logger = getLogger(__name__)

    def start(self, ser: Sender) -> None:
        """入力を送る KeyPress を作る"""
        super().start(ser)
        self.key = KeyPress(ser)
        self._logger.debug("Start RightStick Serial Connection")

    def RStick(self, angle: float, r: float = 1.0, duration: float = 0.015) -> None:
        """
        右スティックを倒す行を、合成を経由せずに送り、duration 秒待つ
        (Default の形式の行。倒したまま戻る。start の後で呼ぶ)

        angle: 角度(度。0 が右、90 が上)
        r: 倒す量(0.0 - 1.0)
        duration: 送った後に待つ時間(秒)
        """
        self.key.ser.writeRow(
            f"3 8 80 80 {hex(int(128 + r * 127.5 * np.cos(np.deg2rad(angle))))} {hex(int(128 - r * 127.5 * np.sin(np.deg2rad(angle))))}",
            is_show=False,
        )
        self.wait(duration)

    def end(self, ser: Sender) -> None:
        """右スティックを中央に戻す"""
        super().end(ser)
        self.stick_end(stick=Direction(Stick.RIGHT, 0))
