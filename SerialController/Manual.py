#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
マニュアル(Instruction Manual)のウィンドウ(メニューバーの ヘルプ > Instruction Manual)

- 本文は assets/manual/manual.md に書く
- 書式: 「# 見出し」で1つの項目(左の一覧に並ぶ)が始まる。「## 小見出し」、「- 」で始まる箇条書き、
  「```」で囲んだ行(コード。等幅で表示する)、「![](画像のファイル名)」(画像。manual フォルダからの相対パス)、
  それ以外の行は文章になる
- 文章と箇条書きの中の URL(http:// または https:// で始まる)は、クリックするとブラウザで開くリンクになる
- 左の一覧で項目を選ぶと、右にその項目の説明を表示する
"""
from __future__ import annotations

import os
import re
import tkinter as tk
import webbrowser
import tkinter.ttk as ttk
from dataclasses import dataclass, field
from logging import getLogger, DEBUG, NullHandler
from typing import Callable

from PIL import Image, ImageTk

import Theme

MANUAL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "manual")
MANUAL_FILE = "manual.md"
# スクリプトの書き方の説明(Web ブラウザ版の Instruction Manual と共通。GitHub 上でも、そのまま読める)
SCRIPTING_FILE = "scripting.md"
# スクリプトの説明を差し込む場所(この見出しの項目の前。無ければ最後)
SCRIPTING_BEFORE = "困ったとき"
TEXT_FONT = ("Yu Gothic UI", 9)
TITLE_FONT = ("Yu Gothic UI", 13, "bold")
HEADING_FONT = ("Yu Gothic UI", 10, "bold")
CODE_FONT = ("Consolas", 9)
# 画像の左右の余白。説明の欄に収まらない幅の画像は、欄の幅に合わせて縮めて表示する
IMAGE_PADX = 8
# リンクにする URL(かっこ・日本語の文字・空白の手前まで。Web ブラウザ版の extras.js と同じ決まり)
URL_PATTERN = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'*+,;=%]+")
LINK_TAG = "link"


def split_links(text: str) -> list[tuple[str, str | None]]:
    """文章を、ふつうの文字と URL に分ける: [(文字, URL または None)]。URL の終わりの「.」「,」は、URL に含めない"""
    parts = []
    position = 0
    for found in URL_PATTERN.finditer(text):
        url = found.group().rstrip(".,;:")
        if found.start() > position:
            parts.append((text[position : found.start()], None))
        parts.append((url, url))
        position = found.start() + len(url)
    if position < len(text):
        parts.append((text[position:], None))
    return parts


@dataclass
class Topic:
    """
    マニュアルの1つの項目(左の一覧の1行)
    """

    title: str
    # (種類, 文章) の並び。種類は "h"(小見出し) / "li"(箇条書き) / "code"(コード) / "img"(画像のファイル名) / "p"(文章)
    lines: list[tuple[str, str]] = field(default_factory=list)


def load_topics() -> list[Topic]:
    """
    本文のファイルを読み、項目の並びにする(ファイルがない場合は空)。
    スクリプトの書き方の説明(別のファイル)は、SCRIPTING_BEFORE の項目の前に差し込む
    """
    topics = _load_file(MANUAL_FILE)
    scripting = _load_file(SCRIPTING_FILE)
    index = next((i for i, topic in enumerate(topics) if topic.title == SCRIPTING_BEFORE), len(topics))
    return topics[:index] + scripting + topics[index:]


def _load_file(name: str) -> list[Topic]:
    """
    本文のファイル(Markdown)を1つ読み、項目の並びにする(ファイルがない場合は空)
    「# 見出し」で項目が始まり、「## 」は小見出し、「- 」は箇条書き、「![](ファイル名)」は画像、``` で囲んだ行はコードになる
    name: MANUAL_DIR の中のファイル名
    """
    try:
        with open(os.path.join(MANUAL_DIR, name), encoding="utf-8-sig") as file:
            lines = [line.rstrip("\r\n") for line in file]
    except OSError:
        return []
    topics = []
    in_code = False
    for line in lines:
        text = line.strip()
        if text.startswith("```"):
            in_code = not in_code
        elif in_code:
            if topics:
                # コードは字下げを残す
                topics[-1].lines.append(("code", line.rstrip()))
        elif text.startswith("# "):
            topics.append(Topic(text[2:].strip()))
        elif text == "" or not topics:
            continue
        elif text.startswith("![") and text.endswith(")") and "](" in text:
            topics[-1].lines.append(("img", text[text.index("](") + 2 : -1].strip()))
        elif text.startswith("## "):
            topics[-1].lines.append(("h", text[3:].strip()))
        elif text.startswith("- "):
            topics[-1].lines.append(("li", text[2:].strip()))
        else:
            topics[-1].lines.append(("p", text))
    return topics


def load_guide(name: str) -> list[Topic]:
    """
    本文のファイル(Markdown)を 1 つ読み、項目の並びにする(ファイルがない場合は空)。
    Instruction Manual とは別の説明(補助ツールの説明など)を、ManualWindow に表示するときに使う
    name: MANUAL_DIR の中のファイル名
    """
    return _load_file(name)


class ManualWindow:
    """
    左に項目の一覧、右に選んだ項目の説明を表示する
    """

    def __init__(self, root: tk.Tk | tk.Toplevel, topics: list[Topic] | None = None, title: str = "Instruction Manual"):
        """
        root: メインウィンドウ(この位置を基準に表示する)
        topics: 表示する項目(None なら、このアプリケーションの Instruction Manual)
        title: ウィンドウのタイトル
        """
        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

        self.root = root
        self.topics = load_topics() if topics is None else topics
        self._close_handler = None
        # 表示中の画像(参照を持っていないと表示されない)
        self._photos = []

        self.window = tk.Toplevel(root)
        self.window.title(title)
        root_geometry = root.geometry().split("+")
        self.window.geometry("%+d%+d" % (80 + int(root_geometry[1]), 40 + int(root_geometry[2])))

        body = ttk.Frame(self.window, padding=10)
        body.pack(fill="both", expand=True)
        content = ttk.Frame(body)
        content.pack(fill="both", expand=True)
        # 左: 項目の一覧
        list_f = ttk.Frame(content)
        self.listbox = tk.Listbox(list_f)
        self.listbox.configure(width=26, height=28, exportselection=False, font=TEXT_FONT, activestyle="none")
        list_sb = ttk.Scrollbar(list_f, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=list_sb.set)
        for topic in self.topics:
            self.listbox.insert("end", " " + topic.title)
        list_sb.pack(side="right", fill="y")
        self.listbox.pack(side="left", fill="y")
        list_f.pack(side="left", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self._onSelect)
        # 右: 選んだ項目の説明(選択してコピーできる)
        text_f = ttk.Frame(content)
        self.text = tk.Text(text_f)
        self.text.configure(
            width=84, height=28, wrap="char", relief="solid", borderwidth=1, padx=12, pady=8, font=TEXT_FONT, cursor="arrow"
        )
        text_sb = ttk.Scrollbar(text_f, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=text_sb.set)
        text_sb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        text_f.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.text.tag_configure("title", font=TITLE_FONT, spacing3=8)
        self.text.tag_configure("h", font=HEADING_FONT, spacing1=12, spacing3=4)
        self.text.tag_configure("p", lmargin1=2, lmargin2=2, spacing3=3)
        self.text.tag_configure("li", lmargin1=8, lmargin2=21, spacing3=3)
        self.text.tag_configure(
            "code", font=CODE_FONT, background=Theme.color("code"), lmargin1=10, lmargin2=10, rmargin=10, wrap="none"
        )
        # リンク(URL): クリックすると、ブラウザで開く
        self.text.tag_configure(LINK_TAG, foreground=Theme.color("link"), underline=True)
        self.text.tag_bind(LINK_TAG, "<Enter>", lambda event: self.text.configure(cursor="hand2"))
        self.text.tag_bind(LINK_TAG, "<Leave>", lambda event: self.text.configure(cursor=""))
        self.text.tag_bind(LINK_TAG, "<Button-1>", self._openLink)
        self._links = {}
        # 右クリックメニュー(Copy)
        self.context_menu = tk.Menu(self.text, tearoff=0)
        self.context_menu.add_command(label="Copy", command=self._copy)
        self.text.bind("<Button-3>", self._showContextMenu)

        footer = ttk.Frame(body)
        self.ok_button = ttk.Button(footer, text="OK", width=10, command=self._close)
        self.ok_button.pack(side="right")
        footer.pack(fill="x", pady=(10, 0))

        self.window.bind("<Escape>", lambda event: self._close())
        self.window.update_idletasks()
        self.window.minsize(self.window.winfo_reqwidth(), 300)
        if self.topics:
            self.listbox.selection_set(0)
            self.showTopic(0)
        else:
            self.text.insert("end", "(マニュアルの本文がありません)")
            self.text.configure(state="disabled")
        self._logger.debug("Create manual window")

    def _onSelect(self, event: tk.Event | None = None) -> None:
        """左の一覧で項目を選んだとき: その項目の説明を表示する"""
        selection = self.listbox.curselection()
        if selection:
            self.showTopic(selection[0])

    def showTopic(self, index: int) -> None:
        """
        項目の説明(見出し・文章・箇条書き・コード・画像)を、右の欄に表示する
        index: 項目の番号(0始まり)
        """
        topic = self.topics[index]
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", topic.title + "\n", "title")
        self._photos = []
        self._links = {}
        for kind, text in topic.lines:
            if kind == "img":
                photo = self._loadImage(text)
                if photo is not None:
                    self.text.image_create("end", image=photo, padx=IMAGE_PADX, pady=6)
                    self.text.insert("end", "\n", "p")
                continue
            if kind not in ("p", "li"):
                self.text.insert("end", text + "\n", kind)
                continue
            if kind == "li":
                self.text.insert("end", "・", kind)
            for part, url in split_links(text):
                if url is None:
                    self.text.insert("end", part, kind)
                else:
                    # URL ごとのタグで、どの URL かを覚える
                    name = f"{LINK_TAG}-{len(self._links)}"
                    self._links[name] = url
                    self.text.insert("end", part, (kind, LINK_TAG, name))
            self.text.insert("end", "\n", kind)
        self.text.configure(state="disabled")
        self.text.yview_moveto(0)

    def _openLink(self, event: tk.Event) -> None:
        """リンクをクリックしたとき: その URL を、ブラウザで開く"""
        for name in self.text.tag_names(f"@{event.x},{event.y}"):
            if name in self._links:
                self._logger.debug(f"Open link: {self._links[name]}")
                webbrowser.open(self._links[name], 2)
                return

    def _loadImage(self, name: str) -> ImageTk.PhotoImage | None:
        """
        画像を読み込む(表示できる幅より大きい場合は縮める)。読み込めない場合はNone
        name: MANUAL_DIR の中の画像のファイル名
        """
        try:
            image = Image.open(os.path.join(MANUAL_DIR, name))
            image.load()
        except OSError as e:
            self._logger.warning(f"Failed to load the image: {name} ({e})")
            return None
        # 説明の欄の中の幅(欄の余白・枠・画像の余白を除く)
        self.text.update_idletasks()
        width = self.text.winfo_width() if self.text.winfo_ismapped() else self.text.winfo_reqwidth()
        max_width = max(width - 2 * (int(self.text.cget("padx")) + IMAGE_PADX) - 8, 100)
        if image.width > max_width:
            height = round(image.height * max_width / image.width)
            image = image.resize((max_width, height), Image.LANCZOS)
        photo = ImageTk.PhotoImage(image, master=self.window)
        self._photos.append(photo)
        return photo

    def _showContextMenu(self, event: tk.Event) -> None:
        """説明の欄を右クリックしたとき: メニュー(Copy)を表示する(文字を選択していない場合、Copy は無効)"""
        has_selection = bool(self.text.tag_ranges("sel"))
        self.context_menu.entryconfigure("Copy", state="normal" if has_selection else "disabled")
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _copy(self) -> None:
        """右クリックメニューの Copy: 選択している文字をクリップボードにコピーする"""
        if self.text.tag_ranges("sel"):
            self.window.clipboard_clear()
            self.window.clipboard_append(self.text.get("sel.first", "sel.last"))

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
            self._logger.debug("Manual window destroyed")
