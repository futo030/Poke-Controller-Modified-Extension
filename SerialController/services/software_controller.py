#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Software-Controller(画面上のコントローラー)の入力

画面(tkinter)には触れない。画面は、レイアウト(ControllerLayouts.describe_layout)を描き、
押した・離した・固定した部品のタグを、このクラスに知らせる。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import ControllerColors
from Commands.Keys import NEUTRAL, Button, Direction, Hat, Stick, Touchscreen
from ControllerLayouts import (
    COMPACT_LAYOUT_ALIASES,
    COMPACT_LAYOUTS,
    DEFAULT_COMPACT_LAYOUT,
    LARGE_LAYOUTS,
    describe_layout,
)

if TYPE_CHECKING:
    from Commands.Keys import KeyPress

# タッチスクリーンの座標の大きさ(3DS の下画面)
TOUCH_WIDTH = 320
TOUCH_HEIGHT = 240
# スティックを、これより小さくしか倒していない場合は、倒していないものとして扱う
STICK_DEADZONE = 0.1


class SoftwareControllerError(Exception):
    """そのレイアウトに無い部品を指定した"""


def layout_names(large: bool = False) -> list:
    """選べるレイアウトの名前の一覧(large: Controller Simulator の大きいレイアウトの一覧にするか)"""
    return list(LARGE_LAYOUTS if large else COMPACT_LAYOUTS)


def normalize_layout_name(name: str) -> str:
    """
    以前のレイアウト名で保存されている場合は、今の名前に読み替える(知らない名前は、既定のレイアウトにする)
    """
    name = COMPACT_LAYOUT_ALIASES.get(name, name)
    return name if name in COMPACT_LAYOUTS else DEFAULT_COMPACT_LAYOUT


class SoftwareController:
    """画面上のコントローラーの部品(タグ)の操作を、KeyPress への入力に変える"""

    def __init__(self, keys: KeyPress, large: bool = False):
        """
        keys: 入力に使う KeyPress(入力源がマウス操作のもの)
        large: Controller Simulator(大きいレイアウト)として使うか
        """
        self.keys = keys
        self.large = large
        self.layout = None
        self._buttons = {}
        self._sticks = {}
        # 押している部品 / 固定している部品 / 倒しているスティックのタグ、タッチ中か
        self._pressed = set()
        self._held = set()
        self._tilted = set()
        self._touching = False

    def set_layout(self, name: str, color_settings: dict | None = None) -> dict:
        """
        レイアウトを切り替える(押している・固定している入力は離す)。レイアウトの内容を返す
        color_settings: 本体の色の設定(設定ファイルの内容。None なら読み込み済みの色のまま)
        """
        self.release_all()
        if color_settings is not None:
            ControllerColors.load_settings(color_settings)
        self.layout = describe_layout(name if self.large else normalize_layout_name(name), large=self.large)
        self._buttons = {
            tag: (Hat if value["kind"] == "hat" else Button)[value["name"]] for tag, value in self.layout["buttons"].items()
        }
        self._sticks = {tag: Stick[info["stick"]] for tag, info in self.layout["sticks"].items()}
        return self.layout

    def _button(self, tag: str) -> Button | Hat:
        """タグに対応するボタン / 十字キーの方向を返す(このレイアウトに無ければ SoftwareControllerError)"""
        if tag not in self._buttons:
            raise SoftwareControllerError(f"このレイアウトに無いボタンです: {tag}")
        return self._buttons[tag]

    def _stick(self, tag: str) -> Stick:
        """タグに対応するスティックを返す(このレイアウトに無ければ SoftwareControllerError)"""
        if tag not in self._sticks:
            raise SoftwareControllerError(f"このレイアウトに無いスティックです: {tag}")
        return self._sticks[tag]

    # ---------------------------------------------------------------- ボタン・十字キー

    def press(self, tag: str) -> None:
        """ボタン / 十字キーを押す(tag: 部品のタグ)"""
        self.keys.input([self._button(tag)])
        self._pressed.add(tag)

    def release(self, tag: str) -> None:
        """ボタン / 十字キーを離す"""
        self.keys.inputEnd([self._button(tag)])
        self._pressed.discard(tag)

    def hold(self, tag: str) -> None:
        """
        押しっぱなしで固定する(ほかのボタンを離したときに、一緒に離れないようにする)
        """
        value = self._button(tag)
        if type(value) is Hat:
            # 十字キーは1方向しか入力できないので、固定中の十字キーは解除する
            for other in [t for t in self._held if type(self._buttons[t]) is Hat]:
                self.hold_end(other)
        self.keys.hold([value])
        self._pressed.discard(tag)
        self._held.add(tag)

    def hold_end(self, tag: str) -> None:
        """固定を解いて離す(固定していなければ何もしない)"""
        value = self._button(tag)
        if tag in self._held:
            self.keys.holdEnd([value])
            self._held.discard(tag)

    # ---------------------------------------------------------------- スティック

    def tilt(self, tag: str, angle: float, magnitude: float) -> None:
        """
        スティックを倒す。angle: 角度(度。右が0、上が90)、magnitude: 倒す大きさ(0～1)
        magnitude が STICK_DEADZONE より小さい場合は、中央に戻す
        """
        stick = self._stick(tag)
        magnitude = min(max(float(magnitude), 0.0), 1.0)
        if magnitude < STICK_DEADZONE:
            self.keys.input(Direction(stick, NEUTRAL))
            self._tilted.discard(tag)
        else:
            self.keys.input(Direction(stick, float(angle), magnitude))
            self._tilted.add(tag)

    def center(self, tag: str) -> None:
        """スティックを中央に戻す"""
        self.keys.input(Direction(self._stick(tag), NEUTRAL))
        self._tilted.discard(tag)

    # ---------------------------------------------------------------- タッチ画面

    def touch(self, x: float, y: float) -> None:
        """
        タッチ画面を押す。x, y: 320x240 の座標((0, 0) は離した状態を表すので、1以上にする)
        タッチ画面の無いレイアウトでは SoftwareControllerError
        """
        if self.layout is None or self.layout["touch"] is None:
            raise SoftwareControllerError("このレイアウトにタッチ画面はありません。")
        x = min(max(round(float(x)), 1), TOUCH_WIDTH)
        y = min(max(round(float(y)), 1), TOUCH_HEIGHT)
        self.keys.input(Touchscreen(x, y))
        self._touching = True

    def touch_end(self) -> None:
        """タッチ画面から離す(押していなければ何もしない)"""
        if self._touching:
            self.keys.inputEnd(Touchscreen(0, 0))
            self._touching = False

    # ---------------------------------------------------------------- まとめて離す

    def is_idle(self) -> bool:
        """何も押していない・固定していない・倒していない・タッチしていない状態か"""
        return not (self._pressed or self._held or self._tilted or self._touching)

    def release_all(self) -> None:
        """
        押している・固定している入力をすべて離す
        """
        for tag in list(self._held):
            self.hold_end(tag)
        for tag in list(self._pressed):
            self.release(tag)
        for tag in list(self._tilted):
            self.center(tag)
        self.touch_end()
