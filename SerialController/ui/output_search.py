#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
出力画面(Output の Page 1〜3 / Serial / Log)の、文字の検索

検索の欄は、出力画面のタブ領域の右上に重ねて置く(place)。重ねるだけなので、ウィンドウや仕切り線の大きさには影響しない。
- 入力した文字を含む所すべてに印を付け、そのうちの 1 つを「今の位置」として、色を変えて表示する
- 大文字と小文字は、初めは区別しない(「Aa」のボタンで、区別する / しないを切り替える)。
  Log タブで、レベルの絞り込みで隠している行は、対象にしない
- 初めは、いちばん新しい(下の)一致を選ぶ。Enter / ▲ で前(上)へ、Shift+Enter / ▼ で次(下)へ動く
"""
from __future__ import annotations

import tkinter as tk
import tkinter.ttk as ttk
from typing import Callable

# 一致した所すべてに付けるタグと、今の位置に付けるタグ
SEARCH_HIT_TAG = "search_hit"
SEARCH_CURRENT_TAG = "search_current"
# 色は、どのテーマでも同じ(黄色と橙色の背景に、黒い文字)
SEARCH_HIT_COLORS = dict(background="#ffe58a", foreground="#000000")
SEARCH_CURRENT_COLORS = dict(background="#ff9632", foreground="#000000")
# 印を付ける数の上限(これより多い場合は、新しい方から、この数だけ)
SEARCH_MAX_HITS = 2000
# 文字を打ってから、検索するまでの待ち時間(ms)。1 文字ごとに検索し直さないため
SEARCH_DELAY_MS = 150
# 検索の欄を置く位置(タブ領域の右上からの距離。タブの見出しと、スクロールバーに重ならない所)
SEARCH_OFFSET_X = -24
SEARCH_OFFSET_Y = 26


def find_all(widget: tk.Text, query: str, limit: int = SEARCH_MAX_HITS, match_case: bool = False) -> tuple[list, bool]:
    """
    Text の中から、query を含む所をすべて探す(隠している行は対象にしない)。
    match_case: 大文字と小文字を区別するか(False: 区別しない)。
    戻り値: ([(始まり, 終わり), ...](上から順。位置は "行.桁")、上限を超えたか)。
    上限を超えた場合は、新しい方(下)から limit 個を返す
    """
    hits = []
    if not query:
        return hits, False
    count = tk.IntVar(widget)
    index = "1.0"
    while True:
        start = widget.search(query, index, stopindex="end", nocase=not match_case, count=count)
        if not start or count.get() == 0:
            break
        end = widget.index(f"{start}+{count.get()}c")
        hits.append((start, end))
        index = end
    if len(hits) > limit:
        return hits[-limit:], True
    return hits, False


class OutputSearchBar:
    """出力画面の検索の欄(入力欄、件数、前へ / 次へ / 閉じる)"""

    def __init__(
        self, anchor: tk.Misc, get_targets: Callable[[], list], on_typing: Callable[[bool], None] | None = None
    ):
        """
        anchor: 検索の欄を重ねる部品(出力画面のタブ領域)。検索の欄は、その右上に置く
        get_targets: 今、検索の対象にする Text の一覧を返す関数(上にあるものから順)
        on_typing: 検索の欄にフォーカスが入ったとき(True)と、出たとき・閉じたとき(False)に呼ぶ関数
            (打っている間、キーボードでの手動操作を止めるために使う)
        """
        self._anchor = anchor
        self._get_targets = get_targets
        self._on_typing = on_typing
        self._typing = False
        self._hits = []  # [(Text, 始まり, 終わり), ...](上から順)
        self._truncated = False
        self._current = -1
        self._pending = None
        self._tagged = set()
        self.frame = ttk.Frame(anchor.master, relief="solid", borderwidth=1, padding=(4, 2))
        self.text = tk.StringVar()
        self.entry = ttk.Entry(self.frame, textvariable=self.text, width=18)
        self.entry.pack(side="left")
        # 大文字と小文字を区別するか(初めは、区別しない。押し込んだ状態が「区別する」)
        self.match_case = tk.BooleanVar(value=False)
        self.case_button = ttk.Checkbutton(
            self.frame, text="Aa", style="Toolbutton", variable=self.match_case, takefocus=0,
            command=lambda: self.refresh(keep_position=True),
        )
        self.case_button.pack(side="left", padx=(4, 0))
        self.count_label = ttk.Label(self.frame, text="", width=9, anchor="center")
        self.count_label.pack(side="left", padx=(4, 2))
        self.previous_button = ttk.Button(self.frame, text="▲", width=2, command=self.previous)
        self.previous_button.pack(side="left")
        self.next_button = ttk.Button(self.frame, text="▼", width=2, command=self.next)
        self.next_button.pack(side="left")
        self.close_button = ttk.Button(self.frame, text="×", width=2, command=self.close)
        self.close_button.pack(side="left", padx=(2, 0))
        self.text.trace_add("write", self._onTextChanged)
        # (Esc は、ウィンドウ全体では「コマンドの停止」なので、検索の欄の中では、そちらに渡さない)
        for widget in (self.entry, self.case_button, self.previous_button, self.next_button, self.close_button):
            widget.bind("<Escape>", self._onEscape)
        self.entry.bind("<Return>", self._onReturn)
        self.entry.bind("<Shift-Return>", self._onShiftReturn)
        self.entry.bind("<Control-f>", lambda event: "break")
        for widget in (self.entry, self.previous_button, self.next_button, self.close_button):
            widget.bind("<FocusIn>", lambda event: self._setTyping(True), add="+")
            widget.bind("<FocusOut>", lambda event: self._setTyping(False), add="+")

    # ---------------------------------------------------------------- 開く・閉じる

    def isOpen(self) -> bool:
        """検索の欄を表示しているか"""
        return bool(self.frame.winfo_manager())

    def open(self, initial: str | None = None) -> None:
        """
        検索の欄を表示して、入力欄にフォーカスを移す(すでに表示していれば、フォーカスを移すだけ)
        initial: 入力欄に入れる文字(None: 前の文字のまま)
        """
        if not self.isOpen():
            self.frame.place(in_=self._anchor, relx=1.0, x=SEARCH_OFFSET_X, y=SEARCH_OFFSET_Y, anchor="ne")
            self.frame.lift()
        if initial:
            self.text.set(initial)
        self.entry.focus_set()
        self.entry.selection_range(0, "end")
        self.entry.icursor("end")
        self.refresh()

    def close(self) -> None:
        """検索の欄を消し、付けた印をすべて外す"""
        self._cancelPending()
        self._clearTags()
        self._hits, self._current = [], -1
        had_focus = self._typing
        self.frame.place_forget()
        self._setTyping(False)
        if had_focus:
            # フォーカスを出力画面に戻す(続けて Ctrl+F で開き直せるように)
            targets = [widget for widget in self._get_targets() if widget.winfo_exists()]
            if targets:
                targets[0].focus_set()

    # ---------------------------------------------------------------- 検索

    def refresh(self, keep_position: bool = False) -> None:
        """
        今の対象を検索し直して、印を付け直す(表示していないときは、何もしない)
        keep_position: 今の位置の近くを選び直す(False: いちばん新しい一致を選ぶ)
        """
        if not self.isOpen():
            return
        self._cancelPending()
        anchor = self._currentPosition() if keep_position else None
        self._collect()
        if not self._hits:
            self._current = -1
        elif anchor is None:
            self._current = len(self._hits) - 1
        else:
            # 今の位置か、それより後ろで、いちばん近い一致(なければ、最後の一致)
            self._current = next((i for i, hit in enumerate(self._hits) if not self._isBefore(hit, anchor)),
                                 len(self._hits) - 1)
        self._showCurrent()

    def previous(self) -> None:
        """前(上)の一致へ動く(いちばん上からは、いちばん下へ回る)"""
        self._move(-1)

    def next(self) -> None:
        """次(下)の一致へ動く(いちばん下からは、いちばん上へ回る)"""
        self._move(1)

    def _move(self, step: int) -> None:
        """出力が増えているかもしれないので、検索し直してから、今の位置の前 / 次へ動く"""
        if not self.isOpen():
            return
        self._cancelPending()
        anchor = self._currentPosition()
        self._collect()
        if not self._hits:
            self._current = -1
        elif anchor is None:
            self._current = len(self._hits) - 1
        else:
            same = next((i for i, hit in enumerate(self._hits) if hit[0] is anchor[0]
                         and hit[0].compare(hit[1], "==", anchor[1])), None)
            if same is not None:
                self._current = (same + step) % len(self._hits)
            else:
                # 今の位置の一致がなくなっていた場合は、その場所から見て、前 / 次の一致
                after = next((i for i, hit in enumerate(self._hits) if not self._isBefore(hit, anchor)), len(self._hits))
                self._current = (after - 1 if step < 0 else after) % len(self._hits)
        self._showCurrent()

    def _collect(self) -> None:
        """今の対象から一致をすべて探し、印を付ける"""
        self._clearTags()
        query = self.text.get()
        self._hits, self._truncated = [], False
        targets = [widget for widget in self._get_targets() if widget.winfo_exists()]
        for widget in targets:
            hits, truncated = find_all(widget, query, match_case=self.match_case.get())
            self._truncated = self._truncated or truncated
            if not hits:
                continue
            widget.tag_configure(SEARCH_HIT_TAG, **SEARCH_HIT_COLORS)
            widget.tag_configure(SEARCH_CURRENT_TAG, **SEARCH_CURRENT_COLORS)
            # レベルの色やリンクの色より優先し、選択の色よりは下にする
            widget.tag_raise(SEARCH_HIT_TAG)
            widget.tag_raise(SEARCH_CURRENT_TAG)
            widget.tag_raise("sel")
            widget.tag_add(SEARCH_HIT_TAG, *(index for hit in hits for index in hit))
            self._tagged.add(widget)
            self._hits.extend((widget, start, end) for start, end in hits)

    def _showCurrent(self) -> None:
        """今の位置の色を変えて、見える所までスクロールし、件数を表示する"""
        for widget in self._tagged:
            if widget.winfo_exists():
                widget.tag_remove(SEARCH_CURRENT_TAG, "1.0", "end")
        if not self.text.get():
            self.count_label.configure(text="")
        elif not self._hits:
            self.count_label.configure(text="0 件")
        else:
            widget, start, end = self._hits[self._current]
            widget.tag_add(SEARCH_CURRENT_TAG, start, end)
            widget.see(start)
            total = f"{len(self._hits)}+" if self._truncated else str(len(self._hits))
            self.count_label.configure(text=f"{self._current + 1}/{total}")

    def _currentPosition(self) -> tuple | None:
        """
        今の位置(Text, 始まり)。文字が増えたり消えたりしても、タグの位置は一緒に動く。
        なければ None(タブを変えて、今の位置が対象の外になった場合も None)
        """
        targets = self._get_targets()
        for widget in self._tagged:
            if widget.winfo_exists() and widget in targets:
                ranges = widget.tag_ranges(SEARCH_CURRENT_TAG)
                if ranges:
                    return widget, str(ranges[0])
        return None

    def _isBefore(self, hit: tuple, anchor: tuple) -> bool:
        """一致 hit が、位置 anchor より前(上)にあるか(対象の並び順 → Text の中の位置 の順に比べる)"""
        targets = self._get_targets()
        order = {widget: i for i, widget in enumerate(targets)}
        if hit[0] is not anchor[0]:
            return order.get(hit[0], 0) < order.get(anchor[0], 0)
        return hit[0].compare(hit[1], "<", anchor[1])

    def _clearTags(self) -> None:
        """付けた印を、すべて外す"""
        for widget in self._tagged:
            if widget.winfo_exists():
                widget.tag_remove(SEARCH_HIT_TAG, "1.0", "end")
                widget.tag_remove(SEARCH_CURRENT_TAG, "1.0", "end")
        self._tagged = set()

    # ---------------------------------------------------------------- 入力

    def _setTyping(self, typing: bool) -> None:
        """検索の欄にフォーカスがあるかが変わったら、on_typing に知らせる(同じ状態を、続けては知らせない)"""
        if typing != self._typing:
            self._typing = typing
            if self._on_typing is not None:
                self._on_typing(typing)

    def _onTextChanged(self, *args: str) -> None:
        """入力欄の文字が変わったとき: 少し待ってから、検索し直す(続けて打っている間は、待ち直す)"""
        self._cancelPending()
        self._pending = self.frame.after(SEARCH_DELAY_MS, self.refresh)

    def _cancelPending(self) -> None:
        """予約した検索を取り消す"""
        if self._pending is not None:
            self.frame.after_cancel(self._pending)
            self._pending = None

    def _onReturn(self, event: tk.Event) -> str:
        """Enter: 前(上)の一致へ"""
        self.previous()
        return "break"

    def _onShiftReturn(self, event: tk.Event) -> str:
        """Shift+Enter: 次(下)の一致へ"""
        self.next()
        return "break"

    def _onEscape(self, event: tk.Event) -> str:
        """Esc: 検索の欄を閉じる(コマンドの停止には、渡さない)"""
        self.close()
        return "break"
