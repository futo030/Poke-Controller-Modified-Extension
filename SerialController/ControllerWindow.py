#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Software Controllerのウィンドウ

上部のコンボボックスでレイアウト(Switch(Joy-Con / Pro Controller) / 3DS / DS / GameCube)を切り替え、その下に選んだレイアウトを表示する。
(送信形式(Data Format)からは対象のゲーム機を区別できないため、レイアウトは手動で選ぶ)
"""
from __future__ import annotations

import tkinter as tk
import tkinter.ttk as ttk
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING, Callable

from ControllerLayouts import (
    Controller3DSGUI,
    ControllerDSGUI,
    ControllerGameCubeGUI,
    ControllerSwitchJoyConGUI,
    ControllerSwitchProGUI,
)

if TYPE_CHECKING:
    from Commands.Sender import Sender

# レイアウト名 -> レイアウトのクラス(親フレームの中に作れること)
CONTROLLER_LAYOUTS = {
    "Switch (Joy-Con)": ControllerSwitchJoyConGUI,
    "Switch (Pro Controller)": ControllerSwitchProGUI,
    "3DS": Controller3DSGUI,
    "DS": ControllerDSGUI,
    "GameCube": ControllerGameCubeGUI,
}
# 保存された名前が一覧に無い場合(以前の"Switch"など)にも使う
DEFAULT_CONTROLLER_LAYOUT = "Switch (Joy-Con)"

# レイアウトの大きさ(全レイアウト共通)
LAYOUT_WIDTH = 600
LAYOUT_HEIGHT = 300


class ControllerWindow:
    """
    Controller Simulator のウィンドウ(レイアウトを選ぶコンボボックスと、選んだレイアウトのコントローラー)
    """

    def __init__(
        self,
        root: tk.Tk,
        ser: Sender,
        layout: str = DEFAULT_CONTROLLER_LAYOUT,
        on_layout_changed: Callable[[str], None] | None = None,
        touch_image_source: Callable | None = None,
        on_keyboard: Callable[[], None] | None = None,
    ):
        """
        root: メインウィンドウ(この位置を基準に表示する)
        ser: 操作を送る先
        layout: 最初に表示するレイアウトの名前(一覧に無い名前の場合は DEFAULT_CONTROLLER_LAYOUT)
        on_layout_changed: レイアウトを切り替えたときに呼ぶ関数(レイアウトの名前)
        touch_image_source: タッチ画面に表示する画像を返す関数(Controller3DSGUIを参照)
        on_keyboard: コントローラーの右下の Keyboard ボタンを押したときに呼ぶ関数(Noneなら、ボタンを置かない)
        """
        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

        self.root = root
        self.ser = ser
        self.on_layout_changed = on_layout_changed
        self.touch_image_source = touch_image_source
        self.on_keyboard = on_keyboard
        self.panel = None

        self.window = tk.Toplevel(root)
        self.window.title("Controller Simulator")
        root_geometry = root.geometry().split("+")
        self.window.geometry("%+d%+d" % (250 + int(root_geometry[1]), 125 + int(root_geometry[2])))
        self.window.resizable(False, False)

        # レイアウトの切り替え
        bar = ttk.Frame(self.window, padding=(5, 3))
        bar.pack(side="top", fill="x")
        ttk.Label(bar, text="Layout:").pack(side="left")
        self.layout = tk.StringVar(value=layout if layout in CONTROLLER_LAYOUTS else DEFAULT_CONTROLLER_LAYOUT)
        self.layout_cb = ttk.Combobox(
            bar, textvariable=self.layout, values=list(CONTROLLER_LAYOUTS), state="readonly", width=22
        )
        self.layout_cb.pack(side="left", padx=5)
        self.layout_cb.bind("<<ComboboxSelected>>", self._on_layout_selected)

        self.body = tk.Frame(self.window, width=LAYOUT_WIDTH, height=LAYOUT_HEIGHT)
        self.body.pack(side="top")
        self._show_layout()
        self._logger.debug("Create GUI controller")

    def _show_layout(self) -> None:
        """選択中のレイアウトのコントローラーを作り直して表示する(表示中のものは、入力を離してから破棄する)"""
        # 表示中のレイアウトの入力を離してから作り直す
        if self.panel is not None:
            self.panel.destroy()
            self.panel = None
        for child in self.body.winfo_children():
            child.destroy()
        self.panel = CONTROLLER_LAYOUTS[self.layout.get()](
            self.root, self.ser, parent=self.body, touch_image_source=self.touch_image_source,
            on_keyboard=self.on_keyboard,
        )

    def refresh(self) -> None:
        """
        表示中のレイアウトを作り直す(本体の色の設定を変えたときに呼ぶ)
        """
        self._show_layout()

    def _on_layout_selected(self, event: tk.Event | None = None) -> None:
        """Layout を選んだとき: そのレイアウトを表示し、on_layout_changed に名前を渡す"""
        self.layout_cb.selection_clear()
        self._show_layout()
        if self.on_layout_changed is not None:
            self.on_layout_changed(self.layout.get())

    def bind(self, event: str, func: Callable[[tk.Event], object]) -> None:
        """
        ウィンドウのイベントに、呼ぶ関数を結び付ける
        event: イベントの名前("<Destroy>" など)
        func: 呼ぶ関数(イベントを受け取る)
        """
        self.window.bind(event, func)

    def protocol(self, event: str, func: Callable[[], None]) -> None:
        """
        ウィンドウの操作("WM_DELETE_WINDOW" など)に、呼ぶ関数を結び付ける
        event: 操作の名前
        func: 呼ぶ関数
        """
        self.window.protocol(event, func)

    def focus_force(self) -> None:
        """ウィンドウにフォーカスを移す"""
        self.window.focus_force()

    def destroy(self) -> None:
        """表示中のコントローラーの入力を離してから、ウィンドウを閉じる"""
        if self.panel is not None:
            self.panel.destroy()
            self.panel = None
        self.window.destroy()
        self._logger.debug("GUI controller destroyed")
