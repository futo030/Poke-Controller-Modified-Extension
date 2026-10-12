#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
画面の配置: 仕切り線、右側のパネルの位置、ミニ画面、テーマ、ウィンドウの大きさ
"""
from __future__ import annotations

import os
import tkinter as tk
import tkinter.ttk as ttk
import Theme
from ui.theme_editor import ThemeEditorWindow
from Audio import AUDIO_AVAILABLE
from ui.constants import (
    SHORTCUT_COLUMNS,
    MINI_WIDTH,
    MINI_SHORTCUT_COLUMNS,
    MINI_COMMAND_NB_WIDTH,
    MINI_OUTPUT_LINES_1,
    MINI_OUTPUT_LINES_2,
    MINI_RIGHT_OUTPUT_LINES_1,
    MINI_RIGHT_OUTPUT_LINES_2,
    PANEL_POSITIONS,
    PANEL_BUTTON_TEXTS,
    BOTTOM_OUTPUT_LINES_1,
    BOTTOM_OUTPUT_LINES_2,
    DEFAULT_OUTPUT_LINES_1,
    DEFAULT_OUTPUT_LINES_2,
    OUTPUT_TEXT_WIDTH,
    OUTPUT_TEXT_WIDTH_HORIZONTAL,
    COMMAND_TREE_LINES,
    MINI_COMMAND_TREE_LINES,
    MINI_BUTTON_SYNC_INTERVAL_MS,
    COMMAND_TAB_NAMES,
    MINI_PREVIEW_MIN_HEIGHT,
    PREVIEW_RESIZE_DELAY_MS,
    SASH_WIDTH,
    SASH_PLACE_DELAY_MS,
    PREVIEW_PAD,
    PANEL_MIN_WIDTH,
    PANEL_MIN_HEIGHT,
    MINI_PANEL_PAD,
    PREVIEW_SCREEN_MARGIN,
)


# 起動時に、配置の処理が落ち着くのを確かめる間隔(ms)、落ち着いたとみなす回数、待つ時間の上限(ms)
SHOW_WINDOW_POLL_MS = 30
SHOW_WINDOW_QUIET_POLLS = 2
SHOW_WINDOW_TIMEOUT_MS = 1500


class LayoutPanelMixin:
    """
    画面の配置: 仕切り線、右側のパネルの位置、ミニ画面、テーマ、ウィンドウの大きさ
    (PokeControllerApp に取り込んで使う。部品や設定は self の属性として、ほかのファイルと共有する)
    """

    def _buildSidePanel(self, right_frame_widget_mode_list: list[str]) -> None:
        """
        右側のパネルの入れ物(ミニ画面用の部品、Software-Controller の枠、仕切り線の枠)を作る(起動時に1回だけ呼ぶ)
        right_frame_widget_mode_list: Widget Mode の選択肢の一覧(ミニ画面用のコンボボックスに入れる)
        """
        self.mini_panel_f = ttk.Frame(self.main_frame)
        self.mini_widget_mode_label = ttk.Label(self.mini_panel_f, text="Widget Mode:")
        self.mini_widget_mode_label.grid(column="1", padx="5", pady="2", row="0", sticky="w")
        self.mini_widget_mode_cb = ttk.Combobox(self.mini_panel_f)
        self.mini_widget_mode_cb.configure(
            justify="left",
            state="readonly",
            textvariable=self.mini_widget_mode,
            values=right_frame_widget_mode_list,
        )
        self.mini_widget_mode_cb.grid(column="2", padx="5", pady="2", row="0", sticky="ew")
        self.mini_widget_mode_cb.bind("<<ComboboxSelected>>", self.replace_right_frame_widget)
        self.mini_clear_button = ttk.Button(self.mini_panel_f)
        self.mini_clear_button.configure(text="Clear Outputs", command=self.clearOutputs)
        self.mini_clear_button.grid(column="0", padx="5", pady="2", row="0", sticky="w")
        self.mini_panel_f.columnconfigure(2, weight=1)
        self.softcon_frame = ttk.LabelFrame(self.output_area_f, relief=tk.GROOVE)
        self.softcon_frame.configure(text="Software-Controller")
        # 中身(Canvasのレイアウト)は、シリアルの準備後に setSoftwareControllerLayout で作る
        self.softcon_panel = None
        self.softcon_frame.pack(
            expand="true", fill="both", padx="0", pady="0", side="top"
        )
        self.softcon_frame.grid_anchor("center")
        # Output#1 / #2 はノートブックの内側の枠の分だけ狭いので、縦に並べるときは
        # Software-Controller の枠も同じだけ内側に置き、幅を揃える(左右の余白。ノートブックの表示後に測る)
        self.softcon_padx = (0, 0)
        self.softcon_applied_padx = (0, 0)
        self.output_nb.bind("<Configure>", self._alignSoftconToOutputs, add="+")
        self.main_frame.config(height="720", padding="5", relief="flat", width="1280")
        self.main_frame.pack(expand="true", fill="both", side="top")
        # 仕切り線で分ける枠: 外側は左右(左側 | 右側のパネル)、左側は上下(Main Panel / タブ / 下のパネル)。
        # 仕切り線はマウスで動かせ、ウィンドウの大きさを変えても、仕切り線の位置の比率は保つ
        pane_options = dict(
            sashwidth=SASH_WIDTH, sashrelief="flat", borderwidth=0, opaqueresize=False, background=Theme.color("sash")
        )
        self.outer_pw = tk.PanedWindow(self.main_frame, orient="horizontal", **pane_options)
        self.left_pw = tk.PanedWindow(self.main_frame, orient="vertical", **pane_options)
        # 右側のパネル(または下のパネル)の入れ物。ミニ画面では Widget Mode・Clear Outputs の行も入れる
        self.panel_container = ttk.Frame(self.main_frame)
        self.outer_pw.grid(column="0", row="0", sticky="nsew")
        self.main_frame.rowconfigure(0, weight=1)
        self.main_frame.columnconfigure(0, weight=1)
        # 仕切り線の位置の比率(画面の種類ごと)。キーは "normal_right" など、値は {"lr": 左右, "v": [上下...]}
        self.pane_ratios = {}
        self.preview_fit_after = None
        self.output_fit_after = None
        self.preview_target = None
        self.sash_place_after = None
        for pw in (self.outer_pw, self.left_pw):
            pw.bind("<ButtonRelease-1>", self._onSashMoved, add="+")
        self.outer_pw.bind("<Configure>", self._onPaneConfigure, add="+")
        self.left_pw.bind("<Configure>", self._onPaneConfigure, add="+")
        self.camera_lf.bind("<Configure>", self._schedulePreviewFit, add="+")
        self.output_area_f.bind("<Configure>", self._scheduleOutputFit, add="+")
        """
        ここまで
        """

    ############### 仕切り線(PanedWindow) ###############
    def _paneKey(self) -> str:
        """
        仕切り線の位置の比率を保存するキー(画面の種類とパネルの位置ごと)
        """
        return f"{'mini' if self.is_mini else 'normal'}_{self.currentPanelPosition()}"

    def _leftPanes(self) -> list[tk.Widget]:
        """左側の仕切り線の枠に、上から並べる部品(Main Panel、左下のタブ、パネルが下のときはパネル)を返す"""
        position = self.currentPanelPosition()
        return [self.camera_lf, self.controller_nb] + ([self.panel_container] if position == "bottom" else [])

    def buildPanes(self) -> None:
        """
        今の画面(通常 / ミニ)とパネルの位置に合わせて、仕切り線の枠に部品を置き直す
        - 左側(left_pw): Main Panel / 左下のタブ(ミニ画面ではコマンド) / パネルが下のときはパネル
        - 外側(outer_pw): 左側 | パネルが右のときはパネル
        """
        position = self.currentPanelPosition()
        for pw in (self.outer_pw, self.left_pw):
            for pane in pw.panes():
                pw.forget(pane)
        for widget in (self.mini_panel_f, self.output_area_f):
            widget.pack_forget()
            widget.grid_forget()
        if position != "hidden":
            if self.is_mini:
                self.mini_panel_f.pack(in_=self.panel_container, fill="x", pady=(0, MINI_PANEL_PAD), side="top")
            self.output_area_f.pack(in_=self.panel_container, expand="true", fill="both", side="top")
        for widget in self._leftPanes():
            self.left_pw.add(widget, stretch="always")
        self.outer_pw.add(self.left_pw, stretch="always")
        if position == "right":
            self.outer_pw.add(self.panel_container, stretch="always")
        # 後から作った枠の下に隠れないよう、置いた部品を手前に出す
        for widget in (
            self.left_pw,
            self.panel_container,
            self.camera_lf,
            self.controller_nb,
            self.mini_panel_f,
            self.output_area_f,
        ):
            widget.lift()
        self.side_panel_button["text"] = PANEL_BUTTON_TEXTS[position]
        self._updatePaneMinSizes()
        if getattr(self, "window_ready", False):
            self.root.update_idletasks()
            if self._paneKey() not in self.pane_ratios:
                self._recordRatios(natural=True)
            self._placeSashes()
            self._schedulePreviewFit()
            self._scheduleOutputFit()

    def _recordRatios(self, natural: bool = False, size: tuple[int, int] | None = None) -> None:
        """
        仕切り線の位置を、比率として覚える
        natural: 今の位置ではなく、中身に必要な大きさで並べたときの位置を覚える(初めて使う配置の場合)。
                 Main Panel とタブは必要な大きさにし、余った大きさは一番下(または右)の領域に回す
        size: 仕切り線の枠全体の大きさ(幅, 高さ)。省略すると今の大きさ
        """
        left_panes = self._leftPanes()
        has_right = len(self.outer_pw.panes()) > 1
        if size is None:
            self.root.update_idletasks()
            size = (self.outer_pw.winfo_width(), self.outer_pw.winfo_height())
        total_width, total_height = max(size[0], 1), max(size[1], 1)
        ratios = {}
        if natural:
            heights = [widget.winfo_reqheight() for widget in left_panes]
            position = 0
            ratios["v"] = []
            for height in heights[:-1]:
                position += height
                ratios["v"].append(min(position / total_height, 0.95))
                position += SASH_WIDTH
            if has_right:
                left_width = max(widget.winfo_reqwidth() for widget in left_panes)
                ratios["lr"] = min(left_width / total_width, 0.95)
        else:
            height = max(self.left_pw.winfo_height(), 1)
            ratios["v"] = [self.left_pw.sash_coord(i)[1] / height for i in range(len(left_panes) - 1)]
            if has_right:
                ratios["lr"] = self.outer_pw.sash_coord(0)[0] / max(self.outer_pw.winfo_width(), 1)
        self.pane_ratios[self._paneKey()] = ratios

    def _placeSashes(self) -> None:
        """
        仕切り線を、覚えている比率の位置に置く(ウィンドウの大きさが変わっても比率を保つ)
        """
        ratios = self.pane_ratios.get(self._paneKey())
        if not ratios:
            return
        if "lr" in ratios and len(self.outer_pw.panes()) > 1:
            self.outer_pw.sash_place(0, int(round(ratios["lr"] * self.outer_pw.winfo_width())), 0)
        panes = self.left_pw.panes()
        height = self.left_pw.winfo_height()
        positions = [int(round(ratio * height)) for ratio in ratios.get("v", [])][: len(panes) - 1]
        # 比率どおりの位置だと最小の大きさより小さくなる領域がある場合は、最小の大きさを守る位置にずらす
        # (仕切り線の枠は、隣の領域の最小の大きさしか見ないため)
        min_sizes = [int(self.left_pw.panecget(pane, "minsize")) for pane in panes]
        for index in range(len(positions)):
            upper = height - sum(min_sizes[index + 1 :]) - SASH_WIDTH * (len(panes) - 1 - index)
            positions[index] = min(positions[index], upper)
            lower = (positions[index - 1] + SASH_WIDTH if index > 0 else 0) + min_sizes[index]
            positions[index] = max(positions[index], lower)
        for index, position in enumerate(positions):
            self.left_pw.sash_place(index, 0, position)

    def _onSashMoved(self, event: tk.Event | None = None) -> None:
        """仕切り線のドラッグを終えたとき: 画面の更新が落ち着いた後に、その位置の比率を覚える"""
        # 仕切り線を動かし終えたら、その位置の比率を覚える
        self.root.after_idle(self._recordSashPosition)

    def _recordSashPosition(self) -> None:
        """今の仕切り線の位置を比率として覚え、プレビューと出力画面の大きさを合わせ直す(起動の途中は何もしない)"""
        if not getattr(self, "window_ready", False):
            return
        self._recordRatios()
        self._schedulePreviewFit()
        self._scheduleOutputFit()

    def _onPaneConfigure(self, event: tk.Event) -> None:
        """仕切り線の枠の大きさが変わったとき: 少し待ってから、仕切り線を同じ比率の位置に置き直す(続けて変わる間は、最後の1回だけ)"""
        # ウィンドウの大きさが変わったら、仕切り線を同じ比率の位置に置き直す
        # (仕切り線の枠が自分で中身を並べ直し、大きさの変更が落ち着いた後に置く)
        if not getattr(self, "window_ready", False):
            return
        if self.sash_place_after is not None:
            self.root.after_cancel(self.sash_place_after)
        self.sash_place_after = self.root.after(SASH_PLACE_DELAY_MS, self._placeSashesLater)

    def _placeSashesLater(self) -> None:
        """_onPaneConfigure で予約した処理: 仕切り線を比率の位置に置き、プレビューと出力画面の大きさを合わせ直す"""
        self.sash_place_after = None
        self._placeSashes()
        self._schedulePreviewFit()
        self._scheduleOutputFit()

    def _updatePaneMinSizes(self) -> None:
        """
        各領域の最小の大きさと、ウィンドウの最小の大きさを設定する(部品が隠れるほど小さくできないように)
        """
        position = self.currentPanelPosition()
        # 部品の必要な大きさを、最新の状態にしてから測る
        self.root.update_idletasks()
        min_width, min_height = self.previewSizeForHeight(self.previewMinHeight())
        border = self.preview.winfo_reqwidth() - self.preview.show_width
        # Main Panel: プレビュー以外の部分(上のボタンの行・枠)+最小のプレビュー
        camera_height = self.camera_lf.winfo_reqheight() - self.preview.winfo_reqheight() + min_height + border
        camera_width = max(
            self.top_command_f.winfo_reqwidth() + 2 * PREVIEW_PAD + 4, min_width + border + 2 * PREVIEW_PAD + 4
        )
        nb_height = self.controller_nb.winfo_reqheight()
        left_heights = [camera_height, nb_height]
        # (パネルを表示していない間も、Software-Controller を並べる設定なら、その高さを確保する)
        softcon_height = self.softcon_frame.winfo_reqheight() if self.softcon_frame.winfo_manager() else 0
        if position == "bottom":
            if self.isPanelHorizontal():
                left_heights.append(max(PANEL_MIN_HEIGHT, softcon_height, self._outputMinHeight()))
            else:
                left_heights.append(
                    self.mini_panel_f.winfo_reqheight() + MINI_PANEL_PAD + softcon_height + max(PANEL_MIN_HEIGHT, self._outputMinHeight())
                )
        for widget, height in zip(self._leftPanes(), left_heights):
            self.left_pw.paneconfigure(widget, minsize=height)
        left_width = max(camera_width, self.controller_nb.winfo_reqwidth(), MINI_WIDTH - 10 if self.is_mini else 0)
        self.outer_pw.paneconfigure(self.left_pw, minsize=left_width)
        window_width = left_width
        window_height = sum(left_heights) + SASH_WIDTH * (len(left_heights) - 1)
        if position == "right":
            right_width = max(PANEL_MIN_WIDTH, self.softcon_frame.winfo_reqwidth() + sum(self.softcon_padx))
            right_height = (
                (self.mini_panel_f.winfo_reqheight() + MINI_PANEL_PAD if self.is_mini else 0)
                + softcon_height
                + max(PANEL_MIN_HEIGHT, self._outputMinHeight())
            )
            self.outer_pw.paneconfigure(self.panel_container, minsize=right_width)
            window_width += SASH_WIDTH + right_width
            window_height = max(window_height, right_height)
        # main_frame の余白(上下左右 5px)と、テーマの色のメニューバー
        self.root.minsize(window_width + 10, window_height + 10 + self._menubarHeight())

    def _previewAvailableSize(self) -> tuple[int, int]:
        """
        Main Panel の中で、プレビューに使える大きさ(幅, 高さ)
        """
        _, _, width, height = self.camera_lf.grid_bbox(0, 2, 6, 2)
        border = self.preview.winfo_reqwidth() - self.preview.show_width
        return width - 2 * PREVIEW_PAD - border, height - 2 * PREVIEW_PAD - border

    def _schedulePreviewFit(self, event: tk.Event | None = None) -> None:
        """
        プレビューを Main Panel に収まる大きさにし直す処理を、少し後に予約する(続けて呼ばれた場合は、最後の1回だけ行う)
        Main Panel の大きさが変わったときなどに呼ばれる
        """
        if self.preview_fit_after is not None:
            self.root.after_cancel(self.preview_fit_after)
        self.preview_fit_after = self.root.after(PREVIEW_RESIZE_DELAY_MS, self._fitPreviewToPane)

    def _fitPreviewToPane(self) -> None:
        """
        プレビューを、Main Panel の中に収まる最大の大きさ(取り込み画像の縦横比を保つ)にする
        """
        self.preview_fit_after = None
        if not getattr(self, "window_ready", False) or not self.camera_lf.winfo_ismapped():
            return
        available_width, available_height = self._previewAvailableSize()
        width, height = self.previewSizeForHeight(min(available_height, available_width / self._previewAspect()))
        target, self.preview_target = self.preview_target, None
        if target is not None and target[0] <= width + 2 and target[1] <= height + 2:
            # Show Size で選んだ大きさ(ウィンドウの大きさの丸めで、1〜2px ずれる場合も、選んだ大きさにする)
            width, height = target
        if (width, height) != (self.preview.show_width, self.preview.show_height):
            self.setPreviewSize(width, height)
            # プレビューの大きさが変わると、仕切り線の枠が中身を並べ直すことがあるので、比率の位置に置き直す
            self.root.update_idletasks()
            self._placeSashes()

    def _scheduleOutputFit(self, event: tk.Event | None = None) -> None:
        """
        出力画面の行数を領域の高さに合わせ直す処理を、少し後に予約する(続けて呼ばれた場合は、最後の1回だけ行う)
        出力画面の領域の大きさが変わったときなどに呼ばれる
        """
        if self.output_fit_after is not None:
            self.root.after_cancel(self.output_fit_after)
        self.output_fit_after = self.root.after(PREVIEW_RESIZE_DELAY_MS, self._fitOutputToPane)

    def _fitOutputToPane(self) -> None:
        """出力画面の行数を、領域の高さに合わせ直す(_scheduleOutputFit で予約した処理)"""
        self.output_fit_after = None
        if getattr(self, "window_ready", False):
            self.changeAreaSize()
            # 出力画面の行数が変わると、仕切り線の枠が中身を並べ直すことがあるので、比率の位置に置き直す
            self.root.update_idletasks()
            self._placeSashes()

    def resizeWindowForPreview(self, width: int, height: int) -> None:
        """
        プレビューが指定の大きさになるように、ウィンドウの大きさを変える(仕切り線の位置の比率は保つ)
        画面に収まらない場合は、画面に収まる大きさまでにする
        width, height: プレビューの大きさ
        """
        root = self.root
        if root.state() != "normal":
            root.state("normal")
        root.update_idletasks()
        available_width, available_height = self._previewAvailableSize()
        ratios = self.pane_ratios.get(self._paneKey(), {})
        # ウィンドウを広げたときに、Main Panel が広がる割合
        width_ratio = ratios.get("lr", 1.0) if len(self.outer_pw.panes()) > 1 else 1.0
        height_ratio = ratios["v"][0] if ratios.get("v") else 1.0
        new_width = root.winfo_width() + (width - available_width) / max(width_ratio, 0.05)
        new_height = root.winfo_height() + (height - available_height) / max(height_ratio, 0.05)
        min_width, min_height = root.minsize()
        max_width = root.winfo_screenwidth() - PREVIEW_SCREEN_MARGIN // 4
        max_height = root.winfo_screenheight() - PREVIEW_SCREEN_MARGIN
        new_width = int(round(min(max(new_width, min_width), max_width)))
        new_height = int(round(min(max(new_height, min_height), max_height)))
        self.preview_target = (width, height)
        root.geometry(f"{new_width}x{new_height}")
        root.update_idletasks()
        self._placeSashes()
        self._schedulePreviewFit()
        self._scheduleOutputFit()

    def _fitWindowToContent(self) -> None:
        """
        ウィンドウを、中身に必要な大きさにする(仕切り線も中身に合わせた位置)。その後は、その大きさで固定する
        (仕切り線の枠は、一度仕切り線を置くと、その大きさを必要な大きさとして持ち続けるので、
         各部品の必要な大きさから計算する)
        """
        root = self.root
        if root.state() != "normal":
            root.state("normal")
        position = self.currentPanelPosition()
        # 出力画面は、その画面の標準の行数にしてから大きさを測る
        if self.is_mini:
            lines = (MINI_RIGHT_OUTPUT_LINES_1, MINI_RIGHT_OUTPUT_LINES_2) if position == "right" else (
                MINI_OUTPUT_LINES_1, MINI_OUTPUT_LINES_2)
        elif self.isPanelHorizontal():
            lines = (BOTTOM_OUTPUT_LINES_1, BOTTOM_OUTPUT_LINES_2)
        else:
            lines = (DEFAULT_OUTPUT_LINES_1, DEFAULT_OUTPUT_LINES_2)
        for text_area_1, text_area_2 in zip(self.text_areas_1, self.text_areas_2):
            text_area_1.config(height=lines[0])
            text_area_2.config(height=lines[1])
        root.update_idletasks()
        left_panes = self._leftPanes()
        width = max(widget.winfo_reqwidth() for widget in left_panes)
        height = sum(widget.winfo_reqheight() for widget in left_panes) + SASH_WIDTH * (len(left_panes) - 1)
        if position == "right":
            width += SASH_WIDTH + self.panel_container.winfo_reqwidth()
            height = max(height, self.panel_container.winfo_reqheight())
        # main_frame の余白(上下左右 5px)と、テーマの色のメニューバー
        menubar_height = self._menubarHeight()
        min_width, min_height = root.minsize()
        width, height = max(width + 10, min_width), max(height + 10 + menubar_height, min_height)
        self._recordRatios(natural=True, size=(width - 10, height - 10 - menubar_height))
        root.geometry(f"{width}x{height}")
        root.update_idletasks()
        self._placeSashes()
        self.fitWindowSize()

    def _hideWindowUntilLayout(self) -> None:
        """
        起動時: 大きさを決め終わるまで、ウィンドウを見えなくする(透明にする。_showWindowAfterLayout で戻す)。
        ウィンドウを隠す(withdraw)のではなく透明にするのは、部品を配置した実際の大きさを使って、仕切り線を置くため。
        透明にできない環境では、何もしない(これまでどおり、表示してから大きさが変わる)
        """
        self._window_hidden = False
        try:
            self.root.attributes("-alpha", 0.0)
            self._window_hidden = True
        except tk.TclError:
            pass

    def _showWindowAfterLayout(self) -> None:
        """起動時に見えなくしたウィンドウを、見えるようにする(見えなくしていない場合は、何もしない)"""
        if not getattr(self, "_window_hidden", False):
            return
        self._window_hidden = False
        try:
            self.root.attributes("-alpha", 1.0)
        except tk.TclError:
            pass

    def _initWindowLayout(self) -> None:
        """
        起動時(メニューバーを付けた後): 前回のウィンドウの大きさと仕切り線の位置にしてから、ウィンドウを見えるようにする
        """
        try:
            self._restoreWindowLayout()
        except Exception:
            # 大きさを戻す途中で失敗しても、ウィンドウは必ず見えるようにする
            self._showWindowAfterLayout()
            raise
        # 大きさを戻すと、プレビューと出力画面の大きさを合わせる処理が、少し後に動く(その間、Software-Controller などの位置が動く)。
        # それが落ち着いてから、ウィンドウを見えるようにする
        self._showWindowWhenSettled(SHOW_WINDOW_TIMEOUT_MS // SHOW_WINDOW_POLL_MS, 0)

    def _layoutJobsPending(self) -> bool:
        """仕切り線・プレビュー・出力画面の大きさを合わせる処理が、予約されたままか"""
        return any(
            getattr(self, name, None) is not None for name in ("sash_place_after", "preview_fit_after", "output_fit_after")
        )

    def _showWindowWhenSettled(self, polls_left: int, quiet_polls: int) -> None:
        """
        配置の処理が落ち着いたら、ウィンドウを見えるようにする(SHOW_WINDOW_POLL_MS ごとに確かめる)。
        予約された処理がない状態が SHOW_WINDOW_QUIET_POLLS 回続いたら、落ち着いたとみなす。
        polls_left 回確かめても落ち着かなければ、そこで見えるようにする(見えないままにしない)
        quiet_polls: 予約された処理がない状態が、続いている回数
        """
        try:
            quiet_polls = 0 if self._layoutJobsPending() else quiet_polls + 1
            if quiet_polls < SHOW_WINDOW_QUIET_POLLS and polls_left > 0:
                self.root.after(SHOW_WINDOW_POLL_MS, self._showWindowWhenSettled, polls_left - 1, quiet_polls)
                return
        except Exception:
            self._logger.exception("Failed to wait for the layout")
        self._showWindowAfterLayout()

    def _restoreWindowLayout(self) -> None:
        """前回のウィンドウの大きさと仕切り線の位置にする(保存した大きさがない場合と、ミニ画面は、中身に合わせた大きさ)"""
        root = self.root
        root.update_idletasks()
        size = None
        try:
            width, height = map(int, str(self.settings.window_size).lower().split("x"))
            if width > 0 and height > 0:
                size = (width, height)
        except ValueError:
            pass
        if self.is_mini:
            # ミニ画面で起動した場合は、中身に合わせた大きさ。通常の画面に戻すときは、前回の大きさにする
            self.normal_window_size = size
            self._fitWindowToContent()
        elif size is None:
            self._fitWindowToContent()
        else:
            if self._paneKey() not in self.pane_ratios:
                self._recordRatios(natural=True)
            root.geometry("{0}x{1}".format(*size))
            root.update_idletasks()
            self._placeSashes()
            self.fitWindowSize()

    def _fitControllerNotebookHeight(self) -> None:
        """
        どのタブのウィジェットも隠れないよう、必要なら左下のタブ領域の高さを広げる
        (どのタブもtab paddingが5あるので上下分を足す。テーマを変えると部品の大きさが変わるので、そのときも行う)
        """
        self.controller_nb.update_idletasks()
        required_height = max(
            f.winfo_reqheight() + 10
            for f in (
                self.camera_f,
                self.status_f,
                *((self.audio_f,) if AUDIO_AVAILABLE else ()),
                self.serial_f,
                self.touch_screen_f,
                self.manual_control_f,
                self.commands_f,
                self.notification_f,
                self.mask_f,
                self.others_f,
            )
        )
        if required_height > int(self.controller_nb.cget("height")):
            self.controller_nb.configure(height=required_height)

    def _menubarHeight(self) -> int:
        """
        テーマの色のメニューバー(ウィンドウの中に置く)の高さ。Windows のメニューバーを使うときは 0
        """
        menubar = getattr(self, "themed_menubar", None)
        return menubar.height() if menubar is not None else 0

    def openThemeEditor(self) -> None:
        """
        表示 > テーマ > テーマを作る / 編集する...: 色を選んでテーマを作る画面を開く(すでに開いている場合は、前面に出す)。
        選んでいる間は、本体の色を一時的に変える(previewTheme)
        """
        window = getattr(self, "theme_editor_window", None)
        if window is not None and window.isOpen():
            window.lift()
            return
        self.theme_editor_window = ThemeEditorWindow(
            self.root, self.previewTheme, self._onThemeSaved, lambda: self.reloadUserThemes(quiet=True)
        )

    def previewTheme(self, theme: dict | None) -> None:
        """
        本体の色を、一時的に theme(テーマの定義)に変える。None なら、元のテーマに戻す(テーマを作る画面から呼ばれる)。
        一時的な色は、設定に保存しない(Theme.saved_theme_id)
        """
        if theme is None and Theme.saved_theme_id() == Theme.current():
            return
        root = self.root
        root.update_idletasks()
        menubar_height = self._menubarHeight()
        width, height = root.winfo_width(), root.winfo_height()
        if theme is None:
            Theme.end_preview()
        else:
            Theme.start_preview(theme)
        self.afterThemeChanged(width, height, menubar_height)

    def _onThemeSaved(self, theme_id: str) -> None:
        """テーマを作る画面で保存した後: 色を試すのをやめて、保存したテーマに切り替え、メニューに並べ直す"""
        root = self.root
        root.update_idletasks()
        menubar_height = self._menubarHeight()
        width, height = root.winfo_width(), root.winfo_height()
        if Theme.saved_theme_id() != Theme.current():
            Theme.end_preview(theme_id)
        else:
            Theme.apply(theme_id, force=True, previous=dict(Theme.THEMES[Theme.current()]["colors"]))
        self.afterThemeChanged(width, height, menubar_height)
        self.menu.buildThemeMenu()
        print(f"テーマを保存しました: {Theme.theme_name(theme_id)}")

    def reloadUserThemes(self, quiet: bool = False) -> None:
        """
        表示 > テーマ > テーマを読み込み直す: themes フォルダーのテーマを読み込み直して、メニューに並べ直す。
        今のテーマのファイルを書き換えていた場合は、その色に変える。読み込めないファイルは、理由を Output に表示する
        quiet: 読み込んだ数を表示しない(ひな形を作った直後)
        """
        root = self.root
        root.update_idletasks()
        menubar_height = self._menubarHeight()
        width, height = root.winfo_width(), root.winfo_height()
        problems = Theme.reload_user_themes()
        self.afterThemeChanged(width, height, menubar_height)
        self.menu.buildThemeMenu()
        for name, reason in problems:
            print(f"テーマのファイル {name} は、読み込めませんでした。{reason}")
        if not quiet:
            print(f"テーマを読み込み直しました(追加のテーマ: {len(Theme.user_theme_ids())} 個)。")

    def openThemeFolder(self) -> None:
        """表示 > テーマ > テーマのフォルダーを開く: themes フォルダーを開く(なければ、作る)"""
        from services.tools_service import open_folder

        try:
            os.makedirs(Theme.USER_THEME_DIR, exist_ok=True)
            open_folder(Theme.USER_THEME_DIR)
        except OSError as error:
            print(f"テーマのフォルダーを開けませんでした。({error})")

    def changeTheme(self, theme_id: str) -> None:
        """
        メニューバーの 表示 > テーマ: テーマ(配色)を変える。開いているすべてのウィンドウに、すぐ反映する
        (部品の大きさが変わるので、プレビュー・出力画面・ウィンドウの最小の大きさを合わせ直す)
        theme_id: テーマの名前(Theme.py で定義しているもの)
        """
        if theme_id == Theme.current():
            return
        root = self.root
        root.update_idletasks()
        menubar_height = self._menubarHeight()
        width, height = root.winfo_width(), root.winfo_height()
        if Theme.saved_theme_id() != Theme.current():
            # テーマを作る画面で色を試している間に、メニューでテーマを選んだ場合: 試すのをやめて、選んだテーマにする
            Theme.end_preview(theme_id)
        else:
            Theme.apply(theme_id)
        self.afterThemeChanged(width, height, menubar_height)

    def afterThemeChanged(self, width: int, height: int, menubar_height: int) -> None:
        """
        テーマを変えた後: メニューバーと、部品・ウィンドウの大きさを合わせ直す
        width / height / menubar_height: テーマを変える前の、ウィンドウの大きさと、テーマの色のメニューバーの高さ
        """
        root = self.root
        self.themed_menubar.update()
        root.update_idletasks()
        if self.is_mini:
            self._applyMiniTabs()
        else:
            self._fitControllerNotebookHeight()
        # メニューバーをウィンドウの中に置く(または外す)分だけ、ウィンドウの高さを変え、中身の大きさを保つ
        if root.state() == "normal":
            root.geometry(f"{width}x{height + self._menubarHeight() - menubar_height}")
            root.update_idletasks()
        self.fitWindowSize()
        self._placeSashes()

    def getWidgetMode(self) -> str:
        """
        右側のパネルに表示する部品の設定(Widget Mode)。ミニ画面と通常画面で別々に持つ
        """
        return self.mini_widget_mode.get() if self.is_mini else self.right_frame_widget_mode.get()

    def replace_right_frame_widget(self, *event: tk.Event) -> None:
        """
        Widget Mode や Software-Controller Position を変えたとき(と起動時、パネルの位置を変えたとき):
        右側のパネルの中の部品(Output#1 / #2・Software-Controller)を、今の設定に合わせて置き直す
        """
        for text_scroll_1, text_scroll_2, output_sash in zip(self.text_scrolls_1, self.text_scrolls_2, self.output_sashes):
            text_scroll_1.pack_forget()
            output_sash.pack_forget()
            text_scroll_2.pack_forget()
        try:
            self.output_nb.pack_forget()
        except Exception:
            pass
        try:
            self.softcon_frame.pack_forget()
        except Exception:
            pass
        # 置き直すと左右の余白はなくなるので、_alignSoftconToOutputs で付け直す
        self.softcon_applied_padx = (0, 0)

        mode = self.getWidgetMode()
        # 通常の画面でパネルを下に置いたときは、Output と Software-Controller を横に並べる
        # (Software-Controller Position の TOP は左、BOTTOM は右)
        side = "left" if self.isPanelHorizontal() else "top"
        # 横に並べるときは、出力画面の幅を詰め、パネルが左側の列より広くならないようにする(空いた幅には広がる)
        for text_area in (*self.text_areas_1, *self.text_areas_2, self.monitor_text_area, self.log_text_area,
                          self.note_text_area):
            text_area.config(width=OUTPUT_TEXT_WIDTH_HORIZONTAL if side == "left" else OUTPUT_TEXT_WIDTH)
        show_output_1 = mode == "ALL (default)" or "#1" in mode
        show_output_2 = mode == "ALL (default)" or "#2" in mode
        # 横に並べるとき、Software-Controller の枠は出力画面の横に必要な幅だけ置く
        # (出力画面を表示しない場合は、パネル全体に広げ、コントローラーを中央に表示する)
        if side == "left" and (show_output_1 or show_output_2):
            softcon_fill, softcon_expand = "y", "false"
        else:
            softcon_fill, softcon_expand = "both", "true"

        if self.pos_software_controller.get() == "1" and (
            mode == "ALL (default)" or "Controller" in mode
        ):
            self.softcon_frame.pack(
                expand=softcon_expand, fill=softcon_fill, padx="0", pady="0", side=side
            )
            self.softcon_frame.grid_anchor("center")

        for text_scroll_1, text_scroll_2, output_sash in zip(self.text_scrolls_1, self.text_scrolls_2, self.output_sashes):
            if show_output_1:
                text_scroll_1.pack(
                    expand="true", fill="both", padx="0", pady="0", side="top"
                )
            if show_output_1 and show_output_2:
                output_sash.pack(fill="x", side="top")
            if show_output_2:
                text_scroll_2.pack(
                    expand="true", fill="both", padx="0", pady="0", side="top"
                )
        if show_output_1 or show_output_2:
            self.output_nb.pack(
                expand="true", fill="both", padx="0", pady="0", side=side
            )

        if self.pos_software_controller.get() == "2" and (
            mode == "ALL (default)" or "Controller" in mode
        ):
            self.softcon_frame.pack(
                expand=softcon_expand, fill=softcon_fill, padx="0", pady="0", side=side
            )
            self.softcon_frame.grid_anchor("center")

        self._alignSoftconToOutputs()
        # 表示する部品が変わると必要な大きさも変わるので、最小の大きさと出力画面の行数を合わせ直す
        self.fitWindowSize()

    def _alignSoftconToOutputs(self, event: tk.Event | None = None) -> None:
        """
        Output#1 / #2 と Software-Controller を縦に並べるとき、Software-Controller の枠の左右を、
        Output#1 / #2 の枠(ノートブックの内側)に揃える
        """
        page = (*self.output_pages, self.monitor_page, self.log_page, self.note_page)[self.output_nb.index("current")]
        if page.winfo_width() > 1:
            padx = (page.winfo_x(), max(self.output_nb.winfo_width() - page.winfo_x() - page.winfo_width(), 0))
            if padx != self.softcon_padx:
                self.softcon_padx = padx
                self._updatePaneMinSizes()
        if self.softcon_frame.winfo_manager() != "pack":
            return
        padx = (0, 0) if self.isPanelHorizontal() or not self.output_nb.winfo_manager() else self.softcon_padx
        if padx != self.softcon_applied_padx:
            self.softcon_applied_padx = padx
            self.softcon_frame.pack_configure(padx=padx)

    def currentPanelPosition(self) -> str:
        """
        今の画面(通常の画面 / ミニ画面)での、右側のパネルの位置
        """
        return self.mini_panel_position if self.is_mini else self.panel_position

    def isPanelHorizontal(self) -> bool:
        """
        パネルの中の Output と Software-Controller を横に並べるか(通常の画面で、パネルを下に置いたとき)
        """
        return not self.is_mini and self.panel_position == "bottom"

    def toggleSidePanel(self) -> None:
        """
        右側のパネル(Output・Software-Controller)の位置を、右 → 下 → 表示しない の順に切り替える
        """
        position = PANEL_POSITIONS[(PANEL_POSITIONS.index(self.currentPanelPosition()) + 1) % len(PANEL_POSITIONS)]
        if self.is_mini:
            self.mini_panel_position = position
        else:
            self.panel_position = position
        self.replace_right_frame_widget()
        if self.is_mini:
            # ミニ画面: 切り替えたときと同じく、プレビューを高さ MINI_PREVIEW_MIN_HEIGHT にし、中身に合わせた大きさにする
            self.setPreviewSize(*self.previewSizeForHeight(MINI_PREVIEW_MIN_HEIGHT))
            self.pane_ratios.pop(self._paneKey(), None)
            self.buildPanes()
            self._fitWindowToContent()
        else:
            # 通常の画面: パネルの中の並び(下に置いたときは横)を合わせてから、プレビューの大きさを保ったまま置き直す
            self.applySidePanel(keep_preview=True)

    def applySidePanel(self, keep_preview: bool = False) -> None:
        """
        右側のパネル(Output・Software-Controller)を、今の位置(右 / 下 / 表示しない)に置き直す
        keep_preview: プレビューの大きさが変わらないように、ウィンドウの大きさを変える
        """
        preview_size = (self.preview.show_width, self.preview.show_height)
        self.buildPanes()
        if keep_preview and getattr(self, "window_ready", False):
            self.resizeWindowForPreview(*preview_size)

    ############### ミニ画面 ###############
    def toggleMiniMode(self) -> None:
        """Mini / Full ボタン: ミニ画面と通常の画面を切り替える"""
        self.setMiniMode(not self.is_mini)

    def setMiniMode(self, mini: bool) -> None:
        """
        ミニ画面と通常の画面を切り替える(mini: True ならミニ画面にする)
        ミニ画面: 表示サイズを最小に固定し、上から ボタン / プレビュー / コマンドの選択 / 右側のパネル を並べる。
                  Commands以外のタブは表示しない
        (部品は作り直さず、配置と大きさだけを切り替える)
        """
        if mini == self.is_mini:
            return
        if mini and self.is_use_Pro_Controller.get():
            # Use Pro Controllerが有効な間はCommandsタブを使えないため、ミニ画面にできない
            print("Mini: Use Pro Controller を無効にしてから切り替えてください。")
            return
        root = self.root
        if mini:
            # 通常画面に戻すときのために、表示サイズ・タブ領域の状態・ウィンドウの大きさ・パネルの位置を覚えておく
            self.mini_saved_show_size = self.show_size.get()
            self.mini_saved_panel_position = self.panel_position
            self.mini_saved_tab = self.controller_nb.select()
            self.mini_saved_nb_height = int(self.controller_nb.cget("height"))
            if getattr(self, "window_ready", False) and root.state() == "normal":
                self.normal_window_size = (root.winfo_width(), root.winfo_height())
        if root.state() != "normal":
            root.state("normal")
        # パネルの位置(右 / 下 / 表示しない)は、切り替える前の画面と同じにする
        if mini:
            self.mini_panel_position = self.panel_position
        else:
            self.panel_position = self.mini_panel_position
        self.is_mini = mini
        if mini:
            # (is_mini を切り替えた後なので、下限はミニ画面の MINI_PREVIEW_MIN_HEIGHT)
            self.show_size.set("{0}x{1}".format(*self.previewSizeForHeight(MINI_PREVIEW_MIN_HEIGHT)))
        else:
            self.show_size.set(self.mini_saved_show_size)

        self._applyMiniButtons()
        self._applyMiniCommands()
        self._applyMiniTabs()
        width, height = map(int, self.show_size.get().split("x"))
        self.setPreviewSize(width, height)
        self.replace_right_frame_widget()
        if mini:
            # ミニ画面: プレビューを高さ MINI_PREVIEW_MIN_HEIGHT にし、中身に合わせた大きさで始める
            # (仕切り線の位置も、中身に合わせた位置にする)
            self.pane_ratios.pop(self._paneKey(), None)
            self.buildPanes()
            if getattr(self, "window_ready", False):
                self._fitWindowToContent()
        else:
            # 通常の画面: ミニ画面にする前の大きさと仕切り線の位置に戻す
            self.buildPanes()
            size = getattr(self, "normal_window_size", None)
            if size is not None and getattr(self, "window_ready", False):
                root.geometry("{0}x{1}".format(*size))
                root.update_idletasks()
                self._placeSashes()
                if self.panel_position != getattr(self, "mini_saved_panel_position", self.panel_position):
                    # ミニ画面でパネルの位置を変えた場合は、ミニ画面にする前のプレビューの大きさになるように、ウィンドウの大きさを変える
                    self.resizeWindowForPreview(width, height)

    def _applyMiniButtons(self) -> None:
        """
        Main Panelのボタン: ミニ画面では Start / Pause / Reload / Capture / Panel / Full だけを並べる
        """
        full_only = (
            (self.simplecon_top_button, 1),
            (self.clear_top_button, 2),
            (self.screenshot_button, 4),
            (self.open_capture_button, 5),
            (self.discord_button, 6),
        )
        if self.is_mini:
            for button, _ in full_only:
                button.grid_remove()
            self.mini_pause_button.grid(column="1", padx="2", pady="5", row="0", sticky="ew")
            self.mini_reload_button.grid(column="2", padx="2", pady="5", row="0", sticky="ew")
            # ミニ画面では、幅を広げない(以前と同じ幅。Loading... は、途中までの表示になる)
            self.start_top_button.configure(width="7")
            self.start_top_button.grid_configure(padx="2")
            self.capture_button.configure(width="7")
            self.capture_button.grid_configure(padx="2")
            self.side_panel_button.grid_configure(padx="2")
            self.mini_button.configure(text="Full")
            self.mini_button.grid_configure(padx="2")
            self._syncMiniButtons()
        else:
            if self.mini_button_sync_after is not None:
                self.root.after_cancel(self.mini_button_sync_after)
                self.mini_button_sync_after = None
            self.mini_pause_button.grid_remove()
            self.mini_reload_button.grid_remove()
            for button, _ in full_only:
                button.grid()
            self.start_top_button.configure(width="9")
            self.start_top_button.grid_configure(padx="5")
            self.capture_button.grid_configure(padx="5")
            self.side_panel_button.grid_configure(padx="5")
            self.mini_button.configure(text="Mini")
            self.mini_button.grid_configure(padx="5")

    def _syncMiniButtons(self) -> None:
        """
        上段のPause/Reloadボタンの表示と有効・無効を、Commandsタブのボタンに合わせる(ミニ画面の間、定期的に行う)
        """
        self.mini_button_sync_after = None
        if not self.is_mini:
            return
        for mini_button, button in (
            (self.mini_pause_button, self.pause_button),
            (self.mini_reload_button, self.reload_command_button),
        ):
            for option in ("text", "state"):
                value = str(button[option])
                if str(mini_button[option]) != value:
                    mini_button[option] = value
        self.mini_button_sync_after = self.root.after(MINI_BUTTON_SYNC_INTERVAL_MS, self._syncMiniButtons)

    def _applyMiniCommands(self) -> None:
        """
        Commandsタブの中身: ミニ画面では幅を狭くする
        (一覧はCommandの列のみ、小タブの名前を短く、Shortcutは3列、右のボタン列は表示しない)
        """
        mini = self.is_mini
        for index, names in enumerate(COMMAND_TAB_NAMES):
            self.command_nb.tab(index, text=names[1] if mini else names[0])
        for tv in self.command_trees.values():
            tv.configure(
                displaycolumns=("command",) if mini else "#all",
                height=MINI_COMMAND_TREE_LINES if mini else COMMAND_TREE_LINES,
            )
            tv.column("command", width=MINI_COMMAND_NB_WIDTH - 40 if mini else 330)
        self.history_tv.configure(displaycolumns=("command",) if mini else "#all")
        self.history_tv.column("command", width=MINI_COMMAND_NB_WIDTH - 40 if mini else 350)
        columns = MINI_SHORTCUT_COLUMNS if mini else SHORTCUT_COLUMNS
        for num, button in self.shortcut_buttons.items():
            button.grid_configure(column=(num - 1) % columns, row=(num - 1) // columns)
        for col in range(max(SHORTCUT_COLUMNS, MINI_SHORTCUT_COLUMNS)):
            if col < columns:
                self.shortcut_f.columnconfigure(col, weight=1, uniform="shortcut")
            else:
                self.shortcut_f.columnconfigure(col, weight=0, uniform="")
        self.command_nb.configure(width=MINI_COMMAND_NB_WIDTH if mini else 580)
        # ミニ画面ではウィンドウの幅を広げたときに、コマンドの一覧も横に伸びるようにする
        self.commands_f.columnconfigure(0, weight=1 if mini else 0)
        if mini:
            self.action_commands_f.pack_forget()
        else:
            self.action_commands_f.pack(padx="5", pady="5", side="left")

    def _applyMiniTabs(self) -> None:
        """
        タブ領域と全体の配置: ミニ画面ではCommandsの中身だけを、タブの見出しなしで表示する
        """
        if self.is_mini:
            # タブの見出しを表示しないスタイルにして、Commandsタブを選ぶ
            style = ttk.Style()
            style.layout("Mini.TNotebook.Tab", [])
            self.controller_nb.configure(style="Mini.TNotebook")
            self.controller_nb.select(self.commands_f)
            self.root.update_idletasks()
            # タブ領域の大きさは、全タブの中身の最大ではなく、Commandsの中身に合わせる
            self.controller_nb.configure(
                width=MINI_WIDTH - 22, height=self.select_commands_f.winfo_reqheight()
            )
        else:
            self.controller_nb.configure(style="TNotebook", width=0, height=self.mini_saved_nb_height)
            # ミニ画面の間にテーマを変えた場合は、部品の大きさが変わっているので、高さを合わせ直す
            self._fitControllerNotebookHeight()
            if self.mini_saved_tab in self.controller_nb.tabs():
                self.controller_nb.select(self.mini_saved_tab)
