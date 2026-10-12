#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ゲーム機をイメージしたSoftware Controllerのレイアウト
(Nintendo Switch(Joy-Con / Proコントローラー) / Nintendo 3DS / Nintendo DS / ゲームキューブ)

- ボタン・十字キーは、マウスのボタンを押している間だけ入力する
- スティック(スライドパッド)はドラッグした向き・距離に倒す
- タッチ画面は320x240の等倍で、クリック・ドラッグした位置がそのままタッチ座標になる
  (カメラ画像のうちタッチスクリーンの範囲を表示する)
入力源はマウス操作(InputSource.MOUSE)として扱う

レイアウトは2種類の大きさがある
- Controller Simulator(別ウィンドウ)用: 600x300。3DS / DSはタッチ画面を持つ
- メイン画面のSoftware-Controller用(Compact〜): 380x190。
  押しっぱなしの固定(HOLDボタンをオンにして左クリック、右クリック、またはShiftを押しながら離す)ができる。
  3DS / DSはタッチ画面なしと、縮小したタッチ画面(200x150)ありの2種類がある

レイアウトを追加する場合は、CanvasControllerGUIを継承してbuild()で部品を並べる

tkinter は、画面に表示するとき(CanvasControllerGUI を作るとき)にだけ読み込む。
レイアウトの内容だけを取り出す describe_layout() は、tkinter なしで使える(Web ブラウザ版の画面が使う)
"""
from __future__ import annotations

import math
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING, Any, Callable

import ControllerColors
from Commands.Keys import NEUTRAL, Button, Direction, Hat, InputSource, KeyPress, Stick, Touchscreen

if TYPE_CHECKING:
    import tkinter as tk
    from types import ModuleType

    from Commands.Sender import Sender

WINDOW_WIDTH = 600
WINDOW_HEIGHT = 300

# 色(全レイアウト共通)
BUTTON_COLOR = "#343434"
BUTTON_ACTIVE_COLOR = "#e8590c"
BUTTON_TEXT_COLOR = "#ffffff"
# 押しっぱなしで固定している入力の色
LOCK_COLOR = "#FFD800"
LOCK_TEXT_COLOR = "#343434"
# マウスイベントのstateのうちShiftキーを表すビット
SHIFT_MASK = 0x0001
TOUCH_COLOR = "#1b1f24"
TOUCH_TEXT_COLOR = "#6c7a89"
TOUCH_MARK_COLOR = "#ffd43b"

# 送信するタッチ座標の範囲(3DSの下画面と同じ320x240)。タッチ画面の表示の大きさの初期値でもある
TOUCH_WIDTH = 320
TOUCH_HEIGHT = 240
# タッチ画面に表示するカメラ画像を更新する間隔(ms)
TOUCH_IMAGE_INTERVAL_MS = 66

# 右下の隅に置く Keyboard ボタンの大きさ(どのレイアウトでも、ほかの部品と重ならない大きさ)
KEYBOARD_BUTTON_WIDTH = 62
KEYBOARD_BUTTON_HEIGHT = 16

# スティックのこの倒し量未満はニュートラルとする
STICK_DEADZONE = 0.1


class CanvasControllerGUI:
    """
    キャンバスに描いたコントローラーの共通処理(部品の作成と入力)
    """

    TITLE = "Controller Simulator"
    WIDTH = WINDOW_WIDTH
    HEIGHT = WINDOW_HEIGHT
    BODY_COLOR = "#c9d6df"
    STICK_BASE_COLOR = "#aab7c2"
    # 本体の色の設定(ControllerColors)での、コントローラーの種類(Noneなら、クラスに書いた色のまま)
    COLOR_TYPE = None
    # スティックの土台の色を、本体の色から決めるか(Falseなら STICK_BASE_COLOR の固定の色)
    STICK_BASE_FROM_BODY = False

    def __init__(
        self,
        root: tk.Misc,
        ser: Sender,
        parent: tk.Misc | None = None,
        touch_image_source: Callable | None = None,
        key: KeyPress | None = None,
        colors: dict | None = None,
        hold_button: bool = True,
        on_keyboard: Callable[[], None] | None = None,
    ) -> None:
        """
        root: 親のウィンドウ(専用のウィンドウを作るときの、位置の基準にもなる)
        ser: 入力を送る相手(key を渡した場合は使わない)
        hold_button: HOLDボタンを置くか(Falseなら置かない。キーコンフィグの画面の図で使う)
        colors: 本体の色(Noneなら設定されている色)。設定画面のプレビューで、設定中の色を表示するために使う
        parent: レイアウトを置くフレーム(Noneなら専用のウィンドウを作る)
        touch_image_source: タッチ画面に表示する画像を返す関数
                            (幅, 高さ) を渡すとその大きさのPIL画像を返す。表示できない場合はNone
        key: 入力に使うKeyPress(Noneなら入力源がマウス操作のKeyPressを作る)
        on_keyboard: 右下の Keyboard ボタンを押したときに呼ぶ関数(Noneなら、ボタンを置かない)
        """
        import tkinter as tk

        self.key = key if key is not None else KeyPress(ser, source=InputSource.MOUSE)
        self._init_state(colors, hold_button, touch_image_source)
        self._create_canvas(tk, root, parent)

        self.build()
        if on_keyboard is not None:
            self.create_keyboard_button(on_keyboard)

        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        # 右クリック(右ドラッグ)は押しっぱなしの固定に使う
        self.canvas.bind("<B3-Motion>", self._on_right_motion)
        self.canvas.bind("<ButtonRelease-3>", self._on_right_release)
        if self.touch_origin is not None and self.touch_image_source is not None:
            self._update_touch_image()
        self._logger.debug(f"Create GUI controller: {self.TITLE}")

    def _init_state(self, colors: dict | None, hold_button: bool, touch_image_source: Callable | None) -> None:
        """
        部品を並べる前の準備(色と、入力の状態)。画面には触れない
        """
        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True
        self._show_hold_button = hold_button
        self._apply_colors(colors)
        self.touch_image_source = touch_image_source
        self._touch_photo = None
        self._touch_image_after = None
        # タッチ画面にカメラ画像を表示しているか
        self._touch_has_image = False
        # タッチ画面の左上の座標(タッチ画面が無いレイアウトではNone)と、表示の大きさ
        self.touch_origin = None
        self.touch_size = (TOUCH_WIDTH, TOUCH_HEIGHT)
        # 押している入力: (種類, キャンバスのタグ, 入力) / None
        self._active = None
        # タグ -> 離したときに戻す色(図形、文字)
        self._fills = {}
        self._text_fills = {}
        # スティックの名前 -> 設定
        self._sticks = {}
        # 押しっぱなしの固定(create_hold_buttonを呼んだレイアウトのみ有効)
        self.lock_enabled = False
        self.hold_mode = False
        # 固定しているボタンのタグ -> 入力、固定しているスティックのタグ
        self._locked = {}
        self._locked_sticks = set()

    def _create_canvas(self, tk: ModuleType, root: tk.Misc, parent: tk.Misc | None) -> None:
        """
        キャンバスを作る(parent が None なら、専用のウィンドウを root の少し右下に作って、その中に置く)
        tk: tkinter のモジュール(このファイルは、画面に表示するときにだけ tkinter を読み込むため、引数で受ける)
        """
        self.owns_window = parent is None
        if self.owns_window:
            self.window = tk.Toplevel(root)
            self.window.title(self.TITLE)
            root_geometry = root.geometry().split("+")
            root_x = int(root_geometry[1])
            root_y = int(root_geometry[2])
            self.window.geometry("%dx%d%+d%+d" % (self.WIDTH, self.HEIGHT, 250 + root_x, 125 + root_y))
            self.window.resizable(False, False)
            parent = self.window
        else:
            self.window = parent.winfo_toplevel()

        self.canvas = tk.Canvas(parent, width=self.WIDTH, height=self.HEIGHT, bg=self.BODY_COLOR, highlightthickness=0)
        # コントローラーの色は、テーマを変えても変えない
        self.canvas.theme_exclude = True
        # 枠が大きくなったときは、中央に置く
        self.canvas.pack(expand=True)

    def build(self) -> None:
        """
        部品を並べる(レイアウトごとに実装する)
        """
        raise NotImplementedError

    # --- 部品の作成
    def _round_rect(self, x1: float, y1: float, x2: float, y2: float, r: float, **kwargs: Any) -> int:
        """
        角の丸い四角形を描く(r: 角の丸みの大きさ。kwargs: create_polygon に渡す fill、tags など)
        戻り値: 描いた図形の番号
        """
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]  # fmt: skip
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    def _bind_button(self, tag: str, value: Button | Hat, fill: str) -> None:
        """
        tagの図形を、押している間だけvalueを入力するボタンにする
        (fill: 離したときに戻す色)
        """
        self._fills[tag] = fill
        self.canvas.tag_bind(tag, "<ButtonPress-1>", lambda _, t=tag, v=value: self._press(t, v))
        self.canvas.tag_bind(tag, "<ButtonPress-3>", lambda _, t=tag, v=value: self._right_press(t, v))

    def create_rect_button(
        self,
        tag: str,
        value: Button | Hat,
        text: str,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: str = BUTTON_COLOR,
        text_color: str = BUTTON_TEXT_COLOR,
        font_size: int = 9,
    ) -> None:
        """
        角の丸い四角形のボタンを置く

        tag: ボタンを区別する名前(キャンバスのタグ)
        value: 押している間に入力するもの
        text: ボタンに書く文字
        x1, y1, x2, y2: 左上と右下の座標
        """
        self._round_rect(x1, y1, x2, y2, 6, fill=color, outline="", tags=(tag, tag + ":shape"))
        self.canvas.create_text(
            (x1 + x2) / 2,
            (y1 + y2) / 2,
            text=text,
            fill=text_color,
            font=("", font_size, "bold"),
            tags=(tag, tag + ":text"),
        )
        self._text_fills[tag] = text_color
        self._bind_button(tag, value, color)

    def create_round_button(
        self,
        tag: str,
        value: Button | Hat,
        text: str,
        cx: float,
        cy: float,
        r: float,
        color: str = BUTTON_COLOR,
        text_color: str = BUTTON_TEXT_COLOR,
        font_size: int = 11,
    ) -> None:
        """
        丸いボタンを置く(tag、value、text は create_rect_button と同じ。cx, cy: 中心の座標。r: 半径)
        """
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline="", tags=(tag, tag + ":shape"))
        self.canvas.create_text(
            cx, cy, text=text, fill=text_color, font=("", font_size, "bold"), tags=(tag, tag + ":text")
        )
        self._text_fills[tag] = text_color
        self._bind_button(tag, value, color)

    def create_abxy(self, cx: float, cy: float, offset: float = 34, r: float = 17, font_size: int = 11) -> None:
        """
        Switch/3DS/DSと同じ配置のABXY(上X・左Y・右A・下B)
        cx, cy: 4 つのボタンの中心。offset: 中心から各ボタンまでの距離。r: ボタンの半径
        """
        self.create_round_button("btn_x", Button.X, "X", cx, cy - offset, r, font_size=font_size)
        self.create_round_button("btn_y", Button.Y, "Y", cx - offset, cy, r, font_size=font_size)
        self.create_round_button("btn_a", Button.A, "A", cx + offset, cy, r, font_size=font_size)
        self.create_round_button("btn_b", Button.B, "B", cx, cy + offset, r, font_size=font_size)

    def create_hold_button(self, x1: float, y1: float, x2: float, y2: float) -> None:
        """
        押しっぱなしの固定を切り替えるHOLDボタンを置き、固定の機能を有効にする
        - HOLDをオンにしている間に左クリックしたボタン・十字キー・スティックは、離しても入力したままになる
        - 右クリックしたボタン・十字キー、右ドラッグしたスティックは、HOLDのオン・オフに関係なく固定する
          (この場合、左クリックの操作は固定されない)
        - Shiftを押しながら離した場合も固定する(従来の操作)
        - 固定中のボタンをもう一度押すと(左右どちらのクリックでも)解除する
        - HOLDボタンは、HOLDがオンか、固定中の入力がある間は黄色になる。
          黄色のHOLDボタンを押すと、HOLDをオフにして固定をすべて解除する
        (x1, y1, x2, y2: 左上と右下の座標。hold_button を False にして作った場合は、何も置かない)
        """
        if not self._show_hold_button:
            return
        self.lock_enabled = True
        tag = "hold_toggle"
        self._round_rect(x1, y1, x2, y2, 6, fill=BUTTON_COLOR, outline="", tags=(tag, tag + ":shape"))
        self.canvas.create_text(
            (x1 + x2) / 2,
            (y1 + y2) / 2,
            text="HOLD",
            fill=BUTTON_TEXT_COLOR,
            font=("", 9, "bold"),
            tags=(tag, tag + ":text"),
        )
        self.canvas.tag_bind(tag, "<ButtonPress-1>", lambda _: self._toggle_hold())

    def create_keyboard_button(self, on_keyboard: Callable[[], None]) -> None:
        """
        右下の隅に、Keyboard ウィンドウ(Switch へのキーボード入力)を開くボタンを置く。
        どのレイアウトでも、ほかの部品と重ならない大きさにしてある
        on_keyboard: 押したときに呼ぶ関数
        """
        tag = "keyboard_open"
        x2, y2 = self.WIDTH - 3, self.HEIGHT - 3
        x1, y1 = x2 - KEYBOARD_BUTTON_WIDTH, y2 - KEYBOARD_BUTTON_HEIGHT
        self._round_rect(x1, y1, x2, y2, 5, fill=BUTTON_COLOR, outline="", tags=(tag, tag + ":shape"))
        self.canvas.create_text(
            (x1 + x2) / 2,
            (y1 + y2) / 2,
            text="Keyboard",
            fill=BUTTON_TEXT_COLOR,
            font=("", 8, "bold"),
            tags=(tag, tag + ":text"),
        )
        self.canvas.tag_bind(tag, "<ButtonPress-1>", lambda _: on_keyboard())

    def _apply_colors(self, colors: dict | None) -> None:
        """
        本体の色を、設定されている色(colorsを渡した場合はその色)にする
        (スティックの土台の色は、STICK_BASE_FROM_BODY のレイアウトのみ本体の色から決める。他は固定の色のまま)
        """
        if self.COLOR_TYPE is None:
            return
        if colors is None:
            colors = ControllerColors.get_colors(self.COLOR_TYPE)
        else:
            colors = ControllerColors.complete_colors(self.COLOR_TYPE, colors)
        if "left" in colors:
            self.LEFT_COLOR = colors["left"]
            self.RIGHT_COLOR = colors["right"]
            self.BODY_COLOR = self.LEFT_COLOR
        else:
            self.BODY_COLOR = colors["body"]
        if self.STICK_BASE_FROM_BODY:
            self.STICK_BASE_COLOR = ControllerColors.stick_base_color(self.BODY_COLOR)

    def create_dpad(self, cx: float, cy: float, cell: float = 24, body_color: str | None = None) -> None:
        """
        十字キーを置く(3x3 のマス。四隅は、見えないが、斜めの入力になる)
        cx, cy: 中心の座標。cell: マス 1 つの大きさ
        body_color: 十字キーを置く場所の本体の色(Noneなら BODY_COLOR)
        """
        # 3x3のマス: 上下左右は十字キー、四隅は斜め入力(本体と同じ色で見えないが押せる)
        body_color = body_color or self.BODY_COLOR
        hats = {
            (0, 0): Hat.TOP_LEFT, (1, 0): Hat.TOP, (2, 0): Hat.TOP_RIGHT,
            (0, 1): Hat.LEFT, (2, 1): Hat.RIGHT,
            (0, 2): Hat.BTM_LEFT, (1, 2): Hat.BTM, (2, 2): Hat.BTM_RIGHT,
        }  # fmt: skip
        # 矢印の向き(dx, dy)。文字(▲▶▼◀)はフォントによって左右だけ形が変わるため、三角形を描く
        arrows = {Hat.TOP: (0, -1), Hat.RIGHT: (1, 0), Hat.BTM: (0, 1), Hat.LEFT: (-1, 0)}
        # 三角形の大きさ: 先端から底辺までの長さの半分、底辺の長さの半分
        arrow_length, arrow_width = cell * 0.17, cell * 0.21
        x0, y0 = cx - cell * 1.5, cy - cell * 1.5
        for col in range(3):
            for row in range(3):
                x1, y1 = x0 + col * cell, y0 + row * cell
                x2, y2 = x1 + cell, y1 + cell
                hat = hats.get((col, row))
                if hat is None:
                    # 中央
                    self.canvas.create_rectangle(x1, y1, x2, y2, fill=BUTTON_COLOR, outline="")
                    continue
                tag = f"hat_{hat.name}"
                color = BUTTON_COLOR if hat in arrows else body_color
                self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="", tags=(tag, tag + ":shape"))
                if hat in arrows:
                    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                    dx, dy = arrows[hat]
                    self.canvas.create_polygon(
                        mx + dx * arrow_length, my + dy * arrow_length,
                        mx - dx * arrow_length - dy * arrow_width, my - dy * arrow_length - dx * arrow_width,
                        mx - dx * arrow_length + dy * arrow_width, my - dy * arrow_length + dx * arrow_width,
                        fill=BUTTON_TEXT_COLOR,
                        outline="",
                        tags=(tag, tag + ":text"),
                    )  # fmt: skip
                    self._text_fills[tag] = BUTTON_TEXT_COLOR
                self._bind_button(tag, hat, color)

    def create_stick(
        self,
        name: str,
        stick: Stick,
        cx: float,
        cy: float,
        base_radius: float = 40,
        knob_radius: float = 22,
        tilt_range: float = 30,
        color: str = BUTTON_COLOR,
        text: str = "",
        text_color: str = BUTTON_TEXT_COLOR,
        font_size: int = 11,
    ) -> None:
        """
        ドラッグで倒すスティック
        name: スティックを区別する名前
        stick: 左右どちらのスティックとして送るか
        cx, cy: 中心の座標。base_radius: 土台の半径。knob_radius: つまみの半径
        tilt_range: 中心からこの距離までドラッグすると最大まで倒れる
        text: つまみに書く文字(空なら書かない)
        """
        tag = f"stick_{name}"
        r = base_radius
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=self.STICK_BASE_COLOR, outline="", tags=(tag,))
        r = knob_radius
        knob = self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r, fill=color, outline="", tags=(tag, tag + ":shape")
        )
        label = None
        if text:
            label = self.canvas.create_text(
                cx, cy, text=text, fill=text_color, font=("", font_size, "bold"), tags=(tag, tag + ":text")
            )
            self._text_fills[tag] = text_color
        self._fills[tag] = color
        self._sticks[tag] = {
            "stick": stick,
            "center": (cx, cy),
            "knob": knob,
            "label": label,
            "knob_radius": knob_radius,
            "range": tilt_range,
        }
        self.canvas.tag_bind(tag, "<ButtonPress-1>", lambda event, t=tag: self._press_stick(t, event))
        self.canvas.tag_bind(tag, "<ButtonPress-3>", lambda event, t=tag: self._right_press_stick(t, event))

    def create_touchscreen(self, x: float, y: float, width: int = TOUCH_WIDTH, height: int = TOUCH_HEIGHT) -> None:
        """
        タッチ画面を置く(クリック・ドラッグした位置を、タッチの座標として送る)
        x, y: 左上の座標
        width, height: 表示の大きさ。320x240より小さい場合、クリック位置を320x240の座標に換算して送る
        """
        self.touch_origin = (x, y)
        self.touch_size = (width, height)
        self.canvas.create_rectangle(x - 3, y - 3, x + width + 3, y + height + 3, fill="#000000", outline="")
        self.canvas.create_rectangle(x, y, x + width, y + height, fill=TOUCH_COLOR, outline="", tags=("touch",))
        # カメラ画像(タッチスクリーンの範囲を切り出したもの)。画像が無い間は表示しない
        self.touch_image = self.canvas.create_image(x, y, anchor="nw", state="hidden", tags=("touch",))
        self.touch_text = self.canvas.create_text(
            x + width / 2,
            y + height / 2,
            text="Touch Screen",
            fill=TOUCH_TEXT_COLOR,
            font=("", 11),
            tags=("touch",),
        )
        self.touch_mark = None
        self.canvas.tag_bind("touch", "<ButtonPress-1>", self._press_touch)

    def refresh_touch_image(self) -> None:
        """
        タッチスクリーンの表示画像を、すぐに取り直す(表示の明るさを変えたときなど)
        """
        if self._touch_image_after is None:
            return
        self.canvas.after_cancel(self._touch_image_after)
        self._update_touch_image()

    def _update_touch_image(self) -> None:
        """
        タッチ画面の画像を取り直して表示し、TOUCH_IMAGE_INTERVAL_MS 後に、もう一度自分を呼ぶ
        (画像を取れない場合は、画像を隠す)
        """
        self._touch_image_after = None
        try:
            image = self.touch_image_source(*self.touch_size)
        except Exception as e:
            self._logger.error(f"Failed to get the touch screen image: {e}")
            image = None
        if image is None:
            self.canvas.itemconfigure(self.touch_image, state="hidden")
            self._touching_text_only(False)
        else:
            if self._touch_photo is None:
                from PIL import ImageTk

                self._touch_photo = ImageTk.PhotoImage(image)
                self.canvas.itemconfigure(self.touch_image, image=self._touch_photo)
            else:
                self._touch_photo.paste(image)
            self.canvas.itemconfigure(self.touch_image, state="normal")
            self._touching_text_only(True)
        self._touch_image_after = self.canvas.after(TOUCH_IMAGE_INTERVAL_MS, self._update_touch_image)

    def _touching_text_only(self, has_image: bool) -> None:
        """タッチ画面の文字の表示を切り替える(has_image: カメラの画像を表示しているか)"""
        # 画像の表示中は「Touch Screen」の文字を隠し、タッチ中の座標のみ表示する
        self._touch_has_image = has_image
        touching = self._active is not None and self._active[0] == "touch"
        self.canvas.itemconfigure(self.touch_text, state="hidden" if (has_image and not touching) else "normal")

    # --- 色
    def _set_color(self, tag: str, fill: str, text_fill: str | None = None) -> None:
        """tag の部品の色を変える(fill: 図形の色。text_fill: 文字の色。None なら文字は変えない)"""
        self.canvas.itemconfigure(tag + ":shape", fill=fill)
        if text_fill is not None and tag in self._text_fills:
            self.canvas.itemconfigure(tag + ":text", fill=text_fill)

    def _restore_color(self, tag: str) -> None:
        """tag の部品を、押していないときの色に戻す"""
        self._set_color(tag, self._fills[tag], self._text_fills.get(tag))

    # --- 押しっぱなしの固定
    def has_locks(self) -> bool:
        """固定している入力(ボタン・十字キー・スティック)があるか"""
        return bool(self._locked or self._locked_sticks)

    def _toggle_hold(self) -> None:
        """HOLD ボタンを押したときの処理"""
        # 黄色(HOLDがオン、または固定中の入力がある)なら、オフにして全て解除する
        self.set_hold_mode(not (self.hold_mode or self.has_locks()))

    def set_hold_mode(self, enabled: bool) -> None:
        """HOLD のオン・オフを切り替える(オフにすると、固定している入力をすべて解除する)"""
        self.hold_mode = bool(enabled)
        if not self.hold_mode:
            self.release_all()
        self._update_hold_button()

    def _update_hold_button(self) -> None:
        """
        HOLDボタンの色を更新する(HOLDがオンか、固定中の入力がある間は黄色)
        """
        if not self.lock_enabled:
            return
        if self.hold_mode or self.has_locks():
            self._set_color("hold_toggle", LOCK_COLOR, LOCK_TEXT_COLOR)
        else:
            self._set_color("hold_toggle", BUTTON_COLOR, BUTTON_TEXT_COLOR)

    def _should_lock(self, event: tk.Event | None) -> bool:
        """
        離したときに、入力を固定するか(HOLD がオンか、Shift を押しながら離した場合)
        event: マウスのボタンを離したイベント(None なら、Shift は見ない)
        """
        if not self.lock_enabled:
            return False
        return self.hold_mode or (event is not None and bool(event.state & SHIFT_MASK))

    def _lock(self, tag: str, value: Button | Hat) -> None:
        """tag のボタン・十字キーを、押したまま固定する(value: 入力するもの)"""
        if type(value) is Hat:
            # Hatは1方向しか入力できないので、固定中のHatは解除する
            for other in [t for t, v in self._locked.items() if type(v) is Hat]:
                self._unlock(other)
        self._locked[tag] = value
        self._set_color(tag, LOCK_COLOR, LOCK_TEXT_COLOR)
        # ホールドに登録して、他のボタンを離したときに一緒に離れないようにする
        self.key.hold([value])
        self._update_hold_button()

    def _unlock(self, tag: str) -> None:
        """tag のボタン・十字キーの固定を解除して、離す(固定していない tag は KeyError)"""
        value = self._locked.pop(tag)
        self._restore_color(tag)
        self.key.holdEnd([value])
        self._update_hold_button()

    def _lock_stick(self, tag: str) -> None:
        """tag のスティックを、今の倒し方のまま固定する"""
        # 倒したままにする(つまみもその位置に残す)
        self._locked_sticks.add(tag)
        self._set_color(tag, LOCK_COLOR, LOCK_TEXT_COLOR)
        self._update_hold_button()

    def _release_stick(self, tag: str) -> None:
        """tag のスティックを中央に戻す(固定していれば解除する)"""
        info = self._sticks[tag]
        self._locked_sticks.discard(tag)
        self._move_knob(info, 0, 0)
        self._restore_color(tag)
        self.key.input(Direction(info["stick"], NEUTRAL))
        self._update_hold_button()

    def release_all(self) -> None:
        """
        固定している入力をすべて解除する
        """
        for tag in list(self._locked):
            self._unlock(tag)
        for tag in list(self._locked_sticks):
            self._release_stick(tag)

    # --- 入力
    def _press(self, tag: str, value: Button | Hat) -> None:
        """ボタン・十字キーを左クリックで押したときの処理(value を入力する)"""
        if tag in self._locked:
            # 固定中のボタンをもう一度押したら解除する
            self._unlock(tag)
            return
        self._active = ("button", tag, value)
        self._set_color(tag, BUTTON_ACTIVE_COLOR, BUTTON_TEXT_COLOR)
        self.key.input([value])

    def _press_stick(self, tag: str, event: tk.Event) -> None:
        """スティックを左クリックで押したときの処理(クリックした位置へ倒す)"""
        # 固定中のスティックは、押し直したら通常の操作に戻す
        self._locked_sticks.discard(tag)
        self._update_hold_button()
        self._active = ("stick", tag, None)
        self._set_color(tag, BUTTON_ACTIVE_COLOR, BUTTON_TEXT_COLOR)
        self._tilt_stick(tag, event)

    # --- 右クリック(押しっぱなしの固定)
    def _right_press(self, tag: str, value: Button | Hat) -> None:
        """
        ボタン・十字キーを右クリック: 固定する(固定中なら解除する)
        """
        if not self.lock_enabled or self._active is not None:
            return
        if tag in self._locked:
            self._unlock(tag)
        else:
            self._lock(tag, value)

    def _right_press_stick(self, tag: str, event: tk.Event) -> None:
        """
        スティックを右ドラッグ: 離した位置で固定する
        """
        if not self.lock_enabled or self._active is not None:
            return
        self._locked_sticks.discard(tag)
        self._active = ("stick_lock", tag, None)
        self._set_color(tag, BUTTON_ACTIVE_COLOR, BUTTON_TEXT_COLOR)
        self._tilt_stick(tag, event)

    def _on_right_motion(self, event: tk.Event) -> None:
        """右ボタンでドラッグしている間の処理(スティックを、マウスの位置へ倒す)"""
        if self._active is not None and self._active[0] == "stick_lock":
            self._tilt_stick(self._active[1], event)

    def _on_right_release(self, event: tk.Event | None = None) -> None:
        """右ボタンを離したときの処理(倒していれば、その位置で固定する。倒していなければ中央に戻す)"""
        if self._active is None or self._active[0] != "stick_lock":
            return
        tag = self._active[1]
        self._active = None
        if self._sticks[tag].get("tilted"):
            self._lock_stick(tag)
        else:
            self._release_stick(tag)

    def _move_knob(self, info: dict, dx: float, dy: float) -> None:
        """スティックのつまみ(と文字)を、中心から (dx, dy) の位置に動かす(info: _sticks の設定)"""
        cx, cy = info["center"]
        r = info["knob_radius"]
        self.canvas.coords(info["knob"], cx + dx - r, cy + dy - r, cx + dx + r, cy + dy + r)
        if info["label"] is not None:
            self.canvas.coords(info["label"], cx + dx, cy + dy)

    def _tilt_stick(self, tag: str, event: tk.Event) -> None:
        """
        スティックを、マウスの位置(event)の向きと距離に倒して送る
        (STICK_DEADZONE より小さい倒し方は、中央として送る)
        """
        info = self._sticks[tag]
        cx, cy = info["center"]
        tilt_range = info["range"]
        dx, dy = event.x - cx, event.y - cy
        dist = math.hypot(dx, dy)
        if dist > tilt_range:
            dx, dy = dx * tilt_range / dist, dy * tilt_range / dist
            dist = tilt_range
        self._move_knob(info, dx, dy)
        mag = dist / tilt_range
        info["tilted"] = mag >= STICK_DEADZONE
        if mag < STICK_DEADZONE:
            self.key.input(Direction(info["stick"], NEUTRAL))
        else:
            # 画面のyは下が正なので反転する
            angle = math.degrees(math.atan2(-dy, dx))
            self.key.input(Direction(info["stick"], angle, mag))

    def _press_touch(self, event: tk.Event) -> None:
        """タッチ画面を押したときの処理"""
        self._active = ("touch", "touch", None)
        self._touch(event)

    def _touch(self, event: tk.Event) -> None:
        """マウスの位置(event)を、タッチの座標(x: 1 - 320、y: 1 - 240)に直して送り、印と座標を表示する"""
        ox, oy = self.touch_origin
        width, height = self.touch_size
        # 表示上の位置(画面内に収める)
        dx = min(max(event.x - ox, 0), width)
        dy = min(max(event.y - oy, 0), height)
        # 送信する座標(320x240)に換算する。(0, 0)は離した状態を表すので、1以上の座標にする
        x = min(max(round(dx * TOUCH_WIDTH / width), 1), TOUCH_WIDTH)
        y = min(max(round(dy * TOUCH_HEIGHT / height), 1), TOUCH_HEIGHT)
        if self.touch_mark is not None:
            self.canvas.delete(self.touch_mark)
        px, py = ox + dx, oy + dy
        self.touch_mark = self.canvas.create_oval(
            px - 5, py - 5, px + 5, py + 5, outline=TOUCH_MARK_COLOR, width=2, tags=("touch",)
        )
        # 座標はタッチ位置の印と重ならないよう、左上に表示する
        self.canvas.coords(self.touch_text, ox + 6, oy + 4)
        self.canvas.itemconfigure(self.touch_text, text=f"({x}, {y})", anchor="nw", state="normal", fill=TOUCH_MARK_COLOR)
        self.key.input(Touchscreen(x, y))

    def _on_motion(self, event: tk.Event) -> None:
        """左ボタンでドラッグしている間の処理(スティックとタッチは、マウスの位置に合わせる)"""
        if self._active is None:
            return
        kind, tag, _ = self._active
        if kind == "stick":
            self._tilt_stick(tag, event)
        elif kind == "touch":
            self._touch(event)

    def _on_release(self, event: tk.Event | None = None) -> None:
        """左ボタンを離したときの処理(押していた入力を離す。固定する場合は、押したままにする)"""
        # 右ドラッグ中(stick_lock)は右ボタンを離したときに処理する
        if self._active is None or self._active[0] == "stick_lock":
            return
        kind, tag, value = self._active
        self._active = None
        lock = self._should_lock(event)
        if kind == "button":
            if lock:
                self._lock(tag, value)
            else:
                self._restore_color(tag)
                self.key.inputEnd([value])
        elif kind == "stick":
            if lock and self._sticks[tag].get("tilted"):
                self._lock_stick(tag)
            else:
                self._release_stick(tag)
        elif kind == "touch":
            ox, oy = self.touch_origin
            if self.touch_mark is not None:
                self.canvas.delete(self.touch_mark)
                self.touch_mark = None
            self.canvas.coords(self.touch_text, ox + self.touch_size[0] / 2, oy + self.touch_size[1] / 2)
            # カメラ画像の表示中は「Touch Screen」の文字を出さない(画像が無い場合のみ表示する)
            self.canvas.itemconfigure(
                self.touch_text,
                text="Touch Screen",
                anchor="center",
                fill=TOUCH_TEXT_COLOR,
                state="hidden" if self._touch_has_image else "normal",
            )
            self.key.inputEnd(Touchscreen(0, 0))

    # --- ControllerGUIと同じ操作
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
        """入力をすべて離して、ウィンドウ(フレームの中に置いた場合は、キャンバス)を消す"""
        # 押したままウィンドウを閉じた場合に入力が残らないようにする
        self._active = None
        self._locked.clear()
        self._locked_sticks.clear()
        if self._touch_image_after is not None:
            self.canvas.after_cancel(self._touch_image_after)
            self._touch_image_after = None
        self.key.release()
        if self.owns_window:
            self.window.destroy()
        else:
            self.canvas.destroy()
        self._logger.debug(f"GUI controller destroyed: {self.TITLE}")


class ControllerSwitchJoyConGUI(CanvasControllerGUI):
    """
    Nintendo Switch(Joy-Con): 左右2色のJoy-Conを並べた配置
    """

    TITLE = "Switch (Joy-Con) Controller Simulator"
    COLOR_TYPE = ControllerColors.SWITCH_JOYCON
    LEFT_COLOR = "#95f1ff"
    RIGHT_COLOR = "#ff6b6b"
    BODY_COLOR = LEFT_COLOR
    STICK_BASE_COLOR = "#5c6770"

    def build(self) -> None:
        """このレイアウトの部品(本体の塗り分け、ボタン、十字キー、スティックなど)を並べる"""
        half = self.WIDTH / 2
        self.canvas.create_rectangle(0, 0, half, self.HEIGHT, fill=self.LEFT_COLOR, outline="")
        self.canvas.create_rectangle(half, 0, self.WIDTH, self.HEIGHT, fill=self.RIGHT_COLOR, outline="")

        # 左のJoy-Con
        self.create_rect_button("btn_zl", Button.ZL, "ZL", 10, 4, 130, 26)
        self.create_rect_button("btn_l", Button.L, "L", 10, 30, 130, 52)
        self.create_rect_button("btn_minus", Button.MINUS, "−", 240, 60, 285, 82)
        self.create_stick("left", Stick.LEFT, 95, 118, text="L")
        self.create_rect_button("btn_lclick", Button.LCLICK, "LCLICK", 150, 107, 220, 129)
        self.create_dpad(150, 218, body_color=self.LEFT_COLOR)
        self.create_rect_button("btn_capture", Button.CAPTURE, "CAPTURE", 220, 268, 290, 290)

        # 右のJoy-Con
        self.create_rect_button("btn_zr", Button.ZR, "ZR", 470, 4, 590, 26)
        self.create_rect_button("btn_r", Button.R, "R", 470, 30, 590, 52)
        self.create_rect_button("btn_plus", Button.PLUS, "+", 315, 60, 360, 82)
        self.create_abxy(500, 118)
        self.create_stick("right", Stick.RIGHT, 430, 218, text="R")
        self.create_rect_button("btn_rclick", Button.RCLICK, "RCLICK", 485, 207, 555, 229)
        self.create_rect_button("btn_home", Button.HOME, "HOME", 310, 268, 380, 290)


class ControllerSwitchProGUI(CanvasControllerGUI):
    """
    Nintendo Switch(Proコントローラー): 単色の本体に、実物と同じ並びで置いた配置
    """

    TITLE = "Switch (Pro Controller) Controller Simulator"
    COLOR_TYPE = ControllerColors.SWITCH_PRO
    BODY_COLOR = "#868e96"
    STICK_BASE_COLOR = "#5c6770"

    def build(self) -> None:
        """このレイアウトの部品(本体の塗り分け、ボタン、十字キー、スティックなど)を並べる"""
        self.create_rect_button("btn_zl", Button.ZL, "ZL", 10, 4, 130, 26)
        self.create_rect_button("btn_l", Button.L, "L", 10, 30, 130, 52)
        self.create_rect_button("btn_zr", Button.ZR, "ZR", 470, 4, 590, 26)
        self.create_rect_button("btn_r", Button.R, "R", 470, 30, 590, 52)

        # 左: Lスティック(上)と十字キー(下)
        self.create_stick("left", Stick.LEFT, 95, 122, text="L")
        self.create_rect_button("btn_lclick", Button.LCLICK, "LCLICK", 60, 172, 130, 194)
        self.create_dpad(195, 232)

        # 中央
        self.create_rect_button("btn_minus", Button.MINUS, "−", 230, 60, 275, 82)
        self.create_rect_button("btn_plus", Button.PLUS, "+", 325, 60, 370, 82)
        self.create_rect_button("btn_capture", Button.CAPTURE, "CAPTURE", 215, 100, 285, 122)
        self.create_rect_button("btn_home", Button.HOME, "HOME", 315, 100, 385, 122)

        # 右: ABXY(上)とRスティック(下)
        self.create_abxy(500, 122)
        self.create_stick("right", Stick.RIGHT, 405, 232, text="R")
        self.create_rect_button("btn_rclick", Button.RCLICK, "RCLICK", 460, 221, 530, 243)


class Controller3DSGUI(CanvasControllerGUI):
    """
    Nintendo 3DS(実機の下画面まわりと同じ配置)
    """

    TITLE = "3DS Controller Simulator"
    COLOR_TYPE = ControllerColors.N3DS
    BODY_COLOR = "#c9d6df"
    STICK_BASE_COLOR = "#aab7c2"

    def build(self) -> None:
        """このレイアウトの部品(本体の塗り分け、ボタン、十字キー、スティックなど)を並べる"""
        self.create_touchscreen(140, 30)
        self.create_rect_button("btn_l", Button.L, "L", 10, 4, 110, 26)
        self.create_rect_button("btn_r", Button.R, "R", 490, 4, 590, 26)
        self.create_abxy(530, 110)
        self.create_rect_button("btn_start", Button.START, "START", 480, 190, 580, 212)
        self.create_rect_button("btn_select", Button.SELECT, "SELECT", 480, 222, 580, 244)
        self.create_rect_button("btn_home", Button.HOME, "HOME", 265, 276, 335, 296)
        self.create_dpad(70, 210)
        # スライドパッド
        self.create_stick("pad", Stick.LEFT, 70, 95)


class ControllerDSGUI(CanvasControllerGUI):
    """
    Nintendo DS(3DSからスライドパッドとHOMEを除いた配置)
    タッチ座標は3DSと同じ320x240で送る
    """

    TITLE = "DS Controller Simulator"
    COLOR_TYPE = ControllerColors.NDS
    BODY_COLOR = "#dfe3e8"

    def build(self) -> None:
        """このレイアウトの部品(本体の塗り分け、ボタン、十字キー、スティックなど)を並べる"""
        self.create_touchscreen(140, 30)
        self.create_rect_button("btn_l", Button.L, "L", 10, 4, 110, 26)
        self.create_rect_button("btn_r", Button.R, "R", 490, 4, 590, 26)
        self.create_abxy(530, 110)
        self.create_rect_button("btn_start", Button.START, "START", 480, 190, 580, 212)
        self.create_rect_button("btn_select", Button.SELECT, "SELECT", 480, 222, 580, 244)
        self.create_dpad(70, 130, cell=30)


# ゲームキューブのボタンと、送信するボタンの対応
# (SwitchでゲームキューブコントローラーをつないだときのL=ZL、R=ZR、Z=R、START=+に合わせている。
#  使うファームウェアの割り当てが違う場合はここを変更する)
GAMECUBE_BUTTONS = {
    "L": Button.ZL,
    "R": Button.ZR,
    "Z": Button.R,
    "START": Button.PLUS,
}


class ControllerGameCubeGUI(CanvasControllerGUI):
    """
    ゲームキューブ(大きなAボタンを中心にした実機の配置。タッチ画面は無い)
    コントロールスティックは左スティック、Cスティックは右スティックとして送る
    """

    TITLE = "GameCube Controller Simulator"
    COLOR_TYPE = ControllerColors.GAMECUBE
    STICK_BASE_FROM_BODY = True
    BODY_COLOR = "#6a5acd"
    STICK_BASE_COLOR = "#5346a8"

    def build(self) -> None:
        """このレイアウトの部品(本体の塗り分け、ボタン、十字キー、スティックなど)を並べる"""
        gray = "#ced4da"
        dark_text = "#212529"
        self.create_rect_button("btn_l", GAMECUBE_BUTTONS["L"], "L", 10, 4, 110, 26, color=gray, text_color=dark_text)
        self.create_rect_button("btn_r", GAMECUBE_BUTTONS["R"], "R", 490, 4, 590, 26, color=gray, text_color=dark_text)
        self.create_rect_button("btn_z", GAMECUBE_BUTTONS["Z"], "Z", 380, 4, 480, 26, color="#4263eb")
        self.create_rect_button(
            "btn_start", GAMECUBE_BUTTONS["START"], "START", 265, 104, 335, 126, color=gray, text_color=dark_text
        )

        # コントロールスティックと十字キー
        self.create_stick("control", Stick.LEFT, 95, 100, base_radius=48, knob_radius=26, tilt_range=36, color=gray)
        self.create_dpad(185, 230, cell=22)

        # A(大)を中心に、B(左下)・X(右)・Y(上)
        self.create_round_button("btn_a", Button.A, "A", 485, 120, 32, color="#2f9e44", font_size=16)
        self.create_round_button("btn_b", Button.B, "B", 428, 160, 18, color="#e03131")
        self.create_round_button("btn_x", Button.X, "X", 545, 105, 18, color=gray, text_color=dark_text)
        self.create_round_button("btn_y", Button.Y, "Y", 470, 62, 18, color=gray, text_color=dark_text)

        # Cスティック
        self.create_stick(
            "c",
            Stick.RIGHT,
            400,
            235,
            base_radius=40,
            knob_radius=22,
            tilt_range=30,
            color="#fcc419",
            text="C",
            text_color=dark_text,
        )


############### メイン画面のSoftware-Controller用(小型・タッチ画面なし) ###############
COMPACT_WIDTH = 380
COMPACT_HEIGHT = 190
# HOLDボタンの位置(全レイアウト共通で左下)
COMPACT_HOLD_BUTTON = (6, 166, 56, 184)


class CompactSwitchJoyConGUI(CanvasControllerGUI):
    """
    Nintendo Switch(Joy-Con): 左右2色のJoy-Conにスティックを加えた配置
    """

    TITLE = "Switch (Joy-Con)"
    COLOR_TYPE = ControllerColors.SWITCH_JOYCON
    WIDTH = COMPACT_WIDTH
    HEIGHT = COMPACT_HEIGHT
    LEFT_COLOR = "#56CCF2"
    RIGHT_COLOR = "#E9514E"
    BODY_COLOR = LEFT_COLOR
    STICK_BASE_COLOR = "#5c6770"

    def build(self) -> None:
        """このレイアウトの部品(本体の塗り分け、ボタン、十字キー、スティックなど)を並べる"""
        half = self.WIDTH / 2
        self.canvas.create_rectangle(0, 0, half, self.HEIGHT, fill=self.LEFT_COLOR, outline="")
        self.canvas.create_rectangle(half, 0, self.WIDTH, self.HEIGHT, fill=self.RIGHT_COLOR, outline="")

        # 左のJoy-Con
        self.create_rect_button("btn_zl", Button.ZL, "ZL", 6, 4, 66, 22)
        self.create_rect_button("btn_l", Button.L, "L", 6, 26, 66, 44)
        self.create_rect_button("btn_minus", Button.MINUS, "−", 146, 26, 184, 44)
        self.create_stick("left", Stick.LEFT, 46, 86, base_radius=27, knob_radius=15, tilt_range=18, text="L", font_size=9)
        self.create_rect_button("btn_lclick", Button.LCLICK, "L-C", 82, 58, 124, 76)
        self.create_dpad(120, 128, cell=18, body_color=self.LEFT_COLOR)
        # CAP / HOME は中央に横並びで置く
        self.create_rect_button("btn_capture", Button.CAPTURE, "CAP", 136, 166, 186, 184)

        # 右のJoy-Con
        self.create_rect_button("btn_zr", Button.ZR, "ZR", 314, 4, 374, 22)
        self.create_rect_button("btn_r", Button.R, "R", 314, 26, 374, 44)
        self.create_rect_button("btn_plus", Button.PLUS, "+", 196, 26, 234, 44)
        self.create_abxy(312, 88, offset=24, r=12, font_size=9)
        self.create_stick("right", Stick.RIGHT, 246, 136, base_radius=27, knob_radius=15, tilt_range=18, text="R", font_size=9)
        self.create_rect_button("btn_rclick", Button.RCLICK, "R-C", 282, 134, 324, 152)
        self.create_rect_button("btn_home", Button.HOME, "HOME", 194, 166, 244, 184)

        self.create_hold_button(*COMPACT_HOLD_BUTTON)


class CompactSwitchProGUI(CanvasControllerGUI):
    """
    Nintendo Switch(Proコントローラー): 単色の本体に、実物と同じ並びで置いた配置
    """

    TITLE = "Switch (Pro Controller)"
    COLOR_TYPE = ControllerColors.SWITCH_PRO
    WIDTH = COMPACT_WIDTH
    HEIGHT = COMPACT_HEIGHT
    BODY_COLOR = "#868e96"
    STICK_BASE_COLOR = "#5c6770"

    def build(self) -> None:
        """このレイアウトの部品(本体の塗り分け、ボタン、十字キー、スティックなど)を並べる"""
        self.create_rect_button("btn_zl", Button.ZL, "ZL", 6, 4, 66, 22)
        self.create_rect_button("btn_l", Button.L, "L", 6, 26, 66, 44)
        self.create_rect_button("btn_zr", Button.ZR, "ZR", 314, 4, 374, 22)
        self.create_rect_button("btn_r", Button.R, "R", 314, 26, 374, 44)

        # 左: Lスティック(上)と十字キー(下)
        self.create_stick("left", Stick.LEFT, 48, 88, base_radius=27, knob_radius=15, tilt_range=18, text="L", font_size=9)
        self.create_rect_button("btn_lclick", Button.LCLICK, "L-C", 27, 122, 69, 140)
        self.create_dpad(124, 138, cell=18)

        # 中央: − / + と、CAP / HOME(横並び)
        self.create_rect_button("btn_minus", Button.MINUS, "−", 146, 30, 184, 48)
        self.create_rect_button("btn_plus", Button.PLUS, "+", 196, 30, 234, 48)
        self.create_rect_button("btn_capture", Button.CAPTURE, "CAP", 136, 56, 186, 74)
        self.create_rect_button("btn_home", Button.HOME, "HOME", 194, 56, 244, 74)

        # 右: ABXY(上)とRスティック(下)
        self.create_abxy(318, 90, offset=24, r=12, font_size=9)
        self.create_stick("right", Stick.RIGHT, 250, 140, base_radius=27, knob_radius=15, tilt_range=18, text="R", font_size=9)
        self.create_rect_button("btn_rclick", Button.RCLICK, "R-C", 286, 138, 328, 156)

        self.create_hold_button(*COMPACT_HOLD_BUTTON)


class Compact3DSGUI(CanvasControllerGUI):
    """
    Nintendo 3DS: 左にスライドパッドと十字キー、右にABXY、中央にSTART / SELECT / HOME
    """

    TITLE = "3DS (w/o TouchScreen)"
    COLOR_TYPE = ControllerColors.N3DS
    WIDTH = COMPACT_WIDTH
    HEIGHT = COMPACT_HEIGHT
    BODY_COLOR = "#c9d6df"
    STICK_BASE_COLOR = "#aab7c2"

    def build(self) -> None:
        """このレイアウトの部品(本体の塗り分け、ボタン、十字キー、スティックなど)を並べる"""
        self.create_rect_button("btn_l", Button.L, "L", 6, 4, 76, 22)
        self.create_rect_button("btn_r", Button.R, "R", 304, 4, 374, 22)
        # スライドパッド
        self.create_stick("pad", Stick.LEFT, 58, 60, base_radius=27, knob_radius=15, tilt_range=18)
        self.create_dpad(58, 124, cell=18)
        self.create_rect_button("btn_start", Button.START, "START", 158, 62, 222, 80)
        self.create_rect_button("btn_select", Button.SELECT, "SELECT", 158, 86, 222, 104)
        self.create_rect_button("btn_home", Button.HOME, "HOME", 158, 130, 222, 148)
        self.create_abxy(318, 100, offset=28, r=14, font_size=10)
        self.create_hold_button(*COMPACT_HOLD_BUTTON)


class CompactDSGUI(CanvasControllerGUI):
    """
    Nintendo DS: 左に十字キー、右にABXY、中央にSTART / SELECT
    """

    TITLE = "DS (w/o TouchScreen)"
    COLOR_TYPE = ControllerColors.NDS
    WIDTH = COMPACT_WIDTH
    HEIGHT = COMPACT_HEIGHT
    BODY_COLOR = "#dfe3e8"

    def build(self) -> None:
        """このレイアウトの部品(本体の塗り分け、ボタン、十字キー、スティックなど)を並べる"""
        self.create_rect_button("btn_l", Button.L, "L", 6, 4, 76, 22)
        self.create_rect_button("btn_r", Button.R, "R", 304, 4, 374, 22)
        self.create_dpad(62, 100, cell=26)
        self.create_rect_button("btn_start", Button.START, "START", 158, 104, 222, 122)
        self.create_rect_button("btn_select", Button.SELECT, "SELECT", 158, 128, 222, 146)
        self.create_abxy(318, 100, offset=28, r=14, font_size=10)
        self.create_hold_button(*COMPACT_HOLD_BUTTON)


# タッチ画面ありの小型レイアウトのタッチ画面(左上の座標と表示の大きさ。320x240の0.625倍)
COMPACT_TOUCH_X = 90
COMPACT_TOUCH_Y = 20
COMPACT_TOUCH_WIDTH = 200
COMPACT_TOUCH_HEIGHT = 150


class Compact3DSTouchGUI(CanvasControllerGUI):
    """
    Nintendo 3DS(タッチ画面あり): 中央に縮小したタッチ画面、左にスライドパッドと十字キー、右にABXYとSTART / SELECT / HOME
    """

    TITLE = "3DS (w/ TouchScreen)"
    COLOR_TYPE = ControllerColors.N3DS
    WIDTH = COMPACT_WIDTH
    HEIGHT = COMPACT_HEIGHT
    BODY_COLOR = "#c9d6df"
    STICK_BASE_COLOR = "#aab7c2"

    def build(self) -> None:
        """このレイアウトの部品(本体の塗り分け、ボタン、十字キー、スティックなど)を並べる"""
        self.create_touchscreen(COMPACT_TOUCH_X, COMPACT_TOUCH_Y, COMPACT_TOUCH_WIDTH, COMPACT_TOUCH_HEIGHT)
        self.create_rect_button("btn_l", Button.L, "L", 6, 4, 80, 22)
        self.create_rect_button("btn_r", Button.R, "R", 300, 4, 374, 22)
        # スライドパッド
        self.create_stick("pad", Stick.LEFT, 44, 58, base_radius=23, knob_radius=13, tilt_range=15)
        self.create_dpad(44, 120, cell=16)
        self.create_abxy(337, 62, offset=21, r=11, font_size=9)
        self.create_rect_button("btn_start", Button.START, "START", 305, 104, 369, 120)
        self.create_rect_button("btn_select", Button.SELECT, "SELECT", 305, 124, 369, 140)
        self.create_rect_button("btn_home", Button.HOME, "HOME", 305, 152, 369, 168)
        self.create_hold_button(*COMPACT_HOLD_BUTTON)


class CompactDSTouchGUI(CanvasControllerGUI):
    """
    Nintendo DS(タッチ画面あり): 中央に縮小したタッチ画面、左に十字キー、右にABXYとSTART / SELECT
    """

    TITLE = "DS (w/ TouchScreen)"
    COLOR_TYPE = ControllerColors.NDS
    WIDTH = COMPACT_WIDTH
    HEIGHT = COMPACT_HEIGHT
    BODY_COLOR = "#dfe3e8"

    def build(self) -> None:
        """このレイアウトの部品(本体の塗り分け、ボタン、十字キー、スティックなど)を並べる"""
        self.create_touchscreen(COMPACT_TOUCH_X, COMPACT_TOUCH_Y, COMPACT_TOUCH_WIDTH, COMPACT_TOUCH_HEIGHT)
        self.create_rect_button("btn_l", Button.L, "L", 6, 4, 80, 22)
        self.create_rect_button("btn_r", Button.R, "R", 300, 4, 374, 22)
        self.create_dpad(44, 92, cell=22)
        self.create_abxy(337, 62, offset=21, r=11, font_size=9)
        self.create_rect_button("btn_start", Button.START, "START", 305, 112, 369, 128)
        self.create_rect_button("btn_select", Button.SELECT, "SELECT", 305, 134, 369, 150)
        self.create_hold_button(*COMPACT_HOLD_BUTTON)


class CompactGameCubeGUI(CanvasControllerGUI):
    """
    ゲームキューブ: 大きなAボタンを中心にした実機の配置
    コントロールスティックは左スティック、Cスティックは右スティックとして送る
    """

    TITLE = "GameCube"
    COLOR_TYPE = ControllerColors.GAMECUBE
    STICK_BASE_FROM_BODY = True
    WIDTH = COMPACT_WIDTH
    HEIGHT = COMPACT_HEIGHT
    BODY_COLOR = "#6a5acd"
    STICK_BASE_COLOR = "#5346a8"

    def build(self) -> None:
        """このレイアウトの部品(本体の塗り分け、ボタン、十字キー、スティックなど)を並べる"""
        gray = "#ced4da"
        dark_text = "#212529"
        self.create_rect_button("btn_l", GAMECUBE_BUTTONS["L"], "L", 6, 4, 76, 22, color=gray, text_color=dark_text)
        self.create_rect_button("btn_z", GAMECUBE_BUTTONS["Z"], "Z", 228, 4, 298, 22, color="#4263eb")
        self.create_rect_button("btn_r", GAMECUBE_BUTTONS["R"], "R", 304, 4, 374, 22, color=gray, text_color=dark_text)
        self.create_rect_button(
            "btn_start", GAMECUBE_BUTTONS["START"], "START", 158, 60, 222, 78, color=gray, text_color=dark_text
        )

        # コントロールスティックと十字キー
        self.create_stick("control", Stick.LEFT, 54, 78, base_radius=31, knob_radius=17, tilt_range=21, color=gray)
        self.create_dpad(118, 146, cell=16)

        # A(大)を中心に、B(左下)・X(右)・Y(上)
        self.create_round_button("btn_a", Button.A, "A", 310, 86, 22, color="#2f9e44", font_size=13)
        self.create_round_button("btn_b", Button.B, "B", 272, 112, 13, color="#e03131", font_size=9)
        self.create_round_button("btn_x", Button.X, "X", 352, 74, 13, color=gray, text_color=dark_text, font_size=9)
        self.create_round_button("btn_y", Button.Y, "Y", 300, 47, 13, color=gray, text_color=dark_text, font_size=9)

        # Cスティック
        self.create_stick(
            "c",
            Stick.RIGHT,
            230,
            150,
            base_radius=25,
            knob_radius=14,
            tilt_range=17,
            color="#fcc419",
            text="C",
            text_color=dark_text,
            font_size=9,
        )

        self.create_hold_button(*COMPACT_HOLD_BUTTON)


# メイン画面のSoftware-Controllerで選べるレイアウト
COMPACT_LAYOUTS = {
    "Switch (Joy-Con)": CompactSwitchJoyConGUI,
    "Switch (Pro Controller)": CompactSwitchProGUI,
    "3DS (w/o TouchScreen)": Compact3DSGUI,
    "3DS (w/ TouchScreen)": Compact3DSTouchGUI,
    "DS (w/o TouchScreen)": CompactDSGUI,
    "DS (w/ TouchScreen)": CompactDSTouchGUI,
    "GameCube": CompactGameCubeGUI,
}
DEFAULT_COMPACT_LAYOUT = "Switch (Joy-Con)"
# 以前のレイアウト名(保存された設定)と、今のレイアウト名の対応
COMPACT_LAYOUT_ALIASES = {
    "Switch": "Switch (Joy-Con)",
    "3DS": "3DS (w/o TouchScreen)",
    "DS": "DS (w/o TouchScreen)",
}


# ---------------------------------------------------------------- レイアウトの内容の取り出し(tkinter を使わない)


class _RecordingCanvas:
    """
    キャンバスへの描画を、図形のリストとして記録する(画面には何も表示しない)
    """

    def __init__(self) -> None:
        """図形のリスト(shapes)を、空で作る"""
        self.shapes = []

    def _add(self, kind: str, coords: tuple | list, options: dict) -> int:
        """
        図形を 1 つ記録して、その番号(shapes の中の位置)を返す
        kind: 図形の種類("rect" など)。coords: 座標の並び。options: tkinter に渡す fill、tags、text など
        """
        tags = options.get("tags", ())
        font = options.get("font")
        self.shapes.append(
            {
                "type": kind,
                "coords": [float(value) for value in coords],
                "fill": options.get("fill") or None,
                "outline": options.get("outline") or None,
                "tags": [tags] if isinstance(tags, str) else list(tags),
                "text": options.get("text"),
                "font_size": font[1] if font else None,
            }
        )
        return len(self.shapes) - 1

    def create_rectangle(self, *coords: float, **options: Any) -> int:
        """四角形を記録する(引数は tkinter の Canvas と同じ。戻り値は図形の番号)"""
        return self._add("rect", coords, options)

    def create_oval(self, *coords: float, **options: Any) -> int:
        """楕円を記録する(引数は tkinter の Canvas と同じ。戻り値は図形の番号)"""
        return self._add("oval", coords, options)

    def create_polygon(self, *coords: float | list, **options: Any) -> int:
        """多角形を記録する(座標は、並べて渡しても、1 つのリストで渡してもよい。戻り値は図形の番号)"""
        if len(coords) == 1:
            coords = coords[0]
        return self._add("polygon", coords, options)

    def create_text(self, *coords: float, **options: Any) -> int:
        """文字を記録する(引数は tkinter の Canvas と同じ。戻り値は図形の番号)"""
        return self._add("text", coords, options)

    def create_image(self, *coords: float, **options: Any) -> int:
        """画像の置き場所を記録する(引数は tkinter の Canvas と同じ。戻り値は図形の番号)"""
        return self._add("image", coords, options)

    def tag_bind(self, *args: object, **kwargs: object) -> None:
        """何もしない(下のとおり)"""
        # 入力の処理は、表示する側が行う
        pass


def _describe_value(value: Button | Hat) -> dict:
    """ボタン・十字キーの入力を、{"kind": "button" か "hat", "name": 名前} にする"""
    return {"kind": "hat" if type(value) is Hat else "button", "name": value.name}


# Controller Simulator(別ウィンドウ)で選べるレイアウト
LARGE_LAYOUTS = {
    "Switch (Joy-Con)": ControllerSwitchJoyConGUI,
    "Switch (Pro Controller)": ControllerSwitchProGUI,
    "3DS": Controller3DSGUI,
    "DS": ControllerDSGUI,
    "GameCube": ControllerGameCubeGUI,
}
DEFAULT_LARGE_LAYOUT = "Switch (Joy-Con)"


def describe_layout(name: str, colors: dict | None = None, large: bool = False) -> dict:
    """
    メイン画面のSoftware-Controller(large なら Controller Simulator)のレイアウトの内容を、辞書で返す(JSON にできる値だけ)。
    tkinter を使わずに、レイアウトの build() を実行して、描いた図形と部品を記録する
    - shapes: 図形のリスト(描く順)。type は rect / oval / roundrect / polygon / text / image
    - buttons: タグ -> 入力(ボタン・十字キー)、sticks: タグ -> スティックの設定、touch: タッチ画面(無ければ None)
    name: レイアウトの名前(以前の名前も使える。知らない名前は、既定のレイアウト)
    colors: 本体の色(None なら、設定されている色)
    """
    if large:
        if name not in LARGE_LAYOUTS:
            name = DEFAULT_LARGE_LAYOUT
        layout_class = LARGE_LAYOUTS[name]
    else:
        name = COMPACT_LAYOUT_ALIASES.get(name, name)
        if name not in COMPACT_LAYOUTS:
            name = DEFAULT_COMPACT_LAYOUT
        layout_class = COMPACT_LAYOUTS[name]

    class Recorder(layout_class):
        """レイアウトを、画面に表示せずに組み立てて、図形と部品を記録するクラス"""

        def __init__(self) -> None:
            """キャンバスの代わりに記録用のものを置いて、部品を並べる(tkinter は使わない)"""
            self.buttons = {}
            self._init_state(colors, True, None)
            self.canvas = _RecordingCanvas()
            self.build()

        def _round_rect(self, x1: float, y1: float, x2: float, y2: float, r: float, **kwargs: Any) -> int:
            """角の丸い四角形を、種類 "roundrect"(radius 付き)として記録する"""
            index = self.canvas._add("roundrect", (x1, y1, x2, y2), kwargs)
            self.canvas.shapes[index]["radius"] = r
            return index

        def _bind_button(self, tag: str, value: Button | Hat, fill: str) -> None:
            """ボタンの入力と、離したときの色を記録する(イベントの処理は付けない)"""
            self._fills[tag] = fill
            self.buttons[tag] = _describe_value(value)

    gui = Recorder()
    sticks = {
        tag: {
            "stick": info["stick"].name,
            "center": list(info["center"]),
            "knob": info["knob"],
            "label": info["label"],
            "knob_radius": info["knob_radius"],
            "range": info["range"],
        }
        for tag, info in gui._sticks.items()
    }
    touch = None
    if gui.touch_origin is not None:
        touch = {"origin": list(gui.touch_origin), "size": list(gui.touch_size), "image": gui.touch_image, "text": gui.touch_text}
    return {
        "name": name,
        "width": gui.WIDTH,
        "height": gui.HEIGHT,
        "background": gui.BODY_COLOR,
        "shapes": gui.canvas.shapes,
        "buttons": gui.buttons,
        "sticks": sticks,
        "touch": touch,
        "hold": gui.lock_enabled,
        "fills": dict(gui._fills),
        "text_fills": dict(gui._text_fills),
        "colors": {
            "button": BUTTON_COLOR,
            "button_text": BUTTON_TEXT_COLOR,
            "active": BUTTON_ACTIVE_COLOR,
            "lock": LOCK_COLOR,
            "lock_text": LOCK_TEXT_COLOR,
            "touch_text": TOUCH_TEXT_COLOR,
            "touch_mark": TOUCH_MARK_COLOR,
        },
        "touch_size": [TOUCH_WIDTH, TOUCH_HEIGHT],
        "stick_deadzone": STICK_DEADZONE,
    }
