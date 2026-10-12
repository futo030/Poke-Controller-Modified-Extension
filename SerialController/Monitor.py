#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Poke-Controller Monitor: 複数起動した Poke-Controller(tkinter 版)を、まとめて見る補助ツール

--monitor を付けて起動した Poke-Controller につなぎ、枠ごとに、実行中のコマンド・Output・カメラの映像を表示する。
再生・一時停止・停止と、そのウィンドウを最前面に表示する操作ができる(コマンドの選び直しは、できない)。

SerialController フォルダで実行する:
    python Monitor.py              前回の数で開く(初回は、数を選ぶ画面が出る)
    python Monitor.py --count 6    枠の数を指定して開く(1〜12)

枠の数、枠ごとのプロファイルと表示する Output、映像の毎秒の枚数、テーマ、ウィンドウの大きさは、profiles/monitor_tool.json に覚える。
テーマ: メニューの 表示 > テーマ は、この補助ツール全体の配色。つながっている枠は、相手のウィンドウのテーマの配色で表示する。
"""
from __future__ import annotations

import argparse
import ctypes
import io
import json
import os
import sys
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import messagebox
from logging import getLogger, DEBUG, NullHandler

from PIL import Image, ImageTk

import Constant
import Manual
import Profile
import Theme
from services.monitor_client import MAX_FPS, MIN_FPS, MonitorConnection, running_profiles

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

TITLE = "Poke-Controller Monitor"
SETTING_PATH = os.path.join(Profile.PROFILES_DIR, "monitor_tool.json")
# この補助ツールの Instruction Manual(assets/manual の中)と、ライセンス(本体とは別のファイル)
GUIDE_FILE = "manual_monitor.md"
LICENSE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "monitor", "LICENSE")
MAX_COUNT = 12
DEFAULT_COUNT = 4
DEFAULT_FPS = 5
NOT_SELECTED = "(未選択)"
# 枠ごとに選ぶ、表示する Output(番号が、そのまま設定の値になる)。
# 0: 相手のウィンドウの print の出力先(Stdout)の出力画面 / 1・2: Output#1・#2
AREA_NAMES = ("Stdout", "#1", "#2")
# 状態の表示と色(明るいテーマ用 / 暗いテーマ用)
STATE_TEXTS = {"idle": "待機", "running": "実行中", "paused": "一時停止", "stopping": "停止中"}
STATE_COLORS = {"idle": "#777777", "running": "#1a7f37", "paused": "#b26a00", "stopping": "#b26a00"}
STATE_COLORS_DARK = {"idle": "#a0a0a0", "running": "#5fd37a", "paused": "#f0b040", "stopping": "#f0b040"}
PREVIEW_BACKGROUND = "#202020"
PREVIEW_TEXT = "#aaaaaa"
# 表示を更新する間隔(ms)と、映像の頼み直し・プロファイルの一覧の更新の間隔(ms)
TICK_MS = 30
SLOW_TICK_MS = 500
# 枠に表示する Output の行数(枠の数が多いときは、少なくする)と、覚えておく行数
OUTPUT_LINES_FEW, OUTPUT_LINES_MANY = 4, 2
OUTPUT_TAIL_LINES = 300
# 頼む映像の幅の刻みと範囲(枠の大きさが少し変わるたびに頼み直さないように、刻みに切り上げる)
WIDTH_STEP, MIN_VIDEO_WIDTH, MAX_VIDEO_WIDTH = 64, 128, 1280
# 枠 1 つの、初めの大きさ(ウィンドウの初めの大きさを決めるのに使う)
TILE_SIZE = (330, 330)


def columns_for(count: int) -> int:
    """枠の数から、横に並べる数を決める(3 個までは横 1 列。4 個は 2x2。9 個まで 3 列。それより多ければ 4 列)"""
    if count <= 3:
        return count
    if count == 4:
        return 2
    return 3 if count <= 9 else 4


def load_settings(path: str = SETTING_PATH) -> dict:
    """覚えてある設定を読む(ない・読めないときは、空)"""
    try:
        with open(path, encoding="utf-8") as file:
            settings = json.load(file)
        return settings if isinstance(settings, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict, path: str = SETTING_PATH) -> None:
    """設定を覚える(書けないときは、何もしない)"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(settings, file, ensure_ascii=False, indent=2)
    except OSError as e:
        _logger.warning(f"Failed to save the monitor settings: {e}")


def to_int(value: object, low: int, high: int, default: int) -> int:
    """value を整数にして、low〜high に収める(整数にできなければ default)"""
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def tail_lines(text: str, count: int) -> str:
    """文字の、最後の count 行(末尾の改行は除く)"""
    return "\n".join(text.rstrip("\n").split("\n")[-count:])


def fit_size(image_size: tuple, box_size: tuple) -> tuple:
    """画像を、縦横比を保って、枠に収まる最大の大きさにする"""
    width, height = image_size
    box_width, box_height = max(box_size[0], 1), max(box_size[1], 1)
    scale = min(box_width / width, box_height / height)
    return max(1, int(width * scale)), max(1, int(height * scale))


def ask_count(root: tk.Misc, initial: int) -> int:
    """枠の数を選ぶ画面を表示し、選んだ数を返す"""
    dialog = tk.Toplevel(root)
    dialog.title(TITLE)
    dialog.resizable(False, False)
    body = ttk.Frame(dialog, padding=14)
    body.pack()
    ttk.Label(body, text="いくつのウィンドウをモニターしますか?").grid(column=0, columnspan=2, row=0, pady=(0, 8))
    value = tk.IntVar(value=initial)
    ttk.Spinbox(body, from_=1, to=MAX_COUNT, textvariable=value, width=5, state="readonly").grid(column=0, row=1, padx=(0, 8))
    ttk.Button(body, text="開く", command=dialog.destroy).grid(column=1, row=1)
    dialog.grab_set()
    root.wait_window(dialog)
    return to_int(value.get(), 1, MAX_COUNT, initial)


class LicenseWindow:
    """この補助ツールのライセンスを表示するウィンドウ"""

    def __init__(self, root: tk.Misc, path: str = LICENSE_PATH):
        """root: 親のウィンドウ。path: ライセンスのファイル(読めないときは、その旨を表示する)"""
        try:
            with open(path, encoding="utf-8") as file:
                text = file.read().rstrip("\n")
        except OSError:
            text = "(LICENSE のファイルを開けません)"
        self.window = tk.Toplevel(root)
        self.window.title(f"LICENSE - {TITLE}")
        self.window.resizable(False, False)
        body = ttk.Frame(self.window, padding=12)
        body.pack(fill="both", expand=True)
        lines = text.split("\n")
        self.text = tk.Text(
            body, width=max(len(line) for line in lines) + 2, height=len(lines), wrap="none", relief="flat", borderwidth=0,
            highlightthickness=0, font=("Consolas", 9), cursor="arrow",
        )
        # 文字の欄を、入力欄の色ではなく、ウィンドウの背景の色にする(テーマを変えたときは、applyTheme で付け直す)
        self.text.theme_exclude = True
        self.applyTheme()
        self.text.insert("1.0", text)
        self.text.configure(state="disabled")
        self.text.pack()
        self.ok_button = ttk.Button(body, text="OK", width=10, command=self.window.destroy)
        self.ok_button.pack(pady=(10, 0))
        self.window.bind("<Escape>", lambda event: self.window.destroy())

    def applyTheme(self) -> None:
        """文字の欄に、今のテーマの色を付ける"""
        try:
            self.text.configure(background=Theme.color("bg"), foreground=Theme.color("fg"))
        except tk.TclError:
            pass

    def isOpen(self) -> bool:
        """ウィンドウが開いているか"""
        return bool(self.window.winfo_exists())


class PreviewCanvas:
    """映像を表示する欄。大きさが変わっても、映像を、縦横比を保って収める"""

    def __init__(self, parent: tk.Misc, width: int, height: int):
        """parent: 置く先。width / height: 初めの大きさ"""
        self.canvas = tk.Canvas(parent, width=width, height=height, background=PREVIEW_BACKGROUND, highlightthickness=0)
        self._image = None
        self._photo = None
        self._message = ""
        self._drawn = None
        self.canvas.bind("<Configure>", lambda event: self.draw())

    def width(self) -> int:
        """今の幅"""
        return max(self.canvas.winfo_width(), 1)

    def show(self, jpeg: bytes | None, message: str = "") -> None:
        """映像(JPEG)を表示する。None のときは、message を表示する"""
        image = None
        if jpeg is not None:
            try:
                image = Image.open(io.BytesIO(jpeg))
                image.load()
            except Exception:
                image = None
        self._image = image
        self._message = message
        self._drawn = None
        self.draw()

    def draw(self) -> None:
        """今の大きさに合わせて、描き直す"""
        canvas = self.canvas
        box = (canvas.winfo_width(), canvas.winfo_height())
        key = (id(self._image), self._message, box)
        if key == self._drawn:
            return
        self._drawn = key
        canvas.delete("all")
        if self._image is None:
            canvas.create_text(box[0] // 2, box[1] // 2, fill=PREVIEW_TEXT, text=self._message, width=max(box[0] - 16, 50),
                               justify="center")
            self._photo = None
            return
        size = fit_size(self._image.size, box)
        image = self._image if size == self._image.size else self._image.resize(size, Image.BILINEAR)
        self._photo = ImageTk.PhotoImage(image, master=canvas)
        canvas.create_image(box[0] // 2, box[1] // 2, image=self._photo)


class View:
    """
    1 つのプロファイルの表示(枠と、拡大表示に共通の部分): 状態・コマンド・映像・Output・操作のボタン
    """

    def __init__(self, app: MonitorApp, parent: tk.Misc, output_lines: int, preview_size: tuple):
        """app: モニターの画面。parent: 置く先。output_lines: Output の欄の行数。preview_size: 映像の欄の初めの大きさ"""
        self.app = app
        self.profile_name = ""
        self._seen = None
        self._theme = None
        self._state_name = ""
        # 表示する Output(AREA_NAMES の番号)
        self.area = 0
        # 枠の中は、相手のウィンドウのテーマの配色にするので、tk の部品で作り、色を自分で付ける
        # (ttk の部品の色は、補助ツール全体で 1 つなので、枠ごとに変えられない)
        self.frame = tk.Frame(parent, padx=6, pady=6, highlightthickness=1)
        # 補助ツール全体のテーマを変えたときの、色の置き換え(Theme)の対象から外す
        self.frame.theme_exclude = True
        self.frame.columnconfigure(0, weight=1)
        self.head = tk.Frame(self.frame)
        self.head.grid(column=0, row=0, sticky="ew")
        self.state_label = tk.Label(self.head, text="", anchor="e")
        self.state_label.pack(side="right")
        self.area_name = tk.StringVar(value=AREA_NAMES[0])
        self.area_cb = ttk.Combobox(self.head, textvariable=self.area_name, values=AREA_NAMES, state="readonly", width=7)
        self.area_cb.pack(side="right", padx=(6, 6))
        self.area_cb.bind("<<ComboboxSelected>>", lambda event: self.setArea(AREA_NAMES.index(self.area_name.get())))
        self.command = tk.StringVar()
        self.command_label = tk.Label(self.frame, textvariable=self.command, anchor="w")
        self.command_label.grid(column=0, row=1, sticky="ew", pady=(4, 2))
        self.preview = PreviewCanvas(self.frame, *preview_size)
        self.preview.canvas.grid(column=0, row=2, sticky="nsew")
        self.frame.rowconfigure(2, weight=1)
        self.output = tk.Text(
            self.frame, height=output_lines, width=10, wrap="none", state="disabled", font=("Consolas", 9),
            borderwidth=0, highlightthickness=1,
        )
        self.output.grid(column=0, row=3, sticky="ew", pady=(4, 4))
        self.buttons_f = tk.Frame(self.frame)
        self.buttons_f.grid(column=0, row=4, sticky="ew")
        self.play_button = self._button("▶", "play", 3)
        self.pause_button = self._button("⏸", "pause", 3)
        self.stop_button = self._button("■", "stop", 3)
        self.front_button = self._button("前面に表示", "front", None)
        self.buttons = (self.play_button, self.pause_button, self.stop_button, self.front_button)
        for button in self.buttons[:3]:
            button.pack(side="left", padx=(0, 3))
        self.front_button.pack(side="right")
        self.applyTheme(Theme.current())

    def _button(self, text: str, action: str, width: int | None) -> tk.Button:
        """操作のボタンを作る(色は applyTheme が付ける)"""
        button = tk.Button(self.buttons_f, text=text, command=lambda: self.act(action), relief="groove", borderwidth=1, padx=6)
        if width is not None:
            button.configure(width=width)
        return button

    def themeId(self) -> str:
        """この表示に使うテーマ: つながっていれば、相手のウィンドウのテーマ。そうでなければ、補助ツール全体のテーマ"""
        connection = self.connection()
        if connection is not None and connection.connected:
            theme = connection.state.get("theme")
            if theme in Theme.THEMES:
                return theme
        return Theme.current()

    def applyTheme(self, theme_id: str) -> None:
        """枠の中の部品に、そのテーマの配色を付ける"""
        self._theme = theme_id
        definition = Theme.THEMES[theme_id]
        colors = definition["colors"]
        self._state_colors = STATE_COLORS_DARK if definition["dark"] else STATE_COLORS
        settings = [
            (self.frame, dict(background=colors["bg"], highlightbackground=colors["border"], highlightcolor=colors["border"])),
            (self.head, dict(background=colors["bg"])),
            (self.buttons_f, dict(background=colors["bg"])),
            (self.state_label, dict(background=colors["bg"])),
            (self.command_label, dict(background=colors["bg"], foreground=colors["fg"])),
            (self.output, dict(background=colors["field"], foreground=colors["text_fg"], insertbackground=colors["text_fg"],
                               selectbackground=colors["select"], selectforeground=colors["select_fg"],
                               highlightbackground=colors["border"], highlightcolor=colors["border"])),
        ]
        settings += [
            (button, dict(background=colors["button"], foreground=colors["fg"], activebackground=colors["button_active"],
                          activeforeground=colors["fg"], disabledforeground=colors["muted"]))
            for button in self.buttons
        ]
        for widget, options in settings:
            try:
                widget.configure(**options)
            except tk.TclError:
                # その環境にない色の名前(Windows 以外での、デフォルトのテーマの色)は、付けない
                pass
        self._colorState()

    def _colorState(self) -> None:
        """状態の文字の色を、今の状態とテーマに合わせる"""
        self.state_label.configure(foreground=self._state_colors.get(self._state_name, self._state_colors["idle"]))

    def connection(self) -> MonitorConnection | None:
        """表示しているプロファイルとのつながり(プロファイルを選んでいなければ None)"""
        return self.app.connection(self.profile_name)

    def setProfile(self, name: str) -> None:
        """表示するプロファイルを変える(空文字は、未選択)"""
        self.profile_name = name
        self._seen = None

    def setArea(self, area: int) -> None:
        """表示する Output を変える(area: AREA_NAMES の番号。0 は Stdout)"""
        self.area = to_int(area, 0, len(AREA_NAMES) - 1, 0)
        self.area_name.set(AREA_NAMES[self.area])

    def act(self, name: str) -> None:
        """操作のボタン: 再生・一時停止・停止・前面に表示を、相手に頼む"""
        connection = self.connection()
        if connection is None or not connection.connected:
            return
        if name == "front" and os.name == "nt" and connection.pid:
            # ほかのアプリのウィンドウを前に出すには、今、前にいる側(この補助ツール)の許可が要る
            try:
                ctypes.windll.user32.AllowSetForegroundWindow(int(connection.pid))
            except Exception:
                pass
        sent = connection.action(name)
        self.app.setStatus(f"{self.profile_name}: {name}" if sent else f"{self.profile_name}: 送れませんでした")

    def refresh(self) -> None:
        """表示を、届いている内容に合わせる(前に表示したときから変わった所だけ、描き直す)"""
        connection = self.connection()
        theme = self.themeId()
        if theme != self._theme:
            self.applyTheme(theme)
        if connection is None:
            seen = (None,)
            if seen != self._seen:
                self._seen = seen
                self._showDisconnected("プロファイルを選んでください")
            return
        connected = connection.connected
        # 表示する Output: 「Stdout」なら、相手の print の出力先の出力画面
        area = self.area or (2 if connection.state.get("stdout_area") == 2 else 1)
        seen = (connection, connected, connection.state_seq, connection.frame_seq, connection.output_seq[area], area)
        previous = self._seen if self._seen is not None and len(self._seen) == len(seen) else (None,) * len(seen)
        if seen == previous:
            return
        self._seen = seen
        if not connected:
            self._showDisconnected("起動していません\n(--monitor を付けて起動すると、表示されます)")
            # 切れる前の Output は、読み返せるように残す
            self._setOutput(connection.output(area))
            return
        if seen[:3] != previous[:3]:
            self._showState(connection.state)
        if seen[:2] != previous[:2] or seen[3] != previous[3]:
            self.preview.show(connection.frame(), "映像がありません\n(カメラを開いていません)")
        if seen[:2] != previous[:2] or seen[4:] != previous[4:]:
            self._setOutput(connection.output(area))

    def _showDisconnected(self, message: str) -> None:
        """つながっていないときの表示"""
        self._state_name = ""
        self.state_label.configure(text="")
        self.command.set("")
        self.preview.show(None, message)
        self._setOutput("")
        for button in self.buttons:
            button.configure(state="disabled")

    def _showState(self, state: dict) -> None:
        """状態・コマンドの名前・ボタンの押せる状態を合わせる"""
        name = state.get("state", "")
        self._state_name = name
        self.state_label.configure(text=("● " + STATE_TEXTS[name]) if name in STATE_TEXTS else "")
        self._colorState()
        if name == "idle" or not name:
            selected = state.get("selected") or ""
            self.command.set(f"(選択中: {selected})" if selected else "")
        else:
            self.command.set(str(state.get("command", "")))
        self.play_button.configure(state="normal" if name == "paused" or state.get("can_start") else "disabled")
        self.pause_button.configure(state="normal" if state.get("can_pause") else "disabled")
        self.stop_button.configure(state="normal" if name in ("running", "paused") else "disabled")
        self.front_button.configure(state="normal")

    def _setOutput(self, text: str) -> None:
        """Output の欄を、最後の部分に書き換えて、末尾を表示する"""
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", tail_lines(text, OUTPUT_TAIL_LINES))
        self.output.configure(state="disabled")
        self.output.see("end")


class Tile(View):
    """枠: プロファイルを選ぶ欄の付いた表示。映像をダブルクリックすると、拡大表示を開く"""

    def __init__(self, app: MonitorApp, parent: tk.Misc, index: int, output_lines: int):
        """index: 枠の番号(0 始まり)"""
        super().__init__(app, parent, output_lines, (160, 90))
        self.index = index
        super().setArea(app.areas[index])
        self.profile = tk.StringVar(value=NOT_SELECTED)
        self.profile_cb = ttk.Combobox(
            self.head, textvariable=self.profile, state="readonly", width=14, postcommand=self._fillProfiles
        )
        self.profile_cb.pack(side="left")
        self.profile_cb.bind("<<ComboboxSelected>>", lambda event: self.app.assign(self.index, self.profile.get()))
        self.preview.canvas.bind("<Double-Button-1>", lambda event: self.app.showDetail(self.profile_name, self.area))

    def setArea(self, area: int) -> None:
        """表示する Output を変えて、この枠の設定として覚える"""
        super().setArea(area)
        self.app.areas[self.index] = self.area
        self.app.saveSettings()

    def _fillProfiles(self) -> None:
        """プロファイルの一覧を開くとき: 選べる名前を、今あるプロファイルに合わせる"""
        self.profile_cb["values"] = [NOT_SELECTED] + self.app.profileNames()

    def setProfile(self, name: str) -> None:
        """表示するプロファイルを変える(空文字は、未選択)"""
        super().setProfile(name)
        self.profile.set(name or NOT_SELECTED)


class MonitorApp:
    """モニターの画面"""

    def __init__(self, root: tk.Tk | tk.Toplevel, count: int | None = None, setting_path: str = SETTING_PATH):
        """
        root: この画面にするウィンドウ。count: 枠の数(None なら、前回の数。覚えていなければ、数を選ぶ画面を出す)
        setting_path: 設定を覚えるファイル
        """
        self.root = root
        self.setting_path = setting_path
        self.settings = load_settings(setting_path)
        # 補助ツール全体のテーマ(前回のもの)。ほかの画面の中に開いた場合(確認用)は、その画面のテーマのままにする
        if isinstance(root, tk.Tk):
            Theme.init(root, str(self.settings.get("theme", Theme.DEFAULT_THEME)))
        if count is None:
            count = self.settings.get("count")
            if count is None:
                root.withdraw()
                count = ask_count(root, DEFAULT_COUNT)
                root.deiconify()
        self.connections: dict[str, MonitorConnection] = {}
        self.tiles: list[Tile] = []
        self.detail = None
        self.detail_view = None
        self.guide_window = None
        self.license_window = None
        self._closed = False
        # 枠ごとのプロファイル(12 個分を覚えておき、数を減らしても、戻したときに元の割り当てになるようにする)
        saved = self.settings.get("assignments")
        if isinstance(saved, list):
            self.assignments = [str(name) if isinstance(name, str) else "" for name in saved][:MAX_COUNT]
        else:
            # 初めて開くとき: 起動中のものを、順に割り当てる
            self.assignments = running_profiles()[:MAX_COUNT]
        self.assignments += [""] * (MAX_COUNT - len(self.assignments))
        # 枠ごとの、表示する Output(12 個分。以前の「全体で 1 つ」の設定があれば、それを初めの値にする)
        saved = self.settings.get("areas")
        default_area = to_int(self.settings.get("area"), 0, 2, 0)
        self.areas = [to_int(area, 0, 2, default_area) for area in (saved if isinstance(saved, list) else [])][:MAX_COUNT]
        self.areas += [default_area] * (MAX_COUNT - len(self.areas))

        root.title(f"{TITLE} ({Constant.NAME} ver.{Constant.VERSION})")
        bar = ttk.Frame(root, padding=(8, 6))
        bar.pack(fill="x")
        self._buildMenu(bar)
        ttk.Label(bar, text="数:").pack(side="left")
        self.count = tk.IntVar(value=to_int(count, 1, MAX_COUNT, DEFAULT_COUNT))
        count_cb = ttk.Combobox(bar, textvariable=self.count, values=list(range(1, MAX_COUNT + 1)), state="readonly", width=4)
        count_cb.pack(side="left", padx=(4, 12))
        count_cb.bind("<<ComboboxSelected>>", lambda event: self.build(resize=True))
        ttk.Label(bar, text="映像 (fps):").pack(side="left")
        self.fps = tk.IntVar(value=to_int(self.settings.get("fps"), MIN_FPS, MAX_FPS, DEFAULT_FPS))
        self.fps_sb = ttk.Spinbox(bar, from_=MIN_FPS, to=MAX_FPS, textvariable=self.fps, width=4, command=self.requestVideo)
        self.fps_sb.pack(side="left", padx=(4, 12))
        for sequence in ("<Return>", "<FocusOut>"):
            self.fps_sb.bind(sequence, lambda event: self.requestVideo())
        # つながっているすべてのウィンドウの、コマンドの開始と停止
        self.all_start_button = ttk.Button(bar, text="All Start", command=self.startAll)
        self.all_start_button.pack(side="left")
        self.all_stop_button = ttk.Button(bar, text="All Stop", command=self.stopAll)
        self.all_stop_button.pack(side="left", padx=(4, 0))
        self.summary = tk.StringVar()
        self.grid = ttk.Frame(root, padding=(8, 0, 8, 4))
        self.grid.pack(fill="both", expand=True)
        self.status = tk.StringVar(value="映像をダブルクリックすると、大きく表示します")
        bottom = ttk.Frame(root, padding=(8, 2))
        bottom.pack(fill="x")
        ttk.Label(bottom, textvariable=self.status).pack(side="left")
        # 起動中の数は、幅の狭いとき(枠が少ないとき)にも隠れないように、下の行に出す
        ttk.Label(bottom, textvariable=self.summary).pack(side="right")

        self.build(resize=not self._restoreGeometry())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._tick()
        self._slowTick()

    # ---------------------------------------------------------------- 設定

    def _restoreGeometry(self) -> bool:
        """前回のウィンドウの大きさと位置にする。できたか"""
        geometry = self.settings.get("geometry")
        if not isinstance(geometry, str) or not geometry:
            return False
        try:
            self.root.geometry(geometry)
            return True
        except tk.TclError:
            return False

    def _buildMenu(self, before: tk.Widget) -> None:
        """
        メニューバー(ファイル / 表示 / ヘルプ)を作る。( ) の中のキーを Alt と一緒に押すと、キーボードから開ける。
        before: 上の欄(デフォルト以外のテーマでは、この上に、テーマの色のメニューバーを置く)
        """
        self.menu = tk.Menu(self.root, tearoff="false")
        self.menu_file = tk.Menu(self.menu, tearoff="false")
        self.menu_file.add("command", label="終了", command=self.close)
        # 表示 > テーマ: 補助ツール全体の配色(本体のメニューと同じ並び)
        self.menu_view = tk.Menu(self.menu, tearoff="false")
        self.menu_theme = tk.Menu(self.menu_view, tearoff="false")
        self.theme_var = tk.StringVar(value=Theme.current())
        for theme_id in Theme.theme_ids():
            self.menu_theme.add_radiobutton(
                label=Theme.theme_name(theme_id), value=theme_id, variable=self.theme_var, command=self.changeTheme
            )
        self.menu_view.add(tk.CASCADE, menu=self.menu_theme, label="テーマ")
        self.menu_help = tk.Menu(self.menu, tearoff="false")
        self.menu_help.add("command", label="Instruction Manual", command=self.openGuide)
        self.menu_help.add("command", label="LICENSE", command=self.openLicense)
        for label, key, menu in (("ファイル", "F", self.menu_file), ("表示", "D", self.menu_view), ("ヘルプ", "H", self.menu_help)):
            self.menu.add(tk.CASCADE, menu=menu, label=f"{label}({key})", underline=len(label) + 1)
        # デフォルト以外のテーマでは、テーマの色のメニューバーを使う(Windows のメニューバーは、色を変えられないため)
        self.themed_menubar = Theme.ThemedMenuBar(self.root, self.menu, before)
        self.themed_menubar.update()

    def openGuide(self) -> None:
        """ヘルプ > Instruction Manual: この補助ツールの説明を開く(すでに開いていれば、前面に出す)"""
        window = self.guide_window.window if self.guide_window is not None else None
        if window is not None and window.winfo_exists():
            self.guide_window.focus_force()
            return
        self.guide_window = Manual.ManualWindow(
            self.root, topics=Manual.load_guide(GUIDE_FILE), title=f"Instruction Manual - {TITLE}"
        )

    def openLicense(self) -> None:
        """ヘルプ > LICENSE: この補助ツールのライセンスを開く(すでに開いていれば、前面に出す)"""
        if self.license_window is not None and self.license_window.isOpen():
            self.license_window.window.lift()
            self.license_window.window.focus_force()
            return
        self.license_window = LicenseWindow(self.root)

    def changeTheme(self, theme_id: str | None = None) -> None:
        """
        補助ツール全体のテーマを変えて、覚える(つながっている枠は、相手のウィンドウのテーマのまま)。
        theme_id: テーマの ID(None なら、メニューの 表示 > テーマ で選んでいるもの)
        """
        if theme_id is None:
            theme_id = self.theme_var.get()
        Theme.apply(theme_id)
        self.themed_menubar.update()
        if self.license_window is not None and self.license_window.isOpen():
            self.license_window.applyTheme()
        self.theme_var.set(Theme.current())
        self.saveSettings()

    def _targets(self, action: str) -> list:
        """
        まとめての操作の対象(プロファイルの名前とつながり)を、枠の順に返す。
        action: "play"(待機中で開始できるものと、一時停止中のもの)/ "stop"(実行中・一時停止中のもの)
        """
        names = [tile.profile_name for tile in self.tiles]
        names += [name for name in self.connections if name not in names]
        targets = []
        for name in dict.fromkeys(names):
            connection = self.connections.get(name)
            if connection is None or not connection.connected:
                continue
            state = connection.state
            if action == "play":
                matched = state.get("state") == "paused" or bool(state.get("can_start"))
            else:
                matched = state.get("state") in ("running", "paused")
            if matched:
                targets.append((name, connection))
        return targets

    def _askAll(self, label: str, action: str, verb: str) -> None:
        """
        まとめての操作: 対象を確かめてもらってから、それぞれに頼む。対象がなければ、その旨を表示するだけ。
        label: ボタンの名前。action: 頼む操作("play" / "stop")。verb: 確認の文に使う言葉("開始" / "停止")
        """
        targets = self._targets(action)
        if not targets:
            self.setStatus(f"{label}: 対象のウィンドウがありません")
            return
        lines = []
        for name, connection in targets:
            state = connection.state
            paused = state.get("state") == "paused"
            command = state.get("command") if state.get("state") != "idle" else state.get("selected")
            note = "(一時停止中 → 再開)" if paused and action == "play" else ""
            lines.append(f"・{name}: {command or '(コマンドなし)'}{note}")
        message = f"次の {len(targets)} 個のウィンドウで、コマンドを{verb}します。よろしいですか?\n\n" + "\n".join(lines)
        if not messagebox.askyesno(f"{label} - {TITLE}", message, parent=self.root):
            self.setStatus(f"{label}: 取り消しました")
            return
        # 確認している間に状態が変わったものには、頼まない(例: 確認中に、コマンドが終わった)
        still = {name for name, _ in self._targets(action)}
        count = sum(bool(connection.action(action)) for name, connection in targets if name in still)
        self.setStatus(f"{label}: {count} 個のウィンドウに、{verb}を頼みました")

    def startAll(self) -> None:
        """
        All Start: 確認のうえ、つながっているすべてのウィンドウで、▶ と同じ操作を行う
        (待機中は、選んでいるコマンドを開始。一時停止中は、再開。実行中のものと、開始できないものは、対象にしない)
        """
        self._askAll("All Start", "play", "開始")

    def stopAll(self) -> None:
        """All Stop: 確認のうえ、つながっているすべてのウィンドウで、実行中・一時停止中のコマンドを停止する"""
        self._askAll("All Stop", "stop", "停止")

    def saveSettings(self) -> None:
        """今の設定(枠の数・割り当て・毎秒の枚数・表示する Output・テーマ・ウィンドウの大きさ)を覚える"""
        self.settings.update(
            count=self.count.get(),
            fps=self.fpsValue(),
            areas=list(self.areas),
            theme=Theme.current(),
            assignments=list(self.assignments),
            geometry=self.root.geometry(),
        )
        # 以前の「全体で 1 つ」の設定は、枠ごとの設定に移したので、消す
        self.settings.pop("area", None)
        save_settings(self.settings, self.setting_path)

    def fpsValue(self) -> int:
        """映像の毎秒の枚数(入力欄の値を、範囲に収めたもの)"""
        try:
            value = self.fps.get()
        except tk.TclError:
            value = DEFAULT_FPS
        value = to_int(value, MIN_FPS, MAX_FPS, DEFAULT_FPS)
        self.fps.set(value)
        return value

    def setStatus(self, text: str) -> None:
        """下の行に、知らせを表示する"""
        self.status.set(text)

    def profileNames(self) -> list:
        """選べるプロファイルの名前(今あるプロファイルと、窓口を開いているもの)"""
        names = Profile.list_profiles()
        return names + [name for name in running_profiles() if name not in names]

    # ---------------------------------------------------------------- 枠

    def build(self, resize: bool = False) -> None:
        """枠を、数に合わせて作り直す。resize: ウィンドウの大きさを、数に合った初めの大きさにするか"""
        count = to_int(self.count.get(), 1, MAX_COUNT, DEFAULT_COUNT)
        for tile in self.tiles:
            tile.frame.destroy()
        columns = columns_for(count)
        rows = -(-count // columns)
        for column in range(MAX_COUNT):
            self.grid.columnconfigure(column, weight=1 if column < columns else 0, uniform="tile" if column < columns else "")
            self.grid.rowconfigure(column, weight=1 if column < rows else 0, uniform="tile" if column < rows else "")
        self.tiles = []
        for index in range(count):
            tile = Tile(self, self.grid, index, OUTPUT_LINES_FEW if count <= 6 else OUTPUT_LINES_MANY)
            tile.frame.grid(column=index % columns, row=index // columns, padx=3, pady=3, sticky="nsew")
            tile.setProfile(self.assignments[index])
            self.tiles.append(tile)
        if resize:
            self.root.geometry(f"{columns * TILE_SIZE[0] + 24}x{rows * TILE_SIZE[1] + 80}")
        self._syncConnections()
        self.saveSettings()

    def assign(self, index: int, name: str) -> None:
        """枠に、プロファイルを割り当てる(name が「未選択」なら、外す)"""
        name = "" if name == NOT_SELECTED else name
        self.assignments[index] = name
        self.tiles[index].setProfile(name)
        self._syncConnections()
        self.saveSettings()

    def connection(self, profile: str) -> MonitorConnection | None:
        """そのプロファイルとのつながり(表示していないプロファイルは None)"""
        return self.connections.get(profile)

    def _shownProfiles(self) -> set:
        """今、表示しているプロファイル(枠と、拡大表示)"""
        shown = {tile.profile_name for tile in self.tiles if tile.profile_name}
        if self.detail_view is not None and self.detail_view.profile_name:
            shown.add(self.detail_view.profile_name)
        return shown

    def _syncConnections(self) -> None:
        """表示しているプロファイルにだけ、つなぐ(表示をやめたものは、切る)"""
        shown = self._shownProfiles()
        for profile in list(self.connections):
            if profile not in shown:
                self.connections.pop(profile).close()
        for profile in shown:
            if profile not in self.connections:
                self.connections[profile] = MonitorConnection(profile)
        self.requestVideo()

    def requestVideo(self) -> None:
        """それぞれの相手に、映像の毎秒の枚数と、表示している大きさに合った幅を頼む"""
        fps = self.fpsValue()
        views = list(self.tiles) + ([self.detail_view] if self.detail_view is not None else [])
        for profile, connection in self.connections.items():
            widths = [view.preview.width() for view in views if view.profile_name == profile]
            width = max(widths, default=MIN_VIDEO_WIDTH)
            width = max(MIN_VIDEO_WIDTH, min(MAX_VIDEO_WIDTH, -(-width // WIDTH_STEP) * WIDTH_STEP))
            connection.set_video(fps, width)

    # ---------------------------------------------------------------- 更新

    def _tick(self) -> None:
        """短い間隔で、届いた内容を表示に反映する"""
        if self._closed:
            return
        for tile in self.tiles:
            tile.refresh()
        if self.detail_view is not None:
            self.detail_view.refresh()
        self.root.after(TICK_MS, self._tick)

    def _slowTick(self) -> None:
        """長い間隔で、起動中の数の表示と、映像の頼み直し(枠の大きさが変わったとき)を行う"""
        if self._closed:
            return
        running = sum(1 for tile in self.tiles if tile.connection() is not None and tile.connection().connected)
        self.summary.set(f"起動中 {running} / {len(self.tiles)}")
        self.requestVideo()
        self.root.after(SLOW_TICK_MS, self._slowTick)

    # ---------------------------------------------------------------- 拡大表示

    def showDetail(self, profile: str, area: int = 0) -> None:
        """
        拡大表示(1 つのプロファイルの映像と Output を大きく)を開く。すでに開いていれば、そのプロファイルに切り替える。
        area: 初めに表示する Output(開いた元の枠と同じにする。拡大表示の中でも、切り替えられる)
        """
        if not profile:
            return
        if self.detail is None or not self.detail.winfo_exists():
            self.detail = tk.Toplevel(self.root)
            self.detail.geometry("760x640")
            self.detail.protocol("WM_DELETE_WINDOW", self.closeDetail)
            self.detail_view = View(self, self.detail, 12, (640, 360))
            self.detail_view.frame.pack(fill="both", expand=True)
        self.detail.title(f"{profile} - {TITLE}")
        self.detail_view.setProfile(profile)
        self.detail_view.setArea(area)
        self.detail.lift()
        self._syncConnections()

    def closeDetail(self) -> None:
        """拡大表示を閉じる"""
        if self.detail is not None and self.detail.winfo_exists():
            self.detail.destroy()
        self.detail = None
        self.detail_view = None
        self._syncConnections()

    # ---------------------------------------------------------------- 終了

    def close(self) -> None:
        """設定を覚えて、すべてのつながりを切り、ウィンドウを閉じる"""
        if self._closed:
            return
        self.saveSettings()
        self._closed = True
        for connection in self.connections.values():
            connection.close()
        self.connections = {}
        self.root.destroy()


def main() -> None:
    """引数を読んで、モニターを開く"""
    parser = argparse.ArgumentParser(description="monitor for multiple Poke-Controller windows (started with --monitor)")
    parser.add_argument("--count", "-n", type=int, default=None, help=f"number of windows to monitor (1-{MAX_COUNT})")
    args = parser.parse_args()
    root = tk.Tk()
    MonitorApp(root, None if args.count is None else to_int(args.count, 1, MAX_COUNT, DEFAULT_COUNT))
    root.mainloop()


if __name__ == "__main__":
    # uv の環境(.venv)があれば、その Python で起動し直す(以前からの起動用のファイルのため。0.3.0 で消す)
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from bootstrap.relaunch import run_in_venv

        run_in_venv()
    except ImportError:
        pass
    finally:
        sys.path.pop(0)
    main()
