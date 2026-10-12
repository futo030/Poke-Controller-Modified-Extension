#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
実行リスト(コマンドの連続実行)の編集と、開始・停止の予約のウィンドウ

メニューの コマンド > 実行リスト... / 開始と停止の予約... から開く(同じウィンドウの、別のタブ)。
- 実行リスト タブ: リストを作って保存する。保存したリストは、Python コマンドの一覧に「名前 (実行リスト)」として並ぶ
- 予約 タブ: メイン画面で選んでいるコマンドの開始と、実行中のコマンドの停止を、時刻や分で予約する
中身(保存、順に実行する処理、予約)は services/run_list.py と services/run_schedule.py にある。
"""
from __future__ import annotations

import datetime
import tkinter as tk
import tkinter.font as tkfont
import tkinter.ttk as ttk
from logging import getLogger, DEBUG, NullHandler
from tkinter import messagebox
from typing import Callable

import Theme
from services import run_list, run_schedule
from services.run_list import RunItem, RunList
from services.run_schedule import RunSchedule

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

TITLE = "実行リストと予約"
TAB_LISTS = 0
TAB_SCHEDULE = 1
NEW_LIST_NAME = "新しいリスト"
ON_ERROR_LABELS = {run_list.ON_ERROR_STOP: "リストを中止する", run_list.ON_ERROR_NEXT: "次のコマンドへ進む"}
# 予約の表示を更新する間隔(ms)と、知らせの欄の行数
REFRESH_MS = 500
MESSAGE_LINES = 2


class RunListWindow:
    """実行リストの編集と、開始・停止の予約のウィンドウ"""

    def __init__(
        self,
        root: tk.Tk,
        schedule: RunSchedule,
        get_selected: Callable[[], tuple],
        on_saved: Callable[[], None],
        is_running: Callable[[], bool],
        tab: int = TAB_LISTS,
    ):
        """
        root: メインウィンドウ(この位置を基準に表示する)
        schedule: 開始と停止の予約(アプリが持っているもの。このウィンドウを閉じても、予約は残る)
        get_selected: メイン画面で選んでいるコマンド(種別, 名前)を返す関数(選んでいなければ、名前は空文字)
        on_saved: 実行リストを保存した後に呼ぶ関数(メイン画面のコマンドの一覧を読み直す)
        is_running: コマンドを実行中かを返す関数
        tab: 初めに表示するタブ(TAB_LISTS / TAB_SCHEDULE)
        """
        self.root = root
        self.schedule = schedule
        self.get_selected = get_selected
        self.on_saved = on_saved
        self.is_running = is_running
        # 保存してある実行リストと、今編集しているもの(保存していない新しいリストは、lists に入っていない)
        self.lists: list = []
        self.editing: RunList | None = None
        self.editing_index: int | None = None
        self.dirty = False
        self._loading = False

        self.window = tk.Toplevel(root)
        self.window.title(TITLE)
        root_geometry = root.geometry().split("+")
        self.window.geometry("%+d%+d" % (100 + int(root_geometry[1]), 80 + int(root_geometry[2])))
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self._buildListsTab()
        self._buildScheduleTab()
        self.notebook.select(tab)
        self.reloadLists()
        self._refresh_job = None
        self._refreshSchedule()
        _logger.debug("Create run list window")

    # ================================================================ 実行リスト タブ

    def _buildListsTab(self) -> None:
        """実行リスト タブの部品を作る"""
        tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab, text="実行リスト")
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)

        # 左: 保存してあるリスト
        left = ttk.Frame(tab)
        left.grid(column=0, row=0, sticky="ns", padx=(0, 10))
        ttk.Label(left, text="保存してあるリスト:").pack(anchor="w")
        self.list_box = tk.Listbox(left, width=24, height=14, exportselection=False)
        self.list_box.pack(fill="y", expand=True, pady=(2, 4))
        self.list_box.bind("<<ListboxSelect>>", self._onSelectList)
        buttons = ttk.Frame(left)
        buttons.pack(fill="x")
        self.new_button = ttk.Button(buttons, text="新規", width=6, command=self.newList)
        self.new_button.pack(side="left")
        self.copy_button = ttk.Button(buttons, text="複製", width=6, command=self.copyList)
        self.copy_button.pack(side="left", padx=4)
        self.delete_button = ttk.Button(buttons, text="削除", width=6, command=self.deleteList)
        self.delete_button.pack(side="left")

        # 右: 選んだリストの中身
        right = ttk.Frame(tab)
        right.grid(column=1, row=0, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        name_f = ttk.Frame(right)
        name_f.grid(column=0, row=0, sticky="ew")
        ttk.Label(name_f, text="名前:").pack(side="left")
        self.name = tk.StringVar()
        self.name_entry = ttk.Entry(name_f, textvariable=self.name, width=30)
        self.name_entry.pack(side="left", padx=(4, 0))
        ttk.Label(name_f, text=f"(一覧には「名前{run_list.NAME_SUFFIX}」と出ます)", foreground=Theme.color("muted")).pack(
            side="left", padx=(8, 0)
        )
        self.name.trace_add("write", self._onEdited)

        tree_f = ttk.Frame(right)
        tree_f.grid(column=0, row=1, sticky="nsew", pady=(6, 4))
        tree_f.columnconfigure(0, weight=1)
        tree_f.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            tree_f, columns=("type", "command", "repeat", "limit"), height=9, selectmode="browse", show="headings"
        )
        for column, text, width, stretch in (("type", "種類", 60, False), ("command", "コマンド", 330, True),
                                             ("repeat", "回数", 50, False), ("limit", "制限時間", 80, False)):
            self.tree.heading(column, anchor="w", text=text)
            self.tree.column(column, anchor="w", width=width, stretch=stretch)
        scrollbar = ttk.Scrollbar(tree_f, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(column=0, row=0, sticky="nsew")
        scrollbar.grid(column=1, row=0, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self._onSelectItem)

        item_buttons = ttk.Frame(right)
        item_buttons.grid(column=0, row=2, sticky="ew")
        self.add_button = ttk.Button(item_buttons, text="メイン画面で選んでいるコマンドを足す", command=self.addSelectedCommand)
        self.add_button.pack(side="left")
        self.up_button = ttk.Button(item_buttons, text="上へ", width=5, command=lambda: self.moveItem(-1))
        self.up_button.pack(side="left", padx=(8, 0))
        self.down_button = ttk.Button(item_buttons, text="下へ", width=5, command=lambda: self.moveItem(1))
        self.down_button.pack(side="left", padx=4)
        self.remove_button = ttk.Button(item_buttons, text="外す", width=5, command=self.removeItem)
        self.remove_button.pack(side="left")

        # 選んだ行の、回数と制限時間
        row_f = ttk.LabelFrame(right, text="選んだ行", padding=(6, 4))
        row_f.grid(column=0, row=3, sticky="ew", pady=(6, 0))
        ttk.Label(row_f, text="回数:").pack(side="left")
        self.repeat = tk.StringVar()
        self.repeat_entry = ttk.Entry(row_f, textvariable=self.repeat, width=6)
        self.repeat_entry.pack(side="left", padx=(4, 12))
        ttk.Label(row_f, text="制限時間 (分):").pack(side="left")
        self.limit = tk.StringVar()
        self.limit_entry = ttk.Entry(row_f, textvariable=self.limit, width=8)
        self.limit_entry.pack(side="left", padx=(4, 6))
        ttk.Label(row_f, text="空なら、終わるまで待つ。Mcu コマンドは必ず入れる", foreground=Theme.color("muted")).pack(side="left")
        self.repeat.trace_add("write", self._onItemEdited)
        self.limit.trace_add("write", self._onItemEdited)

        # リスト全体の設定
        option_f = ttk.LabelFrame(right, text="リスト全体", padding=(6, 4))
        option_f.grid(column=0, row=4, sticky="ew", pady=(6, 0))
        ttk.Label(option_f, text="コマンドの間の待ち時間 (秒):").grid(column=0, row=0, sticky="w")
        self.interval = tk.StringVar()
        self.interval_entry = ttk.Entry(option_f, textvariable=self.interval, width=6)
        self.interval_entry.grid(column=1, row=0, sticky="w", padx=(4, 16))
        ttk.Label(option_f, text="繰り返す回数:").grid(column=2, row=0, sticky="w")
        self.loops = tk.StringVar()
        self.loops_entry = ttk.Entry(option_f, textvariable=self.loops, width=6)
        self.loops_entry.grid(column=3, row=0, sticky="w", padx=(4, 6))
        ttk.Label(option_f, text="0 なら、Stop を押すまで", foreground=Theme.color("muted")).grid(column=4, row=0, sticky="w")
        ttk.Label(option_f, text="エラーで終わったコマンドがあったとき:").grid(column=0, columnspan=2, row=1, sticky="w", pady=(4, 0))
        self.on_error = tk.StringVar()
        self.on_error_cb = ttk.Combobox(
            option_f, textvariable=self.on_error, state="readonly", width=18, values=list(ON_ERROR_LABELS.values())
        )
        self.on_error_cb.grid(column=2, columnspan=3, row=1, sticky="w", pady=(4, 0))
        self.interval.trace_add("write", self._onEdited)
        self.loops.trace_add("write", self._onEdited)
        self.on_error.trace_add("write", self._onEdited)

        # 下: 知らせと、保存
        bottom = ttk.Frame(tab)
        bottom.grid(column=0, columnspan=2, row=1, sticky="ew", pady=(8, 0))
        self.list_message = tk.StringVar()
        self._messageLabel(bottom, self.list_message).pack(side="left", fill="x", expand=True)
        ttk.Button(bottom, text="閉じる", width=9, command=self.close).pack(side="right")
        self.save_button = ttk.Button(bottom, text="保存", width=9, command=self.saveList)
        self.save_button.pack(side="right", padx=4)

    def _messageLabel(self, parent: tk.Misc, variable: tk.StringVar) -> ttk.Frame:
        """知らせの欄を作って返す(文の長さでウィンドウの高さが変わらないように、決まった行数の高さを取っておく)"""
        line_height = tkfont.nametofont("TkDefaultFont").metrics("linespace")
        frame = ttk.Frame(parent, height=line_height * MESSAGE_LINES + 2)
        frame.pack_propagate(False)
        ttk.Label(frame, textvariable=variable, wraplength=520, justify="left").pack(anchor="nw")
        return frame

    # ---------------------------------------------------------------- リストの読み込みと選択

    def reloadLists(self, select: str | None = None) -> None:
        """保存してある実行リストを読み直して、左の一覧に出す。select: 選ぶリストの名前(None なら、先頭)"""
        self.lists = run_list.load_lists()
        self.list_box.delete(0, "end")
        for item in self.lists:
            self.list_box.insert("end", item.name)
        index = next((i for i, item in enumerate(self.lists) if item.name == select), 0 if self.lists else None)
        if index is None:
            self._edit(None, None)
        else:
            self.list_box.selection_set(index)
            self._edit(self.lists[index], index)

    def _copyOf(self, source: RunList) -> RunList:
        """編集用の写しを作る(保存するまで、元のリストは変えない)"""
        return RunList(
            name=source.name,
            items=[RunItem(i.command_type, i.name, i.repeat, i.limit_minutes) for i in source.items],
            interval_seconds=source.interval_seconds,
            on_error=source.on_error,
            loops=source.loops,
        )

    def _edit(self, source: RunList | None, index: int | None) -> None:
        """右の欄に、そのリストの写しを表示する(source が None なら、何も編集していない状態にする)"""
        self._loading = True
        self.editing = self._copyOf(source) if source is not None else None
        self.editing_index = index
        editing = self.editing
        self.name.set(editing.name if editing else "")
        self.interval.set(f"{editing.interval_seconds:g}" if editing else "")
        self.loops.set(str(editing.loops) if editing else "")
        self.on_error.set(ON_ERROR_LABELS[editing.on_error] if editing else "")
        self._fillTree()
        self.dirty = False
        self._loading = False
        self._updateStates()
        self.list_message.set("" if editing else "「新規」を押して、実行リストを作ってください。")

    def _onSelectList(self, event: tk.Event | None = None) -> None:
        """左の一覧でリストを選んだとき: 保存していない変更があれば、確かめてから切り替える"""
        selection = self.list_box.curselection()
        if not selection or selection[0] == self.editing_index:
            return
        if not self._confirmDiscard():
            self.list_box.selection_clear(0, "end")
            if self.editing_index is not None:
                self.list_box.selection_set(self.editing_index)
            return
        self._edit(self.lists[selection[0]], selection[0])

    def _confirmDiscard(self) -> bool:
        """保存していない変更を捨ててよいかを確かめる(変更がなければ、聞かずに True)"""
        if not self.dirty:
            return True
        return messagebox.askyesno(TITLE, "保存していない変更があります。捨ててよいですか?", parent=self.window)

    def _fillTree(self, select: int | None = None) -> None:
        """行の一覧を作り直す。select: 選ぶ行の番号(None なら、選ばない)"""
        self.tree.delete(*self.tree.get_children())
        for index, item in enumerate(self.editing.items if self.editing else []):
            self.tree.insert("", "end", iid=str(index), values=(
                item.command_type, item.name, item.repeat, run_list.describe_limit(item.limit_minutes)))
        if select is not None and self.tree.exists(str(select)):
            self.tree.selection_set(str(select))
            self.tree.see(str(select))
        self._onSelectItem()

    def _selectedItem(self) -> int | None:
        """選んでいる行の番号(選んでいなければ None)"""
        selection = self.tree.selection()
        return int(selection[0]) if selection else None

    def _onSelectItem(self, event: tk.Event | None = None) -> None:
        """行を選んだとき: 下の「選んだ行」の欄に、その行の回数と制限時間を出す"""
        index = self._selectedItem()
        was_loading, self._loading = self._loading, True
        if index is None or self.editing is None:
            self.repeat.set("")
            self.limit.set("")
        else:
            item = self.editing.items[index]
            self.repeat.set(str(item.repeat))
            self.limit.set("" if item.limit_minutes is None else f"{item.limit_minutes:g}")
        self._loading = was_loading
        self._updateStates()

    def _updateStates(self) -> None:
        """ボタンと入力欄を、使える・使えない状態にする"""
        has_list = self.editing is not None
        has_item = has_list and self._selectedItem() is not None

        def state(enabled: bool) -> list:
            return ["!disabled"] if enabled else ["disabled"]

        for widget in (self.name_entry, self.add_button, self.interval_entry, self.loops_entry, self.save_button):
            widget.state(state(has_list))
        self.on_error_cb.state(state(has_list) + (["readonly"] if has_list else []))
        for widget in (self.up_button, self.down_button, self.remove_button, self.repeat_entry, self.limit_entry):
            widget.state(state(has_item))
        saved = self.editing_index is not None
        self.copy_button.state(state(saved))
        self.delete_button.state(state(has_list))

    # ---------------------------------------------------------------- 編集

    def _onEdited(self, *args: str) -> None:
        """名前やリスト全体の設定を変えたとき: 保存していない変更がある、と覚える"""
        if self._loading or self.editing is None:
            return
        self.dirty = True

    def _onItemEdited(self, *args: str) -> None:
        """選んだ行の回数・制限時間を変えたとき: 読める値なら、その行に入れる(読めない間は、前の値のまま)"""
        index = self._selectedItem()
        if self._loading or self.editing is None or index is None:
            return
        item = self.editing.items[index]
        try:
            repeat = int(self.repeat.get().strip())
            limit = run_list.parse_number(self.limit.get(), allow_empty=True)
        except ValueError:
            self.dirty = True
            return
        item.repeat, item.limit_minutes = repeat, limit
        self.tree.item(str(index), values=(item.command_type, item.name, item.repeat, run_list.describe_limit(limit)))
        self.dirty = True

    def newList(self) -> None:
        """新規: 空の実行リストを作る(保存するまでは、左の一覧に出ない)"""
        if not self._confirmDiscard():
            return
        names = [item.name for item in self.lists]
        name, number = NEW_LIST_NAME, 1
        while name in names:
            number += 1
            name = f"{NEW_LIST_NAME} {number}"
        self.list_box.selection_clear(0, "end")
        self._edit(RunList(name=name), None)
        self.dirty = True
        self.list_message.set("メイン画面でコマンドを選び、「メイン画面で選んでいるコマンドを足す」を押してください。")
        self.name_entry.focus_set()
        self.name_entry.selection_range(0, "end")

    def copyList(self) -> None:
        """複製: 選んでいるリストの写しを、新しいリストとして編集する"""
        if self.editing_index is None or not self._confirmDiscard():
            return
        source = self._copyOf(self.lists[self.editing_index])
        names = [item.name for item in self.lists]
        base, number = f"{source.name} のコピー", 1
        source.name = base
        while source.name in names:
            number += 1
            source.name = f"{base} {number}"
        self.list_box.selection_clear(0, "end")
        self._edit(source, None)
        self.dirty = True

    def deleteList(self) -> None:
        """削除: 選んでいるリストを消して保存する(保存していない新しいリストは、編集をやめるだけ)"""
        if self.editing is None:
            return
        if self.editing_index is None:
            if self._confirmDiscard():
                self.reloadLists()
            return
        name = self.lists[self.editing_index].name
        if not messagebox.askyesno(TITLE, f"実行リスト「{name}」を削除しますか?", parent=self.window):
            return
        remaining = [item for i, item in enumerate(self.lists) if i != self.editing_index]
        if self._write(remaining):
            self.dirty = False
            self.reloadLists()
            self.list_message.set(f"「{name}」を削除しました。")

    def addSelectedCommand(self) -> None:
        """メイン画面で選んでいるコマンドを、リストの最後(行を選んでいれば、その下)に足す"""
        if self.editing is None:
            return
        command_type, name = self.get_selected()
        if not name:
            self.list_message.set("メイン画面の Commands タブで、コマンドを選んでください。")
            return
        item = RunItem(command_type=command_type, name=name)
        error = run_list.check_item(item)
        if error and command_type != run_list.MCU:
            self.list_message.set(error)
            return
        index = self._selectedItem()
        position = len(self.editing.items) if index is None else index + 1
        self.editing.items.insert(position, item)
        self.dirty = True
        self._fillTree(select=position)
        self.list_message.set("Mcu コマンドは、「選んだ行」の制限時間を入れてください。" if command_type == run_list.MCU else "")
        if command_type == run_list.MCU:
            self.limit_entry.focus_set()

    def moveItem(self, step: int) -> None:
        """選んでいる行を、上(-1)か下(+1)へ動かす"""
        index = self._selectedItem()
        if self.editing is None or index is None or not 0 <= index + step < len(self.editing.items):
            return
        items = self.editing.items
        items[index], items[index + step] = items[index + step], items[index]
        self.dirty = True
        self._fillTree(select=index + step)

    def removeItem(self) -> None:
        """選んでいる行を、リストから外す"""
        index = self._selectedItem()
        if self.editing is None or index is None:
            return
        del self.editing.items[index]
        self.dirty = True
        self._fillTree(select=min(index, len(self.editing.items) - 1) if self.editing.items else None)

    # ---------------------------------------------------------------- 保存

    def _collect(self) -> str:
        """入力欄の値を、編集中のリストに入れる。使えない値があれば、その理由を返す(なければ空文字)"""
        editing = self.editing
        editing.name = self.name.get().strip()
        try:
            editing.interval_seconds = run_list.parse_number(self.interval.get())
        except ValueError:
            return "コマンドの間の待ち時間は、数で入力してください。"
        try:
            editing.loops = int(self.loops.get().strip())
        except ValueError:
            return "繰り返す回数は、整数で入力してください。"
        editing.on_error = next((key for key, label in ON_ERROR_LABELS.items() if label == self.on_error.get()),
                                run_list.ON_ERROR_STOP)
        index = self._selectedItem()
        if index is not None:
            # 選んでいる行の欄に、読めない値が入ったままになっていないか
            try:
                int(self.repeat.get().strip())
                run_list.parse_number(self.limit.get(), allow_empty=True)
            except ValueError:
                return f"{index + 1} 行目: 回数は整数、制限時間は数で入力してください。"
        others = [item.name for i, item in enumerate(self.lists) if i != self.editing_index]
        return run_list.check_list(editing, others)

    def _write(self, lists: list) -> bool:
        """実行リストをファイルに書き、メイン画面の一覧を読み直す。書けたかを返す(書けないときは、警告を出す)"""
        try:
            run_list.save_lists(lists)
        except OSError as error:
            messagebox.showwarning(TITLE, f"実行リストを保存できませんでした。\n{error}", parent=self.window)
            return False
        self.on_saved()
        return True

    def saveList(self) -> None:
        """保存: 編集中のリストを確かめて、ファイルに書く。メイン画面の Python の一覧に「名前 (実行リスト)」として出る"""
        if self.editing is None:
            return
        error = self._collect()
        if error:
            self.list_message.set(error)
            return
        saved = self._copyOf(self.editing)
        lists = list(self.lists)
        if self.editing_index is None:
            lists.append(saved)
        else:
            lists[self.editing_index] = saved
        if not self._write(lists):
            return
        self.dirty = False
        self.reloadLists(select=saved.name)
        self.list_message.set(f"保存しました。メイン画面の Python の一覧の「{saved.display_name}」を Start で実行できます。")

    # ================================================================ 予約 タブ

    def _buildScheduleTab(self) -> None:
        """予約 タブの部品を作る"""
        tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab, text="予約")
        tab.columnconfigure(0, weight=1)

        start_f = ttk.LabelFrame(tab, text="開始の予約", padding=(8, 6))
        start_f.grid(column=0, row=0, sticky="ew")
        start_f.columnconfigure(3, weight=1)
        ttk.Label(start_f, text="開始するコマンド:").grid(column=0, row=0, sticky="w")
        self.target_text = tk.StringVar()
        ttk.Label(start_f, textvariable=self.target_text, wraplength=420, justify="left").grid(
            column=1, columnspan=3, row=0, sticky="w", padx=(4, 0)
        )
        ttk.Label(start_f, text="(メイン画面の Commands タブで選んでいるコマンド。実行リストも選べます)",
                  foreground=Theme.color("muted")).grid(column=0, columnspan=4, row=1, sticky="w", pady=(0, 6))
        self.start_mode = tk.StringVar(value="clock")
        ttk.Radiobutton(start_f, text="時刻 (時:分):", value="clock", variable=self.start_mode).grid(column=0, row=2, sticky="w")
        self.start_clock = tk.StringVar()
        self.start_clock_entry = ttk.Entry(start_f, textvariable=self.start_clock, width=8)
        self.start_clock_entry.grid(column=1, row=2, sticky="w", padx=(4, 0))
        ttk.Radiobutton(start_f, text="今から (分後):", value="minutes", variable=self.start_mode).grid(column=0, row=3, sticky="w")
        self.start_minutes = tk.StringVar()
        self.start_minutes_entry = ttk.Entry(start_f, textvariable=self.start_minutes, width=8)
        self.start_minutes_entry.grid(column=1, row=3, sticky="w", padx=(4, 0))
        self.reserve_start_button = ttk.Button(start_f, text="開始を予約", width=12, command=self.reserveStart)
        self.reserve_start_button.grid(column=2, row=2, rowspan=2, padx=(16, 4))
        self.cancel_start_button = ttk.Button(start_f, text="取り消す", width=9, command=self.schedule.cancel_start)
        self.cancel_start_button.grid(column=3, row=2, rowspan=2, sticky="w")
        self.start_status = tk.StringVar()
        ttk.Label(start_f, textvariable=self.start_status, wraplength=520, justify="left").grid(
            column=0, columnspan=4, row=4, sticky="w", pady=(6, 0)
        )
        for entry, mode in ((self.start_clock_entry, "clock"), (self.start_minutes_entry, "minutes")):
            entry.bind("<FocusIn>", lambda event, mode=mode: self.start_mode.set(mode), add="+")
            entry.bind("<Return>", lambda event: self.reserveStart())

        stop_f = ttk.LabelFrame(tab, text="停止の予約", padding=(8, 6))
        stop_f.grid(column=0, row=1, sticky="ew", pady=(8, 0))
        stop_f.columnconfigure(3, weight=1)
        self.stop_mode = tk.StringVar(value="clock")
        ttk.Radiobutton(stop_f, text="時刻 (時:分):", value="clock", variable=self.stop_mode).grid(column=0, row=0, sticky="w")
        self.stop_clock = tk.StringVar()
        self.stop_clock_entry = ttk.Entry(stop_f, textvariable=self.stop_clock, width=8)
        self.stop_clock_entry.grid(column=1, row=0, sticky="w", padx=(4, 0))
        ttk.Radiobutton(stop_f, text="開始から (分後):", value="minutes", variable=self.stop_mode).grid(column=0, row=1, sticky="w")
        self.stop_minutes = tk.StringVar()
        self.stop_minutes_entry = ttk.Entry(stop_f, textvariable=self.stop_minutes, width=8)
        self.stop_minutes_entry.grid(column=1, row=1, sticky="w", padx=(4, 0))
        self.reserve_stop_button = ttk.Button(stop_f, text="停止を予約", width=12, command=self.reserveStop)
        self.reserve_stop_button.grid(column=2, row=0, rowspan=2, padx=(16, 4))
        self.cancel_stop_button = ttk.Button(stop_f, text="取り消す", width=9, command=self.schedule.cancel_stop)
        self.cancel_stop_button.grid(column=3, row=0, rowspan=2, sticky="w")
        ttk.Label(stop_f, text="「開始から」は、実行中なら今から、開始を予約していれば、その開始から数えます。",
                  foreground=Theme.color("muted")).grid(column=0, columnspan=4, row=2, sticky="w", pady=(4, 0))
        self.stop_status = tk.StringVar()
        ttk.Label(stop_f, textvariable=self.stop_status, wraplength=520, justify="left").grid(
            column=0, columnspan=4, row=3, sticky="w", pady=(6, 0)
        )
        for entry, mode in ((self.stop_clock_entry, "clock"), (self.stop_minutes_entry, "minutes")):
            entry.bind("<FocusIn>", lambda event, mode=mode: self.stop_mode.set(mode), add="+")
            entry.bind("<Return>", lambda event: self.reserveStop())

        ttk.Label(tab, text="予約は、このウィンドウを閉じても残ります。アプリを終了すると消えます。\n"
                            "予約した時刻に PC がスリープしていると、予約は正常に動作しません。", foreground=Theme.color("muted"),
                  justify="left").grid(column=0, row=2, sticky="w", pady=(8, 0))
        bottom = ttk.Frame(tab)
        bottom.grid(column=0, row=3, sticky="ew", pady=(8, 0))
        self.schedule_message = tk.StringVar()
        self._messageLabel(bottom, self.schedule_message).pack(side="left", fill="x", expand=True)
        ttk.Button(bottom, text="閉じる", width=9, command=self.close).pack(side="right")

    def _confirmSleepWarning(self) -> bool:
        """予約する前に、PC がスリープしていると正常に動作しないことを警告する(すでに予約があるときは、出さない)"""
        if self.schedule.pending:
            return True
        return messagebox.askokcancel(TITLE, run_schedule.SLEEP_WARNING + "\n\n予約しますか?", icon="warning", parent=self.window)

    def reserveStart(self) -> None:
        """開始を予約: メイン画面で選んでいるコマンドを、入力した時刻(または分後)に開始する"""
        command_type, name = self.get_selected()
        if not name:
            self.schedule_message.set("メイン画面の Commands タブで、開始するコマンドを選んでください。")
            return
        now = datetime.datetime.now()
        try:
            if self.start_mode.get() == "clock":
                when = run_schedule.parse_clock(self.start_clock.get(), now)
            else:
                when = now + datetime.timedelta(minutes=run_schedule.parse_minutes(self.start_minutes.get()))
        except ValueError as error:
            self.schedule_message.set(str(error))
            return
        if not self._confirmSleepWarning():
            return
        self.schedule.reserve_start(when, command_type, name)
        self.schedule_message.set("")
        self._refreshSchedule()

    def reserveStop(self) -> None:
        """停止を予約: 入力した時刻、または開始からの分で、実行中のコマンドを止める"""
        now = datetime.datetime.now()
        try:
            if self.stop_mode.get() == "clock":
                when, minutes = run_schedule.parse_clock(self.stop_clock.get(), now), None
            else:
                when, minutes = None, run_schedule.parse_minutes(self.stop_minutes.get())
        except ValueError as error:
            self.schedule_message.set(str(error))
            return
        if minutes is not None and not self.is_running() and self.schedule.start_at is None:
            self.schedule_message.set("コマンドを実行中か、開始を予約しているときだけ、「開始から」の停止を予約できます。")
            return
        if not self._confirmSleepWarning():
            return
        if when is not None:
            self.schedule.reserve_stop_at(when)
            error = ""
        else:
            error = self.schedule.reserve_stop_after(minutes)
        self.schedule_message.set(error)
        self._refreshSchedule()

    def _refreshSchedule(self) -> None:
        """予約 タブの表示(開始するコマンド、今の予約と残り時間)を、今の状態に合わせる(REFRESH_MS ごとに呼ばれる)"""
        if not self.isOpen():
            return
        command_type, name = self.get_selected()
        self.target_text.set(f"[{command_type}] {name}" if name else "(選んでいません)")
        start, stop = self.schedule.describe()
        self.start_status.set("今の予約: " + start)
        self.stop_status.set("今の予約: " + stop)
        self.cancel_start_button.state(["!disabled"] if self.schedule.start_at is not None else ["disabled"])
        has_stop = self.schedule.stop_at is not None or self.schedule.stop_after_minutes is not None
        self.cancel_stop_button.state(["!disabled"] if has_stop else ["disabled"])
        self._refresh_job = self.window.after(REFRESH_MS, self._refreshSchedule)

    # ================================================================ ウィンドウ

    def showTab(self, tab: int) -> None:
        """タブを切り替える(TAB_LISTS / TAB_SCHEDULE)"""
        self.notebook.select(tab)

    def isOpen(self) -> bool:
        """ウィンドウが開いているか"""
        return bool(self.window.winfo_exists())

    def lift(self) -> None:
        """ウィンドウを前面に出す"""
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def close(self) -> None:
        """閉じる: 保存していない変更があるときは、確かめてから閉じる(予約は、残る)"""
        if not self._confirmDiscard():
            return
        if self._refresh_job is not None:
            self.window.after_cancel(self._refresh_job)
            self._refresh_job = None
        self.window.destroy()
        _logger.debug("Close run list window")
