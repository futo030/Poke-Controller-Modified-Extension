#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
部品の上にマウスを置いたときに表示する説明(ツールチップ)
"""
from __future__ import annotations

import tkinter as tk


# ToolTipのクラスは以下のサイトを参考に作成
# https://www.ishikawasekkei.com/index.php/2020/05/17/python-tkinter-gui-programing-tooltip/


class ToolTip:
    """
    部品の上にマウスを置くと、少し遅れて説明を表示するクラス
    (部品の <Motion> と <Leave> に結び付ける。マウスが動いている間は表示せず、止まって0.3秒後に表示する)
    """

    def __init__(self, widget: tk.Misc, text: str = "default tooltip"):
        """
        widget: 説明を付ける部品
        text: 表示する説明
        """
        self.widget = widget
        self.text = text
        self.widget.bind("<Motion>", self.moveCursor)
        self.widget.bind("<Leave>", self.leaveCursor)
        self.id = None
        self.tw = None

    def moveCursor(self, event: tk.Event) -> None:
        """部品の上でマウスが動いたとき: 予約を取り消し、まだ表示していなければ、0.3秒後の表示を予約し直す"""
        id = self.id
        self.id = None
        if id:
            self.widget.after_cancel(id)
        if not self.tw:
            id = self.id
            self.id = None
            if id:
                self.widget.after_cancel(id)
            self.id = self.widget.after(300, self.createTooltip)

    def leaveCursor(self, event: tk.Event) -> None:
        """部品からマウスが出たとき: 表示の予約を取り消し、0.3秒後に説明を消す"""
        id = self.id
        self.id = None
        if id:
            self.widget.after_cancel(id)
        self.id = self.widget.after(300, self.destroyTooltip)

    def createTooltip(self) -> None:
        """マウスの位置の右上に、説明のウィンドウ(枠なし)を表示する"""
        id = self.id
        self.id = None
        if id:
            self.widget.after_cancel(id)
        x, y = self.widget.winfo_pointerxy()
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.geometry(f"+{x + 15}+{y - 35}")
        label = tk.Label(
            self.tw,
            text=self.text,
            background="#98FB98",
            # テーマに関係なく、明るい背景に黒い文字で表示する
            foreground="black",
            relief="solid",
            borderwidth=0.5,
            justify="left",
        )
        label.pack(ipadx=10)

    def destroyTooltip(self) -> None:
        """表示中の説明のウィンドウを消す"""
        tw = self.tw
        self.tw = None
        if tw:
            tw.destroy()
