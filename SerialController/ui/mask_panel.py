#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mask タブ: プレビューの目隠し
"""
from __future__ import annotations

import tkinter as tk
import os
import tkinter.ttk as ttk
import tkinter.messagebox as tkmsg
import tkinter.filedialog as tkfiledialog
import tkinter.colorchooser as tkcolor
from services import geometry
from Mask import DEFAULT_MASK_COLOR, MASK_SHAPES, Mask, draw_masks, load_masks, save_masks
from ui.constants import MASK_DIR


class MaskPanelMixin:
    """
    Mask タブ: プレビューの目隠し
    (PokeControllerApp に取り込んで使う。部品や設定は self の属性として、ほかのファイルと共有する)
    """

    def _buildMaskTab(self) -> None:
        """
        Mask タブの部品を作る(起動時に1回だけ呼ぶ)
        """
        self.mask_f = ttk.Frame(self.controller_nb)
        # 左: 一覧と追加・削除、右: 全体の設定と、選んだ目隠しの編集
        self.mask_f.columnconfigure(1, weight=1)
        self.mask_left_f = ttk.Frame(self.mask_f)
        self.mask_list_f = ttk.Frame(self.mask_left_f)
        mask_columns = (("shape", "Shape", 72), ("x1", "X1", 42), ("y1", "Y1", 42), ("x2", "X2", 42), ("y2", "Y2", 42),
                        ("color", "Color", 58), ("enabled", "Enabled", 58))  # fmt: skip
        self.mask_tv = ttk.Treeview(self.mask_list_f)
        self.mask_tv.configure(
            columns=[c[0] for c in mask_columns], show="headings", height=3, selectmode="browse"
        )
        for name, text, width in mask_columns:
            self.mask_tv.heading(name, text=text)
            self.mask_tv.column(name, width=width, anchor="center", stretch=False)
        self.mask_tv.pack(side="left")
        self.mask_tv_scroll = ttk.Scrollbar(self.mask_list_f, orient="vertical", command=self.mask_tv.yview)
        self.mask_tv.configure(yscrollcommand=self.mask_tv_scroll.set)
        self.mask_tv_scroll.pack(side="left", fill="y")
        self.mask_tv.bind("<<TreeviewSelect>>", self.onMaskSelected)
        self.mask_list_f.pack(anchor="w", side="top")
        self.mask_buttons_f = ttk.Frame(self.mask_left_f)
        self.mask_shape = tk.StringVar(value=MASK_SHAPES[0])
        self.mask_shape_cb = ttk.Combobox(self.mask_buttons_f)
        self.mask_shape_cb.configure(state="readonly", textvariable=self.mask_shape, values=MASK_SHAPES, width="10")
        self.mask_shape_cb.pack(side="left", padx=(0, 4))
        self.mask_add_button = ttk.Button(self.mask_buttons_f)
        self.mask_add_button.configure(text="Add", width="8", command=self.toggleMaskDrawing)
        self.mask_add_button.pack(side="left", padx="4")
        self.mask_delete_button = ttk.Button(self.mask_buttons_f)
        self.mask_delete_button.configure(text="Delete", width="8", command=self.deleteMask)
        self.mask_delete_button.pack(side="left", padx="4")
        # 目隠しの一覧をファイルに書き出す / ファイルから読み込む
        self.mask_load_button = ttk.Button(self.mask_buttons_f)
        self.mask_load_button.configure(text="Load", width="6", command=self.loadMasks)
        self.mask_load_button.pack(side="right")
        self.mask_save_button = ttk.Button(self.mask_buttons_f)
        self.mask_save_button.configure(text="Save", width="6", command=self.saveMasks)
        self.mask_save_button.pack(side="right", padx="4")
        self.mask_buttons_f.pack(fill="x", pady=(4, 0), side="top")
        self.mask_left_f.grid(column="0", row="0", padx="5", pady="3", sticky="nw")

        self.mask_right_f = ttk.Frame(self.mask_f)
        self.mask_options_f = ttk.Frame(self.mask_right_f)
        self.is_show_mask = tk.BooleanVar(value=True)
        self.show_mask_checkbox = ttk.Checkbutton(self.mask_options_f)
        self.show_mask_checkbox.configure(text="Show Mask", variable=self.is_show_mask, command=self.applyMasks)
        self.show_mask_checkbox.pack(side="left", padx="4")
        self.is_mask_apply_to_capture = tk.BooleanVar(value=False)
        self.mask_apply_to_capture_checkbox = ttk.Checkbutton(self.mask_options_f)
        self.mask_apply_to_capture_checkbox.configure(
            text="Apply to Capture", variable=self.is_mask_apply_to_capture, command=self.applyMasks
        )
        self.mask_apply_to_capture_checkbox.pack(side="left", padx="4")
        self.mask_options_f.pack(anchor="w", pady=(0, 2), side="top")
        # 選択中の目隠しの座標(カメラ画像の座標)・色・有効/無効
        self.mask_coords_lf = ttk.Labelframe(self.mask_right_f)
        self.mask_coord_vars = {}
        self.mask_coord_spinboxes = {}
        for name, text, row, column in (("x1", "X1:", 0, 0), ("y1", "Y1:", 0, 2), ("x2", "X2:", 1, 0), ("y2", "Y2:", 1, 2)):
            ttk.Label(self.mask_coords_lf, text=text).grid(column=column, row=row, padx=(8, 4), pady="4", sticky="w")
            var = tk.StringVar(value="")
            spinbox = ttk.Spinbox(
                self.mask_coords_lf, textvariable=var, from_=0, to=9999, increment=1, width=6, command=self.applyMaskCoords
            )
            spinbox.grid(column=column + 1, row=row, padx="4", pady="4", sticky="w")
            spinbox.bind("<Return>", self.applyMaskCoords)
            spinbox.bind("<FocusOut>", self.applyMaskCoords)
            self.mask_coord_vars[name] = var
            self.mask_coord_spinboxes[name] = spinbox
        self.mask_color_button = ttk.Button(self.mask_coords_lf)
        self.mask_color_button.configure(text="Color", width="7", command=self.chooseMaskColor)
        self.mask_color_button.grid(column="4", row="0", padx="8", pady="4", sticky="w")
        self.is_mask_enabled = tk.BooleanVar(value=True)
        self.mask_enabled_checkbox = ttk.Checkbutton(self.mask_coords_lf)
        self.mask_enabled_checkbox.configure(text="Enabled", variable=self.is_mask_enabled, command=self.applyMaskEnabled)
        self.mask_enabled_checkbox.grid(column="4", row="1", padx="8", pady="4", sticky="w")
        self.mask_coords_lf.configure(text="Selected Mask (Capture座標)")
        self.mask_coords_lf.pack(anchor="w", side="top")
        self.mask_right_f.grid(column="1", row="0", padx="5", pady="3", sticky="nw")
        self.controller_nb.add(self.mask_f, padding="5", sticky="nsew", text="Mask")
        # Maskタブを表示している間だけ、選択中の目隠しの枠をプレビューに表示する
        self.controller_nb.bind("<<NotebookTabChanged>>", self.applyMasks, add="+")

    ############### 目隠し ###############
    def _selectedMaskIndex(self) -> int | None:
        """一覧で選択中の目隠しの番号(self.masks の位置)を返す(選択していない場合は None)"""
        selection = self.mask_tv.selection()
        if not selection:
            return None
        index = self.mask_tv.index(selection[0])
        return index if index < len(self.masks) else None

    def refreshMaskList(self, select: int | None = None) -> None:
        """
        目隠しの一覧を表示し直し、プレビュー等に反映する
        select: 選択する目隠しの番号(Noneなら選択しない)
        """
        self.mask_tv.delete(*self.mask_tv.get_children())
        for mask in self.masks:
            self.mask_tv.insert(
                "", "end", values=(mask.shape, mask.x1, mask.y1, mask.x2, mask.y2, mask.color, "✓" if mask.enabled else "")
            )
        if select is not None and 0 <= select < len(self.masks):
            item = self.mask_tv.get_children()[select]
            self.mask_tv.selection_set(item)
            self.mask_tv.see(item)
        self.onMaskSelected()

    def onMaskSelected(self, *event: tk.Event) -> None:
        """
        選択中の目隠しの座標・有効を入力欄に表示する(一覧で選んだとき、一覧を表示し直したとき)
        選択していない間は、入力欄と Delete・Color・Enabled を無効にする
        """
        index = self._selectedMaskIndex()
        mask = None if index is None else self.masks[index]
        for name, var in self.mask_coord_vars.items():
            var.set("" if mask is None else str(getattr(mask, name)))
        self.is_mask_enabled.set(True if mask is None else mask.enabled)
        state = "disabled" if mask is None else "normal"
        for widget in (self.mask_delete_button, self.mask_color_button, self.mask_enabled_checkbox):
            widget["state"] = state
        for spinbox in self.mask_coord_spinboxes.values():
            spinbox["state"] = state
        self.applyMasks()

    def applyMasks(self, *event: tk.Event) -> None:
        """
        目隠しをプレビューと、スクリーンショットの保存に反映する
        (タッチ画面の表示は、画像を作るたびにself.masksを参照する)
        Show Mask・Apply to Capture を切り替えたとき、タブを切り替えたとき、目隠しを選んだときに呼ばれる
        """
        if not hasattr(self, "preview"):
            return
        # 選択中の目隠しの枠は、Maskタブを表示している間だけ表示する
        on_mask_tab = self.controller_nb.select() == str(self.mask_f)
        self.preview.setMasks(self.masks, self.is_show_mask.get(), self._selectedMaskIndex() if on_mask_tab else None)
        if self.is_show_mask.get() and self.is_mask_apply_to_capture.get():
            self.camera.capture_filter = lambda frame: draw_masks(frame, self.masks)
        else:
            self.camera.capture_filter = None

    def toggleMaskDrawing(self) -> None:
        """
        Addボタン: 次にプレビュー上を左ドラッグした範囲に目隠しを追加する(もう一度押すと取り消す)
        """
        if self.mask_add_button["text"] == "Cancel":
            self.preview.cancelMaskDrawing()
            self.mask_add_button["text"] = "Add"
            return
        self.mask_add_button["text"] = "Cancel"
        self.preview.startMaskDrawing(self.mask_shape.get(), self._onMaskDrawn)
        print("Mask: キャプチャ画面の上を左ドラッグして、目隠しの範囲を指定してください。")

    def _onMaskDrawn(self, shape: str, x1: int, y1: int, x2: int, y2: int) -> None:
        """
        プレビュー上のドラッグが終わったとき: その範囲の目隠しを一覧に追加する(小さすぎる範囲は追加しない)
        shape: 図形(MASK_SHAPES のどれか)
        x1, y1, x2, y2: 範囲(カメラ画像の座標)
        """
        self.mask_add_button["text"] = "Add"
        if x2 - x1 < 2 or y2 - y1 < 2:
            print("Mask: 範囲が小さすぎるため、追加しませんでした。")
            return
        self.masks.append(Mask(shape, x1, y1, x2, y2, DEFAULT_MASK_COLOR, True))
        self.refreshMaskList(select=len(self.masks) - 1)

    def deleteMask(self) -> None:
        """Deleteボタン: 選択中の目隠しを削除する"""
        index = self._selectedMaskIndex()
        if index is None:
            return
        del self.masks[index]
        self.refreshMaskList(select=min(index, len(self.masks) - 1) if self.masks else None)

    def saveMasks(self) -> None:
        """
        Saveボタン: 目隠しの一覧を、名前を付けてファイルに書き出す
        """
        if not self.masks:
            tkmsg.showinfo("Save Masks", "書き出す目隠しがありません。")
            return
        os.makedirs(MASK_DIR, exist_ok=True)
        path = tkfiledialog.asksaveasfilename(
            parent=self.root,
            title="Save Masks",
            initialdir=MASK_DIR,
            defaultextension=".json",
            filetypes=[("Mask", "*.json")],
        )
        if not path:
            return
        try:
            save_masks(path, self.masks)
        except OSError as e:
            self._logger.error(f"Failed to save masks: {e}")
            tkmsg.showerror("Save Masks", f"書き出せませんでした。\n{e}")
            return
        print(f"Mask: {len(self.masks)}個の目隠しを書き出しました。({path})")

    def loadMasks(self) -> None:
        """
        Loadボタン: ファイルから目隠しの一覧を読み込む(今の目隠しがある場合は、置き換えるか追加するかを選ぶ)
        """
        os.makedirs(MASK_DIR, exist_ok=True)
        path = tkfiledialog.askopenfilename(
            parent=self.root, title="Load Masks", initialdir=MASK_DIR, filetypes=[("Mask", "*.json")]
        )
        if not path:
            return
        try:
            masks = load_masks(path)
        except (OSError, ValueError) as e:
            self._logger.error(f"Failed to load masks: {e}")
            tkmsg.showerror("Load Masks", f"読み込めませんでした。\n{e}")
            return
        if self.masks:
            ret = tkmsg.askyesnocancel(
                "Load Masks",
                f"今の目隠し({len(self.masks)}個)を、読み込んだ目隠し({len(masks)}個)に置き換えますか？\n\n"
                "「はい」: 置き換える\n「いいえ」: 今の目隠しに追加する",
            )
            if ret is None:
                return
            if ret:
                self.masks.clear()
        self.masks.extend(masks)
        self.refreshMaskList(select=len(self.masks) - 1 if self.masks else None)
        print(f"Mask: {len(masks)}個の目隠しを読み込みました。({path})")

    def chooseMaskColor(self) -> None:
        """Colorボタン: 色を選ぶ画面を開き、選んだ色を選択中の目隠しに設定する"""
        index = self._selectedMaskIndex()
        if index is None:
            return
        _, color = tkcolor.askcolor(color=self.masks[index].color, title="Mask Color", parent=self.root)
        if color is None:
            return
        self.masks[index].color = color.lower()
        self.refreshMaskList(select=index)

    def applyMaskEnabled(self) -> None:
        """Enabled のチェックを切り替えたとき: 選択中の目隠しの有効・無効に反映する"""
        index = self._selectedMaskIndex()
        if index is None:
            return
        self.masks[index].enabled = self.is_mask_enabled.get()
        self.refreshMaskList(select=index)

    def applyMaskCoords(self, *event: tk.Event) -> None:
        """
        入力欄の座標を選択中の目隠しに反映する(数値でない場合や範囲が空になる場合は、元の値に戻す)
        """
        index = self._selectedMaskIndex()
        if index is None:
            return
        mask = self.masks[index]
        try:
            x1, y1, x2, y2 = (int(self.mask_coord_vars[name].get()) for name in ("x1", "y1", "x2", "y2"))
        except ValueError:
            self.onMaskSelected()
            return
        # カメラ画像の範囲に収める
        area = geometry.clamp_area(x1, y1, x2, y2, *self.camera.capture_size)
        if area is None:
            self.onMaskSelected()
            return
        x1, y1, x2, y2 = area
        if area == (mask.x1, mask.y1, mask.x2, mask.y2):
            self.onMaskSelected()
            return
        mask.x1, mask.y1, mask.x2, mask.y2 = x1, y1, x2, y2
        self.refreshMaskList(select=index)
