#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
タグの編集画面(Commands タブの、タグの絵のボタンで開く)

左でコマンドを選び、右で、そのコマンドのタグを足したり外したりする。保存を押すと、変更したコマンドのファイルの
TAGS を、まとめて書き換える(services/tag_editor.py)。
"""
from __future__ import annotations

import os
import tkinter as tk
import tkinter.font as tkfont
import tkinter.ttk as ttk
from logging import getLogger, DEBUG, NullHandler
from tkinter import messagebox
from typing import TYPE_CHECKING, Callable

import Theme
from services import tag_editor
from services.tag_editor import CHANGED, TagEditError, TagSource

if TYPE_CHECKING:
    from CommandLoader import CommandEntry

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

TITLE = "タグの編集"
COMMAND_TYPES = ("Python", "Mcu")
# 一覧の行の先頭に付ける印(編集できない / 変更がある)
MARK_LOCKED = "⚠ "
MARK_CHANGED = "● "
# タグを並べる欄の、幅(文字数)と高さ(行数)
FLOW_WIDTH = 46
FLOW_HEIGHT = 4
# タグの一括変更の、結果の知らせの欄の行数(いちばん長い知らせが収まる数)
BULK_MESSAGE_LINES = 3


class TagEditorWindow:
    """
    タグの編集画面
    """

    def __init__(
        self,
        root: tk.Tk,
        get_entries: Callable[[str], list],
        command_type: str = "Python",
        selected_name: str | None = None,
        on_saved: Callable[[], None] | None = None,
    ):
        """
        root: メインウィンドウ(この位置を基準に表示する)
        get_entries: コマンドの種類("Python" / "Mcu")から、今のコマンドの一覧(CommandEntry)を返す関数
        command_type: 初めに表示する種類。selected_name: 初めに選んでおくコマンドの名前(なければ、先頭)
        on_saved: 保存した後に呼ぶ関数(メイン画面の一覧を読み直すのに使う)
        """
        self.root = root
        self.get_entries = get_entries
        self.on_saved = on_saved
        # キー(種類, コマンドの名前)ごとの、コマンド・ファイルの状態・編集前のタグ・フォルダーのタグ
        self.entries: dict[tuple, CommandEntry] = {}
        self.sources: dict[tuple, TagSource] = {}
        self.initial: dict[tuple, list] = {}
        self.folder_tags: dict[tuple, list] = {}
        # 変更したコマンドの、今のタグ(保存していないもの)
        self.pending: dict[tuple, list] = {}
        self.selected: tuple | None = None

        self.window = tk.Toplevel(root)
        self.window.title(TITLE)
        root_geometry = root.geometry().split("+")
        self.window.geometry("%+d%+d" % (80 + int(root_geometry[1]), 60 + int(root_geometry[2])))
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda event: self.close())

        body = ttk.Frame(self.window, padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        # 左: コマンドの一覧
        left = ttk.Frame(body)
        left.grid(column=0, row=0, sticky="nsew", padx=(0, 10))
        left.columnconfigure(2, weight=1)
        left.rowconfigure(1, weight=1)
        self.command_type = tk.StringVar(value=command_type if command_type in COMMAND_TYPES else COMMAND_TYPES[0])
        self.type_cb = ttk.Combobox(left, textvariable=self.command_type, values=COMMAND_TYPES, state="readonly", width=8)
        self.type_cb.grid(column=0, row=0, sticky="w", pady=(0, 4))
        self.type_cb.bind("<<ComboboxSelected>>", lambda event: self.refreshList())
        self.filter_text = tk.StringVar()
        self.filter_entry = ttk.Entry(left, textvariable=self.filter_text)
        ttk.Label(left, text="絞り込み:").grid(column=1, row=0, padx=(10, 0), pady=(0, 4))
        self.filter_entry.grid(column=2, row=0, sticky="ew", padx=(4, 0), pady=(0, 4))
        self.filter_text.trace_add("write", lambda *args: self.refreshList())
        self.tree = ttk.Treeview(left, columns=("command", "tags"), height=14, selectmode="browse", show="headings")
        self.tree.heading("command", anchor="w", text="Command")
        self.tree.heading("tags", anchor="w", text="Tags")
        self.tree.column("command", anchor="w", stretch=True, width=300)
        self.tree.column("tags", anchor="w", stretch=True, width=170)
        self.tree.tag_configure("locked", foreground=Theme.color("muted"))
        scrollbar = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(column=0, columnspan=3, row=1, sticky="nsew")
        scrollbar.grid(column=3, row=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self._onSelect)
        ttk.Label(left, text=f"{MARK_LOCKED}編集できない  {MARK_CHANGED}保存していない変更がある",
                  foreground=Theme.color("muted")).grid(column=0, columnspan=4, row=2, sticky="w", pady=(4, 0))
        # タグの一括変更(表示している種類の、すべてのコマンドが対象。保存するまでは、ファイルを書き換えない)
        bulk = ttk.LabelFrame(left, text="タグの一括変更(この種類のすべてのコマンド)", padding=(6, 4))
        bulk.grid(column=0, columnspan=4, row=3, sticky="ew", pady=(8, 0))
        bulk.columnconfigure(3, weight=1)
        ttk.Label(bulk, text="タグ:").grid(column=0, row=0, sticky="w")
        self.bulk_tag = tk.StringVar()
        self.bulk_tag_cb = ttk.Combobox(bulk, textvariable=self.bulk_tag, state="readonly", width=16)
        self.bulk_tag_cb.grid(column=1, row=0, sticky="w", padx=(4, 8))
        ttk.Label(bulk, text="新しい名前:").grid(column=2, row=0, sticky="w")
        self.bulk_new = tk.StringVar()
        self.bulk_new_entry = ttk.Entry(bulk, textvariable=self.bulk_new, width=16)
        self.bulk_new_entry.grid(column=3, row=0, sticky="ew", padx=(4, 8))
        self.bulk_new_entry.bind("<Return>", lambda event: self.renameTag())
        self.bulk_rename_button = ttk.Button(bulk, text="名前を変更", width=10, command=self.renameTag)
        self.bulk_rename_button.grid(column=4, row=0)
        self.bulk_delete_button = ttk.Button(bulk, text="削除", width=6, command=self.deleteTag)
        self.bulk_delete_button.grid(column=5, row=0, padx=(4, 0))
        # 結果の知らせ。文の長さでウィンドウの高さが変わらないように、決まった行数の高さを取っておく
        self.bulk_message = tk.StringVar()
        line_height = tkfont.nametofont("TkDefaultFont").metrics("linespace")
        bulk_message_f = ttk.Frame(bulk, height=line_height * BULK_MESSAGE_LINES + 2)
        bulk_message_f.grid(column=0, columnspan=6, row=1, sticky="ew", pady=(4, 0))
        bulk_message_f.pack_propagate(False)
        ttk.Label(bulk_message_f, textvariable=self.bulk_message, wraplength=470, justify="left").pack(anchor="nw")

        # 右: 選んだコマンドのタグ
        right = ttk.Frame(body)
        right.grid(column=1, row=0, sticky="nsew")
        self.name_text = tk.StringVar()
        ttk.Label(right, textvariable=self.name_text, wraplength=340, justify="left").pack(anchor="w")
        ttk.Label(right, text="付いているタグ(押すと外す):", foreground=Theme.color("muted")).pack(anchor="w", pady=(8, 2))
        self.tags_flow = self._createFlow(right)
        ttk.Label(right, text="タグを足す:", foreground=Theme.color("muted")).pack(anchor="w", pady=(8, 2))
        add_f = ttk.Frame(right)
        add_f.pack(fill="x")
        self.new_tag = tk.StringVar()
        self.new_tag_entry = ttk.Entry(add_f, textvariable=self.new_tag)
        self.new_tag_entry.pack(side="left", fill="x", expand=True)
        self.new_tag_entry.bind("<Return>", lambda event: self.addTag())
        self.add_button = ttk.Button(add_f, text="追加", width=6, command=self.addTag)
        self.add_button.pack(side="left", padx=(6, 0))
        ttk.Label(right, text="ほかのコマンドで使っているタグ(押すと足す):", foreground=Theme.color("muted")).pack(
            anchor="w", pady=(8, 2)
        )
        self.suggest_flow = self._createFlow(right)
        self.message = tk.StringVar()
        self.message_label = ttk.Label(
            right, textvariable=self.message, wraplength=340, justify="left", foreground=Theme.color("danger")
        )
        self.message_label.pack(anchor="w", pady=(8, 0))

        # 下: 変更の件数と、ボタン
        bottom = ttk.Frame(body)
        bottom.grid(column=0, columnspan=2, row=1, sticky="ew", pady=(10, 0))
        self.status = tk.StringVar()
        ttk.Label(bottom, textvariable=self.status).pack(side="left")
        ttk.Button(bottom, text="閉じる", width=9, command=self.close).pack(side="right")
        self.save_button = ttk.Button(bottom, text="保存", width=9, command=self.save)
        self.save_button.pack(side="right", padx=4)
        self.revert_button = ttk.Button(bottom, text="元に戻す", width=9, command=self.revert)
        self.revert_button.pack(side="right")

        self.load()
        self.refreshList(select=selected_name)
        self.filter_entry.focus_set()
        _logger.debug("Create tag editor window")

    # ---------------------------------------------------------------- 部品

    def _createFlow(self, parent: tk.Misc) -> tk.Text:
        """タグのボタンを、幅に合わせて折り返して並べる欄(書き込めない Text に、ボタンを埋め込む)を作って返す"""
        flow = tk.Text(
            parent, width=FLOW_WIDTH, height=FLOW_HEIGHT, wrap="char", borderwidth=0, highlightthickness=0,
            background=Theme.color("bg"), cursor="arrow", takefocus=0, spacing1=2, spacing3=2,
        )
        flow.configure(state="disabled")
        flow.pack(fill="x")
        flow.buttons = []
        return flow

    def _fillFlow(self, flow: tk.Text, items: list) -> None:
        """
        欄の中身を作り直す。items: (ボタンの文字, 押したときに呼ぶ関数)の一覧。関数が None のものは、押せないボタンにする
        """
        flow.configure(state="normal")
        flow.delete("1.0", "end")
        for button in flow.buttons:
            button.destroy()
        flow.buttons = []
        for text, command in items:
            button = ttk.Button(flow, text=text, takefocus=0)
            if command is None:
                button.state(["disabled"])
            else:
                button.configure(command=command)
            flow.window_create("end", window=button, padx=2, pady=1)
            flow.buttons.append(button)
        flow.configure(state="disabled")

    # ---------------------------------------------------------------- 読み込み

    def load(self) -> None:
        """
        コマンドの一覧と、ファイルに書いてあるタグを読み直す。
        保存していない変更は、そのコマンドがまだあり、編集できる場合に限り、残す
        """
        self.entries, self.sources, self.initial, self.folder_tags = {}, {}, {}, {}
        for command_type in COMMAND_TYPES:
            for entry in self.get_entries(command_type):
                key = (command_type, entry.name)
                own, folder = tag_editor.split_entry_tags(entry)
                path = os.path.abspath(entry.file_path) if entry.file_path else ""
                self.entries[key] = entry
                self.sources[key] = tag_editor.read_source(path, entry.class_name)
                # 一覧に出ているタグ(同じファイルの基底クラスから引き継いだものを含む)を、編集前のタグとする
                self.initial[key] = [str(tag) for tag in own]
                self.folder_tags[key] = [str(tag) for tag in folder]
        self.pending = {
            key: tags for key, tags in self.pending.items()
            if key in self.sources and self.sources[key].editable and tags != self.initial[key]
        }

    def tagsOf(self, key: tuple) -> list:
        """そのコマンドの、今のタグ(保存していない変更があれば、変更した後のもの。フォルダーのタグは含まない)"""
        return list(self.pending.get(key, self.initial[key]))

    def _knownTags(self, command_type: str) -> list:
        """その種類のコマンドで使っているタグ(保存していない変更を含む。フォルダーのタグは除く)を、名前の順に返す"""
        known = set()
        for key in self.entries:
            if key[0] == command_type and self.sources[key].editable:
                known.update(self.tagsOf(key))
        return sorted(known)

    # ---------------------------------------------------------------- 一覧

    def refreshList(self, select: str | None = None) -> None:
        """
        左の一覧を、種類と絞り込みの文字に合わせて作り直す。
        select: 選ぶコマンドの名前(None なら、今選んでいるもの。一覧になければ、先頭)
        """
        command_type = self.command_type.get()
        if select is None and self.selected is not None and self.selected[0] == command_type:
            select = self.selected[1]
        text = self.filter_text.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        self._rows = {}
        for key, entry in self.entries.items():
            if key[0] != command_type:
                continue
            tags = self.tagsOf(key) + self.folder_tags[key]
            if text and text not in entry.name.lower() and not any(text in tag.lower() for tag in tags):
                continue
            item = self.tree.insert("", "end", values=self._rowValues(key), tags=self._rowTags(key))
            self._rows[item] = key
        items = self.tree.get_children()
        target = next((item for item in items if self._rows[item][1] == select), items[0] if items else None)
        if target is None:
            self.selected = None
            self.showSelected()
        else:
            self.tree.selection_set(target)
            self.tree.see(target)
        self.updateStatus()
        self._refreshBulkTags()

    def _rowValues(self, key: tuple) -> tuple:
        """一覧の 1 行の表示(印を付けた名前, タグ)"""
        mark = MARK_LOCKED if not self.sources[key].editable else (MARK_CHANGED if key in self.pending else "")
        return mark + key[1], ", ".join(self.tagsOf(key) + self.folder_tags[key])

    def _rowTags(self, key: tuple) -> tuple:
        """一覧の 1 行の見た目(編集できないものは、薄い色)"""
        return () if self.sources[key].editable else ("locked",)

    def _onSelect(self, event: tk.Event | None = None) -> None:
        """一覧でコマンドを選んだとき: 右に、そのコマンドのタグを表示する"""
        selection = self.tree.selection()
        self.selected = self._rows.get(selection[0]) if selection else None
        self.showSelected()

    # ---------------------------------------------------------------- 右の欄

    def showSelected(self, message: str = "") -> None:
        """
        右の欄を、選んでいるコマンドに合わせて作り直す。
        message: 下に表示する知らせ(空なら、編集できないコマンドのときだけ、その理由を表示する)
        """
        key = self.selected
        if key is None:
            self.name_text.set("コマンドを選んでください。")
            self._fillFlow(self.tags_flow, [])
            self._fillFlow(self.suggest_flow, [])
            self._setEditable(False)
            self.message.set(message)
            return
        source = self.sources[key]
        self.name_text.set(key[1])
        tags = self.tagsOf(key)
        chips = [(f"{tag}  ×", (lambda tag=tag: self.removeTag(tag)) if source.editable else None) for tag in tags]
        chips += [(f"{tag} (フォルダー)", None) for tag in self.folder_tags[key]]
        self._fillFlow(self.tags_flow, chips)
        suggestions = []
        if source.editable:
            suggestions = [(f"+ {tag}", lambda tag=tag: self.addTag(tag)) for tag in self._knownTags(key[0]) if tag not in tags]
        self._fillFlow(self.suggest_flow, suggestions)
        self._setEditable(source.editable)
        self.message.set(message or ("" if source.editable else f"このコマンドのタグは編集できません。{source.reason}"))

    def _setEditable(self, editable: bool) -> None:
        """タグを足す欄とボタンを、使える・使えない状態にする"""
        state = ["!disabled"] if editable else ["disabled"]
        self.new_tag_entry.state(state)
        self.add_button.state(state)

    def _setTags(self, key: tuple, tags: list) -> None:
        """コマンドのタグを tags にする(編集前と同じなら、変更なしに戻す)。一覧の行と、右の欄と、件数を合わせる"""
        if tags == self.initial[key]:
            self.pending.pop(key, None)
        else:
            self.pending[key] = tags
        for item, row_key in self._rows.items():
            if row_key == key:
                self.tree.item(item, values=self._rowValues(key))
        self.showSelected()
        self.updateStatus()
        self._refreshBulkTags()

    def addTag(self, tag: str | None = None) -> None:
        """
        選んでいるコマンドにタグを足す。
        tag: 足すタグ(None なら、入力欄の文字。使えない文字のときは、理由を表示して足さない)
        """
        key = self.selected
        if key is None or not self.sources[key].editable:
            return
        tags = self.tagsOf(key)
        tag, error = tag_editor.check_tag(self.new_tag.get() if tag is None else tag, tags + self.folder_tags[key])
        if error:
            self.showSelected(error)
            return
        self.new_tag.set("")
        self._setTags(key, tags + [tag])

    def removeTag(self, tag: str) -> None:
        """選んでいるコマンドから、タグを外す"""
        key = self.selected
        if key is None or not self.sources[key].editable:
            return
        self._setTags(key, [t for t in self.tagsOf(key) if t != tag])

    # ---------------------------------------------------------------- 一括変更

    def _refreshBulkTags(self) -> None:
        """一括変更で選べるタグ(表示している種類で、編集できるコマンドが使っているタグ)を、今の状態に合わせる"""
        known = self._knownTags(self.command_type.get())
        self.bulk_tag_cb.configure(values=known)
        if self.bulk_tag.get() not in known:
            self.bulk_tag.set(known[0] if known else "")
        state = ["!disabled"] if known else ["disabled"]
        for widget in (self.bulk_new_entry, self.bulk_rename_button, self.bulk_delete_button):
            widget.state(state)

    def _replaceTagEverywhere(self, old: str, new: str | None) -> tuple[int, int]:
        """
        表示している種類のすべてのコマンドで、タグ old を new に変える(new が None なら、外す)。保存はしない。
        戻り値: (変えたコマンドの数, 編集できないので変えなかったコマンドの数)
        """
        command_type = self.command_type.get()
        changed = skipped = 0
        for key in self.entries:
            if key[0] != command_type:
                continue
            tags = self.tagsOf(key)
            if old not in tags:
                continue
            if not self.sources[key].editable:
                skipped += 1
                continue
            tags = tag_editor.replace_tag(tags, old, new)
            if tags == self.initial[key]:
                self.pending.pop(key, None)
            else:
                self.pending[key] = tags
            changed += 1
        self.refreshList()
        return changed, skipped

    def _bulkResult(self, text: str, changed: int, skipped: int) -> None:
        """一括変更の結果を、欄の下に表示する"""
        if skipped:
            text += f" 編集できない {skipped} 件は、変えていません。"
        if changed:
            text += " 「保存」を押すまでは、ファイルを書き換えません(「元に戻す」で取り消せます)。"
        self.bulk_message.set(text)

    def renameTag(self, old: str | None = None, new: str | None = None) -> None:
        """
        タグの名前を、表示している種類のすべてのコマンドで変える(保存はしない)。
        old: 変えるタグ(None なら、選んでいるタグ)。new: 新しい名前(None なら、入力欄の文字)。
        新しい名前のタグをすでに持っているコマンドでは、1 つにまとめる
        """
        old = self.bulk_tag.get() if old is None else old
        if not old:
            return
        new, error = tag_editor.check_new_name(old, self.bulk_new.get() if new is None else new)
        if error:
            self.bulk_message.set(error)
            return
        changed, skipped = self._replaceTagEverywhere(old, new)
        self.bulk_new.set("")
        self.bulk_tag.set(new if new in self.bulk_tag_cb.cget("values") else self.bulk_tag.get())
        self._bulkResult(f"{changed} 件のコマンドで、「{old}」を「{new}」に変えました。", changed, skipped)

    def deleteTag(self, old: str | None = None) -> None:
        """
        タグを、表示している種類のすべてのコマンドから外す(保存はしない)。old: 外すタグ(None なら、選んでいるタグ)
        """
        old = self.bulk_tag.get() if old is None else old
        if not old:
            return
        changed, skipped = self._replaceTagEverywhere(old, None)
        self._bulkResult(f"{changed} 件のコマンドから、「{old}」を外しました。", changed, skipped)

    # ---------------------------------------------------------------- 保存

    def updateStatus(self) -> None:
        """変更の件数の表示と、保存・元に戻すのボタンの状態を合わせる"""
        count = len(self.pending)
        self.status.set(f"変更 {count} 件" if count else "変更はありません")
        state = ["!disabled"] if count else ["disabled"]
        self.save_button.state(state)
        self.revert_button.state(state)

    def revert(self) -> None:
        """元に戻す: 保存していない変更を、すべて取り消す"""
        self.pending = {}
        self.refreshList()

    def save(self) -> None:
        """
        保存: 変更したコマンドのファイルを書き換える(同じファイルのコマンドは、まとめて 1 回で書く)。
        書き込めなかったファイルは、理由を警告として表示する。
        画面を開いた後に書き換えられていたファイルは、上書きせず、今の内容を読み直す(そのファイルの変更は取り消す)
        """
        files: dict[str, dict] = {}
        for key, tags in self.pending.items():
            files.setdefault(self.sources[key].file_path, {})[key] = tags
        saved, failures = 0, []
        for path, changes in files.items():
            digest = self.sources[next(iter(changes))].digest
            try:
                tag_editor.save_tags(path, digest, {self.entries[key].class_name: tags for key, tags in changes.items()})
            except TagEditError as error:
                names = "、".join(key[1] for key in changes)
                failures.append(f"・{names}\n  {os.path.basename(path)}: {error}")
                _logger.warning(f"Failed to save tags: {path} ({error.kind}: {error})")
                if error.kind != CHANGED:
                    # 書き込めなかっただけなら、変更を残す(原因を取り除いて、もう一度保存できる)
                    continue
            else:
                saved += len(changes)
            for key in changes:
                self.pending.pop(key, None)
        # メイン画面の一覧も、今のファイルの内容に合わせる(保存できなかったファイルが、書き換えられていた場合を含む)
        if self.on_saved is not None:
            self.on_saved()
        self.load()
        self.refreshList()
        if failures:
            self.showSelected()
            messagebox.showwarning(
                TITLE,
                "次のコマンドのタグは、保存できませんでした。\n\n" + "\n".join(failures)
                + "\n\n「書き換えられています」と出たファイルは、今の内容を読み直しました。もう一度、編集してください。",
                parent=self.window,
            )
        elif saved:
            self.showSelected()
            self.status.set(f"{saved} 件のコマンドのタグを保存しました")

    # ---------------------------------------------------------------- ウィンドウ

    def isOpen(self) -> bool:
        """ウィンドウが開いているか"""
        return bool(self.window.winfo_exists())

    def lift(self) -> None:
        """ウィンドウを前面に出す"""
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def close(self) -> None:
        """閉じる: 保存していない変更があるときは、確かめてから閉じる"""
        if self.pending and not messagebox.askyesno(
            TITLE, f"保存していない変更が {len(self.pending)} 件あります。保存せずに閉じますか?", parent=self.window
        ):
            return
        self.window.destroy()
        _logger.debug("Close tag editor window")
