#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
機能紹介のウィンドウ(起動時に表示する。メニュー > ヘルプ > 機能紹介 からも開ける)

- 紹介文は assets/introduction/introduction.md に書く。「# 見出し」で1ページが始まり、
  「![](画像のファイル名)」がそのページの画像、「- 」で始まる行が箇条書き、それ以外の行は文章になる
- 「今後は表示しない」にチェックを入れてOKを押すと、そのときの紹介文の内容(文章と画像)の識別値を保存する。
  起動時に、保存した識別値と今の紹介文の識別値が同じなら表示しない(紹介文が更新されると、また表示する)
- 保存先は profiles/introduction.json(全プロファイル共通)
"""
from __future__ import annotations

import os
import tkinter as tk
import tkinter.font as tkfont
import tkinter.ttk as ttk
from logging import getLogger, DEBUG, NullHandler
from typing import Callable

import Theme


INTRODUCTION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "introduction")
INTRODUCTION_FILE = "introduction.md"
STATE_FILE = "introduction.json"
# 画像を置く場所の大きさ(画像はこの大きさ以内で用意する)
IMAGE_WIDTH = 690
IMAGE_HEIGHT = 300
TITLE_FONT = ("Yu Gothic UI", 13, "bold")
TEXT_FONT = ("Yu Gothic UI", 9)
TEXT_LINES = 8
# 説明の右側の、スクロールバーのために空けておく幅と、説明の行の後ろの余白
SCROLLBAR_WIDTH = 18
TEXT_SPACING = 3
# この文字で始まる文章(箇条書きでない行)は、赤い文字で表示する
IMPORTANT_PREFIX = "【重要】"
IMPORTANT_TAG = "important"


# 紹介文の読み込みと「今後は表示しない」の保存(画面に依存しない部分)は、services/introduction_store.py にある
from services.introduction_store import (  # noqa: E402,F401
    Page,
    content_revision,
    hidden_revision,
    load_pages,
    set_hidden,
    should_show_at_startup,
)


class IntroductionWindow:
    """
    1ページに1項目(見出し・画像・説明)を表示し、「前へ」「次へ」で送る
    """

    def __init__(self, root: tk.Tk):
        """
        root: メインウィンドウ(この位置を基準に表示する)
        """
        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

        self.root = root
        self.pages = load_pages()
        self.index = 0
        self._photo = None
        self._close_handler = None

        self.window = tk.Toplevel(root)
        self.window.title("機能紹介")
        self.window.resizable(False, False)
        root_geometry = root.geometry().split("+")
        self.window.geometry("%+d%+d" % (120 + int(root_geometry[1]), 60 + int(root_geometry[2])))

        body = ttk.Frame(self.window, padding=10)
        body.pack(fill="both", expand=True)
        self.title_label = ttk.Label(body, font=TITLE_FONT)
        self.title_label.pack(anchor="w")
        # 画像(ページに画像がない場合は、場所だけを空けておく)
        self.image_f = tk.Frame(body, width=IMAGE_WIDTH, height=IMAGE_HEIGHT)
        self.image_f.pack_propagate(False)
        self.image_label = tk.Label(self.image_f, bd=0)
        self.image_label.pack(expand=True)
        self.image_f.pack(pady=(6, 8))
        # 説明(枠に収まらないページでは、右側にスクロールバーを出す)
        text_f = ttk.Frame(body)
        self.text = tk.Text(text_f)
        self.text_scrollbar = ttk.Scrollbar(text_f, orient="vertical", command=self.text.yview)
        self.text.configure(
            width=10,
            height=TEXT_LINES,
            wrap="char",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=TEXT_FONT,
            background=ttk.Style().lookup("TFrame", "background"),
            cursor="arrow",
            yscrollcommand=self._onTextScrolled,
        )
        self.text.tag_configure("li", lmargin1=4, lmargin2=17, spacing3=TEXT_SPACING)
        self.text.tag_configure("p", lmargin1=4, lmargin2=4, spacing3=TEXT_SPACING)
        self.text.tag_configure(IMPORTANT_TAG, foreground=Theme.color("danger"))
        # (スクロールバーの場所は、文章の右に、いつも空けておく。出したときに、文章の折り返しが変わらないようにするため。
        #  文章の幅は、画像の幅と同じ。高さは、TEXT_LINES 行と、行の後ろの余白が収まる大きさにする)
        text_f.columnconfigure(0, minsize=IMAGE_WIDTH, weight=1)
        text_f.columnconfigure(1, minsize=SCROLLBAR_WIDTH)
        line_height = tkfont.Font(root=self.window, font=TEXT_FONT).metrics("linespace") + TEXT_SPACING
        text_f.rowconfigure(0, minsize=TEXT_LINES * line_height, weight=1)
        text_f.grid_propagate(False)
        text_f.configure(width=IMAGE_WIDTH + SCROLLBAR_WIDTH, height=TEXT_LINES * line_height)
        self.text.grid(column=0, row=0, sticky="nsew")
        text_f.pack()

        nav = ttk.Frame(body)
        self.prev_button = ttk.Button(nav, text="< 前へ", width=8, command=self.showPrevious)
        self.prev_button.pack(side="left")
        self.page_label = ttk.Label(nav)
        self.page_label.pack(side="left", expand=True)
        self.next_button = ttk.Button(nav, text="次へ >", width=8, command=self.showNext)
        self.next_button.pack(side="right")
        nav.pack(fill="x", pady=(4, 0))
        ttk.Separator(body).pack(fill="x", pady=8)

        footer = ttk.Frame(body)
        # 今の紹介文をすでに「今後は表示しない」にしている場合は、チェックを入れた状態で開く
        self.is_hidden = tk.BooleanVar(value=hidden_revision() == content_revision())
        self.hidden_checkbox = ttk.Checkbutton(footer, text="今後は表示しない", variable=self.is_hidden)
        self.hidden_checkbox.pack(side="left")
        self.ok_button = ttk.Button(footer, text="OK", width=10, command=self.ok)
        self.ok_button.pack(side="right")
        footer.pack(fill="x")

        self.window.bind("<Left>", lambda event: self.showPrevious())
        self.window.bind("<Right>", lambda event: self.showNext())
        self.window.bind("<Escape>", lambda event: self._close())
        self.showPage(0)
        self._logger.debug("Create introduction window")

    def _onTextScrolled(self, first: str, last: str) -> None:
        """説明の表示範囲が変わったとき: 枠に収まっていなければスクロールバーを出し、収まっていれば隠す"""
        self.text_scrollbar.set(first, last)
        overflows = float(first) > 0.0 or float(last) < 1.0
        if overflows and not self.text_scrollbar.winfo_manager():
            self.text_scrollbar.grid(column=1, row=0, sticky="ns")
        elif not overflows and self.text_scrollbar.winfo_manager():
            self.text_scrollbar.grid_remove()

    def showPage(self, index: int) -> None:
        """
        ページを表示する(見出し・画像・説明と、「前へ」「次へ」の有効・無効)
        index: ページの番号(0始まり。範囲の外の場合は、最初または最後のページ)
        """
        if not self.pages:
            self.title_label.configure(text="(紹介文がありません)")
            self.prev_button.configure(state="disabled")
            self.next_button.configure(state="disabled")
            return
        self.index = min(max(index, 0), len(self.pages) - 1)
        page = self.pages[self.index]
        self.title_label.configure(text=page.title)
        self._photo = None
        if page.image:
            try:
                self._photo = tk.PhotoImage(master=self.window, file=os.path.join(INTRODUCTION_DIR, page.image))
            except tk.TclError as e:
                self._logger.warning(f"Failed to load the image: {page.image} ({e})")
        self.image_label.configure(image=self._photo if self._photo is not None else "")
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for number, (is_item, text) in enumerate(page.lines):
            # (最後の行の後ろには、改行を入れない。空の行の分だけ、枠からはみ出して見えるため)
            end = "\n" if number < len(page.lines) - 1 else ""
            tags = ("li",) if is_item else ("p", IMPORTANT_TAG) if text.startswith(IMPORTANT_PREFIX) else ("p",)
            self.text.insert("end", ("・" if is_item else "") + text + end, tags)
        self.text.configure(state="disabled")
        self.text.yview_moveto(0)
        self.page_label.configure(text=f"{self.index + 1} / {len(self.pages)}")
        self.prev_button.configure(state="normal" if self.index > 0 else "disabled")
        self.next_button.configure(state="normal" if self.index < len(self.pages) - 1 else "disabled")

    def showPrevious(self) -> None:
        """「前へ」ボタン、または ← キー: 前のページを表示する"""
        self.showPage(self.index - 1)

    def showNext(self) -> None:
        """「次へ」ボタン、または → キー: 次のページを表示する"""
        self.showPage(self.index + 1)

    def ok(self) -> None:
        """
        OK: 「今後は表示しない」の状態を保存して閉じる
        """
        try:
            set_hidden(self.is_hidden.get())
        except OSError as e:
            self._logger.error(f"Failed to save the introduction state: {e}")
        self._close()

    def _close(self) -> None:
        """ウィンドウを閉じる(OK、Esc)。× ボタン用の関数が登録されていれば、それを呼ぶ"""
        # ×ボタンと同じ閉じ方をする(開いた側が、開いていない状態に戻せるように)
        if self._close_handler is not None:
            self._close_handler()
        else:
            self.destroy()

    def protocol(self, event: str, func: Callable[[], None]) -> None:
        """
        ウィンドウの操作に、呼ぶ関数を結び付ける
        ("WM_DELETE_WINDOW" の関数は覚えておき、OK や Esc で閉じるときにも、× ボタンと同じ関数を呼ぶ)
        event: 操作の名前
        func: 呼ぶ関数
        """
        if event == "WM_DELETE_WINDOW":
            self._close_handler = func
        self.window.protocol(event, func)

    def focus_force(self) -> None:
        """ウィンドウを手前に出して、フォーカスを移す"""
        self.window.lift()
        self.window.focus_force()

    def destroy(self) -> None:
        """ウィンドウを破棄する(2回呼んでも何もしない)"""
        if self.window is not None:
            window, self.window = self.window, None
            window.destroy()
            self._logger.debug("Introduction window destroyed")
