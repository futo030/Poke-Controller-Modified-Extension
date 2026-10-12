#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
環境の診断のウィンドウ(メニューの ヘルプ > 環境の診断)

調べる中身は services/diagnostics.py。このウィンドウは、結果を一覧にして表示する
(文字は選んでコピーできる。「コピー」で、全体をクリップボードに入れる)。
"""
from __future__ import annotations

import tkinter as tk
import tkinter.ttk as ttk
from logging import getLogger, DEBUG, NullHandler
from typing import Callable

import Theme
from services import diagnostics
from ui.constants import LOG_WARNING_COLORS

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

TITLE = "環境の診断"
TEXT_WIDTH = 100
TEXT_HEIGHT = 24


class DiagnosticsWindow:
    """環境の診断の結果を表示するウィンドウ"""

    def __init__(self, root: tk.Tk, get_context: Callable[[], dict]):
        """
        root: メインウィンドウ(この位置を基準に表示する)
        get_context: 今の状態(接続しているか、カメラが映っているか など。diagnostics.diagnose に渡すもの)を返す関数
        """
        self.root = root
        self.get_context = get_context
        self.items: list = []
        self.window = tk.Toplevel(root)
        self.window.title(TITLE)
        root_geometry = root.geometry().split("+")
        self.window.geometry("%+d%+d" % (60 + int(root_geometry[1]), 60 + int(root_geometry[2])))
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda event: self.close())

        body = ttk.Frame(self.window, padding=10)
        body.pack(fill="both", expand=True)
        self.summary = tk.StringVar()
        ttk.Label(body, textvariable=self.summary).pack(anchor="w", pady=(0, 6))
        text_f = ttk.Frame(body)
        text_f.pack(fill="both", expand=True)
        self.text = tk.Text(
            text_f, width=TEXT_WIDTH, height=TEXT_HEIGHT, wrap="word", relief="flat", borderwidth=0,
            highlightthickness=0, font="TkDefaultFont", state="disabled",
        )
        scrollbar = ttk.Scrollbar(text_f, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Label(buttons, text="質問や報告に貼るときは「コピー」。フォルダーの場所(ユーザー名など)を隠すなら「マスクしてコピー」。",
                  foreground=Theme.color("muted")).pack(side="left")
        ttk.Button(buttons, text="閉じる", width=9, command=self.close).pack(side="right")
        self.copy_button = ttk.Button(buttons, text="コピー", width=9, command=self.copyAll)
        self.copy_button.pack(side="right", padx=(0, 4))
        self.masked_copy_button = ttk.Button(buttons, text="マスクしてコピー", width=16, command=self.copyMasked)
        self.masked_copy_button.pack(side="right", padx=4)
        self.run_button = ttk.Button(buttons, text="もう一度診断", width=12, command=self.run)
        self.run_button.pack(side="right")
        self.run()
        _logger.debug("Create diagnostics window")

    def run(self) -> None:
        """診断して、結果を表示し直す"""
        try:
            self.items = diagnostics.diagnose(self.get_context())
        except Exception as error:
            _logger.exception("Failed to diagnose")
            self.items = [diagnostics.Item(diagnostics.ERROR, "診断", f"診断の途中で、エラーが起きました({error})")]
        self.summary.set(diagnostics.summary(self.items))
        text = self.text
        # レベルごとの色(Log タブと同じ決め方)
        text.tag_configure(diagnostics.WARNING, foreground=LOG_WARNING_COLORS[1 if Theme.is_dark() else 0])
        text.tag_configure(diagnostics.ERROR, foreground=Theme.color("danger"))
        text.tag_configure(diagnostics.INFO, foreground=Theme.color("muted"))
        text.tag_configure("detail", lmargin1=24, lmargin2=24)
        text.configure(state="normal")
        text.delete("1.0", "end")
        for item in self.items:
            text.insert("end", f"[{item.level}] {item.title}\n", item.level)
            if item.detail:
                text.insert("end", item.detail + "\n", "detail")
        text.configure(state="disabled")

    def copyAll(self) -> None:
        """コピー: 結果の全体を、クリップボードに入れる"""
        self.root.clipboard_clear()
        self.root.clipboard_append(diagnostics.to_text(self.items))
        self.summary.set(diagnostics.summary(self.items) + " (コピーしました)")

    def copyMasked(self) -> None:
        """
        マスクしてコピー: フォルダーの場所を隠した形で、結果の全体を、クリップボードに入れる
        (アプリのフォルダーより上の階層と、ユーザーのフォルダーを *** にする。公開の場所に貼るとき用)
        """
        self.root.clipboard_clear()
        self.root.clipboard_append(diagnostics.to_text(self.items, mask=True))
        self.summary.set(diagnostics.summary(self.items) + " (フォルダーの場所を隠して、コピーしました)")

    def isOpen(self) -> bool:
        """ウィンドウが開いているか"""
        return bool(self.window.winfo_exists())

    def lift(self) -> None:
        """ウィンドウを前面に出す"""
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def close(self) -> None:
        """閉じる"""
        self.window.destroy()
        _logger.debug("Close diagnostics window")
