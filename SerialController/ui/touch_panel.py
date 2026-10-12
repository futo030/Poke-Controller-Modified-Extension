#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Touch Screen タブ: プレビュー上のタッチスクリーンの範囲
"""
from __future__ import annotations

import tkinter as tk
import cv2
import tkinter.ttk as ttk
from PIL import Image
from Mask import draw_masks
from services import geometry


class TouchPanelMixin:
    """
    Touch Screen タブ: プレビュー上のタッチスクリーンの範囲
    (PokeControllerApp に取り込んで使う。部品や設定は self の属性として、ほかのファイルと共有する)
    """

    def _buildTouchScreenTab(self) -> None:
        """
        Touch Screen タブの部品を作る(起動時に1回だけ呼ぶ)
        """
        # Touch Screenタブ: プレビュー上のタッチスクリーンの範囲(Qingpi/3DS用)を数値で設定する
        # (プレビュー上のCtrl+右ドラッグで設定する値と共通)
        self.touch_screen_f = ttk.Frame(self.controller_nb)
        # Start / End を行に、X / Y を列にそろえる。右に範囲の大きさを表示する
        self.touchscreen_vars = {}
        self.touchscreen_spinboxes = {}
        touchscreen_fields = (
            ("start_x", "Start", 0, "X:", 1),
            ("start_y", None, 0, "Y:", 3),
            ("end_x", "End", 1, "X:", 1),
            ("end_y", None, 1, "Y:", 3),
        )
        for name, row_text, row, text, column in touchscreen_fields:
            if row_text is not None:
                ttk.Label(self.touch_screen_f, text=row_text).grid(
                    column="0", row=row, padx=(8, 4), pady="4", sticky="w"
                )
            ttk.Label(self.touch_screen_f, text=text).grid(column=column, row=row, padx=(8, 4), pady="4", sticky="w")
            var = tk.StringVar(value="0")
            spinbox = ttk.Spinbox(
                self.touch_screen_f,
                textvariable=var,
                from_=0,
                to=9999,
                increment=1,
                width=7,
                command=self.applyTouchscreenArea,
            )
            spinbox.grid(column=column + 1, row=row, padx="4", pady="4", sticky="w")
            spinbox.bind("<Return>", self.applyTouchscreenArea)
            spinbox.bind("<FocusOut>", self.applyTouchscreenArea)
            self.touchscreen_vars[name] = var
            self.touchscreen_spinboxes[name] = spinbox
        self.touch_screen_size_label = ttk.Label(self.touch_screen_f)
        self.touch_screen_size_label.configure(text="Size:")
        self.touch_screen_size_label.grid(column="5", row="0", padx=(24, 4), pady="4", sticky="w")
        self.touch_screen_coord_label = ttk.Label(self.touch_screen_f)
        self.touch_screen_coord_label.configure(text="(Main Panel上の座標)")
        self.touch_screen_coord_label.grid(column="5", row="1", padx=(24, 4), pady="4", sticky="w")
        # 座標を、取り込みサイズ(Capture Size)上の値で表示・入力するか(オフならMain Panel(Show Size)上の値)
        self.is_touchscreen_capture_size = tk.BooleanVar(value=False)
        self.touch_screen_capture_size_checkbox = ttk.Checkbutton(self.touch_screen_f)
        self.touch_screen_capture_size_checkbox.configure(
            text="Capture Size",
            variable=self.is_touchscreen_capture_size,
            command=self.onTouchscreenCaptureSizeToggled,
        )
        self.touch_screen_capture_size_checkbox.grid(column="6", row="0", padx=(24, 4), pady="4", sticky="w")
        self.touch_screen_hint = ttk.Label(self.touch_screen_f)
        self.touch_screen_hint.configure(text="Main Panel上で Ctrl + 右ドラッグ しても設定できます(値は共通です)")
        self.touch_screen_hint.grid(column="0", columnspan="7", row="2", padx=(8, 4), pady="4", sticky="w")
        self.touch_screen_f.pack()
        self.controller_nb.add(self.touch_screen_f, padding="5", sticky="nsew", text="Touch Screen")

    def _scaleTouchscreenArea(self, width: int, height: int) -> None:
        """
        プレビューの大きさを変えたとき: タッチスクリーンの範囲を、プレビューに対する割合を保ったまま変える
        (割合がまだ無い場合は何もしない)
        width, height: 新しいプレビューの大きさ
        """
        ratio = getattr(self, "touchscreen_ratio", None)
        if ratio is None:
            return
        # 範囲を変えたことによる Touch Screen タブの更新で、割合を計算し直さない(丸めの誤差がたまらないように)
        self._touchscreen_scaling = True
        try:
            self.preview.setTouchscreenArea(*geometry.ratio_to_area(ratio, width, height))
        finally:
            self._touchscreen_scaling = False

    def updateTouchscreenEntries(self) -> None:
        """
        プレビューのタッチスクリーンの範囲を、Touch Screenタブの数値に反映する
        """
        preview = self.preview
        values = {
            "start_x": preview.touchscreen_start_x,
            "start_y": preview.touchscreen_start_y,
            "end_x": preview.touchscreen_end_x,
            "end_y": preview.touchscreen_end_y,
        }
        if not getattr(self, "_touchscreen_scaling", False) and preview.show_width > 0 and preview.show_height > 0:
            # プレビューの大きさを変えたときに、範囲を同じ割合で変えるための、プレビューに対する割合
            self.touchscreen_ratio = geometry.area_to_ratio(
                tuple(values.values()), preview.show_width, preview.show_height
            )
        if self.is_touchscreen_capture_size.get():
            # 取り込みサイズ上の座標で表示する(プレビューの大きさを変えても、値は変わらない)
            capture_values = self._touchscreenCaptureValues()
            if capture_values is not None:
                values = dict(zip(values, capture_values))
        for name, value in values.items():
            self.touchscreen_vars[name].set(str(int(value)))
        width = int(values["end_x"]) - int(values["start_x"])
        height = int(values["end_y"]) - int(values["start_y"])
        self.touch_screen_size_label["text"] = f"Size:  {width} x {height}"
        self.touch_screen_coord_label["text"] = (
            "(Capture Size上の座標)" if self.is_touchscreen_capture_size.get() else "(Main Panel上の座標)"
        )

    def _touchscreenCaptureValues(self) -> tuple[int, int, int, int] | None:
        """
        タッチスクリーンの範囲を、取り込みサイズ上の座標 (start_x, start_y, end_x, end_y) で返す(求められない場合はNone)
        """
        ratio = getattr(self, "touchscreen_ratio", None)
        camera = getattr(self, "camera", None)
        if ratio is None or camera is None:
            return None
        return geometry.ratio_to_area(ratio, *camera.capture_size)

    def _restoreTouchscreenRatio(self, text: str) -> None:
        """
        起動時: 保存していた割合を読み込む。保存していたプレビュー上の範囲と合っている場合のみ使う
        (合っていない場合は、プレビュー上の範囲から求めた割合のままにする)
        text: 設定ファイルに保存していた割合の文字
        """
        ratio = geometry.parse_ratio(text)
        if ratio is None:
            return
        preview = self.preview
        actual = (
            preview.touchscreen_start_x,
            preview.touchscreen_start_y,
            preview.touchscreen_end_x,
            preview.touchscreen_end_y,
        )
        if geometry.ratio_matches_area(ratio, actual, preview.show_width, preview.show_height):
            self.touchscreen_ratio = ratio
            self.onTouchscreenCaptureSizeToggled()

    def onTouchscreenCaptureSizeToggled(self) -> None:
        """
        Touch Screenタブの Capture Size: 座標の表示を、取り込みサイズ上の値とMain Panel上の値で切り替える
        (範囲そのものは変えず、数値だけを変換する)
        """
        self._touchscreen_scaling = True
        try:
            self.updateTouchscreenEntries()
        finally:
            self._touchscreen_scaling = False

    def _applyTouchscreenCaptureArea(self, start_x: int, start_y: int, end_x: int, end_y: int) -> None:
        """
        取り込みサイズ上の座標で入力された範囲を反映する。
        入力された値をそのまま保つため、割合を入力値から決め、プレビュー上の範囲はそこから求める
        """
        capture_width, capture_height = self.camera.capture_size
        area = geometry.clamp_area(start_x, start_y, end_x, end_y, capture_width, capture_height)
        if area is None:
            print("Touch Screen: End は Start より大きい値にしてください。")
            self.onTouchscreenCaptureSizeToggled()
            return
        start_x, start_y, end_x, end_y = area
        if area == self._touchscreenCaptureValues():
            # 範囲に収めた結果を表示に戻すだけ
            self.onTouchscreenCaptureSizeToggled()
            return
        self.touchscreen_ratio = geometry.area_to_ratio(area, capture_width, capture_height)
        self._scaleTouchscreenArea(self.preview.show_width, self.preview.show_height)
        self.preview.showTouchscreenArea()
        print(f"Touchscreen Area (Capture Size): ({start_x}, {start_y}), ({end_x}, {end_y})")

    def applyTouchscreenArea(self, *event: tk.Event) -> None:
        """
        Touch Screenタブの数値を、プレビューのタッチスクリーンの範囲に反映する
        (数値でない場合や範囲が空になる場合は、元の値に戻す)
        event: 使わない(Enter・フォーカスが外れたときはイベントが渡され、上下のボタンからは引数なしで呼ばれる)
        """
        if self.is_touchscreen_capture_size.get():
            try:
                values = [int(self.touchscreen_vars[name].get()) for name in ("start_x", "start_y", "end_x", "end_y")]
            except ValueError:
                self.onTouchscreenCaptureSizeToggled()
                return
            self._applyTouchscreenCaptureArea(*values)
            return
        preview = self.preview
        current = (
            preview.touchscreen_start_x,
            preview.touchscreen_start_y,
            preview.touchscreen_end_x,
            preview.touchscreen_end_y,
        )
        try:
            start_x, start_y, end_x, end_y = (
                int(self.touchscreen_vars[name].get()) for name in ("start_x", "start_y", "end_x", "end_y")
            )
        except ValueError:
            self.updateTouchscreenEntries()
            return
        # プレビューの範囲に収める
        area = geometry.clamp_area(start_x, start_y, end_x, end_y, preview.show_width, preview.show_height)
        if area is None:
            print("Touch Screen: End は Start より大きい値にしてください。")
            self.updateTouchscreenEntries()
            return
        start_x, start_y, end_x, end_y = area
        if area == current:
            # 範囲に収めた結果を表示に戻すだけ
            self.updateTouchscreenEntries()
            return
        preview.setTouchscreenArea(start_x, start_y, end_x, end_y)
        preview.showTouchscreenArea()
        print(f"Touchscreen Area: ({start_x}, {start_y}), ({end_x}, {end_y})")

    def getTouchscreenImage(self, width: int, height: int) -> Image.Image | None:
        """
        カメラ画像からタッチスクリーンの範囲を切り出し、width x height のPIL画像にして返す
        (カメラが開いていない等で表示できない場合はNone)
        """
        # カメラが開いていない間は最新フレームがNoneになる
        # (isOpened()は呼ぶたびにデバッグログを出すので、定期的に呼ばれるここでは使わない)
        frame = self.camera.image_bgr
        if frame is None:
            return None
        preview = self.preview
        frame_height, frame_width = frame.shape[:2]
        # 範囲はプレビューの表示座標なので、カメラ画像の座標に直す
        ratio_x = frame_width / preview.show_width
        ratio_y = frame_height / preview.show_height
        x1 = min(max(int(preview.touchscreen_start_x * ratio_x), 0), frame_width)
        x2 = min(max(int(preview.touchscreen_end_x * ratio_x), 0), frame_width)
        y1 = min(max(int(preview.touchscreen_start_y * ratio_y), 0), frame_height)
        y2 = min(max(int(preview.touchscreen_end_y * ratio_y), 0), frame_height)
        if x2 <= x1 or y2 <= y1:
            return None
        cropped = frame[y1:y2, x1:x2]
        if self.is_show_mask.get():
            # プレビューと同じ場所を隠す(切り出した範囲に掛かる部分のみ描かれる)
            cropped = draw_masks(cropped, self.masks, offset=(x1, y1))
        image = cv2.resize(cropped, (width, height), interpolation=cv2.INTER_LINEAR)
        image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        # プレビューと同じ明るさにする(スクリーンショットの保存中は、明るさを変える前の画像)
        return image if self.preview.show_raw_display else self.camera.adjustDisplayImage(image)
