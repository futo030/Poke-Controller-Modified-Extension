#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
# from typing import Tuple
from typing import TYPE_CHECKING, Callable

import cv2
import os
import time
import tkinter as tk
from tkinter.scrolledtext import ScrolledText
import numpy as np
import datetime
from collections import deque
from tkinter import filedialog

from PIL import Image, ImageDraw, ImageFont, ImageTk

from Commands import UnitCommand

# from Commands import StickCommand
from Commands.Keys import Direction, Stick, Touchscreen, NEUTRAL, KeyPress

import logging
from logging import StreamHandler, getLogger, DEBUG, NullHandler
from Commands.PythonCommandBase import PythonCommand
from UiDispatcher import UiDispatcher

if TYPE_CHECKING:
    from Camera import Camera
    from Commands.Keys import Button, Hat
    from Commands.Sender import Sender
    from Mask import Mask

try:
    os.makedirs("log")
except FileExistsError:
    pass

isTakeLog = False
# logger_stick = getLogger(__name__)
nowtime = datetime.datetime.fromtimestamp(time.time()).strftime("%Y%m%d_%H%M%S")


class MouseStick(PythonCommand):
    """マウスでスティックを倒すためのコマンド(今は、どこからも使われていない)"""

    NAME = "MOUSEスティック"

    def __init__(self) -> None:
        """実行していない状態で作る"""
        super().__init__()
        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

    def do(self) -> None:
        """何もしない(入力は stick / stickEnd で送る)"""
        pass

    def stick(self, buttons: Button | Hat | Direction | list, duration: float = 0.1, wait: float = 0.1) -> None:
        """buttons を押した(スティックは倒した)状態にして、duration + wait 秒待つ(離すのは stickEnd)"""
        self.keys.input(buttons, ifPrint=False)
        self.wait(duration)
        self.wait(wait)

    # press button at duration times(s)
    def stickEnd(self, buttons: Button | Hat | Direction | list) -> None:
        """buttons を離した(スティックは中央に戻した)状態にする"""
        self.keys.inputEnd(buttons)


# カメラを読み込んでいないときに表示する画像
DISABLED_IMAGE_TEXT = "No Image"
DISABLED_IMAGE_COLOR = "#ffffff"
DISABLED_IMAGE_BACKGROUND = "#000000"
# 文字の大きさ(表示の高さに対する比率)と、文字列の幅の上限(表示の幅に対する比率)
DISABLED_IMAGE_FONT_RATIO = 0.1
DISABLED_IMAGE_MAX_TEXT_WIDTH = 0.8
# 使うフォント(見つかったものを使う。どれも無い場合はPillowの既定のフォント)
DISABLED_IMAGE_FONTS = ("verdana.ttf", "tahoma.ttf", "arial.ttf", "DejaVuSans.ttf")


def _loadDisabledImageFont(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    「No Image」の文字に使うフォントを、大きさ size で返す
    (DISABLED_IMAGE_FONTS のうち、見つかったもの。どれも無ければ Pillow の既定のフォント)
    """
    for name in DISABLED_IMAGE_FONTS:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        # 古いPillowは大きさを指定できない
        return ImageFont.load_default()


class CaptureArea(tk.Canvas):
    """
    キャプチャーの画像を表示するプレビュー(メイン画面のキャンバス)。

    画像の表示のほかに、マウスでのスティック・タッチスクリーンの操作、範囲を選んでのスクリーンショット、
    タッチスクリーンの範囲の指定、目隠しの表示、画像認識の結果(四角形・文字)の表示を受け持つ
    """

    def __init__(
        self,
        camera: Camera,
        fps: int | str,
        right_mouse_mode: str,
        is_show: tk.BooleanVar,
        ser: KeyPress,
        master: tk.Misc | None = None,
        show_width: int = 640,
        show_height: int = 360,
    ) -> None:
        """
        camera: 画像を読むカメラ
        fps: 表示を更新する回数(1 秒あたり)
        right_mouse_mode: 今の Data Format の名前(右ドラッグが、右スティックかタッチスクリーンかを決める)
        is_show: プレビューを表示するか(画面のチェックボックスの変数)
        ser: マウスでの操作を送る KeyPress(名前は ser だが、Sender ではない)
        master: 置く先のフレーム(is_use_left_stick_mouse / is_use_right_stick_mouse の変数を持つもの)
        show_width, show_height: 表示の大きさ
        """
        super().__init__(
            master, borderwidth=0, cursor="tcross", width=show_width, height=show_height
        )

        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

        self.master = master
        self.radius = 60  # 描画する円の半径
        self.camera = camera
        # self.show_size = (640, 360)
        self.show_width = int(show_width)
        self.show_height = int(show_height)
        self.show_size = (self.show_width, self.show_height)
        self.is_show_var = is_show
        self.lx_init, self.ly_init = 0, 0
        self.rx_init, self.ry_init = 0, 0
        self.min_x, self.min_y = 0, 0
        self.max_x, self.max_y = 0, 0
        self.keys = None
        self.ser = ser
        self.lcircle = None
        self.lcircle2 = None
        self.rcircle = None
        self.rcircle2 = None
        self.LStick = None
        self.RStick = None
        self.calc_time = None
        self.ss = None
        self.dq = None
        # 範囲の枠(SelectArea)を消す処理の予約(after の番号。予約していない間は None)
        self._select_area_after = None
        # 目隠し(Mask.Maskのリスト)、表示するか、枠を表示する(選択中の)目隠しの番号
        self._masks = []
        self._masks_visible = False
        self._mask_selected = None
        # ドラッグで目隠しを追加している間の状態: (図形, 完了時に呼ぶ関数, 開始位置)
        self._mask_drawing = None
        # プレビューを、明るさを変える前の画像で表示するか(スクリーンショットの保存中)
        self.show_raw_display = False
        self._display_raw_shown = False
        self._langle = None
        self._lmag = None
        self._rangle = None
        self._rmag = None
        self.RightMouseMode = "Default"
        self.touchscreen_start_x = 1
        self.touchscreen_start_y = 1
        self.touchscreen_end_x = 320
        self.touchscreen_end_y = 240

        self.stick_handler = StreamHandler()
        self.stick_logging_level = DEBUG
        self.stick_handler.setLevel(self.stick_logging_level)
        # self._logger.setLevel(self.stick_logging_level)
        # self._logger.addHandler(self.stick_handler)
        # self._logger.propagate = False
        if isTakeLog:
            filename_base = os.path.join("log", f"{nowtime}")
            self.LS = logging.FileHandler(
                filename=f"{filename_base}_LStick.log", encoding="utf-8"
            )
            self.LS.setLevel(logging.DEBUG)
            self.LSTICK_logger = logging.getLogger("L_STICK")
            self.LSTICK_logger.setLevel(logging.DEBUG)
            self.LSTICK_logger.addHandler(self.LS)

            self.RS = logging.FileHandler(
                filename=f"{filename_base}_RStick.log", encoding="utf-8"
            )
            self.RS.setLevel(logging.DEBUG)
            self.RSTICK_logger = logging.getLogger("R_STICK")
            self.RSTICK_logger.setLevel(logging.DEBUG)
            self.RSTICK_logger.addHandler(self.RS)
        # self.circle =

        self.setFps(fps)
        self.changeRightMouseMode(right_mouse_mode)

        self.bind("<Control-ButtonPress-1>", self.mouseCtrlLeftPress)
        self.bind("<Control-ButtonRelease-1>", self.mouseCtrlLeftRelease)
        self.bind("<Control-Shift-ButtonPress-1>", self.StartRangeSS)
        self.bind("<Control-Shift-Button1-Motion>", self.MotionRangeSS)
        self.bind("<Control-Shift-ButtonRelease-1>", self.ReleaseRangeSS)

        self.bind("<Control-Alt-ButtonPress-1>", self.StartRangeSS)
        self.bind("<Control-Alt-Button1-Motion>", self.MotionRangeSS)
        self.bind(
            "<Control-Alt-ButtonRelease-1>", self.ReleaseRangeSS_asksaveasfilename
        )

        self.bind("<Control-ButtonPress-3>", self.StartRangeTouchscreen)
        self.bind("<Control-Button3-Motion>", self.MotionRangeTouchscreen)
        self.bind("<Control-ButtonRelease-3>", self.ReleaseRangeTouchscreen)

        # Set disabled image first
        # (カメラを読み込んでいないときに表示する画像。表示サイズに合わせて生成する)
        self.disabled_tk = self._createDisabledImage()
        self.im = self.disabled_tk
        self._display_seq = None
        # self.configure(image=self.disabled_tk)  # labelからキャンバスに変更したので微修正
        self.im_ = self.create_image(0, 0, image=self.disabled_tk, anchor=tk.NW)

    def ApplyLStickMouse(self) -> None:
        """左ドラッグでの左スティックの操作を、画面の設定に合わせて、有効・無効にする"""
        if self.master.is_use_left_stick_mouse.get():
            self.BindLeftClick()
        else:
            self.UnbindLeftClick()

    def ApplyRStickMouse(self) -> None:
        """右ドラッグでの右スティック(タッチスクリーン)の操作を、画面の設定に合わせて、有効・無効にする"""
        if self.master.is_use_right_stick_mouse.get():
            self.BindRightClick()
        else:
            self.UnbindRightClick()

    def _cancelSelectAreaRemoval(self) -> None:
        """予約してある「範囲の枠を消す処理」を取り消す(次の範囲を選び始めたときに、新しい枠が消されないようにする)"""
        if self._select_area_after is not None:
            self.after_cancel(self._select_area_after)
            self._select_area_after = None

    def _removeSelectAreaLater(self) -> None:
        """
        範囲の枠を、0.25 秒後に消す(選んだ範囲が、少しの間、見えるようにする)。
        待つ間も、画面の処理は止めない
        """
        self._cancelSelectAreaRemoval()

        def remove() -> None:
            """予約を片付けて、枠を消す"""
            self._select_area_after = None
            self.delete("SelectArea")

        self._select_area_after = self.after(250, remove)

    def StartRangeSS(self, event: tk.Event) -> None:
        """範囲を選んでのスクリーンショットを始める(Ctrl+Shift、または Ctrl+Alt を押しながら左ボタンを押したとき)"""
        self.ss = self.camera.image_bgr
        if self.master.is_use_left_stick_mouse.get():
            self.UnbindLeftClick()
        if self.master.is_use_right_stick_mouse.get():
            self.UnbindRightClick()

        self.min_x, self.min_y = event.x, event.y
        self._cancelSelectAreaRemoval()
        self.delete("SelectArea")
        self.create_rectangle(
            self.min_x,
            self.min_y,
            self.min_x + 1,
            self.min_y + 1,
            width=3.0,
            outline="red",
            tag="SelectArea",
        )

        ratio_x = float(self.camera.capture_size[0] / self.show_size[0])
        ratio_y = float(self.camera.capture_size[1] / self.show_size[1])
        print(
            "Mouse down: Show ({}, {}) / Capture ({}, {})".format(
                self.min_x,
                self.min_y,
                int(self.min_x * ratio_x),
                int(self.min_y * ratio_y),
            )
        )
        self._logger.info(
            "Mouse down: Show ({}, {}) / Capture ({}, {})".format(
                self.min_x,
                self.min_y,
                int(self.min_x * ratio_x),
                int(self.min_y * ratio_y),
            )
        )

        if self.master.is_use_left_stick_mouse.get():
            self.BindLeftClick()
        if self.master.is_use_right_stick_mouse.get():
            self.BindRightClick()

    def MotionRangeSS(self, event: tk.Event) -> None:
        """スクリーンショットの範囲を、マウスの位置まで広げる(プレビューの外へは出さない)"""
        if event.x < 0:
            self.max_x = 0
        else:
            self.max_x = min(self.show_width, event.x)
        if event.y < 0:
            self.max_y = 0
        else:
            self.max_y = min(self.show_height, event.y)
        self.coords(
            "SelectArea", self.min_x, self.min_y, self.max_x + 1, self.max_y + 1
        )
        self.coords(
            "SelectAreaFilled", self.min_x, self.min_y, self.max_x + 1, self.max_y + 1
        )

    def ReleaseRangeSS(self, event: tk.Event) -> None:
        """選んだ範囲を、キャプチャーのフォルダーに、日時の名前で保存する(Ctrl+Shift+左ボタンを離したとき)"""
        # self.max_x, self.max_y = event.x, event.y
        ratio_x = float(self.camera.capture_size[0] / self.show_size[0])
        ratio_y = float(self.camera.capture_size[1] / self.show_size[1])
        print(
            "Mouse up: Show ({}, {}) / Capture ({}, {})".format(
                self.max_x,
                self.max_y,
                int(self.max_x * ratio_x),
                int(self.max_y * ratio_y),
            )
        )
        self._logger.info(
            "Mouse up: Show ({}, {}) / Capture ({}, {})".format(
                self.max_x,
                self.max_y,
                int(self.max_x * ratio_x),
                int(self.max_y * ratio_y),
            )
        )
        if self.min_x > self.max_x:
            self.min_x, self.max_x = self.max_x, self.min_x
        if self.min_y > self.max_y:
            self.min_y, self.max_y = self.max_y, self.min_y

        self.camera.saveCapture(
            crop=1,
            crop_ax=[
                int(self.min_x * ratio_x),
                int(self.min_y * ratio_y),
                int(self.max_x * ratio_x),
                int(self.max_y * ratio_y),
            ],
        )

        # t = 0
        self._removeSelectAreaLater()

        if self.master.is_use_left_stick_mouse.get():
            self.BindLeftClick()
        if self.master.is_use_right_stick_mouse.get():
            self.BindRightClick()

    def ReleaseRangeSS_asksaveasfilename(self, event: tk.Event) -> None:
        """選んだ範囲を、名前を付けて保存する(Ctrl+Alt+左ボタンを離したとき。保存先を尋ねる)"""
        # self.max_x, self.max_y = event.x, event.y
        ratio_x = float(self.camera.capture_size[0] / self.show_size[0])
        ratio_y = float(self.camera.capture_size[1] / self.show_size[1])
        print(
            "Mouse up: Show ({}, {}) / Capture ({}, {})".format(
                self.max_x,
                self.max_y,
                int(self.max_x * ratio_x),
                int(self.max_y * ratio_y),
            )
        )
        self._logger.info(
            "Mouse up: Show ({}, {}) / Capture ({}, {})".format(
                self.max_x,
                self.max_y,
                int(self.max_x * ratio_x),
                int(self.max_y * ratio_y),
            )
        )
        if self.min_x > self.max_x:
            self.min_x, self.max_x = self.max_x, self.min_x
        if self.min_y > self.max_y:
            self.min_y, self.max_y = self.max_y, self.min_y

        filename = filedialog.asksaveasfilename(
            title="名前を付けて保存",
            filetypes=[("PNG", ".png")],
            initialdir="./TEMPLATE/",
            defaultextension="png",
        )
        if filename != "":
            self.camera.saveCapture(
                filename=filename[:-4],
                crop=1,
                crop_ax=[
                    int(self.min_x * ratio_x),
                    int(self.min_y * ratio_y),
                    int(self.max_x * ratio_x),
                    int(self.max_y * ratio_y),
                ],
            )

        # t = 0
        self._removeSelectAreaLater()

        if self.master.is_use_left_stick_mouse.get():
            self.BindLeftClick()
        if self.master.is_use_right_stick_mouse.get():
            self.BindRightClick()

    def StartRangeTouchscreen(self, event: tk.Event) -> None:
        """プレビューの中の、タッチスクリーンの範囲の指定を始める(Ctrl を押しながら右ボタンを押したとき)"""
        self.ss = self.camera.image_bgr
        if self.master.is_use_left_stick_mouse.get():
            self.UnbindLeftClick()
        if self.master.is_use_right_stick_mouse.get():
            self.UnbindRightClick()

        self.touchscreen_start_x, self.touchscreen_start_y = event.x, event.y
        self._cancelSelectAreaRemoval()
        self.delete("SelectArea")
        self.create_rectangle(
            self.touchscreen_start_x,
            self.touchscreen_start_y,
            self.touchscreen_start_x + 1,
            self.touchscreen_start_y + 1,
            width=3.0,
            outline="red",
            tag="SelectArea",
        )

        if self.master.is_use_left_stick_mouse.get():
            self.BindLeftClick()
        if self.master.is_use_right_stick_mouse.get():
            self.BindRightClick()

    def MotionRangeTouchscreen(self, event: tk.Event) -> None:
        """タッチスクリーンの範囲を、マウスの位置まで広げる(プレビューの外へは出さない)"""
        if event.x < 0:
            self.touchscreen_end_x = 0
        else:
            self.touchscreen_end_x = min(self.show_width, event.x)
        if event.y < 0:
            self.touchscreen_end_y = 0
        else:
            self.touchscreen_end_y = min(self.show_height, event.y)
        self.coords(
            "SelectArea",
            self.touchscreen_start_x,
            self.touchscreen_start_y,
            self.touchscreen_end_x + 1,
            self.touchscreen_end_y + 1,
        )
        self.coords(
            "SelectAreaFilled",
            self.touchscreen_start_x,
            self.touchscreen_start_y,
            self.touchscreen_end_x + 1,
            self.touchscreen_end_y + 1,
        )
        self._notifyTouchscreenArea()

    def ReleaseRangeTouchscreen(self, event: tk.Event) -> None:
        """タッチスクリーンの範囲を決める(左上と右下の順に直して、表示する)"""
        if self.touchscreen_start_x > self.touchscreen_end_x:
            self.touchscreen_start_x, self.touchscreen_end_x = (
                self.touchscreen_end_x,
                self.touchscreen_start_x,
            )
        if self.touchscreen_start_y > self.touchscreen_end_y:
            self.touchscreen_start_y, self.touchscreen_end_y = (
                self.touchscreen_end_y,
                self.touchscreen_start_y,
            )

        print(
            f"Touchscreen Area: ({self.touchscreen_start_x}, {self.touchscreen_start_y}), ({self.touchscreen_end_x}, {self.touchscreen_end_y})"
        )

        # t = 0
        self._removeSelectAreaLater()
        self._notifyTouchscreenArea()

        if self.master.is_use_left_stick_mouse.get():
            self.BindLeftClick()
        if self.master.is_use_right_stick_mouse.get():
            self.BindRightClick()

    def _notifyTouchscreenArea(self) -> None:
        """タッチスクリーンの範囲が変わったことを知らせる(on_touchscreen_area_changed に関数が入っていれば呼ぶ)"""
        # タッチスクリーンの範囲が変わったことを通知する(Touch Screenタブの数値を更新するため)
        callback = getattr(self, "on_touchscreen_area_changed", None)
        if callback is not None:
            callback()

    def showTouchscreenArea(self, duration_ms: int = 1500) -> None:
        """
        タッチスクリーンの範囲をプレビュー上に一定時間表示する
        """
        self.delete("TouchscreenArea")
        self.create_rectangle(
            self.touchscreen_start_x,
            self.touchscreen_start_y,
            self.touchscreen_end_x,
            self.touchscreen_end_y,
            width=3.0,
            outline="red",
            tag="TouchscreenArea",
        )
        self.after(duration_ms, lambda: self.delete("TouchscreenArea"))

    def setFps(self, fps: int | str) -> None:
        """表示を更新する回数(1 秒あたり)を決める(数字の文字列でもよい)"""
        # self.next_frames = int(16 * (60 / int(fps)))
        self.next_frames = int(1000 / int(fps))
        self._logger.info(f"FPS set to {fps}")

    def setShowsize(self, show_height: int | str, show_width: int | str) -> None:
        """表示の大きさを変える(引数は、高さ、幅の順。目隠しと「No Image」の画像も、大きさを合わせる)"""
        self.show_width = int(show_width)
        self.show_height = int(show_height)
        self.show_size = (self.show_width, self.show_height)
        self.config(width=self.show_width, height=self.show_height)
        print("Show size set to {0} x {1}".format(self.show_width, self.show_height))
        self._logger.info(
            "Show size set to {0} x {1}".format(self.show_width, self.show_height)
        )
        # カメラを読み込んでいないときの画像を、新しい表示サイズで作り直す
        showing_disabled = self.im is self.disabled_tk
        self.disabled_tk = self._createDisabledImage()
        if showing_disabled:
            self.im = self.disabled_tk
            self.itemconfig(self.im_, image=self.disabled_tk)
        self.redrawMasks()

    def _createDisabledImage(self) -> ImageTk.PhotoImage:
        """
        カメラを読み込んでいないときに表示する画像(黒地に白文字の「No Image」)を、現在の表示サイズで生成する
        """
        width, height = self.show_width, self.show_height
        image = Image.new("RGB", (width, height), DISABLED_IMAGE_BACKGROUND)
        draw = ImageDraw.Draw(image)
        # 文字の大きさは表示の高さに比例させ、幅に収まらない場合は縮める
        font_size = max(int(height * DISABLED_IMAGE_FONT_RATIO), 8)
        font = _loadDisabledImageFont(font_size)
        text_width = draw.textlength(DISABLED_IMAGE_TEXT, font=font)
        max_width = width * DISABLED_IMAGE_MAX_TEXT_WIDTH
        if text_width > max_width:
            font = _loadDisabledImageFont(max(int(font_size * max_width / text_width), 8))
        draw.text((width / 2, height / 2), DISABLED_IMAGE_TEXT, fill=DISABLED_IMAGE_COLOR, font=font, anchor="mm")
        return ImageTk.PhotoImage(image)

    ############### 目隠し ###############
    def setMasks(self, masks: list[Mask], visible: bool, selected: int | None = None) -> None:
        """
        目隠しを設定して描き直す
        masks: Mask.Maskのリスト(座標はカメラ画像の座標)
        visible: 目隠しを表示するか
        selected: 枠を表示する目隠しの番号(Noneなら表示しない)
        """
        self._masks = list(masks)
        self._masks_visible = bool(visible)
        self._mask_selected = selected
        self.redrawMasks()

    def redrawMasks(self) -> None:
        """目隠しを、今の表示の大きさで描き直す(選択中の目隠しには、点線の枠を付ける)"""
        self.delete("Mask")
        ratio_x = self.show_size[0] / self.camera.capture_size[0]
        ratio_y = self.show_size[1] / self.camera.capture_size[1]
        for index, mask in enumerate(self._masks):
            box = (mask.x1 * ratio_x, mask.y1 * ratio_y, mask.x2 * ratio_x, mask.y2 * ratio_y)
            create = self.create_oval if mask.shape == "Ellipse" else self.create_rectangle
            if self._masks_visible and mask.enabled:
                create(*box, fill=mask.color, outline="", tags=("Mask",))
            if index == self._mask_selected:
                # 選択中の目隠しは、非表示・無効でも位置が分かるように枠を表示する
                create(*box, fill="", outline="#FFD800", width=2, dash=(4, 3), tags=("Mask",))
        # カメラ画像のすぐ上に置く(認識結果の枠等のガイドは、目隠しより上に表示される)
        self.tag_raise("Mask", self.im_)

    def startMaskDrawing(self, shape: str, on_done: Callable[[str, int, int, int, int], None]) -> None:
        """
        次の左ドラッグで目隠しを追加する
        shape: 図形("Ellipse" は楕円。それ以外は四角形)
        on_done: 追加する図形が決まったときに呼ぶ関数(図形, x1, y1, x2, y2)。座標はカメラ画像の座標
        """
        self._mask_drawing = [shape, on_done, None]
        self.bind("<ButtonPress-1>", self._maskDrawPress)
        self.bind("<Button1-Motion>", self._maskDrawMotion)
        self.bind("<ButtonRelease-1>", self._maskDrawRelease)

    def cancelMaskDrawing(self) -> None:
        """目隠しの追加をやめて、左ドラッグを、元の操作(左スティック)に戻す"""
        if self._mask_drawing is None:
            return
        self._mask_drawing = None
        self.delete("MaskDraw")
        # 左クリックの操作を元(スティック操作の有無)に戻す
        self.ApplyLStickMouse()

    def _maskDrawClamp(self, event: tk.Event) -> tuple[int, int]:
        """マウスの位置を、プレビューの中に収めて (x, y) で返す"""
        return min(max(event.x, 0), self.show_width), min(max(event.y, 0), self.show_height)

    def _maskDrawPress(self, event: tk.Event) -> None:
        """目隠しの範囲のドラッグを始める(点線の図形を描く)"""
        shape = self._mask_drawing[0]
        x, y = self._maskDrawClamp(event)
        self._mask_drawing[2] = (x, y)
        self.delete("MaskDraw")
        create = self.create_oval if shape == "Ellipse" else self.create_rectangle
        create(x, y, x, y, outline="red", width=2, dash=(4, 3), tags=("MaskDraw",))

    def _maskDrawMotion(self, event: tk.Event) -> None:
        """目隠しの範囲を、マウスの位置まで広げる"""
        if self._mask_drawing is None or self._mask_drawing[2] is None:
            return
        self.coords("MaskDraw", *self._mask_drawing[2], *self._maskDrawClamp(event))

    def _maskDrawRelease(self, event: tk.Event) -> None:
        """目隠しの範囲を決めて、カメラ画像の座標に直し、on_done を呼ぶ"""
        if self._mask_drawing is None or self._mask_drawing[2] is None:
            return
        shape, on_done, (x1, y1) = self._mask_drawing
        x2, y2 = self._maskDrawClamp(event)
        self.cancelMaskDrawing()
        ratio_x = self.camera.capture_size[0] / self.show_size[0]
        ratio_y = self.camera.capture_size[1] / self.show_size[1]
        on_done(
            shape,
            int(round(min(x1, x2) * ratio_x)),
            int(round(min(y1, y2) * ratio_y)),
            int(round(max(x1, x2) * ratio_x)),
            int(round(max(y1, y2) * ratio_y)),
        )

    def changeRightMouseMode(self, mode: str) -> None:
        """今の Data Format の名前を覚える(右ドラッグが、右スティックかタッチスクリーンかを決める)"""
        self.RightMouseMode = mode

    def _right_mouse_is_touchscreen(self) -> bool:
        """
        右ドラッグが、右スティックではなくタッチスクリーンの操作になるか(送るデータの形式で決まる)
        """
        from Commands.transport import get_transport

        return get_transport(self.RightMouseMode).has_touchscreen

    def setTouchscreenArea(
        self,
        touchscreen_start_x: int,
        touchscreen_start_y: int,
        touchscreen_end_x: int,
        touchscreen_end_y: int,
    ) -> None:
        """プレビューの中の、タッチスクリーンの範囲を決める(左上と右下。プレビューの表示の座標)"""
        self.touchscreen_start_x = touchscreen_start_x
        self.touchscreen_start_y = touchscreen_start_y
        self.touchscreen_end_x = touchscreen_end_x
        self.touchscreen_end_y = touchscreen_end_y
        self._notifyTouchscreenArea()

    def mouseCtrlLeftPress(self, event: tk.Event) -> None:
        """Ctrl を押しながら左クリックした位置の、座標(表示とキャプチャー)と、色を表示する"""
        _img = cv2.cvtColor(self.camera.image_bgr, cv2.COLOR_BGR2RGB)
        if self.master.is_use_left_stick_mouse.get():
            self.UnbindLeftClick()
        x, y = event.x, event.y
        ratio_x = float(self.camera.capture_size[0] / self.show_size[0])
        ratio_y = float(self.camera.capture_size[1] / self.show_size[1])
        print(
            "Mouse down: Show ({}, {}) / Capture ({}, {})".format(
                x, y, int(x * ratio_x), int(y * ratio_y)
            )
        )
        print(
            f"Color [R: {_img[int(y * ratio_y), int(x * ratio_x)][0]}, "
            f"G: {_img[int(y * ratio_y), int(x * ratio_x)][1]}, "
            f"B: {_img[int(y * ratio_y), int(x * ratio_x)][2]}]"
        )
        self._logger.info(
            "Mouse down: Show ({}, {}) / Capture ({}, {})".format(
                x, y, int(x * ratio_x), int(y * ratio_y)
            )
        )

    def mouseCtrlLeftRelease(self, event: tk.Event) -> None:
        """Ctrl+左クリックを離したら、左ドラッグでの左スティックの操作を戻す"""
        if self.master.is_use_left_stick_mouse.get():
            self.BindLeftClick()

    def mouseLeftPress(self, event: tk.Event, ser: KeyPress) -> None:
        """左ドラッグでの左スティックの操作を始める(押した位置を中心にして、円を描く。ser は使わない)"""
        if self.master.is_use_right_stick_mouse.get():
            self.UnbindRightClick()
        self.config(cursor="dot")
        self.lx_init, self.ly_init = event.x, event.y
        self.lcircle = self.create_oval(
            self.lx_init - self.radius,
            self.ly_init - self.radius,
            self.lx_init + self.radius,
            self.ly_init + self.radius,
            outline="cyan",
            tag="lcircle",
        )
        self.lcircle2 = self.create_oval(
            self.lx_init - self.radius // 10,
            self.ly_init - self.radius // 10,
            self.lx_init + self.radius // 10,
            self.ly_init + self.radius // 10,
            fill="cyan",
            tag="lcircle2",
        )
        # self.LStick = StickCommand.StickLeft()
        # self.LStick.start(ser)
        if isTakeLog:
            if self.dq is None:
                self.dq = deque()
            else:
                self.dq.clear()

            if self.calc_time is None:
                self.calc_time = time.perf_counter()
            else:
                # LSTICK_logger.debug(f"{0},{0},{time.perf_counter() - self.calc_time}")
                self.dq.append([0, 0, time.perf_counter() - self.calc_time])
            self._langle = None
            self._lmag = None

    def mouseLeftPressing(self, event: tk.Event, ser: KeyPress, angle: float = 0) -> None:
        """
        左ドラッグの間、左スティックを、押した位置からの向きと距離に倒して送る
        (円の半径(radius)で、最大まで倒れる。ser と angle は使わない。送るのは self.ser)
        """
        # _time = self.calc_time
        langle = np.rad2deg(np.arctan2(self.ly_init - event.y, event.x - self.lx_init))
        mag = (
            np.sqrt((self.ly_init - event.y) ** 2 + (event.x - self.lx_init) ** 2)
            / self.radius
        )
        if mag <= 0:
            mag = 0
        elif mag >= 1:
            mag = 1

        if (self._langle and self._lmag) is not None and isTakeLog:
            _time = time.perf_counter()
            if _time - self.calc_time > 0.05:
                self.ser.input(
                    Direction(
                        Stick.LEFT,
                        (
                            int(128 + mag * 127.5 * np.cos(np.deg2rad(langle))),
                            255 - int(128 - mag * 127.5 * np.sin(np.deg2rad(langle))),
                        ),
                    )
                )
                self.dq.append([langle, mag, _time - self.calc_time])
                self.calc_time = _time
        elif not isTakeLog:
            self.ser.input(
                Direction(
                    Stick.LEFT,
                    (
                        int(128 + mag * 127.5 * np.cos(np.deg2rad(langle))),
                        255 - int(128 - mag * 127.5 * np.sin(np.deg2rad(langle))),
                    ),
                )
            )

        if mag >= 1:
            center_x = (self.radius + self.radius // 11) * np.cos(np.deg2rad(langle))
            center_y = (self.radius + self.radius // 11) * np.sin(np.deg2rad(langle))
            circ_x_1 = self.lx_init + center_x - self.radius // 10
            circ_x_2 = self.lx_init + center_x + self.radius // 10
            circ_y_1 = self.ly_init - center_y - self.radius // 10
            circ_y_2 = self.ly_init - center_y + self.radius // 10
        else:
            circ_x_1 = event.x - self.radius // 10
            circ_x_2 = event.x + self.radius // 10
            circ_y_1 = event.y - self.radius // 10
            circ_y_2 = event.y + self.radius // 10

        self.coords(
            "lcircle2",
            circ_x_1,
            circ_y_1,
            circ_x_2,
            circ_y_2,
        )
        self._langle = langle
        self._lmag = mag

    def mouseLeftRelease(self, ser: KeyPress) -> None:
        """左ドラッグを終えたら、左スティックを中央に戻して、円を消す(ser は使わない)"""
        self.config(cursor="tcross")
        self.ser.input(Direction(Stick.LEFT, NEUTRAL))
        self.delete("lcircle")
        self.delete("lcircle2")
        if self.master.is_use_right_stick_mouse.get():
            self.BindRightClick()
        # self.event_generate('<Motion>', warp=True, x=self.lx_init, y=self.ly_init)
        if isTakeLog:
            self.dq.append(
                [self._langle, self._lmag, time.perf_counter() - self.calc_time]
            )
            for _ in self.dq:
                self.LSTICK_logger.debug(",".join(list(map(str, _))))

    def mouseRightPress(self, event: tk.Event, ser: KeyPress) -> None:
        """
        右ドラッグの操作を始める。
        タッチスクリーンを送れる形式では、タッチスクリーンの範囲の中なら、その位置(320x240 に換算)を ser に送る。
        それ以外の形式では、右スティックの操作を始める(押した位置を中心にして、円を描く)
        """
        if self.master.is_use_left_stick_mouse.get():
            self.UnbindLeftClick()

        if self._right_mouse_is_touchscreen():  # Modified 2026.09.02
            if (
                self.touchscreen_start_x < event.x
                and event.x < self.touchscreen_end_x
                and self.touchscreen_start_y < event.y
                and event.y < self.touchscreen_end_y
            ):
                width = self.touchscreen_end_x - self.touchscreen_start_x
                height = self.touchscreen_end_y - self.touchscreen_start_y
                pos_x = int(320.0 * (event.x - self.touchscreen_start_x) / width)
                pos_y = int(240.0 * (event.y - self.touchscreen_start_y) / height)
                ser.input(Touchscreen(pos_x, pos_y))
        else:
            self.config(cursor="dot")
            self.rx_init, self.ry_init = event.x, event.y
            self.rcircle = self.create_oval(
                self.rx_init - self.radius,
                self.ry_init - self.radius,
                self.rx_init + self.radius,
                self.ry_init + self.radius,
                outline="red",
                tag="rcircle",
            )
            self.rcircle2 = self.create_oval(
                self.rx_init - self.radius // 10,
                self.ry_init - self.radius // 10,
                self.rx_init + self.radius // 10,
                self.ry_init + self.radius // 10,
                fill="red",
                tag="rcircle2",
            )

            # self.RStick = StickCommand.StickRight()
            # self.RStick.start(ser)
            if isTakeLog:
                if self.dq is None:
                    self.dq = deque()
                else:
                    self.dq.clear()

                if self.calc_time is None:
                    self.calc_time = time.perf_counter()
                else:
                    # LSTICK_logger.debug(f"{0},{0},{time.perf_counter() - self.calc_time}")
                    self.dq.append([0, 0, time.perf_counter() - self.calc_time])
            self._rangle = None
            self._rmag = None

    def mouseRightPressing(self, event: tk.Event, ser: KeyPress, angle: float = 0) -> None:
        """
        右ドラッグの間、タッチの位置(または右スティックの向きと倒す量)を送る
        (タッチは ser に、スティックは self.ser に送る。angle は使わない)
        """
        if self._right_mouse_is_touchscreen():  # Modified 2026.09.02
            if (
                self.touchscreen_start_x < event.x
                and event.x < self.touchscreen_end_x
                and self.touchscreen_start_y < event.y
                and event.y < self.touchscreen_end_y
            ):
                width = self.touchscreen_end_x - self.touchscreen_start_x
                height = self.touchscreen_end_y - self.touchscreen_start_y
                pos_x = int(320.0 * (event.x - self.touchscreen_start_x) / width)
                pos_y = int(240.0 * (event.y - self.touchscreen_start_y) / height)
                ser.input(Touchscreen(pos_x, pos_y))
        else:
            rangle = np.rad2deg(
                np.arctan2(self.ry_init - event.y, event.x - self.rx_init)
            )
            mag = (
                np.sqrt((self.ry_init - event.y) ** 2 + (event.x - self.rx_init) ** 2)
                / self.radius
            )
            if mag <= 0:
                mag = 0
            elif mag >= 1:
                mag = 1
            if (self._rangle and self._rmag) is not None and isTakeLog:
                _time = time.perf_counter()
                if _time - self.calc_time > 0.05:
                    self.ser.input(
                        Direction(
                            Stick.RIGHT,
                            (
                                int(128 + mag * 127.5 * np.cos(np.deg2rad(rangle))),
                                255
                                - int(128 - mag * 127.5 * np.sin(np.deg2rad(rangle))),
                            ),
                        )
                    )
                    self.dq.append([rangle, mag, _time - self.calc_time])
                    self.calc_time = _time
            elif not isTakeLog:
                self.ser.input(
                    Direction(
                        Stick.RIGHT,
                        (
                            int(128 + mag * 127.5 * np.cos(np.deg2rad(rangle))),
                            255 - int(128 - mag * 127.5 * np.sin(np.deg2rad(rangle))),
                        ),
                    )
                )
            if mag >= 1:
                center_x = (self.radius + self.radius // 11) * np.cos(
                    np.deg2rad(rangle)
                )
                center_y = (self.radius + self.radius // 11) * np.sin(
                    np.deg2rad(rangle)
                )
                circ_x_1 = self.rx_init + center_x - self.radius // 10
                circ_x_2 = self.rx_init + center_x + self.radius // 10
                circ_y_1 = self.ry_init - center_y - self.radius // 10
                circ_y_2 = self.ry_init - center_y + self.radius // 10
            else:
                circ_x_1 = event.x - self.radius // 10
                circ_x_2 = event.x + self.radius // 10
                circ_y_1 = event.y - self.radius // 10
                circ_y_2 = event.y + self.radius // 10

            self.coords(
                "rcircle2",
                circ_x_1,
                circ_y_1,
                circ_x_2,
                circ_y_2,
            )
            self._rangle = rangle
            self._rmag = mag

    def mouseRightRelease(self, ser: KeyPress) -> None:
        """右ドラッグを終えたら、タッチを離す(または、右スティックを中央に戻して、円を消す)"""
        if self._right_mouse_is_touchscreen():  # Modified 2026.09.02
            ser.inputEnd(Touchscreen(0, 0))
            if self.master.is_use_left_stick_mouse.get():
                self.BindLeftClick()
        else:
            self.config(cursor="tcross")
            self.ser.input(Direction(Stick.RIGHT, NEUTRAL))
            self.delete("rcircle")
            self.delete("rcircle2")
            if self.master.is_use_left_stick_mouse.get():
                self.BindLeftClick()

            # self.event_generate('<Motion>', warp=True, x=self.rx_init, y=self.ry_init)
            if isTakeLog:
                self.dq.append(
                    [self._rangle, self._rmag, time.perf_counter() - self.calc_time]
                )
                for _ in self.dq:
                    self.RSTICK_logger.debug(",".join(list(map(str, _))))

    def startCapture(self) -> None:
        """プレビューの表示の更新を始める(以後は、capture が、自分を繰り返し呼ぶ)"""
        self.capture()

    def capture(self) -> None:
        """
        プレビューの画像を、カメラの最新の画像に替える(新しい画像があるときだけ)。
        カメラを読み込んでいない間は「No Image」を表示する。終わりに、次の更新を予約する
        """
        # カメラの読み取り・色変換・リサイズはCameraの読み取りスレッドで行い、
        # メインスレッドでは新しいフレームがある場合のみPhotoImageの生成と差し替えを行う
        if not self.is_show_var.get():
            self.camera.setDisplaySize(None)
            self.after(self.next_frames, self.capture)
            return

        self.camera.setDisplaySize(self.show_size)
        image_pil, seq = self.camera.getDisplayImage(raw=self.show_raw_display)
        if image_pil is not None:
            if seq != self._display_seq or self.show_raw_display != self._display_raw_shown:
                self._display_seq = seq
                self._display_raw_shown = self.show_raw_display
                image_tk = ImageTk.PhotoImage(image_pil)

                self.im = image_tk
                # self.configure( image=image_tk)
                self.itemconfig(self.im_, image=image_tk)
        elif self.camera.image_bgr is None and self.im is not self.disabled_tk:
            self._display_seq = None
            self.im = self.disabled_tk
            # self.configure(image=self.disabled_tk)
            self.itemconfig(self.im_, image=self.disabled_tk)

        self.after(self.next_frames, self.capture)

    def setShowRawDisplay(self, raw: bool) -> None:
        """
        raw: プレビューを、明るさを変える前の画像で表示する(スクリーンショットの保存中)。すぐに描き直す
        """
        self.show_raw_display = raw
        image_pil, seq = self.camera.getDisplayImage(raw=raw)
        if image_pil is None or not self.is_show_var.get():
            return
        self._display_seq = seq
        self._display_raw_shown = raw
        self.im = ImageTk.PhotoImage(image_pil)
        self.itemconfig(self.im_, image=self.im)

    def saveCapture(self) -> None:
        """今のキャプチャーの画像を、キャプチャーのフォルダーに、日時の名前で保存する"""
        self.camera.saveCapture()

    def ImgRect(
        self, x1: float, y1: float, x2: float, y2: float, outline: str, tag: str, ms: int, flag: bool = True
    ) -> None:
        """
        プレビューに四角形を表示する(どのスレッドからでも呼べる)

        x1, y1, x2, y2: 左上と右下(キャプチャーの画像の座標)
        outline: 線の色。tag: 四角形に付ける名前(消すときに使う)
        ms: 表示する時間(ミリ秒)。flag: False なら、時間が過ぎても消さない
        """
        # コマンド実行スレッドから呼ばれるため、描画はメインスレッドで行う(呼び出し元は待たない)
        UiDispatcher.post(self._ImgRect, x1, y1, x2, y2, outline, tag, ms, flag)

    def _ImgRect(
        self, x1: float, y1: float, x2: float, y2: float, outline: str, tag: str, ms: int, flag: bool = True
    ) -> None:
        """四角形を描く(ImgRect の中身。画面のスレッドで呼ぶ。白い縁取りの上に、outline の色で描く)"""
        ratio_x = float(self.show_size[0] / self.camera.capture_size[0])
        ratio_y = float(self.show_size[1] / self.camera.capture_size[1])
        self.create_rectangle(
            (x1 - 1.0) * ratio_x,
            (y1 - 1.0) * ratio_y,
            (x2 + 1.0) * ratio_x,
            (y2 + 1.0) * ratio_y,
            width=4.5,
            outline="white",
            tag=tag,
        )
        self.create_rectangle(
            x1 * ratio_x,
            y1 * ratio_y,
            x2 * ratio_x,
            y2 * ratio_y,
            width=2.5,
            outline=outline,
            tag=tag,
        )
        if flag:
            self.after(ms, self.deleteImageRect, tag)

    def deleteImageRect(self, tag: str) -> None:
        """tag の名前の四角形を消す"""
        self.delete(tag)

    def ImgText(
        self,
        x1: float,
        y1: float,
        txt: str,
        tag: str,
        ms: int,
        ft: tuple[str, int] = ("UD デジタル 教科書体 NP-B", 20),
        color: str = "black",
        flag: bool = True,
    ) -> None:
        """
        プレビューに文字を表示する(どのスレッドからでも呼べる)

        x1, y1: 文字の位置(キャプチャーの画像の座標)
        txt: 表示する文字。tag: 文字に付ける名前(消すときに使う)
        ms: 表示する時間(ミリ秒)。ft: (フォントの名前, 大きさ)。color: 文字の色
        flag: False なら、時間が過ぎても消さない
        """
        # コマンド実行スレッドから呼ばれるため、描画はメインスレッドで行う(呼び出し元は待たない)
        UiDispatcher.post(self._ImgText, x1, y1, txt, tag, ms, ft, color, flag)

    def _ImgText(
        self,
        x1: float,
        y1: float,
        txt: str,
        tag: str,
        ms: int,
        ft: tuple[str, int] = ("UD デジタル 教科書体 NP-B", 20),
        color: str = "black",
        flag: bool = True,
    ) -> None:
        """文字を描く(ImgText の中身。画面のスレッドで呼ぶ)"""
        ratio_x = float(self.show_size[0] / self.camera.capture_size[0])
        ratio_y = float(self.show_size[1] / self.camera.capture_size[1])
        str_len = 0.3528 * ft[1] * len(txt)  # 1[pt] = 0.3528[mm]
        self.create_text(
            ((x1 - 1.0) * ratio_x) + str_len,
            (y1 - 1.0) * ratio_y,
            text=txt,
            font=ft,
            tag=tag,
            fill=color,
        )
        if flag:
            self.after(ms, self.deleteImageText, tag)

    def deleteImageText(self, tag: str) -> None:
        """tag の名前の文字を消す"""
        self.delete(tag)

    def BindLeftClick(self) -> None:
        """左ドラッグを、左スティックの操作にする"""
        self.bind("<ButtonPress-1>", lambda ev: self.mouseLeftPress(ev, self.ser))
        self.bind("<Button1-Motion>", lambda ev: self.mouseLeftPressing(ev, self.ser))
        self.bind("<ButtonRelease-1>", lambda ev: self.mouseLeftRelease(self.ser))
        self._logger.debug("Bind <ButtonPress-1>")
        self._logger.debug("Bind <Button1-Motion>")
        self._logger.debug("Bind <ButtonRelease-1>")

    def BindRightClick(self) -> None:
        """右ドラッグを、右スティック(タッチスクリーン)の操作にする"""
        self.bind("<ButtonPress-3>", lambda ev: self.mouseRightPress(ev, self.ser))
        self.bind("<Button3-Motion>", lambda ev: self.mouseRightPressing(ev, self.ser))
        self.bind("<ButtonRelease-3>", lambda ev: self.mouseRightRelease(self.ser))
        self._logger.debug("Bind <ButtonPress-3>")
        self._logger.debug("Bind <Button3-Motion>")
        self._logger.debug("Bind <ButtonRelease-3>")

    def UnbindLeftClick(self) -> None:
        """左ドラッグでの、左スティックの操作をやめる"""
        self.unbind("<ButtonPress-1>")
        self.unbind("<Button1-Motion>")
        self.unbind("<ButtonRelease-1>")
        self._logger.debug("Unbind <ButtonPress-1>")
        self._logger.debug("Unbind <Button1-Motion>")
        self._logger.debug("Unbind <ButtonRelease-1>")

    def UnbindRightClick(self) -> None:
        """右ドラッグでの、右スティック(タッチスクリーン)の操作をやめる"""
        self.unbind("<ButtonPress-3>")
        self.unbind("<Button3-Motion>")
        self.unbind("<ButtonRelease-3>")
        self._logger.debug("Unbind <ButtonPress-3>")
        self._logger.debug("Unbind <Button3-Motion>")
        self._logger.debug("Unbind <ButtonRelease-3>")


# GUI of switch controller simulator
class ControllerGUI:
    """
    以前からある Switch Controller Simulator の画面(tkinter のボタンを並べたもの)。
    ボタンを押すたびに、UnitCommand で、そのボタンを 0.1 秒押す
    """

    def __init__(
        self,
        root: tk.Misc,
        ser: Sender,
        parent: tk.Misc | None = None,
        touch_image_source: Callable | None = None,
    ) -> None:
        """
        root: 親のウィンドウ(専用のウィンドウを作るときの、位置の基準にもなる)
        ser: 入力を送る相手
        parent: レイアウトを置くフレーム(Noneなら専用のウィンドウを作る)
        touch_image_source: 他のレイアウトと引数を揃えるためのもので、このレイアウトでは使わない
        """
        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

        self.owns_window = parent is None
        if self.owns_window:
            self.window = tk.Toplevel(root)
            self.window.title("Switch Controller Simulator")
            root_geometry = root.geometry().split("+")
            root_x = int(root_geometry[1])
            root_y = int(root_geometry[2])
            self.window.geometry("%dx%d%+d%+d" % (600, 300, 250 + root_x, 125 + root_y))
            self.window.resizable(False, False)
            parent = self.window
        else:
            self.window = parent.winfo_toplevel()

        joycon_L_color = "#95f1ff"
        joycon_R_color = "#ff6b6b"

        joycon_L_frame = tk.Frame(
            parent, width=300, height=300, relief="flat", bg=joycon_L_color
        )
        joycon_R_frame = tk.Frame(
            parent, width=300, height=300, relief="flat", bg=joycon_R_color
        )
        self.frames = [joycon_L_frame, joycon_R_frame]
        hat_frame = tk.Frame(joycon_L_frame, relief="flat", bg=joycon_L_color)
        abxy_frame = tk.Frame(joycon_R_frame, relief="flat", bg=joycon_R_color)

        # ABXY
        tk.Button(
            abxy_frame, text="A", command=lambda: UnitCommand.A().start(ser)
        ).grid(row=1, column=2)
        tk.Button(
            abxy_frame, text="B", command=lambda: UnitCommand.B().start(ser)
        ).grid(row=2, column=1)
        tk.Button(
            abxy_frame, text="X", command=lambda: UnitCommand.X().start(ser)
        ).grid(row=0, column=1)
        tk.Button(
            abxy_frame, text="Y", command=lambda: UnitCommand.Y().start(ser)
        ).grid(row=1, column=0)
        abxy_frame.place(relx=0.2, rely=0.3)

        # HAT
        tk.Button(
            hat_frame, text="UP", command=lambda: UnitCommand.UP().start(ser)
        ).grid(row=0, column=1)
        tk.Button(
            hat_frame, text="", command=lambda: UnitCommand.UP_RIGHT().start(ser)
        ).grid(row=0, column=2)
        tk.Button(
            hat_frame, text="RIGHT", command=lambda: UnitCommand.RIGHT().start(ser)
        ).grid(row=1, column=2)
        tk.Button(
            hat_frame, text="", command=lambda: UnitCommand.DOWN_RIGHT().start(ser)
        ).grid(row=2, column=2)
        tk.Button(
            hat_frame, text="DOWN", command=lambda: UnitCommand.DOWN().start(ser)
        ).grid(row=2, column=1)
        tk.Button(
            hat_frame, text="", command=lambda: UnitCommand.DOWN_LEFT().start(ser)
        ).grid(row=2, column=0)
        tk.Button(
            hat_frame, text="LEFT", command=lambda: UnitCommand.LEFT().start(ser)
        ).grid(row=1, column=0)
        tk.Button(
            hat_frame, text="", command=lambda: UnitCommand.UP_LEFT().start(ser)
        ).grid(row=0, column=0)
        hat_frame.place(relx=0.2, rely=0.6)

        # L side
        tk.Button(
            joycon_L_frame,
            text="L",
            width=20,
            command=lambda: UnitCommand.L().start(ser),
        ).place(x=30, y=30)
        tk.Button(
            joycon_L_frame,
            text="ZL",
            width=20,
            command=lambda: UnitCommand.ZL().start(ser),
        ).place(x=30, y=0)
        tk.Button(
            joycon_L_frame,
            text="LCLICK",
            width=7,
            command=lambda: UnitCommand.LCLICK().start(ser),
        ).place(x=120, y=120)
        tk.Button(
            joycon_L_frame,
            text="MINUS",
            width=5,
            command=lambda: UnitCommand.MINUS().start(ser),
        ).place(x=220, y=70)
        tk.Button(
            joycon_L_frame,
            text="CAP",
            width=5,
            command=lambda: UnitCommand.CAPTURE().start(ser),
        ).place(x=200, y=270)

        # R side
        tk.Button(
            joycon_R_frame,
            text="R",
            width=20,
            command=lambda: UnitCommand.R().start(ser),
        ).place(x=120, y=30)
        tk.Button(
            joycon_R_frame,
            text="ZR",
            width=20,
            command=lambda: UnitCommand.ZR().start(ser),
        ).place(x=120, y=0)
        tk.Button(
            joycon_R_frame,
            text="RCLICK",
            width=7,
            command=lambda: UnitCommand.RCLICK().start(ser),
        ).place(x=120, y=205)
        tk.Button(
            joycon_R_frame,
            text="PLUS",
            width=5,
            command=lambda: UnitCommand.PLUS().start(ser),
        ).place(x=35, y=70)
        tk.Button(
            joycon_R_frame,
            text="HOME",
            width=5,
            command=lambda: UnitCommand.HOME().start(ser),
        ).place(x=50, y=270)

        joycon_L_frame.grid(row=0, column=0)
        joycon_R_frame.grid(row=0, column=1)

        # button style settings
        for button in abxy_frame.winfo_children():
            self.applyButtonSetting(button)
        for button in hat_frame.winfo_children():
            self.applyButtonSetting(button)
        for button in [
            b for b in joycon_L_frame.winfo_children() if type(b) is tk.Button
        ]:
            self.applyButtonColor(button)
        for button in [
            b for b in joycon_R_frame.winfo_children() if type(b) is tk.Button
        ]:
            self.applyButtonColor(button)

        self._logger.debug("Create GUI controller")

    def applyButtonSetting(self, button: tk.Button) -> None:
        """ボタンの幅と色を、そろえる(ABXY と十字キー用)"""
        button["width"] = 7
        self.applyButtonColor(button)

    def applyButtonColor(self, button: tk.Button) -> None:
        """ボタンを、黒地に白文字にする"""
        button["bg"] = "#343434"
        button["fg"] = "#fff"

    def bind(self, event: str, func: Callable) -> None:
        """ウィンドウに、イベントの処理を付ける(tkinter の bind と同じ)"""
        self.window.bind(event, func)

    def protocol(self, event: str, func: Callable) -> None:
        """ウィンドウの、閉じるボタンなどの処理を決める(tkinter の protocol と同じ)"""
        self.window.protocol(event, func)

    def focus_force(self) -> None:
        """ウィンドウを、いちばん手前にして、入力を受けるようにする"""
        self.window.focus_force()

    def destroy(self) -> None:
        """ウィンドウ(フレームの中に置いた場合は、置いた部品)を消す"""
        if self.owns_window:
            self.window.destroy()
        else:
            for frame in self.frames:
                frame.destroy()
        self._logger.debug("GUI controller destroyed")


# To avoid the error says 'ScrolledText' object has no attribute 'flush'
class MyScrolledText(ScrolledText):
    """標準出力の出力先にできる ScrolledText(flush を持たせたもの)"""

    def flush(self) -> None:
        """何もしない(標準出力の代わりに使うときに、flush が呼ばれてもエラーにならないようにする)"""
        pass
