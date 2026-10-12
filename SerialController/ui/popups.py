#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
コマンド一覧の見出しから開く、絞り込みのポップアップ
"""
from __future__ import annotations

import tkinter as tk
import tkinter.ttk as ttk
from typing import Callable, Iterable

from ui.constants import COMMAND_SORT_DEFAULT, COMMAND_SORTS


class TagFilterPopup:
    """
    タグの一覧をチェックボックスで表示し、フィルタに使うタグを選択するポップアップ。
    上の欄に文字を入力すると、その文字を含むタグ(部分一致。大文字・小文字は区別しない)に自動でチェックを入れる。
    チェックや文字を変更するたびに on_change(選択中のタグの集合, 入力した文字) を呼ぶ。枠外クリック/Escで閉じる。
    """

    MAX_VISIBLE_ROWS = 12

    def __init__(
        self,
        widget: tk.Misc,
        x: int,
        y: int,
        tags: list[str],
        selected: Iterable[str],
        on_change: Callable[[set[str], str], None],
        y_above: int | None = None,
        text: str = "",
    ):
        """
        widget: ポップアップの親にする部品(コマンド一覧)
        x, y: 表示位置(左上、画面上の座標)。画面下にはみ出す場合は y_above の上側に表示する
        tags: 一覧に並べるタグ
        selected: 開いたときにチェックを入れておくタグ
        on_change: チェックや文字を変更するたびに呼ぶ関数(選択中のタグの集合, 入力した文字)
        y_above: 上側に表示するときの、下端の位置(None: 上側には表示しない)
        text: 開いたときに検索欄に入れておく文字
        """
        # (x, y): 表示位置(左上)。画面下にはみ出す場合は y_above の上側に表示する
        self.on_change = on_change
        # 入力した文字によって自動でチェックを入れたタグ(文字を変えて一致しなくなったら、チェックを外す)
        self.auto_checked = set()
        self.text = tk.StringVar(value=text)
        self.top = tk.Toplevel(widget)
        self.top.wm_overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.withdraw()
        frame = ttk.Frame(self.top, relief="solid", borderwidth=1, padding="5")
        frame.pack(fill="both", expand=True)

        self.vars = {}
        self.entry = None
        if len(tags) == 0:
            ttk.Label(frame, text="タグがありません").pack(anchor="w", padx="5", pady="2")
        else:
            search_f = ttk.Frame(frame)
            ttk.Label(search_f, text="検索:").pack(side="left", padx=(0, 4))
            self.entry = ttk.Entry(search_f, textvariable=self.text, width="16")
            self.entry.pack(side="left", expand=True, fill="x")
            search_f.pack(fill="x", pady=(0, 4))
            # タグが多い場合はスクロールできるようにする
            list_f = ttk.Frame(frame)
            canvas = tk.Canvas(list_f, highlightthickness=0)
            inner = ttk.Frame(canvas)
            for tag in tags:
                var = tk.BooleanVar(value=tag in selected)
                ttk.Checkbutton(inner, text=tag, variable=var, command=lambda tag=tag: self._onCheck(tag)).pack(
                    anchor="w", pady="1"
                )
                self.vars[tag] = var
            # 前回入力した文字に一致していて、チェックが入っているタグは、自動で入れたものとして扱う
            self.auto_checked = {tag for tag in self._matched() if tag in selected}
            self.text.trace_add("write", self._onText)
            canvas.create_window(0, 0, anchor="nw", window=inner)
            inner.update_idletasks()
            row_h = inner.winfo_reqheight() / len(tags)
            height = int(row_h * min(len(tags), self.MAX_VISIBLE_ROWS))
            canvas.configure(
                width=inner.winfo_reqwidth(), height=height, scrollregion=(0, 0, 0, inner.winfo_reqheight())
            )
            if len(tags) > self.MAX_VISIBLE_ROWS:
                sb = ttk.Scrollbar(list_f, orient="vertical", command=canvas.yview)
                canvas.configure(yscrollcommand=sb.set)
                sb.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            list_f.pack(fill="both", expand=True)

        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady="4")
        buttons_f = ttk.Frame(frame)
        ttk.Button(buttons_f, text="クリア", width="6", command=self._clear).pack(side="left", padx="2")
        ttk.Button(buttons_f, text="閉じる", width="6", command=self.close).pack(side="left", padx="2")
        buttons_f.pack(anchor="e")

        # 画面からはみ出さない位置に表示する
        self.top.update_idletasks()
        w, h = self.top.winfo_reqwidth(), self.top.winfo_reqheight()
        if y + h > self.top.winfo_screenheight() and y_above is not None:
            y = y_above - h
        x = max(0, min(x, self.top.winfo_screenwidth() - w))
        self.top.wm_geometry(f"+{x}+{max(0, y)}")
        self.top.deiconify()

        self.top.bind("<Escape>", lambda e: self.close())
        self.top.bind("<Button-1>", self._onClick)
        self.top.focus_force()
        self.top.grab_set()
        if self.entry is not None:
            self.entry.focus_set()
            self.entry.icursor("end")

    def _selected(self) -> set[str]:
        """チェックが入っているタグの集合を返す"""
        return {tag for tag, var in self.vars.items() if var.get()}

    def _matched(self) -> set[str]:
        """
        入力した文字を含むタグ(文字が空なら、なし)
        """
        text = self.text.get().strip().lower()
        if text == "":
            return set()
        return {tag for tag in self.vars if text in tag.lower()}

    def _onText(self, *args: str) -> None:
        """検索欄の文字が変わったとき: 文字を含むタグに自動でチェックを入れ、on_change を呼ぶ"""
        matched = self._matched()
        # 一致しなくなったタグは、自動で入れたチェックを外す。一致するタグにチェックを入れる
        for tag in self.auto_checked - matched:
            self.vars[tag].set(False)
        for tag in matched:
            if not self.vars[tag].get():
                self.vars[tag].set(True)
                self.auto_checked.add(tag)
        self.auto_checked &= matched
        self._notify()

    def _onCheck(self, tag: str) -> None:
        """チェックボックスを手で切り替えたとき: on_change を呼ぶ。tag: 切り替えたタグ"""
        # 手で変更したタグは、文字を変えてもそのままにする
        self.auto_checked.discard(tag)
        self._notify()

    def _notify(self) -> None:
        """今の選択(選択中のタグの集合, 入力した文字)を on_change に渡す"""
        self.on_change(self._selected(), self.text.get())

    def _clear(self) -> None:
        """クリアボタン: すべてのチェックを外し、検索欄の文字を消す"""
        self.auto_checked = set()
        for var in self.vars.values():
            var.set(False)
        if self.text.get() != "":
            # 文字を消す(_onTextから通知される)
            self.text.set("")
        else:
            self._notify()

    def _onClick(self, event: tk.Event) -> None:
        """クリックしたとき: ポップアップの枠の外であれば閉じる"""
        # grab中は枠外のクリックもこのウィンドウに届くので、枠外なら閉じる
        if self.top is None:
            return
        x, y = event.x_root, event.y_root
        top = self.top
        inside_x = top.winfo_rootx() <= x < top.winfo_rootx() + top.winfo_width()
        inside_y = top.winfo_rooty() <= y < top.winfo_rooty() + top.winfo_height()
        if not (inside_x and inside_y):
            self.close()

    def close(self) -> None:
        """ポップアップを閉じる(閉じるボタン、Esc、枠外のクリック)"""
        if self.top is not None:
            self.top.grab_release()
            self.top.destroy()
            self.top = None


class CommandFilterPopup:
    """
    コマンド一覧の並び順(名前・更新日時・使用頻度)と、名前の部分一致のフィルタを設定するポップアップ。
    変更するたびに on_change(並び順のキー, 入力した文字) を呼ぶ。枠外クリック/Escで閉じる。
    """

    def __init__(
        self,
        widget: tk.Misc,
        x: int,
        y: int,
        sort: str,
        text: str,
        on_change: Callable[[str, str], None],
        y_above: int | None = None,
    ):
        """
        widget: ポップアップの親にする部品(コマンド一覧)
        x, y: 表示位置(左上、画面上の座標)。画面下にはみ出す場合は y_above の上側に表示する
        sort: 開いたときに選んでおく並び順のキー(COMMAND_SORTS のどれか)
        text: 開いたときに検索欄に入れておく文字
        on_change: 変更するたびに呼ぶ関数(並び順のキー, 入力した文字)
        y_above: 上側に表示するときの、下端の位置(None: 上側には表示しない)
        """
        # (x, y): 表示位置(左上)。画面下にはみ出す場合は y_above の上側に表示する
        self.on_change = on_change
        self.top = tk.Toplevel(widget)
        self.top.wm_overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.withdraw()
        frame = ttk.Frame(self.top, relief="solid", borderwidth=1, padding="5")
        frame.pack(fill="both", expand=True)

        search_f = ttk.Frame(frame)
        ttk.Label(search_f, text="検索:").pack(side="left", padx=(0, 4))
        self.text = tk.StringVar(value=text)
        self.entry = ttk.Entry(search_f, textvariable=self.text, width="24")
        self.entry.pack(side="left", expand=True, fill="x")
        search_f.pack(fill="x", pady=(0, 4))
        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady="4")
        ttk.Label(frame, text="並び順").pack(anchor="w")
        self.sort = tk.StringVar(value=sort)
        for key, label, _ in COMMAND_SORTS:
            ttk.Radiobutton(frame, text=label, value=key, variable=self.sort, command=self._notify).pack(
                anchor="w", padx=(8, 0), pady="1"
            )
        self.text.trace_add("write", self._notify)

        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady="4")
        buttons_f = ttk.Frame(frame)
        ttk.Button(buttons_f, text="クリア", width="6", command=self._clear).pack(side="left", padx="2")
        ttk.Button(buttons_f, text="閉じる", width="6", command=self.close).pack(side="left", padx="2")
        buttons_f.pack(anchor="e")

        # 画面からはみ出さない位置に表示する
        self.top.update_idletasks()
        w, h = self.top.winfo_reqwidth(), self.top.winfo_reqheight()
        if y + h > self.top.winfo_screenheight() and y_above is not None:
            y = y_above - h
        x = max(0, min(x, self.top.winfo_screenwidth() - w))
        self.top.wm_geometry(f"+{x}+{max(0, y)}")
        self.top.deiconify()

        self.top.bind("<Escape>", lambda e: self.close())
        self.top.bind("<Return>", lambda e: self.close())
        self.top.bind("<Button-1>", self._onClick)
        self.top.focus_force()
        self.top.grab_set()
        self.entry.focus_set()
        self.entry.icursor("end")

    def _notify(self, *args: str) -> None:
        """今の設定(並び順のキー, 入力した文字)を on_change に渡す(並び順を選んだとき、検索欄の文字が変わったとき)"""
        self.on_change(self.sort.get(), self.text.get())

    def _clear(self) -> None:
        """クリアボタン: 並び順を初期値に戻し、検索欄の文字を消す"""
        self.sort.set(COMMAND_SORT_DEFAULT)
        if self.text.get() != "":
            # 文字を消す(traceから通知される)
            self.text.set("")
        else:
            self._notify()

    def _onClick(self, event: tk.Event) -> None:
        """クリックしたとき: ポップアップの枠の外であれば閉じる"""
        # grab中は枠外のクリックもこのウィンドウに届くので、枠外なら閉じる
        if self.top is None:
            return
        x, y = event.x_root, event.y_root
        top = self.top
        inside_x = top.winfo_rootx() <= x < top.winfo_rootx() + top.winfo_width()
        inside_y = top.winfo_rooty() <= y < top.winfo_rooty() + top.winfo_height()
        if not (inside_x and inside_y):
            self.close()

    def close(self) -> None:
        """ポップアップを閉じる(閉じるボタン、Esc、Enter、枠外のクリック)"""
        if self.top is not None:
            self.top.grab_release()
            self.top.destroy()
            self.top = None
