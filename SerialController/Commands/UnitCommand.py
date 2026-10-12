#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from time import sleep
from typing import TYPE_CHECKING, Callable

from . import CommandBase
from .Keys import Button, Hat, InputSource, KeyPress

if TYPE_CHECKING:
    from .Keys import Direction
    from .Sender import Sender


# Sigle button command
class UnitCommand(CommandBase.Command):
    """
    ボタンや十字キーを 1 回押すだけのコマンドの基底クラス
    (Switch Controller Simulator の画面のボタンが使う。下に、ボタンごとの子クラスがある)
    """

    def __init__(self) -> None:
        """実行していない状態で作る(入力を送る KeyPress は、start で作る)"""
        super().__init__()

    def start(self, ser: Sender, postProcess: Callable[[], None] | None = None) -> None:
        """入力を送る KeyPress を作る(子クラスは、続けて自分のボタンを押す。postProcess は使わない)"""
        self.isRunning = True
        # Switch Controller Simulatorのボタン操作で使われるため、マウス操作の入力源とする
        self.key = KeyPress(ser, source=InputSource.MOUSE)

    def end(self, ser: Sender) -> None:
        """何もしない(入力は、start の中で離し終えている)"""
        pass

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


class A(UnitCommand):
    """A ボタンを 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """A ボタンを 0.1 秒押して、離す"""
        super().start(ser)
        self.press(Button.A)


class B(UnitCommand):
    """B ボタンを 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """B ボタンを 0.1 秒押して、離す"""
        super().start(ser)
        self.press(Button.B)


class X(UnitCommand):
    """X ボタンを 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """X ボタンを 0.1 秒押して、離す"""
        super().start(ser)
        self.press(Button.X)


class Y(UnitCommand):
    """Y ボタンを 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """Y ボタンを 0.1 秒押して、離す"""
        super().start(ser)
        self.press(Button.Y)


class L(UnitCommand):
    """L ボタンを 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """L ボタンを 0.1 秒押して、離す"""
        super().start(ser)
        self.press(Button.L)


class R(UnitCommand):
    """R ボタンを 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """R ボタンを 0.1 秒押して、離す"""
        super().start(ser)
        self.press(Button.R)


class ZL(UnitCommand):
    """ZL ボタンを 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """ZL ボタンを 0.1 秒押して、離す"""
        super().start(ser)
        self.press(Button.ZL)


class ZR(UnitCommand):
    """ZR ボタンを 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """ZR ボタンを 0.1 秒押して、離す"""
        super().start(ser)
        self.press(Button.ZR)


class MINUS(UnitCommand):
    """MINUS ボタンを 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """MINUS ボタンを 0.1 秒押して、離す"""
        super().start(ser)
        self.press(Button.MINUS)


class PLUS(UnitCommand):
    """PLUS ボタンを 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """PLUS ボタンを 0.1 秒押して、離す"""
        super().start(ser)
        self.press(Button.PLUS)


class LCLICK(UnitCommand):
    """LCLICK ボタンを 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """LCLICK ボタンを 0.1 秒押して、離す"""
        super().start(ser)
        self.press(Button.LCLICK)


class RCLICK(UnitCommand):
    """RCLICK ボタンを 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """RCLICK ボタンを 0.1 秒押して、離す"""
        super().start(ser)
        self.press(Button.RCLICK)


class HOME(UnitCommand):
    """HOME ボタンを 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """HOME ボタンを 0.1 秒押して、離す"""
        super().start(ser)
        self.press(Button.HOME)


class CAPTURE(UnitCommand):
    """CAPTURE ボタンを 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """CAPTURE ボタンを 0.1 秒押して、離す"""
        super().start(ser)
        self.press(Button.CAPTURE)


class UP(UnitCommand):
    """十字キーの上を 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """十字キーの上を 0.1 秒押して、離す(終わったら、コマンドを終わった状態にして、KeyPress を手放す)"""
        super().start(ser)
        self.key.input(Hat.TOP)
        self.wait(0.1)
        self.key.input(Hat.CENTER)
        self.isRunning = False
        self.key = None


class UP_RIGHT(UnitCommand):
    """十字キーの右上を 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """十字キーの右上を 0.1 秒押して、離す(終わったら、コマンドを終わった状態にして、KeyPress を手放す)"""
        super().start(ser)
        self.key.input(Hat.TOP_RIGHT)
        self.wait(0.1)
        self.key.input(Hat.CENTER)
        self.isRunning = False
        self.key = None


class RIGHT(UnitCommand):
    """十字キーの右を 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """十字キーの右を 0.1 秒押して、離す(終わったら、コマンドを終わった状態にして、KeyPress を手放す)"""
        super().start(ser)
        self.key.input(Hat.RIGHT)
        self.wait(0.1)
        self.key.input(Hat.CENTER)
        self.isRunning = False
        self.key = None


class DOWN_RIGHT(UnitCommand):
    """十字キーの右下を 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """十字キーの右下を 0.1 秒押して、離す(終わったら、コマンドを終わった状態にして、KeyPress を手放す)"""
        super().start(ser)
        self.key.input(Hat.BTM_RIGHT)
        self.wait(0.1)
        self.key.input(Hat.CENTER)
        self.isRunning = False
        self.key = None


class DOWN(UnitCommand):
    """十字キーの下を 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """十字キーの下を 0.1 秒押して、離す(終わったら、コマンドを終わった状態にして、KeyPress を手放す)"""
        super().start(ser)
        self.key.input(Hat.BTM)
        self.wait(0.1)
        self.key.input(Hat.CENTER)
        self.isRunning = False
        self.key = None


class DOWN_LEFT(UnitCommand):
    """十字キーの左下を 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """十字キーの左下を 0.1 秒押して、離す(終わったら、コマンドを終わった状態にして、KeyPress を手放す)"""
        super().start(ser)
        self.key.input(Hat.BTM_LEFT)
        self.wait(0.1)
        self.key.input(Hat.CENTER)
        self.isRunning = False
        self.key = None


class LEFT(UnitCommand):
    """十字キーの左を 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """十字キーの左を 0.1 秒押して、離す(終わったら、コマンドを終わった状態にして、KeyPress を手放す)"""
        super().start(ser)
        self.key.input(Hat.LEFT)
        self.wait(0.1)
        self.key.input(Hat.CENTER)
        self.isRunning = False
        self.key = None


class UP_LEFT(UnitCommand):
    """十字キーの左上を 0.1 秒押して離すコマンド"""

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()

    def start(self, ser: Sender) -> None:
        """十字キーの左上を 0.1 秒押して、離す(終わったら、コマンドを終わった状態にして、KeyPress を手放す)"""
        super().start(ser)
        self.key.input(Hat.TOP_LEFT)
        self.wait(0.1)
        self.key.input(Hat.CENTER)
        self.isRunning = False
        self.key = None
