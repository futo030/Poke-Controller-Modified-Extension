#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Commands タブ: コマンドの一覧・絞り込み・実行、ショートカット、履歴
"""
from __future__ import annotations

import tkinter as tk
import os
import platform
import subprocess
from typing import TYPE_CHECKING, Callable, Iterable
import tkinter.ttk as ttk
import tkinter.messagebox as tkmsg
import Settings
import Utility as util
from Commands import PythonCommandBase
from Commands.CommandBase import Command
from ui.constants import SHORTCUT_COLUMNS, SHORTCUT_TEXT_LENGTH, COMMAND_SORT_DEFAULT, COMMAND_SORTS
from ui.popups import TagFilterPopup, CommandFilterPopup
from ui.run_list_window import TAB_LISTS, TAB_SCHEDULE, RunListWindow
from ui.script_creator import ScriptCreatorWindow
from ui.tag_editor import TagEditorWindow
from services import command_catalog, command_service
from services.run_schedule import RunSchedule, format_remaining
from services.sleep_watch import SleepWatch
from UiDispatcher import UiDispatcher
from services.command_service import CommandLoadError, CommandService

if TYPE_CHECKING:
    from CommandLoader import CombinedLoader, CommandEntry, CommandLoader
    from services.script_creator import ScriptResult

# 開始と停止の予約の時刻を確かめる間隔(ms)
SCHEDULE_TICK_MS = 250
# スクリプトを読み込んでいる間の、Start ボタンの文字と、Output に出す文
COMMAND_LOADING_TEXT = "Loading..."
COMMAND_LOADING_MESSAGE = "スクリプトを読み込んでいます...(初回は、時間がかかることがあります)"


class CommandPanelMixin:
    """
    Commands タブ: コマンドの一覧・絞り込み・実行、ショートカット、履歴
    (PokeControllerApp に取り込んで使う。部品や設定は self の属性として、ほかのファイルと共有する)
    """

    def _buildCommandsTab(self) -> None:
        """
        Commands タブの部品を作る(起動時に1回だけ呼ぶ)
        """
        self.commands_f = ttk.Frame(self.controller_nb)
        self.select_commands_f = ttk.Frame(self.commands_f)
        self.command_nb = ttk.Notebook(self.select_commands_f)
        self.py_f = ttk.Frame(self.command_nb)
        # コマンド一覧(Command/Tags)。Tags列の見出しクリックでタグによるフィルタを表示する
        self.command_tag_filters = {"Python": set(), "Mcu": set()}
        # Tagsの見出しのポップアップに入力した文字(部分一致するタグに自動でチェックを入れる)
        self.command_tag_texts = {"Python": "", "Mcu": ""}
        # Command列の見出しクリックで設定する、並び順と名前のフィルタ(部分一致)
        self.command_sorts = {"Python": COMMAND_SORT_DEFAULT, "Mcu": COMMAND_SORT_DEFAULT}
        self.command_name_filters = {"Python": "", "Mcu": ""}
        self.command_mtimes = {}
        # HistoryのLast Runの並び順(Trueなら新しい順)
        self.history_descending = True
        self.command_trees = {}
        self.py_tv = self._createCommandTree(self.py_f, "Python")
        self.py_f.pack(fill="x", side="top")
        self.py_f.columnconfigure(0, weight=1)
        self.command_nb.add(self.py_f, padding="5", text="Python Command")
        self.mcu_f = ttk.Frame(self.command_nb)
        self.mcu_tv = self._createCommandTree(self.mcu_f, "Mcu")
        self.mcu_f.pack(fill="x", side="top")
        self.mcu_f.columnconfigure(0, weight=1)
        self.command_nb.add(self.mcu_f, padding="5", text="Mcu Command")
        self.shortcut_f = ttk.Frame(self.command_nb)
        # ショートカットボタンを SHORTCUT_ROWS行 x SHORTCUT_COLUMNS列 に並べる
        self.shortcut_buttons = {}
        self.shortcut_button_texts = {}
        for num in range(1, Settings.GuiSettings.SHORTCUT_NUM + 1):
            button = ttk.Button(self.shortcut_f)
            text = tk.StringVar(value=f"Shortcut({num})")
            button.configure(textvariable=text, width="12")
            button.grid(
                column=(num - 1) % SHORTCUT_COLUMNS, padx="5", pady="2", row=(num - 1) // SHORTCUT_COLUMNS, sticky="ew"
            )
            button.configure(command=lambda num=num: self.startShortcutPlay(num=num))
            # 右クリックメニュー(Open file)
            button.bind("<Button-3>", lambda event, num=num: self.showShortcutContextMenu(event, num))
            if platform.system() == "Darwin":
                button.bind("<Button-2>", lambda event, num=num: self.showShortcutContextMenu(event, num))
            self.shortcut_buttons[num] = button
            self.shortcut_button_texts[num] = text
        for col in range(SHORTCUT_COLUMNS):
            self.shortcut_f.columnconfigure(col, weight=1, uniform="shortcut")
        self.command_nb.add(self.shortcut_f, padding="5", text="Shortcut")
        self.history_f = ttk.Frame(self.command_nb)
        self.history_tv = ttk.Treeview(self.history_f)
        self.history_tv.configure(
            columns=("command", "last_run"), height="3", selectmode="browse", show="headings"
        )
        self.history_tv.heading("command", anchor="w", text="Command")
        self.history_tv.heading("last_run", anchor="w", text="Last Run ▼", command=self.toggleHistorySort)
        self.history_tv.column("command", anchor="w", stretch=True, width="350")
        self.history_tv.column("last_run", anchor="w", stretch=False, width="150")
        self.history_sb = ttk.Scrollbar(self.history_f, orient="vertical", command=self.history_tv.yview)
        self.history_tv.configure(yscrollcommand=self.history_sb.set)
        self.history_sb.pack(fill="y", side="right")
        self.history_tv.pack(expand="true", fill="both", side="left")
        self.history_tv.bind("<ButtonRelease-1>", self.onClickHistory, add="")
        # 右クリックメニュー(Shortcut > #n に設定)
        self.history_context_menu = self._bindShortcutContextMenu(self.history_tv, self._historyCommandOf)
        # 右クリックメニュー(Delete: 選択している履歴を消す / Delete (ALL): すべての履歴を消す)
        self.history_context_menu.add_separator()
        self.history_context_menu.add_command(label="Delete", command=self.deleteHistory)
        self.history_context_menu.add_command(label="Delete (ALL)", command=self.deleteAllHistory)
        self.command_nb.add(self.history_f, padding="5", text="History")
        # (幅は、右のボタンの列を「Loading...」が収まる幅にした分、狭くしてある。Commands タブに必要な幅は、変えない)
        self.command_nb.configure(padding="0", width="562")
        self.command_nb.pack(padx="5", pady="5", side="left")
        self.command_nb.pack(fill="both", expand=True, padx="5", pady="5", side="left")
        self.command_nb.bind("<<NotebookTabChanged>>", self.controllButtons, add="")
        # ノートブックの右に、押す順(Start/Pause/Reload/ディレクトリを開く)にボタンを縦に並べる
        self.action_commands_f = ttk.Frame(self.select_commands_f)
        self.start_button = ttk.Button(self.action_commands_f)
        # 幅は、スクリプトの読み込み中の表示(Loading...)が収まる文字数
        self.start_button.configure(text="Start", width="9")
        self.start_button.pack(fill="x", pady="2", side="top")
        self.start_button.configure(command=self.startPlay)
        self.pause_button = ttk.Button(self.action_commands_f)
        self.pause_button.configure(text="Pause", width="6")
        self.pause_button.pack(fill="x", pady="2", side="top")
        self.pause_button.configure(command=self.pausePlay)
        self.reload_command_button = ttk.Button(self.action_commands_f)
        self.reload_command_button.configure(text="Reload", width="6")
        self.reload_command_button.pack(fill="x", pady="2", side="top")
        self.reload_command_button.configure(command=self.reloadCommands)
        self.open_command_dir_button = ttk.Button(self.action_commands_f)
        self.open_command_dir_button.config(image=self.open_folder_img)
        self.open_command_dir_button.pack(fill="x", pady="2", side="top")
        self.open_command_dir_button.configure(command=self.OpenCommandDir)
        # タグの編集画面を開くボタン
        self.tag_editor_window = None
        self.script_creator_window = None
        # 実行リストと予約のウィンドウと、開始・停止の予約(予約は、ウィンドウを閉じても残る)
        self.run_list_window = None
        self.run_schedule = RunSchedule(
            self.startNamedCommand, self._stopForSchedule, self.isCommandRunning, lambda text: print(f"[予約] {text}")
        )
        self._schedule_title = None
        self.root.after(SCHEDULE_TICK_MS, self._tickSchedule)
        # PC がスリープから戻ったら、実行中のコマンドを止める(検知は別のスレッド。止めるのは、画面のスレッド)
        self.sleep_watch = SleepWatch(lambda seconds: UiDispatcher.post(self._onResumeFromSleep, seconds))
        self.sleep_watch.start()
        self.tag_img = tk.PhotoImage(file="./assets/tag-16.png")
        self.edit_tags_button = ttk.Button(self.action_commands_f)
        self.edit_tags_button.config(image=self.tag_img)
        self.edit_tags_button.pack(fill="x", pady="2", side="top")
        self.edit_tags_button.configure(command=self.openTagEditor)
        self.action_commands_f.pack(padx="5", pady="5", side="left")
        # self.select_commands_f.configure(height='200', width='200')
        self.select_commands_f.grid(column="0", row="0", sticky="ew")
        self.commands_f.configure(height="200", width="500")
        self.commands_f.pack(side="top")
        self.controller_nb.add(self.commands_f, padding="5", text="Commands")

    def OpenCommandDir(self) -> None:
        """フォルダのボタン、または メニューの「コマンドのフォルダを開く」: 選択中のタブ(Python / Mcu)のコマンドのフォルダを開く"""
        # 今のフォルダーに関わらず、このアプリの Commands フォルダーを開く
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if self.command_nb.index("current") == 1:
            directory = os.path.join(base, "Commands", "McuCommands")
        else:
            directory = os.path.join(base, "Commands", "PythonCommands")
        self._logger.debug(f"Open folder: '{directory}'")
        if platform.system() == "Windows":
            subprocess.call(f'explorer "{directory}"')
        elif platform.system() == "Darwin":
            command = f'open "{directory}"'
            subprocess.run(command, shell=True)

    def openTagEditor(self) -> None:
        """
        タグの絵のボタン: タグの編集画面を開く(すでに開いている場合は前面に出す)。
        選択中のタブ(Python / Mcu)の、選択中のコマンドを、初めに表示する
        """
        if self.tag_editor_window is not None and self.tag_editor_window.isOpen():
            self.tag_editor_window.lift()
            return
        # ファイルの今の内容で編集を始められるように、開く前に、コマンドの一覧を読み直す
        self._reloadCommandList()
        commandtype = "Mcu" if self.command_nb.index("current") == 1 else "Python"
        self.tag_editor_window = TagEditorWindow(
            self.root,
            self._commandsOf,
            command_type=commandtype,
            selected_name=self.getSelectedCommandName(commandtype),
            on_saved=self._reloadCommandList,
        )

    def selectedCommand(self) -> tuple:
        """メイン画面で選んでいるコマンド(種別, 名前)。選んでいなければ、名前は空文字(History / Shortcut のタブでは、Python)"""
        commandtype = "Mcu" if self.command_nb.index("current") == 1 else "Python"
        return commandtype, self.getSelectedCommandName(commandtype)

    def openRunLists(self, tab: int = TAB_LISTS) -> None:
        """
        メニューの コマンド > 実行リスト...: 実行リスト(コマンドの連続実行)と予約のウィンドウを開く
        (すでに開いている場合は、前面に出して、タブを切り替える)。tab: 表示するタブ
        """
        if self.run_list_window is not None and self.run_list_window.isOpen():
            self.run_list_window.showTab(tab)
            self.run_list_window.lift()
            return
        self.run_list_window = RunListWindow(
            self.root, self.run_schedule, self.selectedCommand, self._reloadCommandList, self.isCommandRunning, tab=tab
        )

    def openSchedule(self) -> None:
        """メニューの コマンド > 開始と停止の予約...: 同じウィンドウの、予約のタブを開く"""
        self.openRunLists(TAB_SCHEDULE)

    def startNamedCommand(self, commandtype: str, commandname: str) -> bool:
        """
        種別と名前で指定したコマンドを開始する(予約から呼ばれる)。開始できたかを返す
        (実行中・操作の記録中・一覧にない名前・読み込みの失敗のときは、開始しない)
        """
        if self.isCommandRunning() or self.isRecording():
            return False
        self.is_use_Pro_Controller.set(False)
        self.mode_change_Pro_Controller()
        if not self._assignCommandByName(commandtype, commandname, "schedule"):
            return False
        self._startAssignedCommand(commandtype, commandname)
        return True

    def _stopForSchedule(self) -> None:
        """実行中のコマンドを止める(予約から呼ばれる。止めている途中・実行していないときは、何もしない)"""
        if self.command_service.state == command_service.RUNNING:
            self.stopPlay()

    def _onResumeFromSleep(self, seconds: float) -> None:
        """
        PC が止まっていた(スリープから戻った)とき: 実行中のコマンドを止める。
        スリープの間もゲーム機は動いているので、続けると、スクリプトとゲームの画面がずれたまま進むため
        seconds: 止まっていた時間(秒)
        """
        if self.command_service.state != command_service.RUNNING:
            return
        print(f"[スリープ] PC が約 {format_remaining(seconds)}、止まっていました(スリープなど)。実行中のコマンドを止めます。")
        print("[スリープ] シリアルの接続が切れている場合は、Serial タブの Reload Port でつなぎ直してください。")
        self.stopPlay()

    def watchSendFailures(self) -> None:
        """送信の失敗が続いたら、実行中のコマンドを止めるようにする(Sender を作った後に、1 回呼ぶ)"""
        self.ser.on_send_failures = lambda count, error: UiDispatcher.post(self._onSendFailures, count, error)

    def _onSendFailures(self, count: int, error: Exception) -> None:
        """
        送信の失敗が続いたとき: 知らせて、実行中のコマンドを止める(接続が切れたまま、スクリプトだけが進まないように)
        count: 続いた回数。error: 最後のエラー
        """
        print(f"[シリアル] 送信に {count} 回続けて失敗しました。接続が切れている可能性があります。({error})")
        if self.command_service.state == command_service.RUNNING:
            print("[シリアル] 実行中のコマンドを止めます。")
            self.stopPlay()
        print("[シリアル] ケーブルを確かめて、Serial タブの Reload Port でつなぎ直してください。")

    def _tickSchedule(self) -> None:
        """予約の時刻が来ていれば、開始・停止する。予約がある間は、タイトルに「予約中」と出す(SCHEDULE_TICK_MS ごと)"""
        try:
            self.run_schedule.tick()
            pending = self.run_schedule.pending
            if pending != (self._schedule_title is not None):
                if pending:
                    self._schedule_title = self.root.title()
                    self.root.title(self._schedule_title + " [予約中]")
                else:
                    self.root.title(self._schedule_title)
                    self._schedule_title = None
        except Exception:
            self._logger.exception("Failed to check the schedule")
        finally:
            self.root.after(SCHEDULE_TICK_MS, self._tickSchedule)

    def openScriptCreator(self) -> None:
        """
        メニューの ツール > 新しい自動化スクリプトをつくる: 新しいスクリプトを作る画面を開く(すでに開いている場合は前面に出す)
        """
        if self.script_creator_window is not None and self.script_creator_window.isOpen():
            self.script_creator_window.lift()
            return
        self.script_creator_window = ScriptCreatorWindow(self.root, on_created=self._onScriptCreated)

    def _onScriptCreated(self, result: ScriptResult) -> None:
        """
        新しいスクリプトを作った後: コマンドの一覧を読み直して、作ったコマンドを選び、ファイルをエディタで開く
        """
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        print(f"スクリプトを作成しました: {os.path.relpath(result.path, base)}")
        for folder in result.created_folders:
            print(f"フォルダーを作成しました: {os.path.relpath(folder, base)}")
        for path in result.created_files:
            print(f"ひな形を作成しました: {os.path.relpath(path, base)}(要約や使い方を、書き足してください)")
        for path in result.skipped_files:
            print(f"すでにあるため、作成していません: {os.path.relpath(path, base)}")
        self._logger.info(f"Script created: {result.path}")
        self.command_service.reload()
        self.setCommandItems()
        # 絞り込みで隠れていなければ、作ったコマンドを選んだ状態にする(Start を押せば、すぐ試せる)
        self.command_nb.select(0)
        self.updateCommandView("Python", select_name=result.command_name)
        self.openCommandFile(result.path)

    def _reloadCommandList(self) -> None:
        """コマンドの一覧を読み直して、画面に反映する(コマンドのモジュールは、読み込み直さない)"""
        self.command_service.reload()
        self.setCommandItems()

    def isCommandRunning(self) -> bool:
        """コマンドを実行中か(command_service の is_running)"""
        return self.command_service.is_running

    # コマンドの一覧と実行の対象は command_service が持つ。以前の属性の名前でも読めるようにしておく
    @property
    def py_loader(self) -> CommandLoader | CombinedLoader:
        """Python コマンドの読み込み先(追加の機能が読み込み先を足している場合は、それらをまとめたもの)"""
        return self.command_service.loaders["Python"]

    @property
    def mcu_loader(self) -> CommandLoader:
        """Mcu コマンドの読み込み先"""
        return self.command_service.loaders["Mcu"]

    @property
    def py_commands(self) -> list[CommandEntry]:
        """Python コマンドの一覧"""
        return self.command_service.commands["Python"]

    @property
    def mcu_commands(self) -> list[CommandEntry]:
        """Mcu コマンドの一覧"""
        return self.command_service.commands["Mcu"]

    @property
    def py_cur_command(self) -> Command | None:
        """最後に用意した Python コマンド(まだ無い場合は None)"""
        return self.command_service.current_by_type["Python"]

    @property
    def mcu_cur_command(self) -> Command | None:
        """最後に用意した Mcu コマンド(まだ無い場合は None)"""
        return self.command_service.current_by_type["Mcu"]

    @property
    def cur_command(self) -> Command | None:
        """実行の対象のコマンド(まだ無い場合は None)"""
        return self.command_service.current

    @cur_command.setter
    def cur_command(self, command: Command | None) -> None:
        """実行の対象のコマンドを差し替える"""
        self.command_service.current = command

    def loadCommands(self) -> None:
        """起動時: コマンドの読み込みと実行を受け持つ command_service を作り、コマンドの一覧を表示する"""
        # コマンドの一覧のみ取得する(モジュールはStart/Reload時に必要なものだけインポートする)
        self.command_service = CommandService(
            get_camera=lambda: self.camera,
            get_gui=lambda: self.preview,
            on_state_changed=self._onCommandStateChanged,
        )
        self.command_service.load()

        self.setCommandItems()

    @staticmethod
    def _sortTags(commands: Iterable[CommandEntry]) -> list:
        """コマンドが持つタグの一覧を返す(ディレクトリのタグ(@...)は後半にまとめる)"""
        return command_catalog.sort_tags(commands)

    def _commandsOf(self, commandtype: str) -> list[CommandEntry]:
        """コマンドの種別("Python" / "Mcu")のコマンドの一覧を返す"""
        return self.py_commands if commandtype == "Python" else self.mcu_commands

    def _createCommandTree(self, parent: tk.Misc, commandtype: str) -> ttk.Treeview:
        """
        コマンドの一覧(Command / Tags の2列)を作って返す(見出しのクリックで絞り込み、行の右クリックでメニューを表示する)
        parent: 一覧を置く枠
        commandtype: コマンドの種別("Python" / "Mcu")
        """
        tree_f = ttk.Frame(parent)
        tv = ttk.Treeview(tree_f)
        tv.configure(columns=("command", "tags"), height="3", selectmode="browse", show="headings")
        tv.heading("command", anchor="w", command=lambda: self.showCommandFilter(commandtype))
        tv.heading("tags", anchor="w", command=lambda: self.showTagFilter(commandtype))
        tv.column("command", anchor="w", stretch=True, width="330")
        tv.column("tags", anchor="w", stretch=False, width="170")
        sb = ttk.Scrollbar(tree_f, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.pack(fill="y", side="right")
        tv.pack(expand="true", fill="both", side="left")
        tree_f.grid(column="0", row="0", sticky="nsew")
        self.command_trees[commandtype] = tv
        # 右クリックメニュー(Shortcut > #n に設定)
        self._bindShortcutContextMenu(tv, lambda row: (commandtype, tv.set(row, "command")))
        self._updateTagsHeading(commandtype)
        return tv

    def _updateTagsHeading(self, commandtype: str) -> None:
        """一覧の見出し(Tags・Command)に、今のフィルタの数・並び順・検索の文字を表示する"""
        n = len(self.command_tag_filters[commandtype])
        text = f"Tags ▼ (フィルタ: {n})" if n > 0 else "Tags ▼"
        self.command_trees[commandtype].heading("tags", text=text)
        # Command列の見出しには、並び順と名前のフィルタを表示する
        notes = [label for key, _, label in COMMAND_SORTS if key == self.command_sorts[commandtype] and label]
        name_filter = self.command_name_filters[commandtype].strip()
        if name_filter:
            notes.append(f"検索: {name_filter}")
        text = f"Command ▼ ({', '.join(notes)})" if notes else "Command ▼"
        self.command_trees[commandtype].heading("command", text=text)

    def _commandMtime(self, command: CommandEntry) -> float:
        """
        コマンドのファイルの更新日時(取得できない場合は0)
        """
        path = command.file_path
        if path not in self.command_mtimes:
            try:
                self.command_mtimes[path] = os.path.getmtime(path)
            except OSError:
                self.command_mtimes[path] = 0.0
        return self.command_mtimes[path]

    def _commandUsageOf(self, commandtype: str) -> Callable[[CommandEntry], int] | None:
        """
        コマンドを実行した回数を返す関数(使用頻度の順に並べているときだけ。それ以外は None)
        回数は、呼ぶたびに記録から読む(ほかのウィンドウで実行した分も含む)
        """
        if not self.command_sorts[commandtype].startswith("usage"):
            return None
        counts = self.command_service.usage_counts(commandtype)
        return lambda command: counts.get(command.name, 0)

    def getSelectedCommandName(self, commandtype: str) -> str:
        """一覧で選択中のコマンドの名前を返す(選択していない場合は空文字)"""
        tv = self.command_trees[commandtype]
        selection = tv.selection()
        if len(selection) == 0:
            return ""
        return tv.set(selection[0], "command")

    def updateCommandView(self, commandtype: str, select_name: str | None = None) -> None:
        """
        フィルタと並び順を適用して、コマンドの一覧を表示し直す
        commandtype: コマンドの種別("Python" / "Mcu")
        select_name: 表示し直した後に選択するコマンドの名前(None: 今選択しているコマンド。一覧に無ければ先頭)
        """
        # フィルタ(選択されたタグのいずれかを持つ、名前に入力した文字を含む)と並び順を適用して一覧を作り直す
        tv = self.command_trees[commandtype]
        if select_name is None:
            select_name = self.getSelectedCommandName(commandtype)
        # 行のiidはコマンドの番号のまま、表示の順番だけを変える
        commands = command_catalog.filter_commands(
            self._commandsOf(commandtype),
            self.command_tag_filters[commandtype],
            self.command_name_filters[commandtype],
            self.command_sorts[commandtype],
            self._commandMtime,
            self._commandUsageOf(commandtype),
        )
        tv.delete(*tv.get_children())
        selected = None
        for i, c in commands:
            iid = tv.insert("", "end", iid=str(i), values=(c.name, ", ".join(c.tags)))
            if c.name == select_name and selected is None:
                selected = iid
        children = tv.get_children()
        if selected is None and len(children) > 0:
            selected = children[0]
        if selected is not None:
            tv.selection_set(selected)
            tv.see(selected)
        self._updateTagsHeading(commandtype)

    def setCommandItems(self) -> None:
        """読み込んだコマンドの一覧を画面に反映する(起動時と Reload。無くなったタグはフィルタから外す)"""
        self.py_cb_all = [c.name for c in self.py_commands]
        self.mcu_cb_all = [c.name for c in self.mcu_commands]
        # 更新日時は読み込み(Reload)のたびに取り直す
        self.command_mtimes = {}
        for commandtype in ("Python", "Mcu"):
            # 無くなったタグはフィルタから外す
            self.command_tag_filters[commandtype] &= set(self._sortTags(self._commandsOf(commandtype)))
            self.updateCommandView(commandtype)

    def showTagFilter(self, commandtype: str) -> None:
        """Tags列の見出し: タグで絞り込むポップアップを、見出しのすぐ下に表示する"""
        tv = self.command_trees[commandtype]
        tags = self._sortTags(self._commandsOf(commandtype))
        # Tags列の見出しのすぐ下に表示する
        tv.update_idletasks()
        x = tv.winfo_rootx() + tv.column("command", "width")
        y = tv.winfo_rooty() + 25
        children = tv.get_children()
        if len(children) > 0 and tv.bbox(children[0]):
            y = tv.winfo_rooty() + tv.bbox(children[0])[1]

        def on_change(selected: set[str], text: str) -> None:
            """ポップアップで変更するたびに、選択中のタグと入力した文字を覚えて、一覧を表示し直す"""
            self.command_tag_filters[commandtype] = set(selected)
            self.command_tag_texts[commandtype] = text
            self.updateCommandView(commandtype)

        TagFilterPopup(
            tv,
            x,
            y,
            tags,
            self.command_tag_filters[commandtype],
            on_change,
            y_above=tv.winfo_rooty(),
            text=self.command_tag_texts[commandtype],
        )

    def showCommandFilter(self, commandtype: str) -> None:
        """
        Command列の見出し: 並び順(名前・更新日時・使用頻度)と、名前の部分一致のフィルタを設定するポップアップ
        """
        tv = self.command_trees[commandtype]
        tv.update_idletasks()
        x = tv.winfo_rootx()
        y = tv.winfo_rooty() + 25
        children = tv.get_children()
        if len(children) > 0 and tv.bbox(children[0]):
            y = tv.winfo_rooty() + tv.bbox(children[0])[1]

        def on_change(sort: str, text: str) -> None:
            """ポップアップで変更するたびに、並び順と入力した文字を覚えて、一覧を表示し直す"""
            self.command_sorts[commandtype] = sort
            self.command_name_filters[commandtype] = text
            self.updateCommandView(commandtype)

        CommandFilterPopup(
            tv,
            x,
            y,
            self.command_sorts[commandtype],
            self.command_name_filters[commandtype],
            on_change,
            y_above=tv.winfo_rooty(),
        )

    def _createShortcutMenu(self, parent: tk.Misc, command: Callable[[int], None]) -> tk.Menu:
        """
        「#1に設定」～「#Nに設定」のメニューを作って返す
        parent: メニューの親
        command: 項目を選んだときに呼ぶ関数(選んだ番号)
        """
        # 「#1に設定」～「#Nに設定」のメニュー (選択された番号を command に渡す)
        menu = tk.Menu(parent, tearoff=0)
        for num in range(1, Settings.GuiSettings.SHORTCUT_NUM + 1):
            menu.add_command(label=f"#{num}に設定", command=lambda num=num: command(num))
        return menu

    def _bindShortcutContextMenu(self, tv: ttk.Treeview, get_command: Callable[[str], tuple[str, str]]) -> tk.Menu:
        """
        Treeviewの行を右クリックしたときに「Shortcut > #nに設定」と、コマンドのファイルを開くメニューを表示する。
        get_command(行のiid) は (コマンド種別, コマンド名) を返す。
        戻り値: 作ったメニュー(呼び出し側で項目を足せる)
        """
        target = {"row": None}

        def on_select(num: int) -> None:
            """「#nに設定」を選んだとき: 右クリックした行のコマンドを、その番号のショートカットに設定する"""
            if target["row"] is None:
                return
            commandtype, commandname = get_command(target["row"])
            self.setShortcut(num, commandtype, commandname)
            print(f"Set shortcut #{num}: {commandname}")

        def show(event: tk.Event) -> None:
            """右クリックしたとき: その行を選択して、メニューを表示する(行の外では表示しない)"""
            # 右クリックした行を選択し、その行を対象にメニューを表示する
            row = tv.identify_row(event.y)
            if row == "" or tv.identify_region(event.x, event.y) not in ("cell", "tree"):
                return
            tv.selection_set(row)
            target["row"] = row
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        menu = tk.Menu(tv, tearoff=0)
        menu.add_cascade(label="Shortcut", menu=self._createShortcutMenu(menu, on_select))
        menu.add_separator()

        self._addCommandFileMenu(menu, lambda: get_command(target["row"]) if target["row"] is not None else None)
        tv.bind("<Button-3>", show, add="")
        if platform.system() == "Darwin":
            tv.bind("<Button-2>", show, add="")
        return menu

    def showShortcutContextMenu(self, event: tk.Event, num: int) -> None:
        """
        Shortcutのボタンの右クリックメニュー(コマンドのファイルを開く)。コマンドが設定されていないボタンでは表示しない
        num: ショートカットの番号
        """
        commandname = self.shortcut_command_name[num]
        if not commandname:
            return
        menu = tk.Menu(event.widget, tearoff=0)
        self._addCommandFileMenu(menu, lambda: (self.shortcut_command_class[num], commandname))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _addCommandFileMenu(self, menu: tk.Menu, get_command: Callable[[], tuple[str, str] | None]) -> None:
        """
        右クリックメニューに、コマンドのファイルを開く項目(Open file / Open with... / Open folder / Copy path)を追加する
        get_command() は (コマンド種別, コマンド名) を返す(対象がない場合はNone)
        """

        def run(action: Callable[[str], None]) -> None:
            """対象のコマンドのファイルのパスを求め、見つかれば action(パス) を呼ぶ"""
            command = get_command()
            if command is None:
                return
            path = self.commandFilePath(*command)
            if path is not None:
                action(path)

        menu.add_command(label="Open file", command=lambda: run(self.openCommandFile))
        if platform.system() == "Windows":
            menu.add_command(
                label="Open with...", command=lambda: run(lambda path: self.openCaptureFile(path, choose_app=True))
            )
            menu.add_command(label="Open folder", command=lambda: run(self.openCaptureFolder))
        menu.add_separator()
        menu.add_command(label="Copy path", command=lambda: run(self.copyText))

    def commandFilePath(self, commandtype: str, commandname: str) -> str | None:
        """
        コマンドが書かれたファイルのパスを返す(見つからない場合はメッセージを表示してNone)
        """
        loader = self.py_loader if self._normalizeCommandType(commandtype) == "Python" else self.mcu_loader
        entry = loader.findEntry(commandname)
        if entry is None or not os.path.isfile(entry.file_path):
            print(f"'{commandname}' のファイルが見つかりません。(Reloadで一覧を更新してください)")
            return None
        return os.path.abspath(entry.file_path)

    def openCommandFile(self, path: str) -> None:
        """
        コマンドが書かれたファイルを、エディタで開く
        """
        self._logger.debug(f"Open file: '{path}'")
        try:
            util.open_text_file(path)
        except OSError as e:
            self._logger.error(f"Failed to open the file: {e}")
            print(f"Open file: ファイルを開けませんでした。({path})")

    def setShortcut(self, num: int, commandtype: str, commandname: str) -> None:
        """
        ショートカットのボタンにコマンドを設定する(ボタンの文字とツールチップも変える)
        num: ショートカットの番号
        commandtype: コマンドの種別
        commandname: コマンドの名前
        """
        self.shortcut_command_class[num] = commandtype
        self.shortcut_command_name[num] = commandname
        self.shortcut_button_texts[num].set(commandname[:SHORTCUT_TEXT_LENGTH])
        self.shortcut_button_tooltips[num].text = commandname

    def _assignCommand(self, commandtype: str, commandname: str, reload: bool = False) -> bool:
        """
        実行の対象のコマンドを用意する。
        モジュールが未インポートの場合(reload=Trueの場合は常に)、そのモジュールと必要なモジュールのみインポートする。
        戻り値: 用意できたか(読み込みに失敗した場合は、エラーの画面を表示して False)
        """
        loading = self.command_service.needs_import(commandtype, commandname, reload)
        if loading:
            self._showCommandLoading(True)
        try:
            return self.command_service.assign(commandtype, commandname, reload)
        except CommandLoadError as e:
            tkmsg.showerror("Command load error", f"コマンドの読み込みに失敗しました。\n{e.entry.file_path}")
            return False
        finally:
            if loading:
                self._showCommandLoading(False)

    def _showCommandLoading(self, loading: bool) -> None:
        """
        スクリプトを読み込んでいる間の表示(Start ボタンの文字を Loading... にし、カーソルを待ちの形にする)。
        読み込みは画面のスレッドで行うので、重いライブラリを使うスクリプトでは、初回に数秒〜十数秒、画面が止まる。
        その間、何も起きていないように見えないよう、読み込みの前に、表示を描き直しておく
        """
        if loading:
            self._loading_texts = (self.start_button["text"], self.start_top_button["text"])
            self.start_button["text"] = self.start_top_button["text"] = COMMAND_LOADING_TEXT
            print(COMMAND_LOADING_MESSAGE)
        else:
            texts = getattr(self, "_loading_texts", None) or ("Start", "Start")
            self.start_button["text"], self.start_top_button["text"] = texts
            self._loading_texts = None
        try:
            self.root.configure(cursor="watch" if loading else "")
            # 読み込みで画面が止まる前に、ここまでの表示を描く(入力は、処理しない)
            self.root.update_idletasks()
        except tk.TclError:
            pass

    def assignCommand(self, reload: bool = False) -> bool:
        """
        選択中のタブ(Python / Mcu)の一覧で選んでいるコマンドを、実行の対象として用意する
        reload: True なら、モジュールを読み込み直す
        戻り値: 用意できたか(選んでいない場合は False)
        """
        # 選択されているタブのコマンドのみ読み込む
        commandtype = "Python" if self.command_nb.index(self.command_nb.select()) == 0 else "Mcu"
        commandname = self.getSelectedCommandName(commandtype)
        if commandname == "":
            print("No commands have been selected.")
            return False
        return self._assignCommand(commandtype, commandname, reload)

    def assignShortcutCommand(self, num: int) -> bool:
        """ショートカット(番号 num)に設定したコマンドを、実行の対象として用意する。戻り値: 用意できたか"""
        commandtype = self.shortcut_command_class[num]
        commandname = self.shortcut_command_name[num]
        if commandtype == "None":
            print(f"shortcut command ({num}) is not assigned.")
            return False
        return self._assignCommandByName(commandtype, commandname, "shortcut")

    @staticmethod
    def _normalizeCommandType(commandtype: str) -> str:
        """コマンドの種別の書き方をそろえる("Python" / "Mcu"。それ以外はそのまま返す)"""
        return command_catalog.normalize_command_type(commandtype)

    def _assignCommandByName(self, commandtype: str, commandname: str, source: str) -> bool:
        """
        コマンドの種別と名前から、実行の対象のコマンドを用意する(ショートカットと履歴から実行するとき)
        source: 見つからないときのメッセージの先頭に付ける文字("shortcut" / "history")
        戻り値: 用意できたか
        """
        # コマンド種別と名前からコマンドを設定する(モジュールが未インポートの場合はインポートする)
        commandtype, error = command_catalog.find_named_command(commandtype, commandname, self.py_cb_all, self.mcu_cb_all)
        if commandtype is None:
            print(f"{source} {error}")
            return False
        return self._assignCommand(commandtype, commandname)

    def addCommandHistory(self, commandtype: str, commandname: str) -> None:
        """実行したコマンドを履歴の先頭に入れ、History の一覧を表示し直す"""
        # 同じコマンドは先頭に移動し、最大件数を超えた古い履歴は削除する
        command_catalog.add_history(self.command_history, commandtype, commandname, Settings.GuiSettings.HISTORY_MAX)
        self.updateHistoryView()

    def updateHistoryView(self) -> None:
        """History の一覧を、Last Run の順に表示し直す"""
        self.history_tv.delete(*self.history_tv.get_children())
        # 行のiidは履歴の番号のまま、Last Runの順に並べる
        rows = command_catalog.sorted_history(self.command_history, self.history_descending)
        for i, h in rows:
            self.history_tv.insert("", "end", iid=str(i), values=(h["name"], h["last_run"]))
        self.history_tv.heading("last_run", text="Last Run ▼" if self.history_descending else "Last Run ▲")
        self.history_tv.yview_moveto(0)

    def deleteHistory(self) -> None:
        """
        Historyの右クリックメニュー Delete: 選択している履歴を消す
        """
        selection = self.history_tv.selection()
        if len(selection) == 0:
            return
        del self.command_history[int(selection[0])]
        self.updateHistoryView()

    def deleteAllHistory(self) -> None:
        """
        Historyの右クリックメニュー Delete (ALL): 確認のうえ、すべての履歴を消す
        """
        if len(self.command_history) == 0:
            return
        if not tkmsg.askokcancel("確認", f"すべての履歴({len(self.command_history)}件)を削除しますか？"):
            return
        self.command_history.clear()
        self.updateHistoryView()

    def toggleHistorySort(self) -> None:
        """
        HistoryのLast Runの見出し: 新しい順(▼)と古い順(▲)を切り替える
        """
        self.history_descending = not self.history_descending
        self.updateHistoryView()

    def _historyCommandOf(self, row: str) -> tuple[str, str]:
        """History の行(iid は履歴の番号)から、(コマンド種別, コマンド名) を返す"""
        h = self.command_history[int(row)]
        return h["class"], h["name"]

    def onClickHistory(self, event: tk.Event) -> None:
        """History の行をクリックしたとき: そのコマンドを実行する(コマンドの実行中は実行しない)"""
        if self.history_tv.identify_region(event.x, event.y) not in ("cell", "tree"):
            return
        row = self.history_tv.identify_row(event.y)
        if row == "":
            return
        if self.start_button["text"] == "Stop":
            print("Command is now working!")
            self._logger.debug("Command is now working!")
            return
        h = self.command_history[int(row)]
        self.startHistoryPlay(h["class"], h["name"])

    def controllButtons(self, event: tk.Event) -> None:
        """コマンドのタブを切り替えたとき: Shortcut・History のタブでは Start ボタンを押せなくする(実行中は変えない)"""
        note = event.widget
        if self.start_button["text"] == "Start":
            if note.tab(note.select(), "text") in ("Shortcut", "History"):
                self.start_button["state"] = "disabled"
                self.start_top_button["state"] = "disabled"
            else:
                self.start_button["state"] = "normal"
                self.start_top_button["state"] = "normal"
        else:
            pass

    def reloadCommands(self) -> None:
        """Reload ボタン、または F5: コマンドの一覧を更新し、選択中のコマンドのモジュールを読み込み直す"""
        # コマンドの一覧を更新する(選択中のコマンドとフィルタは可能な限り維持する)
        self.command_service.reload()
        self.setCommandItems()

        # 設定されているコマンドのモジュール(および必要なモジュール)のみ読み込み直す
        if self.command_nb.tab(self.command_nb.select(), "text") not in ("Shortcut", "History"):
            self.assignCommand(reload=True)
        print("Finished reloading command modules.")
        self._logger.info("Reloaded commands.")

    def _pauseButtonState(self) -> str:
        """
        Pauseボタンを押せるか(Mcuコマンドはマイコン側で動くため、一時停止できない)
        """
        return "normal" if self.command_service.can_pause else "disabled"

    def pausePlay(self, *event: tk.Event) -> None:
        """
        Pause ボタン: 実行中のコマンドを一時停止し、ボタンを Restart に変える
        event: 使わない(ボタンからは引数なしで呼ばれる)
        """
        self.command_service.pause()
        self.pause_button["text"] = "Restart"
        self.pause_button["command"] = self.restartPlay

    def restartPlay(self, *event: tk.Event) -> None:
        """
        Restart ボタン: 一時停止したコマンドを再開し、ボタンを Pause に戻す
        event: 使わない(ボタンからは引数なしで呼ばれる)
        """
        self.command_service.resume()
        self.pause_button["text"] = "Pause"
        self.pause_button["command"] = self.pausePlay

    def startPlay(self, *event: tk.Event) -> None:
        """
        Start ボタン、または F6: 一覧で選んでいるコマンドを実行する(操作の記録中は実行しない)
        実行の前に、Pro Controller の使用をオフにする
        event: 使わない(ボタンからは引数なしで呼ばれる)
        """
        if self.isRecording():
            return
        # set and init selected command
        # (モジュールが未インポートの場合は、選択中のコマンドのモジュールと必要なモジュールのみインポートする)
        commandtype = "Python" if self.command_nb.index(self.command_nb.select()) == 0 else "Mcu"
        commandname = self.getSelectedCommandName(commandtype)
        if not self.assignCommand():
            print("No commands have been assigned yet.")
            self._logger.info("No commands have been assigned yet.")
            return

        self.is_use_Pro_Controller.set(False)
        self.mode_change_Pro_Controller()

        self._startAssignedCommand(commandtype, commandname)

    def startShortcutPlay(self, *event: tk.Event, num: int = 0) -> None:
        """
        Shortcut のボタン: 設定したコマンドを実行する(操作の記録中は実行しない)
        event: 使わない
        num: ショートカットの番号
        """
        if self.isRecording():
            return
        self.is_use_Pro_Controller.set(False)
        self.mode_change_Pro_Controller()
        # set and init selected command
        if self.assignShortcutCommand(num):
            self._startAssignedCommand(self.shortcut_command_class[num], self.shortcut_command_name[num])

    def startHistoryPlay(self, commandtype: str, commandname: str) -> None:
        """履歴から選んだコマンド(種別と名前)を実行する(操作の記録中は実行しない)"""
        if self.isRecording():
            return
        self.is_use_Pro_Controller.set(False)
        self.mode_change_Pro_Controller()
        # set and init selected command (モジュールが未インポートの場合はインポートする)
        if self._assignCommandByName(commandtype, commandname, "history"):
            self._startAssignedCommand(commandtype, commandname)

    def _startAssignedCommand(self, commandtype: str, commandname: str) -> None:
        """用意したコマンドを開始し、履歴に入れる(出力先は、開始したときに表示しているページ)"""
        self.printStartMessage()
        # Start時にアクティブなページを、コマンドの出力先にする
        self.command_service.start(self.ser, self.get_active_output_page())
        self.addCommandHistory(commandtype, commandname)
        # 実行した回数を足し、使用頻度の順に並べている一覧は、並べ直す
        self.command_service.record_usage(commandtype, commandname)
        commandtype = command_catalog.normalize_command_type(commandtype)
        if self.command_sorts.get(commandtype, "").startswith("usage"):
            self.updateCommandView(commandtype)

    def _onCommandStateChanged(self, state: str) -> None:
        """
        コマンドの実行の状態(command_service)が変わったときに、ボタンの表示を合わせる
        state: 新しい状態(command_service の IDLE / RUNNING / STOPPING)
        """
        if state == command_service.RUNNING:
            self.start_button["text"] = "Stop"
            self.start_top_button["text"] = "Stop"
            self.start_button["command"] = self.stopPlay
            self.start_top_button["command"] = self.stopPlay
            self.start_button["state"] = "normal"
            self.start_top_button["state"] = "normal"
            self.reload_command_button["state"] = "disabled"
            self.setShortcutButtonsState("disabled")
            self.configureRecordButtons(state="disabled")
            self.pause_button["state"] = self._pauseButtonState()
        elif state == command_service.STOPPING:
            self.start_button["state"] = "disabled"
            self.start_top_button["state"] = "disabled"
            self.pause_button["text"] = "Pause"
            self.pause_button["command"] = self.pausePlay
            self.pause_button["state"] = "disable"
        else:
            self.stopPlayPost()

    def setShortcutButtonsState(self, state: str) -> None:
        """すべての Shortcut のボタンを、押せる("normal")/ 押せない("disabled")にする"""
        for button in self.shortcut_buttons.values():
            button["state"] = state

    def printStartMessage(self) -> None:
        """コマンドの開始をログに残す(Python コマンド以外は、出力画面にも表示する)"""
        self._logger.info(self.start_button["text"] + " " + self.cur_command.NAME)
        # Pythonコマンドは実行スレッド側で「スクリプト開始: ...」を表示するため、ここでは表示しない
        if not isinstance(self.cur_command, PythonCommandBase.PythonCommand):
            print(self.start_button["text"] + " " + self.cur_command.NAME)

    def stopPlay(self) -> None:
        """Stop ボタン、または Esc: 実行中のコマンドに停止を求める"""
        # 停止時の出力は、ページを切り替えていてもStart時のページ(コマンドの出力先)に表示する
        with Command.output_to_page(Command.output_page):
            print(self.start_button["text"] + " " + self.cur_command.NAME)
            self._logger.info(self.start_button["text"] + " " + self.cur_command.NAME)
            self.command_service.stop(self.ser)

    def stopPlayPost(self) -> None:
        """コマンドが終わったとき: Start・Reload・Shortcut・記録のボタンを、実行前の状態に戻す"""
        self.start_button["text"] = "Start"
        self.start_top_button["text"] = "Start"
        self.start_button["command"] = self.startPlay
        self.start_top_button["command"] = self.startPlay
        if self.command_nb.tab(self.command_nb.select(), "text") in ("Shortcut", "History"):
            self.start_button["state"] = "disable"
            self.start_top_button["state"] = "disable"
        else:
            self.start_button["state"] = "normal"
            self.start_top_button["state"] = "normal"
        self.reload_command_button["state"] = "normal"
        self.setShortcutButtonsState("normal")
        self.configureRecordButtons(state="normal")

    def ReloadCommandWithF5(self, *event: tk.Event | None) -> None:
        """
        F5 キー、または メニューの「再読み込み」: コマンドを読み込み直す
        event: 使わない(メニューからは None が渡される)
        """
        self.reloadCommands()

    def StartCommandWithF6(self, *event: tk.Event | None) -> None:
        """
        F6 キー、または メニューの「開始」: 一覧で選んでいるコマンドを実行する
        (実行中、または Shortcut・History のタブを表示している間は実行しない)
        event: 使わない(メニューからは None が渡される)
        """
        if self.isCommandRunning():
            print("Command is now working!")
            self._logger.debug("Command is now working!")
        else:
            if self.command_nb.tab(self.command_nb.select(), "text") in ("Shortcut", "History"):
                return
            self.startPlay()

    def StopCommandWithEsc(self, *event: tk.Event | None) -> None:
        """
        Esc キー、または メニューの「停止」: 実行中のコマンドを止める
        event: 使わない(メニューからは None が渡される)
        """
        if self.isCommandRunning():
            self.stopPlay()
