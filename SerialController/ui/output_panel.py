#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
出力画面(Output)と Others タブ: 出力先、大きさ、リンク、部品の位置
"""
from __future__ import annotations

import tkinter as tk
import os
import tkinter.font as tkfont
import platform
import subprocess
import Profile
from typing import Callable
import tkinter.ttk as ttk
import OutputLinks
import Theme
from Commands.CommandBase import Command
from UiDispatcher import UiDispatcher
from ui.constants import (
    OUTPUT_PAGE_NUM,
    OUTPUT_MAX_LINES,
    OUTPUT_TEXT_WIDTH,
    SASH_WIDTH,
    DEFAULT_AREA_SIZE,
    ACTION_LINK_TAG,
    ACTION_LINK_TAG_PREFIX,
    ACTION_LINK_DRAG_PIXELS,
    CAPTURE_LINK_TAG,
    NOTE_SAVE_DELAY_MS,
    LOG_LEVEL_CHOICES,
    LOG_LEVEL_TAGS,
    LOG_WARNING_COLORS,
)
from services import log_buffer, note_store
from services.output_service import OutputService
from ui.output import LogWriter, MonitorWriter, OutputTextAreaProxy, OutputWriter
from ui.output_search import OutputSearchBar


class OutputPanelMixin:
    """
    出力画面(Output)と Others タブ: 出力先、大きさ、リンク、部品の位置
    (PokeControllerApp に取り込んで使う。部品や設定は self の属性として、ほかのファイルと共有する)
    """

    def _buildOthersTab(self) -> list[str]:
        """
        Others タブの部品を作る(起動時に1回だけ呼ぶ)
        戻り値: Widget Mode の選択肢の一覧
        """
        self.others_f = ttk.Frame(self.controller_nb)
        # Output(右側のパネルの出力画面) と Position(部品の位置) の2つの枠にまとめる
        self.others_f.columnconfigure(0, weight=1)
        self.othres_outputs_lf = ttk.Labelframe(self.others_f)
        self.select_right_frame_widget_label = ttk.Label(self.othres_outputs_lf)
        self.select_right_frame_widget_label.configure(text="Widget Mode:")
        self.select_right_frame_widget_label.grid(column="0", padx=(8, 4), pady="4", row="0", sticky="w")
        self.select_right_frame_widget_cb = ttk.Combobox(self.othres_outputs_lf)
        self.right_frame_widget_mode = tk.StringVar(value="ALL (default)")
        right_frame_widget_mode_list = [
            "ALL (default)",
            "Output#1 + Output#2",
            "Output#1 + Software-Controller",
            "Output#2 + Software-Controller",
            "Output#1 Only",
            "Output#2 Only",
            "Software-Controller Only",
        ]
        self.select_right_frame_widget_cb.configure(
            justify="left",
            state="readonly",
            textvariable=self.right_frame_widget_mode,
            values=right_frame_widget_mode_list,
        )
        self.select_right_frame_widget_cb.configure(width="14")
        self.select_right_frame_widget_cb.grid(column="1", columnspan="3", padx=(4, 8), pady="4", row="0", sticky="ew")
        self.select_right_frame_widget_cb.bind(
            "<<ComboboxSelected>>", self.replace_right_frame_widget
        )
        # Output#1 と Output#2 の高さの比率
        self.area_size_label = ttk.Label(self.othres_outputs_lf)
        self.area_size_label.configure(text="Size:")
        self.area_size_label.grid(column="0", padx=(8, 4), pady="4", row="1", sticky="w")
        self.area_size_scale = ttk.Scale(self.othres_outputs_lf)
        self.area_size = tk.IntVar(value=DEFAULT_AREA_SIZE)
        self.area_size_scale.configure(
            from_="0", length="200", orient="horizontal", to="100"
        )
        self.area_size_scale.configure(value="50", variable=self.area_size)
        self.area_size_scale.grid(column="1", columnspan="3", padx=(4, 8), pady="4", row="1", sticky="ew")
        self.area_size_scale.configure(command=self.changeAreaSize)
        # 標準出力(print)の出力先
        self.stdout_destination_label = ttk.Label(self.othres_outputs_lf)
        self.stdout_destination_label.configure(text="Stdout:")
        self.stdout_destination_label.grid(column="0", padx=(8, 4), pady="4", row="2", sticky="w")
        self.outputs_stdout_dest_f = ttk.Frame(self.othres_outputs_lf)
        self.stdout_destination_1_rb = ttk.Radiobutton(self.outputs_stdout_dest_f)
        self.stdout_destination = tk.StringVar(value="1")
        self.stdout_destination_1_rb.configure(
            text="#1", value="1", variable=self.stdout_destination
        )
        self.stdout_destination_1_rb.pack(side="left", padx=(0, 8))
        self.stdout_destination_1_rb.configure(command=self.switchStdoutDestination)
        self.stdout_destination_2_rb = ttk.Radiobutton(self.outputs_stdout_dest_f)
        self.stdout_destination_2_rb.configure(
            text="#2", value="2", variable=self.stdout_destination
        )
        self.stdout_destination_2_rb.pack(side="left", padx=(0, 8))
        self.stdout_destination_2_rb.configure(command=self.switchStdoutDestination)
        self.outputs_stdout_dest_f.grid(column="1", padx="4", pady="4", row="2", sticky="w")
        self.outputs_text_area_1_clear_button = ttk.Button(self.othres_outputs_lf)
        self.outputs_text_area_1_clear_button.configure(text="Clear #1", width="7")
        self.outputs_text_area_1_clear_button.grid(column="2", padx="2", pady="4", row="2", sticky="e")
        self.outputs_text_area_1_clear_button.configure(command=self.clearTextArea1)
        self.outputs_text_area_2_clear_button = ttk.Button(self.othres_outputs_lf)
        self.outputs_text_area_2_clear_button.configure(text="Clear #2", width="7")
        self.outputs_text_area_2_clear_button.grid(column="3", padx=(2, 6), pady="4", row="2", sticky="e")
        self.outputs_text_area_2_clear_button.configure(command=self.clearTextArea2)
        self.othres_outputs_lf.columnconfigure(1, weight=1)
        self.othres_outputs_lf.configure(text="Output")
        self.othres_outputs_lf.grid(column="0", padx="5", pady="3", row="0", sticky="nsew")

        self.others_position_lf = ttk.Labelframe(self.others_f)
        self.pos_software_controller_label = ttk.Label(self.others_position_lf)
        self.pos_software_controller_label.configure(text="Software-Controller:")
        self.pos_software_controller_label.grid(column="0", padx=(8, 4), pady="4", row="0", sticky="w")
        self.pos_software_controller_f = ttk.Frame(self.others_position_lf)
        self.pos_software_controller = tk.StringVar(value="2")
        self.pos_top_rb = ttk.Radiobutton(self.pos_software_controller_f)
        self.pos_top_rb.configure(
            text="TOP", value="1", variable=self.pos_software_controller
        )
        self.pos_top_rb.pack(side="left", padx=(0, 8))
        self.pos_top_rb.configure(command=self.replace_right_frame_widget)
        self.pos_bottom_rb = ttk.Radiobutton(self.pos_software_controller_f)
        self.pos_bottom_rb.configure(
            text="BOTTOM", value="2", variable=self.pos_software_controller
        )
        self.pos_bottom_rb.pack(side="left", padx=(0, 8))
        self.pos_bottom_rb.configure(command=self.replace_right_frame_widget)
        self.pos_software_controller_f.grid(column="1", pady="4", row="0", sticky="w")
        self.pos_dialogue_buttons_label = ttk.Label(self.others_position_lf)
        self.pos_dialogue_buttons_label.configure(text="Dialogue OK/Cancel:")
        self.pos_dialogue_buttons_label.grid(column="0", padx=(8, 4), pady="4", row="1", sticky="w")
        self.pos_dialogue_buttons_f = ttk.Frame(self.others_position_lf)
        self.pos_dialogue_buttons = tk.StringVar(value="2")
        self.pos_dialogue_top_rb = ttk.Radiobutton(self.pos_dialogue_buttons_f)
        self.pos_dialogue_top_rb.configure(
            text="TOP", value="1", variable=self.pos_dialogue_buttons
        )
        self.pos_dialogue_top_rb.pack(side="left", padx=(0, 8))
        self.pos_dialogue_top_rb.configure(command=self.change_buttons_position)
        self.pos_dialogue_bottom_rb = ttk.Radiobutton(self.pos_dialogue_buttons_f)
        self.pos_dialogue_bottom_rb.configure(
            text="BOTTOM", value="2", variable=self.pos_dialogue_buttons
        )
        self.pos_dialogue_bottom_rb.pack(side="left", padx=(0, 8))
        self.pos_dialogue_bottom_rb.configure(command=self.change_buttons_position)
        self.pos_dialogue_both_rb = ttk.Radiobutton(self.pos_dialogue_buttons_f)
        self.pos_dialogue_both_rb.configure(
            text="BOTH", value="3", variable=self.pos_dialogue_buttons
        )
        self.pos_dialogue_both_rb.pack(side="left", padx=(0, 4))
        self.pos_dialogue_both_rb.configure(command=self.change_buttons_position)
        self.pos_dialogue_buttons_f.grid(column="1", pady="4", row="1", sticky="w")
        self.others_position_lf.configure(text="Position")
        self.others_position_lf.grid(column="1", padx="5", pady="3", row="0", sticky="nsew")
        self.others_f.pack()
        self.controller_nb.add(self.others_f, padding="5", sticky="nsew", text="Others")
        return right_frame_widget_mode_list

    def _buildOutputArea(self) -> None:
        """
        出力画面(Output#1 / #2 のページ)を作る(起動時に1回だけ呼ぶ)
        """
        # 左下のタブは、仕切り線の枠(left_pw)に置く(buildPanes)
        self.output_area_f = ttk.Frame(self.main_frame)
        # 出力画面をNotebook化(Page 1～3)し、各ページにOutput#1/#2を配置する
        self.output_nb = ttk.Notebook(self.output_area_f)
        self.output_pages = []
        self.text_scrolls_1 = []
        self.text_scrolls_2 = []
        self.text_areas_1 = []
        self.text_areas_2 = []
        self.output_sashes = []
        for page_index in range(OUTPUT_PAGE_NUM):
            page_f = ttk.Frame(self.output_nb)
            text_scroll_1, text_area_1 = self.create_output_text_area(page_f, "Output#1")
            # Output#1 と Output#2 の間の仕切り線(ドラッグすると、Others タブの Size の比率が変わる)
            output_sash = tk.Frame(page_f, height=SASH_WIDTH, background=Theme.color("sash"), cursor="sb_v_double_arrow")
            output_sash.pack(fill="x", side="top")
            output_sash.bind("<B1-Motion>", self._onDragOutputSash)
            self.output_sashes.append(output_sash)
            text_scroll_2, text_area_2 = self.create_output_text_area(page_f, "Output#2")
            self.output_nb.add(page_f, sticky="nsew", text=f"Page {page_index + 1}")
            self.output_pages.append(page_f)
            self.text_scrolls_1.append(text_scroll_1)
            self.text_scrolls_2.append(text_scroll_2)
            self.text_areas_1.append(text_area_1)
            self.text_areas_2.append(text_area_2)
        # シリアルモニター(Show Serial にチェックを入れている間に送ったデータ)。Output#1 / #2 に分けず、1つにまとめる
        self.monitor_page = ttk.Frame(self.output_nb)
        self.monitor_text_scroll, self.monitor_text_area = self.create_output_text_area(
            self.monitor_page, "Serial Monitor", on_clear=self.clearSerialMonitor
        )
        # 行数は最小にして、ページの大きさに合わせて広げる(出力画面の行数の計算に影響させない)
        self.monitor_text_area.config(height="1")
        self.output_nb.add(self.monitor_page, sticky="nsew", text="Serial")
        # ログ(コンソールに出しているものと同じ内容)。これも、1つにまとめる
        self.log_page = ttk.Frame(self.output_nb)
        # 表示するレベルの絞り込み(選んだレベルより低い行を隠す。隠すだけで、消さない)
        log_filter_f = ttk.Frame(self.log_page)
        ttk.Label(log_filter_f, text="Level:").pack(side="left", padx=(5, 4))
        self.log_level = tk.StringVar(value=LOG_LEVEL_CHOICES[0][1])
        self.log_level_cb = ttk.Combobox(
            log_filter_f, textvariable=self.log_level, state="readonly", width=20,
            values=[label for _, label in LOG_LEVEL_CHOICES],
        )
        self.log_level_cb.pack(side="left")
        self.log_level_cb.bind("<<ComboboxSelected>>", self.applyLogLevelFilter)
        log_filter_f.pack(fill="x", side="top", pady=(3, 0))
        self.log_text_scroll, self.log_text_area = self.create_output_text_area(
            self.log_page, "Log", on_clear=self.clearLogView
        )
        self.log_text_area.config(height="1")
        self.output_nb.add(self.log_page, sticky="nsew", text="Log")
        # Note(利用者が自由に書けるメモ。プロファイルごとに保存する)
        self.note_page = ttk.Frame(self.output_nb)
        self.note_text_scroll, self.note_text_area = self.create_note_text_area(self.note_page)
        self.output_nb.add(self.note_page, sticky="nsew", text="Note")
        # 書き換えたら、少し待ってから保存する(打っている間に、何度も書かない)
        self._note_save_job = None
        self._note_saved_text = ""
        self._note_loading = False
        self.note_text_area.bind("<<Modified>>", self._onNoteModified)
        # Serial / Log / Note タブを表示している間の出力先は、直前に表示していたページにする
        self.last_output_page = 0
        self.output_nb.bind("<<NotebookTabChanged>>", lambda event: self.get_active_output_page(), add="+")
        self.output_nb.pack(expand="true", fill="both", padx="0", pady="0", side="top")
        # 文字の検索(出力画面で Ctrl+F、または右クリックの Find...)。表示しているタブの出力画面を対象にする
        # (検索の欄に文字を打っている間は、ほかの入力欄と同じく、キーボードでの手動操作が止まる。controller_panel)
        self.output_search = OutputSearchBar(self.output_nb, self._outputSearchTargets)
        self.output_nb.bind(
            "<<NotebookTabChanged>>", lambda event: self.output_search.refresh(keep_position=True), add="+"
        )
        # 別スレッド(コマンド実行スレッド)からのGUI操作はメインスレッドで実行する
        UiDispatcher.init(self.root)
        # 出力画面への書き込みはキュー経由でメインスレッドから反映する
        self.output_service = OutputService(Command.get_output_page_for_current_thread, OUTPUT_MAX_LINES)
        self.output_writer = OutputWriter(
            self.root, self.output_service, {1: self.text_areas_1, 2: self.text_areas_2}, self.get_active_output_page
        )
        # 出力先ページを解決するプロキシ(アクティブページ or Start時のページ)
        self.text_area_1 = OutputTextAreaProxy(self, self.text_areas_1, self.output_service.channel(1))
        self.text_area_2 = OutputTextAreaProxy(self, self.text_areas_2, self.output_service.channel(2))
        # シリアルモニターも、溜まった分をメインスレッドからまとめて反映する(Sender は、この後で作る)
        # (Serial タブを表示している間だけ反映する。送ったデータは、Show Serial のチェックに関係なく、いつも溜まるため)
        self.monitor_writer = MonitorWriter(
            self.root, lambda: getattr(getattr(self, "ser", None), "monitor", None), self.monitor_text_area,
            is_visible=self.monitor_text_area.winfo_viewable,
        )
        # ログは、Log タブを表示している間だけ反映する(表示していない間は溜めておき、コマンドと画面の処理を増やさない)
        self.log_buffer = log_buffer.install()
        self.log_writer = LogWriter(
            self.root, lambda: self.log_buffer, self.log_text_area, is_visible=self.log_text_area.winfo_viewable
        )
        # レベルごとの文字の色(テーマを変えるたびに、付け直す)
        Theme.add_style_hook(self._configureLogColors)
        # 右側のパネルは、仕切り線の枠に置く入れ物(panel_container)に入れる(buildPanes)
        # ミニ画面でのみ、右側のパネルの上に表示するWidget ModeとClear Outputs
        # (Widget Modeは通常画面とは別に持ち、ミニ画面での変更を通常画面に反映しない)
        self.mini_widget_mode = tk.StringVar(value="ALL (default)")

    def change_buttons_position(self, *event: tk.Event) -> None:
        """
        Others タブの Position(ダイアログのボタンの位置)を選んだとき(と起動時): 選んだ位置を Command に反映する
        event: 使わない(ラジオボタンからは引数なしで呼ばれる)
        """
        Command.pos_dialogue_buttons = self.pos_dialogue_buttons.get()

    def clearTextArea1(self) -> None:
        """Output#1 の内容を消す(Others タブの Clear #1 ボタンなど)"""
        # キュー経由にして、未反映の出力との順序を保つ
        self.text_area_1.enqueue("d")

    def clearTextArea2(self) -> None:
        """Output#2 の内容を消す(Others タブの Clear #2 ボタンなど)"""
        self.text_area_2.enqueue("d")

    def clearSerialMonitor(self) -> None:
        """シリアルモニター(Serial タブ)の内容を消す(右クリックメニューの Clear)"""
        self.monitor_writer.clear()

    def _configureLogColors(self, style: ttk.Style | None = None) -> None:
        """
        Log タブの、レベルごとの文字の色を、今のテーマに合わせる(DEBUG: 薄い文字 / WARNING: 黄〜橙 / ERROR 以上: 赤。INFO は通常の色)
        style: 使わない(Theme.add_style_hook から、テーマを変えるたびに呼ばれる)
        """
        colors = {
            "debug": Theme.color("muted"),
            "warning": LOG_WARNING_COLORS[1 if Theme.is_dark() else 0],
            "error": Theme.color("danger"),
        }
        try:
            for group, color in colors.items():
                self.log_text_area.tag_configure(LOG_LEVEL_TAGS[group], foreground=color)
            # 選択した範囲は、選択の色を優先する
            self.log_text_area.tag_raise("sel")
        except tk.TclError:
            # 終了処理中などで、ウィジェットが破棄されている場合
            pass

    def getLogLevel(self) -> str:
        """Log タブで選んでいるレベル("debug" / "info" / "warning" / "error"。設定に保存する値)"""
        return next((group for group, label in LOG_LEVEL_CHOICES if label == self.log_level.get()), LOG_LEVEL_CHOICES[0][0])

    def setLogLevel(self, group: str) -> None:
        """Log タブのレベルを選び、絞り込みを当てる(group: getLogLevel の値。知らない値は、すべて表示)"""
        labels = dict(LOG_LEVEL_CHOICES)
        self.log_level.set(labels.get(group, LOG_LEVEL_CHOICES[0][1]))
        self.applyLogLevelFilter()

    def applyLogLevelFilter(self, event: tk.Event | None = None) -> None:
        """
        Log タブの Level を選んだとき: 選んだレベルより低い行を隠す(表示済みの行にも、これから出る行にも効く。
        隠すだけなので、選び直せば、また表示される)
        event: 使わない
        """
        labels = [label for _, label in LOG_LEVEL_CHOICES]
        threshold = labels.index(self.log_level.get()) if self.log_level.get() in labels else 0
        for position, tag in enumerate(LOG_LEVEL_TAGS.values()):
            self.log_text_area.tag_configure(tag, elide=position < threshold)
        self.log_text_area.see("end")
        # 検索の印は、表示している行だけに付け直す
        self.output_search.refresh(keep_position=True)

    def _outputSearchTargets(self) -> list:
        """
        検索の対象にする出力画面(今のタブのもの。上から順)。
        Widget Mode で外している出力画面(枠を配置していないもの)は、対象にしない
        (タブを変えた直後は、まだ画面に出ていないので、見えているかではなく、配置しているかで判断する)
        """
        try:
            page = self.output_nb.index(self.output_nb.select())
        except tk.TclError:
            return []
        if page < len(self.output_pages):
            areas = [self.text_areas_1[page], self.text_areas_2[page]]
        elif self.output_nb.select() == str(self.monitor_page):
            areas = [self.monitor_text_area]
        elif self.output_nb.select() == str(self.note_page):
            areas = [self.note_text_area]
        else:
            areas = [self.log_text_area]
        return [area for area in areas if area.master.winfo_manager()]

    def openOutputSearch(self, text_area: tk.Text | None = None) -> None:
        """
        出力画面の検索の欄を開く(Ctrl+F、右クリックの Find...)
        text_area: 開いた元の出力画面(1 行の中で文字を選んでいれば、その文字を検索する)
        """
        initial = None
        if text_area is not None and text_area.tag_ranges("sel"):
            selected = text_area.get("sel.first", "sel.last")
            if selected.strip() and "\n" not in selected:
                initial = selected
        self.output_search.open(initial)

    # ---------------------------------------------------------------- Note

    def create_note_text_area(self, parent: tk.Misc) -> tuple[ttk.LabelFrame, tk.Text]:
        """
        Note の入力欄(LabelFrame + 書き込める Text + Scrollbar)を作る。戻り値: (枠, Text)
        (Text に入力している間は、キーボードでの手動操作が止まる。controller_panel の、入力欄の扱いと同じ)
        """
        frame = ttk.LabelFrame(parent, relief=tk.GROOVE, text="Note")
        text_area = tk.Text(frame, height="1", width=OUTPUT_TEXT_WIDTH, relief="flat", undo=True, maxundo=-1, wrap="word")
        yscroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text_area.yview)
        yscroll.pack(side="right", fill="y", padx=(0, 5), pady="5")
        text_area["yscrollcommand"] = yscroll.set
        text_area.pack(expand="true", fill="both", padx=(5, 0), pady="5")
        frame.pack(expand="true", fill="both", padx="0", pady="0", side="top")
        context_menu = tk.Menu(text_area, tearoff=0)
        context_menu.add_command(label="Cut", command=lambda: text_area.event_generate("<<Cut>>"))
        context_menu.add_command(label="Copy", command=lambda: text_area.event_generate("<<Copy>>"))
        context_menu.add_command(label="Paste", command=lambda: text_area.event_generate("<<Paste>>"))
        context_menu.add_command(label="Select All", command=lambda: text_area.tag_add("sel", "1.0", "end-1c"))
        context_menu.add_separator()
        context_menu.add_command(label="Find...", accelerator="Ctrl+F", command=lambda: self.openOutputSearch(text_area))

        def show_menu(event: tk.Event) -> None:
            """右クリックのメニューを出す(選んでいる文字がなければ、Cut と Copy は押せない)"""
            text_area.focus_set()
            state = "normal" if text_area.tag_ranges("sel") else "disabled"
            context_menu.entryconfigure("Cut", state=state)
            context_menu.entryconfigure("Copy", state=state)
            try:
                context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                context_menu.grab_release()

        text_area.bind("<Button-3>", show_menu)
        if platform.system() == "Darwin":
            text_area.bind("<Button-2>", show_menu)
        # 文字の検索(Ctrl+F)。Text の既定の Ctrl+F(カーソルを進める)は、行わない
        text_area.bind("<Control-f>", lambda e: self.openOutputSearch(text_area) or "break")
        return frame, text_area

    def loadNote(self) -> None:
        """Note の内容を、今のプロファイルのファイルから読んで表示する(起動時。プロファイルの設定を読んだ後に呼ぶ)"""
        text = note_store.load()
        self._note_loading = True
        self.note_text_area.delete("1.0", "end")
        self.note_text_area.insert("1.0", text)
        self.note_text_area.edit_reset()
        self.note_text_area.edit_modified(False)
        self._note_loading = False
        self._note_saved_text = text

    def noteText(self) -> str:
        """Note に書いてある内容"""
        return self.note_text_area.get("1.0", "end-1c")

    def _onNoteModified(self, event: tk.Event | None = None) -> None:
        """Note を書き換えたとき: NOTE_SAVE_DELAY_MS 待ってから保存する(続けて打っている間は、待ち直す)"""
        if not self.note_text_area.edit_modified():
            return
        self.note_text_area.edit_modified(False)
        if self._note_loading:
            return
        if self._note_save_job is not None:
            self.root.after_cancel(self._note_save_job)
        self._note_save_job = self.root.after(NOTE_SAVE_DELAY_MS, self.saveNote)

    def saveNote(self) -> None:
        """
        Note の内容を、今のプロファイルのファイルに保存する(変わっていなければ、書かない)。
        同じプロファイルの 2 つ目のウィンドウ(設定を保存しないウィンドウ)では、保存しない
        """
        if self._note_save_job is not None:
            self.root.after_cancel(self._note_save_job)
            self._note_save_job = None
        text = self.noteText()
        if text == self._note_saved_text or Profile.is_read_only():
            return
        if note_store.save(text):
            self._note_saved_text = text

    def clearLogView(self) -> None:
        """Log タブの内容を消す(右クリックメニューの Clear。ログのファイルは消さない)"""
        self.log_writer.clear()

    def clearOutputs(self) -> None:
        """Clear Outputs ボタン: Output#1 と Output#2 の内容を消す"""
        self.clearTextArea1()
        self.clearTextArea2()

    def changeAreaSize(self, *event: str) -> None:
        """
        出力画面(Output#1 / #2)の行数を、右側のパネル(または下のパネル)の高さに合わせる
        2つ表示する場合は、Others タブの Size の比率(間の仕切り線をドラッグしても変わる)で分ける
        event: 使わない(Size のスライダーを動かしたときは、その値が文字で渡される)
        """
        if not self.output_area_f.winfo_ismapped():
            return
        mode = self.getWidgetMode()
        show_1 = mode == "ALL (default)" or "#1" in mode
        show_2 = mode == "ALL (default)" or "#2" in mode
        if not (show_1 or show_2):
            return
        self.root.update_idletasks()
        text_1, text_2 = self.text_areas_1[0], self.text_areas_2[0]
        linespace = tkfont.Font(font=text_1.cget("font")).metrics("linespace")
        # 出力画面以外(タブの見出し・枠・Software-Controller)に使う高さ
        lines_now = (int(text_1.cget("height")) if show_1 else 0) + (int(text_2.cget("height")) if show_2 else 0)
        overhead = self.output_nb.winfo_reqheight() - lines_now * linespace
        available = self.output_area_f.winfo_height()
        # Software-Controller を並べる設定かどうかで判定する(画面に出ているかでは判定しない)。
        # 出力画面の下に並べる場合、出力画面が高いままだと Software-Controller は押し出されて表示されず、
        # 「表示されていない」と判定すると、その分の高さを空けられないままになる
        if self.softcon_frame.winfo_manager() and not self.isPanelHorizontal():
            available -= self.softcon_frame.winfo_reqheight()
        # Output#1 / #2 の枠は、スクロールバーより低くならない(数行以下では、行数を減らしても枠は低くならない)ので、
        # 枠の高さで収まる行数を求める
        shown = [index for index, show in ((0, show_1), (1, show_2)) if show]
        frames_height = available - (self.output_nb.winfo_reqheight() - sum(self._outputFrameHeight(i) for i in shown))

        def split(total: int) -> tuple[int, int]:
            """
            合計の行数を、(Output#1 の行数, Output#2 の行数) に分ける
            (片方だけ表示する場合は、どちらも total。2つ表示する場合は、Size の比率で分け、どちらも1行以上にする)
            """
            if len(shown) == 1:
                return (total, total)
            lines_1 = min(max(int(round(total * float(self.area_size.get()) / 100.0)), 1), total - 1)
            return (lines_1, total - lines_1)

        total = max((available - overhead) // linespace, len(shown))
        while total > len(shown):
            lines = split(total)
            if sum(self._outputFrameHeight(i, lines[i]) for i in shown) <= frames_height:
                break
            total -= 1
        lines_1, lines_2 = split(total)
        for text_area_1, text_area_2 in zip(self.text_areas_1, self.text_areas_2):
            if int(text_area_1.cget("height")) != lines_1:
                text_area_1.config(height=lines_1)
            if int(text_area_2.cget("height")) != lines_2:
                text_area_2.config(height=lines_2)

    def _outputFrameHeight(self, index: int, lines: int | None = None) -> int:
        """
        出力画面の枠(Output#1: index 0、Output#2: index 1)の高さ。lines: 行数(省略時は今の行数)
        (行数が少ないときは、スクロールバーの高さより低くならない)
        """
        text_scroll = (self.text_scrolls_1, self.text_scrolls_2)[index][0]
        text_area = (self.text_areas_1, self.text_areas_2)[index][0]
        if lines is None:
            return text_scroll.winfo_reqheight()
        scrollbar = next(widget for widget in text_scroll.winfo_children() if isinstance(widget, ttk.Scrollbar))
        linespace = tkfont.Font(font=text_area.cget("font")).metrics("linespace")
        text_height = text_area.winfo_reqheight() - int(text_area.cget("height")) * linespace
        # 枠の、Text とスクロールバー以外の部分(見出し・余白)
        frame_extra = text_scroll.winfo_reqheight() - max(text_area.winfo_reqheight(), scrollbar.winfo_reqheight())
        return frame_extra + max(text_height + lines * linespace, scrollbar.winfo_reqheight())

    def _outputMinHeight(self) -> int:
        """
        出力画面(タブと Output#1 / #2)の最小の高さ(各出力画面を1行にしたとき)。出力画面を表示しない場合は 0
        """
        mode = self.getWidgetMode()
        shown = [
            index
            for index, show in ((0, mode == "ALL (default)" or "#1" in mode), (1, mode == "ALL (default)" or "#2" in mode))
            if show
        ]
        if not shown:
            return 0
        others = self.output_nb.winfo_reqheight() - sum(self._outputFrameHeight(i) for i in shown)
        return others + sum(self._outputFrameHeight(i, 1) for i in shown)

    def _onDragOutputSash(self, event: tk.Event) -> None:
        """
        Output#1 と Output#2 の間の仕切り線をドラッグしたとき: マウスの位置に合わせて、2つの行数の比率(Size)を変える
        """
        page = self.output_nb.index("current")
        text_scroll_1, text_scroll_2 = self.text_scrolls_1[page], self.text_scrolls_2[page]
        text_1, text_2 = self.text_areas_1[page], self.text_areas_2[page]
        linespace = tkfont.Font(font=text_1.cget("font")).metrics("linespace")
        total = int(text_1.cget("height")) + int(text_2.cget("height"))
        # 出力画面の枠の、行以外の部分(見出し・余白)の高さ(Output#1 と #2 で同じ)
        overhead = (text_scroll_1.winfo_height() + text_scroll_2.winfo_height() - total * linespace) / 2
        y = event.y_root - text_scroll_1.winfo_rooty() - SASH_WIDTH / 2
        size = int(round(100.0 * (y - overhead) / linespace / max(total, 1)))
        size = min(max(size, 0), 100)
        if size != self.area_size.get():
            self.area_size.set(size)
            self.changeAreaSize()

    def switchStdoutDestination(self) -> None:
        """
        Others タブの Stdout(標準出力の出力先)を選んだとき(と起動時): print の出力先を Output#1 / #2 に切り替える
        (出力画面の見出しにも、(Stdout) を付ける)
        """
        val = self.stdout_destination.get()
        if val == "1":
            self.output_service.redirect_stdout(1)
            print("standard output destination is switched.")
            Command.stdout_destination = val
            label_1, label_2 = "Output#1 (Stdout)", "Output#2"
        elif val == "2":
            self.output_service.redirect_stdout(2)
            print("standard output destination is switched.")
            Command.stdout_destination = val
            label_1, label_2 = "Output#1", "Output#2 (Stdout)"
        else:
            return
        for text_scroll_1, text_scroll_2 in zip(self.text_scrolls_1, self.text_scrolls_2):
            text_scroll_1.configure(text=label_1)
            text_scroll_2.configure(text=label_2)

    def create_output_text_area(
        self, parent: tk.Misc, label: str, on_clear: Callable[[], None] | None = None
    ) -> tuple[ttk.LabelFrame, tk.Text]:
        """
        出力画面(LabelFrame + Text + Scrollbar)を生成する
        parent: 出力画面を置く枠
        label: 枠の見出し
        on_clear: 右クリックメニューに Clear を足す場合の、内容を消す関数
        戻り値: (枠, Textウィジェット)
        """
        text_scroll = ttk.LabelFrame(parent, relief=tk.GROOVE)
        text_scroll.configure(text=label)
        text_area = tk.Text(text_scroll)
        text_area.config(
            blockcursor="true", height="3", insertunfocussed="none", maxundo="0"
        )
        text_area.config(relief="flat", state="disabled", undo="false", width=OUTPUT_TEXT_WIDTH)
        yscroll = ttk.Scrollbar(text_scroll, orient=tk.VERTICAL, command=text_area.yview)
        yscroll.pack(side="right", fill="y", padx=(0, 5), pady="5")
        text_area["yscrollcommand"] = yscroll.set
        text_area.pack(expand="true", fill="both", padx=(5, 0), pady="5")
        text_scroll.pack(expand="true", fill="both", padx="0", pady="0", side="top")
        # 保存した画像のパスのリンク(クリックで開く。右クリックでアプリを選んで開く)
        text_area.tag_configure(CAPTURE_LINK_TAG, foreground=Theme.color("link"), underline=True)
        text_area.tag_bind(CAPTURE_LINK_TAG, "<Enter>", lambda e: text_area.configure(cursor="hand2"))
        text_area.tag_bind(CAPTURE_LINK_TAG, "<Leave>", lambda e: text_area.configure(cursor=""))
        text_area.tag_bind(CAPTURE_LINK_TAG, "<ButtonRelease-1>", self.onClickCaptureLink)
        # クリックで処理を行うリンク(一時停止した位置のファイル、Show variables など)
        text_area.tag_configure(ACTION_LINK_TAG, foreground=Theme.color("link"), underline=True)
        text_area.tag_bind(ACTION_LINK_TAG, "<Enter>", lambda e: text_area.configure(cursor="hand2"))
        text_area.tag_bind(ACTION_LINK_TAG, "<Leave>", lambda e: text_area.configure(cursor=""))
        text_area.tag_bind(ACTION_LINK_TAG, "<ButtonPress-1>", self.onPressActionLink)
        text_area.tag_bind(ACTION_LINK_TAG, "<ButtonRelease-1>", self.onClickActionLink)
        # 右クリックメニュー(Copy)
        context_menu = tk.Menu(text_area, tearoff=0)
        context_menu.add_command(
            label="Copy", command=lambda: self.copy_output_selection(text_area)
        )
        if on_clear is not None:
            context_menu.add_command(label="Clear", command=on_clear)
        # 文字の検索(Ctrl+F)。Text の既定の Ctrl+F(カーソルを進める)は、行わない
        context_menu.add_command(
            label="Find...", accelerator="Ctrl+F", command=lambda: self.openOutputSearch(text_area)
        )
        text_area.bind("<Control-f>", lambda e: self.openOutputSearch(text_area) or "break")
        text_area.bind(
            "<Button-3>", lambda e: self.show_output_context_menu(e, context_menu)
        )
        if platform.system() == "Darwin":
            text_area.bind(
                "<Button-2>", lambda e: self.show_output_context_menu(e, context_menu)
            )
        return text_scroll, text_area

    def show_output_context_menu(self, event: tk.Event, context_menu: tk.Menu) -> None:
        """
        出力画面の右クリックメニューを表示する(選択範囲がない場合Copyは無効)
        保存した画像のパスのリンクの上では、リンク用のメニューを表示する
        context_menu: その出力画面の右クリックメニュー
        """
        path = self._captureLinkPath(event.widget, f"@{event.x},{event.y}")
        if path is not None:
            self.showCaptureLinkMenu(event, path)
            return
        has_selection = bool(event.widget.tag_ranges("sel"))
        context_menu.entryconfigure(
            "Copy", state="normal" if has_selection else "disabled"
        )
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    @staticmethod
    def _captureLinkPath(text_area: tk.Text, index: str) -> str | None:
        """
        出力画面のindexの位置がリンクなら、そのパスを返す(リンクでなければNone)
        """
        if CAPTURE_LINK_TAG not in text_area.tag_names(index):
            return None
        tag_range = text_area.tag_prevrange(CAPTURE_LINK_TAG, f"{index}+1c")
        if not tag_range:
            return None
        return text_area.get(*tag_range).strip()

    def onClickCaptureLink(self, event: tk.Event) -> None:
        """
        リンクをクリック: 保存した画像を既定のアプリで開く(文字を選択するドラッグの場合は開かない)
        """
        if event.widget.tag_ranges("sel"):
            return
        path = self._captureLinkPath(event.widget, f"@{event.x},{event.y}")
        if path is not None:
            self.openCaptureFile(path)

    def onPressActionLink(self, event: tk.Event) -> None:
        """クリックで処理を行うリンクの上でボタンを押したとき: 押した位置を覚える(離したときに、ドラッグかどうかを判定する)"""
        # 押した位置(離した位置と比べて、文字を選択するドラッグかどうかを判定する)
        self.action_link_press = (event.widget, event.x, event.y)

    def onClickActionLink(self, event: tk.Event) -> None:
        """
        クリックで処理を行うリンクをクリック: 処理を呼ぶ(1回だけのリンクは、リンクではなくする)
        (続けて押したときにダブルクリックで文字が選択されても、押した位置から動いていなければクリックとして扱う)
        """
        press = getattr(self, "action_link_press", None)
        self.action_link_press = None
        if press is None or press[0] is not event.widget:
            return
        if abs(press[1] - event.x) > ACTION_LINK_DRAG_PIXELS or abs(press[2] - event.y) > ACTION_LINK_DRAG_PIXELS:
            # 文字を選択するドラッグ
            return
        event.widget.tag_remove("sel", "1.0", "end")
        index = f"@{event.x},{event.y}"
        names = [name for name in event.widget.tag_names(index) if name.startswith(ACTION_LINK_TAG_PREFIX)]
        if not names:
            return
        tag = names[0]
        if OutputLinks.run(int(tag[len(ACTION_LINK_TAG_PREFIX) :])):
            for text_area in (*self.text_areas_1, *self.text_areas_2):
                for start, end in zip(*[iter(text_area.tag_ranges(tag))] * 2):
                    text_area.tag_remove(ACTION_LINK_TAG, start, end)
                text_area.tag_delete(tag)
            event.widget.configure(cursor="")

    def openCaptureFile(self, path: str, choose_app: bool = False) -> None:
        """
        保存した画像を開く(コマンドのファイルを、アプリを選んで開くときにも使う)
        path: 開くファイルのパス
        choose_app: Trueなら、開くアプリを選ぶ画面を表示する(Windowsのみ)
        """
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            print(f"ファイルが見つかりません: {path}")
            return
        self._logger.debug(f"Open file: '{path}'")
        try:
            system = platform.system()
            if system == "Windows":
                if choose_app:
                    subprocess.Popen(["rundll32.exe", "shell32.dll,OpenAs_RunDLL", path])
                else:
                    os.startfile(path)
            elif system == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except OSError as e:
            self._logger.error(f"Failed to open the file: {e}")
            print(f"ファイルを開けませんでした: {path}")

    def showCaptureLinkMenu(self, event: tk.Event, path: str) -> None:
        """
        リンクの右クリックメニュー: 開く / アプリを選んで開く / 保存先のフォルダを開く / パスをコピー
        path: リンクが指すファイルのパス
        """
        menu = tk.Menu(event.widget, tearoff=0)
        menu.add_command(label="Open", command=lambda: self.openCaptureFile(path))
        if platform.system() == "Windows":
            menu.add_command(label="Open with...", command=lambda: self.openCaptureFile(path, choose_app=True))
            menu.add_command(label="Open folder", command=lambda: self.openCaptureFolder(path))
        menu.add_separator()
        menu.add_command(label="Copy path", command=lambda: self.copyText(os.path.abspath(path)))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def openCaptureFolder(self, path: str) -> None:
        """
        保存先のフォルダを開き、そのファイルを選んだ状態にする(Windowsのみ)
        """
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            print(f"ファイルが見つかりません: {path}")
            return
        subprocess.Popen(f'explorer /select,"{path}"')

    def copyText(self, text: str) -> None:
        """文字をクリップボードにコピーする"""
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def copy_output_selection(self, text_area: tk.Text) -> None:
        """
        出力画面で選択(ドラッグ)した文字列をクリップボードにコピーする
        """
        if not text_area.tag_ranges("sel"):
            return
        selected_text = text_area.get("sel.first", "sel.last")
        self.root.clipboard_clear()
        self.root.clipboard_append(selected_text)

    def get_active_output_page(self) -> int:
        """
        アクティブな出力ページ番号(0始まり)を返す
        (Serial / Log / Note タブを表示している間は、直前に表示していたページ)
        """
        try:
            page = self.output_nb.index(self.output_nb.select())
        except Exception:
            return 0
        if page < len(self.output_pages):
            self.last_output_page = page
        return self.last_output_page
