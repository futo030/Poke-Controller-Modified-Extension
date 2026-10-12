#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Manual Control タブ: 画面上のコントローラー、キーボード・マウス、接続したコントローラー、操作の記録
"""
from __future__ import annotations

import tkinter as tk
import os
import platform
import threading
import tkinter.ttk as ttk
import tkinter.messagebox as tkmsg
import KeyMap
from Commands.transport import get_transport
from Keyboard import SwitchKeyboardController
import Theme
from Commands.ProController import ProController
from Commands.ControllerProfile import (
    AUTO_DEVICE,
    ControllerProfileError,
    device_label,
    list_joystick_names,
    load_profiles,
    profile_file_for,
    select_device,
)
from services.record_service import RecordError
from ControllerLayouts import COMPACT_LAYOUT_ALIASES, COMPACT_LAYOUTS, DEFAULT_COMPACT_LAYOUT
from ControllerWindow import ControllerWindow
from ControllerColorWindow import ControllerColorWindow
import ControllerColors
from ControllerSetup import ControllerSetupWindow
from UiDispatcher import UiDispatcher
from ui.constants import PROCON_STOP_TIMEOUT
from ui.switch_keyboard import SwitchKeyboardWindow
from ui.tooltip import ToolTip


# フォーカスがある間、キーボードでの操作を止める部品の種類(_isTypingWidget)と、そのうち state を持つもの
KEY_CONSUMING_CLASSES = frozenset({
    "Entry", "TEntry", "Spinbox", "TSpinbox", "Text", "TCombobox", "TNotebook", "Treeview", "Listbox",
    "Scale", "TScale", "Scrollbar", "TScrollbar", "Radiobutton", "TRadiobutton", "Menubutton", "TMenubutton",
})
STATEFUL_CLASSES = frozenset({
    "Entry", "TEntry", "Spinbox", "TSpinbox", "Text", "TCombobox", "Listbox", "Scale", "TScale",
    "Radiobutton", "TRadiobutton", "Menubutton", "TMenubutton",
})

# コマンドの実行中に「すべての入力を離す」を選んだときの、確認の文
RELEASE_ALL_WARNING = (
    "コマンドを実行中です。\n"
    "すべての入力を離すと、コマンドが押したままにしている入力も離れるので、実行中のコマンドの動きに影響することがあります。\n"
    "(コマンドは止まりません。止めるには Stop を押してください)\n\n"
    "すべての入力を離しますか?"
)


class ControllerPanelMixin:
    """
    Manual Control タブ: 画面上のコントローラー、キーボード・マウス、接続したコントローラー、操作の記録
    (PokeControllerApp に取り込んで使う。部品や設定は self の属性として、ほかのファイルと共有する)
    """

    def _buildManualControlTab(self) -> None:
        """
        Manual Control タブの部品を作る(起動時に1回だけ呼ぶ)
        """
        self.manual_control_f = ttk.Frame(self.controller_nb)
        # Software(画面上のコントローラー・キーボード・マウス) と Hardware(PCに接続したコントローラー) を左右に並べる
        self.manual_control_f.columnconfigure(0, weight=1, uniform="manual")
        self.manual_control_f.columnconfigure(1, weight=1, uniform="manual")
        self.software_lf = ttk.Labelframe(self.manual_control_f)
        # メイン画面のSoftware-Controllerのレイアウト(Switch(Joy-Con / Pro Controller) / 3DS / DS / GameCube)
        self.software_controller_layout_label = ttk.Label(self.software_lf)
        self.software_controller_layout_label.configure(text="Layout:")
        self.software_controller_layout_label.grid(column="0", padx=(8, 4), pady="4", row="0", sticky="w")
        self.software_controller_layout = tk.StringVar(value=DEFAULT_COMPACT_LAYOUT)
        self.software_controller_layout_cb = ttk.Combobox(self.software_lf)
        self.software_controller_layout_cb.configure(
            state="readonly",
            textvariable=self.software_controller_layout,
            values=list(COMPACT_LAYOUTS),
            width="18",
        )
        self.software_controller_layout_cb.grid(column="1", padx="4", pady="4", row="0", sticky="ew")
        self.software_controller_layout_cb.bind("<<ComboboxSelected>>", self.setSoftwareControllerLayout)
        # Controller Simulatorのウィンドウを開く
        self.simplecon_button = ttk.Button(self.software_lf)
        self.simplecon_button.configure(text="Open", width="6")
        self.simplecon_button.grid(column="2", padx=(4, 8), pady="4", row="0", sticky="e")
        self.simplecon_button.configure(command=self.createControllerWindow)
        self.software_input_f = ttk.Frame(self.software_lf)
        self.use_keyboard_checkbox = ttk.Checkbutton(self.software_input_f)
        self.is_use_keyboard = tk.BooleanVar()  # modified
        self.use_keyboard_checkbox.configure(
            text="Keyboard", variable=self.is_use_keyboard
        )
        self.use_keyboard_checkbox.pack(side="left", padx=(8, 4))
        # Macでは、画面の表示中にキー入力の受け付けを開始・停止できない(pynputの制限)ため、
        # チェックの変更は次回の起動時に反映する
        if platform.system() != "Darwin":
            self.use_keyboard_checkbox.configure(command=self.activateKeyboard)
        else:
            self.use_keyboard_checkbox.configure(command=self.noticeKeyboardSetting)
        self.left_stick_mouse_checkbox = ttk.Checkbutton(self.software_input_f)
        self.camera_lf.is_use_left_stick_mouse = (
            tk.BooleanVar()
        )  # modified(継承いじるの面倒なので暫定的にこのまま)
        self.left_stick_mouse_checkbox.configure(
            text="LStick Mouse", variable=self.camera_lf.is_use_left_stick_mouse
        )  # modified
        self.left_stick_mouse_checkbox.pack(side="left", padx="4")
        self.left_stick_mouse_checkbox.configure(command=self.activate_Left_stick_mouse)
        self.right_stick_mouse_checkbox = ttk.Checkbutton(self.software_input_f)
        self.camera_lf.is_use_right_stick_mouse = (
            tk.BooleanVar()
        )  # modified(継承いじるの面倒なので暫定的にこのまま)
        self.right_stick_mouse_checkbox.configure(
            text="RStick Mouse", variable=self.camera_lf.is_use_right_stick_mouse
        )  # modified
        self.right_stick_mouse_checkbox.pack(side="left", padx="4")
        self.right_stick_mouse_checkbox.configure(
            command=self.activate_Right_stick_mouse
        )
        self.software_input_f.grid(column="0", columnspan="3", pady="4", row="1", sticky="w")
        self.software_lf.columnconfigure(1, weight=1)
        self.software_lf.configure(text="Software")
        self.software_lf.grid(column="0", padx="5", pady="3", row="0", sticky="nsew")

        self.hardware_lf = ttk.Labelframe(self.manual_control_f)
        # 使うコントローラー(「番号: 名前」で同じ種類のコントローラーを区別する。
        # Autoはプロファイルに名前が一致する最初のコントローラー)。プロファイルは名前から自動で選ぶ
        self.controller_device_label = ttk.Label(self.hardware_lf)
        self.controller_device_label.configure(text="Device:")
        self.controller_device_label.grid(column="0", padx=(8, 4), pady="4", row="0", sticky="w")
        self.controller_device = tk.StringVar(value=AUTO_DEVICE)
        self.controller_device_cb = ttk.Combobox(self.hardware_lf)
        self.controller_device_cb.configure(
            state="readonly",
            textvariable=self.controller_device,
            values=[AUTO_DEVICE],
            width="14",
            postcommand=self.refreshControllerDevices,
        )
        self.controller_device_cb.grid(column="1", padx="4", pady="4", row="0", sticky="ew")
        # 選択中のコントローラーのボタン割り当て(プロファイル)をGUIで設定する
        self.controller_setup_button = ttk.Button(self.hardware_lf)
        self.controller_setup_button.configure(text="Add Profile", command=self.openControllerSetup)
        self.controller_setup_button.grid(column="2", padx=(4, 8), pady="4", row="0", sticky="e")
        self.use_pro_controller_checkbox = ttk.Checkbutton(self.hardware_lf)
        self.is_use_Pro_Controller = tk.BooleanVar()  # modified
        self.use_pro_controller_checkbox.configure(
            text="Use Pro Controller", variable=self.is_use_Pro_Controller
        )
        self.use_pro_controller_checkbox.grid(column="0", columnspan="3", padx=(8, 4), pady="4", row="1", sticky="w")
        self.use_pro_controller_checkbox.configure(
            command=self.mode_change_Pro_Controller
        )
        self.hardware_lf.columnconfigure(1, weight=1)
        self.hardware_lf.configure(text="Hardware")
        self.hardware_lf.grid(column="1", padx="5", pady="3", row="0", sticky="nsew")
        # 手動操作(キーボード・マウス・Proコントローラー)の記録の開始・終了(記録中は文字が赤くなる)
        Theme.add_style_hook(lambda style: style.configure("Recording.TButton", foreground=Theme.color("danger")))
        self.record_buttons = []
        self.record_button_tooltips = []
        self._createRecordButton(self.manual_control_f)
        self.manual_control_f.pack()
        self.controller_nb.add(
            self.manual_control_f, padding="5", sticky="nsew", text="Manual Control"
        )

    def keyboardConsole(self) -> str:
        """
        キーボード操作で使うキーの対応(キーコンフィグ)のゲーム機。メイン画面のSoftware-Controllerのレイアウトで決まる
        """
        return KeyMap.console_of_layout(self.software_controller_layout.get())

    def activateKeyboard(self) -> None:
        """Keyboard のチェックを切り替えたとき(と起動時): キーボードでの操作を始める / やめる(ウィンドウが手前にある間だけ受け付ける)"""
        if self.is_use_keyboard.get():
            # enable Keyboard as controller
            if self.keyboard is None:
                self.keyboard = SwitchKeyboardController(self.keyPress, self.keyboardConsole())
                self.keyboard.listen()

            # bind focus
            # (Linuxでは、pynput 1.7.7 以降でクラッシュしなくなったので行う。Macでは上の理由で行わない)
            if platform.system() != "Darwin":
                self.root.bind("<FocusIn>", self.onFocusInController)
                self.root.bind("<FocusOut>", self.onFocusOutController)

        else:
            # stop listening to keyboard events
            if self.keyboard is not None:
                self.keyboard.stop()
                self.keyboard = None

            if platform.system() != "Darwin":
                self.root.bind("<FocusIn>", lambda _: None)
                self.root.bind("<FocusOut>", lambda _: None)

    def releaseAllInputs(self) -> None:
        """
        メニューの 操作 > すべての入力を離す: 押したまま・倒したままになっている入力を、すべて離す。
        画面上のコントローラーの固定(HOLD)、キーボードでの操作、そのほかの入力源(実行中のコマンドを含む)が対象。
        実行中のコマンドは、止めない(コマンドが次に入力を送ると、その入力は、また送られる)。
        コマンドの実行中は、動きに影響することがあるので、行ってよいかを確かめる
        """
        if self.isCommandRunning() and not tkmsg.askokcancel(
            "確認", RELEASE_ALL_WARNING, icon="warning", parent=self.root
        ):
            return
        # 画面上のコントローラー(固定している入力の表示も、戻す)
        for panel in (self.softcon_panel, getattr(self.controller, "panel", None)):
            if panel is not None:
                try:
                    panel.release_all()
                except Exception:
                    self._logger.exception("Failed to release the software controller")
        # キーボードでの操作
        if self.keyboard is not None:
            self.keyboard.releaseAll()
        # そのほかの入力源もまとめて離し、何も押していない状態を送る
        if not self.ser.isOpened():
            print("すべての入力を離しました(シリアルに接続していないので、機器へは送っていません)。")
            return
        self.ser.release_all(get_transport(self.serial_data_format_name.get()).end_row)
        print("すべての入力を離しました。")

    def watchTypingForKeyboard(self) -> None:
        """
        キーを受け取って動く部品(入力欄、タブの並び、コンボボックス、一覧など)にフォーカスがある間は、
        キーボードでの操作を止めるようにする(起動時に 1 回呼ぶ)。
        その部品を動かすためのキー(打った文字、タブや項目を切り替える矢印キー)を、ゲーム機に送らないため。
        対象は、このアプリのすべてのウィンドウ
        """
        self.root.bind_all("<FocusIn>", self._onFocusChangedForKeyboard, add="+")
        self.root.bind_all("<FocusOut>", self._onFocusChangedForKeyboard, add="+")

    @staticmethod
    def _isTypingWidget(widget: object) -> bool:
        """
        フォーカスがある間、キーボードでの操作を止める部品か(キーを受け取って、自分が動く部品):
        - 文字を打つ部品: 入力欄(読み取り専用でないもの)、数を入れる欄、書き込める Text
        - 矢印キーで動く部品: タブの並び(Notebook)、コンボボックス(選ぶだけのものを含む)、一覧(Treeview / Listbox)、
          つまみ(Scale)、スクロールバー、ラジオボタン、メニューのボタン
        ボタンとチェックボックス、書き込めない Text(出力画面)は、対象にしない(矢印キーでは動かないため)。
        使えない状態(disabled)の部品も、対象にしない
        """
        if not isinstance(widget, tk.Misc):
            return False
        try:
            widget_class = widget.winfo_class()
            if widget_class not in KEY_CONSUMING_CLASSES:
                return False
            state = str(widget.cget("state")) if widget_class in STATEFUL_CLASSES else "normal"
            if "disabled" in state:
                return False
            if widget_class in ("Entry", "TEntry"):
                return state != "readonly"
            if widget_class == "Text":
                return state == "normal"
            return True
        except tk.TclError:
            pass
        return False

    def _onFocusChangedForKeyboard(self, event: tk.Event) -> None:
        """
        フォーカスが移ったとき(入った知らせと、出た知らせの両方): 今フォーカスがある部品に合わせて、キーボードでの操作を止める / 元に戻す。
        知らせが来た部品ではなく、今フォーカスがある部品を見る
        (タブの中の部品から、Shift + Tab でタブの並びに戻ったときは、タブの並びに「入った」知らせが来ないため。
         また、中の部品に移ったときは、親の部品にも「入った」知らせが来るため)
        """
        try:
            focused = self.root.focus_get()
        except KeyError:
            # コンボボックスの一覧(開いている間、矢印キーで項目を選ぶ)。tkinter が部品として知らないので、エラーになる
            self.setKeyboardSuspended(True)
            return
        self.setKeyboardSuspended(self._isTypingWidget(focused))

    def setKeyboardSuspended(self, suspended: bool) -> None:
        """
        キーボードでの操作を、いったんやめる / 元に戻す(入力欄に、文字を打っている間など)。
        Keyboard のチェックは変えない。やめている間に押したキーは、ゲーム機に送らない
        """
        if suspended == SwitchKeyboardController.suspended:
            return
        if not suspended:
            SwitchKeyboardController.resume()
        elif self.keyboard is not None:
            self.keyboard.suspend()
        else:
            # 受け付けていない間(ウィンドウが手前にない間など)も、覚えておく
            SwitchKeyboardController.suspended = True

    def reloadKeyboard(self) -> None:
        """
        キーボード操作中なら、キーの対応(キーコンフィグ)を読み直す(キーコンフィグでOKを押したときに呼ぶ)
        """
        if self.keyboard is not None:
            self.keyboard.reloadKeyMap(self.keyboardConsole())

    def noticeKeyboardSetting(self) -> None:
        """
        MacでKeyboardのチェックを変更したとき: 次回の起動時に反映されることを知らせる
        """
        print("Macでは、Keyboard の設定は次回の起動時に反映されます。")

    def onFocusInController(self, event: tk.Event) -> None:
        """メインウィンドウが手前に来たとき: キーボードでの操作を受け付け始める"""
        # enable Keyboard as controller
        if event.widget == self.root and self.keyboard is None:
            self.keyboard = SwitchKeyboardController(self.keyPress, self.keyboardConsole())
            self.keyboard.listen()

    def onFocusOutController(self, event: tk.Event) -> None:
        """メインウィンドウからフォーカスが外れたとき: キーボードでの操作の受け付けをやめる"""
        # stop listening to keyboard events
        if event.widget == self.root and self.keyboard is not None:
            self.keyboard.stop()
            self.keyboard = None

    def createControllerWindow(self) -> None:
        """Controller ボタン: Controller Simulator のウィンドウを開く(すでに開いていれば手前に出す)"""
        if self.controller is not None:
            self.controller.focus_force()
            return

        # 前回選んだレイアウトで開く。ウィンドウ内のコンボボックスで切り替えられる
        window = ControllerWindow(
            self.root,
            self.ser,
            layout=self.settings.controller_layout.get(),
            on_layout_changed=self.settings.controller_layout.set,
            touch_image_source=self.getTouchscreenImage,
            on_keyboard=self.openSwitchKeyboard,
        )
        window.protocol("WM_DELETE_WINDOW", self.closingController)
        self.controller = window

    def openSwitchKeyboard(self) -> None:
        """
        Software-Controller / Controller Simulator の Keyboard ボタン、メニューバーの 操作 > Keyboard を開く:
        Keyboard ウィンドウ(Switch へのキーボード入力)を開く
        (すでに開いていれば手前に出す)
        """
        window = getattr(self, "switch_keyboard_window", None)
        if window is not None and window.isOpen():
            window.lift()
            return
        self.switch_keyboard_window = SwitchKeyboardWindow(self.root, self.ser)

    def openControllerColorSettings(self) -> None:
        """
        メニューバーの 設定 > コントローラーの色...: Software-Controller / Controller Simulator の本体の色を設定する
        """
        if self.controller_color_window is not None:
            self.controller_color_window.focus_force()
            return
        # メイン画面で使っているレイアウトの種類のタブを最初に表示する
        initial_type = getattr(COMPACT_LAYOUTS.get(self.software_controller_layout.get()), "COLOR_TYPE", None)
        window = ControllerColorWindow(self.root, self.applyControllerColors, initial_type=initial_type)
        window.protocol("WM_DELETE_WINDOW", self.closingControllerColorSettings)
        window.window.bind("<Destroy>", self._onControllerColorWindowDestroyed)
        self.controller_color_window = window

    def closingControllerColorSettings(self) -> None:
        """コントローラー設定のウィンドウを閉じる(ウィンドウの × ボタン)"""
        if self.controller_color_window is not None:
            self.controller_color_window.destroy()
            self.controller_color_window = None

    def _onControllerColorWindowDestroyed(self, event: tk.Event) -> None:
        """コントローラー設定のウィンドウが破棄されたとき: 開いていない状態に戻す"""
        # OK / Cancel で閉じた場合も、開いていない状態に戻す
        window = self.controller_color_window
        if window is not None and (window.window is None or event.widget is window.window):
            self.controller_color_window = None

    def applyControllerColors(self, colors_by_type: dict[str, dict[str, str]]) -> None:
        """
        コントローラー設定のOK: 本体の色を保存用の設定に入れ、表示中のコントローラーを作り直す
        colors_by_type: コントローラーの種類 -> 色(色の項目 -> "#RRGGBB")
        """
        for controller_type, colors in colors_by_type.items():
            ControllerColors.set_colors(controller_type, colors)
        self.settings.controller_colors = ControllerColors.settings_texts()
        self.setSoftwareControllerLayout()
        if self.controller is not None:
            self.controller.refresh()

    def activate_Left_stick_mouse(self) -> None:
        """LStick Mouse のチェックを切り替えたとき: プレビュー上のマウスでの左スティックの操作に反映する"""
        self.preview.ApplyLStickMouse()

    def activate_Right_stick_mouse(self) -> None:
        """RStick Mouse のチェックを切り替えたとき: プレビュー上のマウスでの右スティックの操作に反映する"""
        self.preview.ApplyRStickMouse()

    def refreshControllerDevices(self) -> None:
        """
        接続中のコントローラーを別スレッドで調べ直し、終わったらコンボボックスの選択肢を更新する
        (取得に1秒ほどかかるため、コンボボックスを開いたときは前回の一覧を表示し、次に開いたときに反映される)
        """
        if self.controller_devices_refreshing:
            return
        self.controller_devices_refreshing = True
        threading.Thread(target=self._listControllerDevices, name="ControllerList", daemon=True).start()

    def _listControllerDevices(self) -> None:
        """接続中のコントローラーの名前を調べ、結果をメインスレッドに渡す(別スレッドで呼ばれる)"""
        try:
            names, error = list_joystick_names(), None
        except Exception as e:
            names, error = [], e
        UiDispatcher.post(self._setControllerDevices, names, error)

    def _setControllerDevices(self, names: list[str], error: Exception | None) -> None:
        """
        調べ終わったコントローラーの一覧を、コンボボックスの選択肢に入れる(メインスレッドで呼ばれる)
        names: 接続中のコントローラーの名前(番号順)
        error: 調べるときに起きた例外(無ければ None)
        """
        # GUIの終了後はUiDispatcherが呼び出し元スレッドで実行するので、何もしない
        if not UiDispatcher.is_main_thread():
            return
        # 選択中のコントローラーが外れていても選択は残す(開始時に見つからなければエラーを表示する)
        self.controller_devices_refreshing = False
        if error is not None:
            self._logger.error(f"Failed to list controllers: {error}")
            print(f"接続中のコントローラーを取得できませんでした: {error}")
        self.controller_device_names = names
        self.controller_device_cb["values"] = [AUTO_DEVICE] + [device_label(i, n) for i, n in enumerate(names)]

    def openControllerSetup(self) -> None:
        """
        選択中のコントローラーの割り当てを設定するウィンドウを開く
        """
        if self.controller_setup is not None:
            self.controller_setup.focus()
            return
        profiles, errors = load_profiles()
        for error in errors:
            print(f"コントローラーのプロファイルを読み込めませんでした: {error}")
        device = self.controller_device.get()
        names = self.controller_device_names
        try:
            index, _, _ = select_device(names, profiles, device)
        except ControllerProfileError as e:
            tkmsg.showerror(
                "コントローラーの設定",
                f"{e}\nコントローラーを接続し、Controllerの一覧を開き直してからもう一度お試しください。",
            )
            self.refreshControllerDevices()
            return
        joystick_name = names[index]
        path, base, exists = profile_file_for(joystick_name, profiles)
        if exists and not tkmsg.askokcancel(
            "設定ファイルがあります",
            f"{joystick_name} の設定ファイル {os.path.basename(path)} が既にあります。\n"
            "設定を始めますか？(保存するときに、ファイルを更新するか確認します)",
        ):
            return
        self.controller_setup = ControllerSetupWindow(
            self.root,
            device_label(index, joystick_name),
            joystick_name,
            base,
            path,
            exists,
            on_close=self._onControllerSetupClosed,
        )

    def _onControllerSetupClosed(self) -> None:
        """コントローラーの割り当てを設定するウィンドウが閉じたとき: 開いていない状態に戻す"""
        self.controller_setup = None

    def start_ProController(self) -> None:
        """接続したコントローラーでの操作を、専用のスレッドで始める(前のスレッドが残っていれば、止めてから始める)"""
        # 前のスレッドが残っていれば止めてから起動する
        self.stop_ProController()
        profiles, errors = load_profiles()
        for error in errors:
            print(f"コントローラーのプロファイルを読み込めませんでした: {error}")
        procon = ProController(profiles, self.controller_device.get())
        self.procon = procon
        # 停止待ちがタイムアウトしてもアプリの終了を妨げないようにdaemonにする
        self.procon_thread = threading.Thread(
            target=self._run_ProController,
            args=(procon,),
            name="ProController",
            daemon=True,
        )
        self.procon_thread.start()

    def _run_ProController(self, procon: ProController) -> None:
        """
        コントローラーの入力を読み取り続ける(専用のスレッドの中身)
        停止を求められていないのに止まった場合(接続エラー・切断)は、メインスレッドに知らせる
        """
        procon.controller_loop(self.ser)
        # 接続エラーや切断で止まった場合は、GUIを無効の状態に戻す
        if not procon.stop_requested:
            UiDispatcher.post(self._onProControllerStopped, procon)

    def _onProControllerStopped(self, procon: ProController) -> None:
        """コントローラーでの操作が、エラーや切断で止まったとき: Use Pro Controller をオフに戻す"""
        # 既に停止・再起動されていれば何もしない
        if self.procon is procon:
            self.is_use_Pro_Controller.set(False)
            self.mode_change_Pro_Controller()

    def stop_ProController(self) -> None:
        """
        Proコントローラーのスレッドに停止を要求し、終了処理(入力の解放・操作記録の出力)が終わるまで待つ
        """
        if self.procon is not None:
            self.procon.stop()
        if self.procon_thread is not None and self.procon_thread.is_alive():
            self.procon_thread.join(PROCON_STOP_TIMEOUT)
            if self.procon_thread.is_alive():
                self._logger.warning("Pro Controller thread did not stop in time.")
        self.procon = None
        self.procon_thread = None

    def mode_change_Pro_Controller(self) -> None:
        """
        Use Pro Controller のチェックを切り替えたとき(とコマンドの開始時): コントローラーでの操作を始める / やめる
        操作中は、Controller Simulator を閉じ、Camera・Serial・Commands・Notification のタブと Start ボタンを使えなくする
        """
        if self.is_use_Pro_Controller.get():  # Proconでの操作を有効化する。
            try:
                self.closingController()
            except Exception:
                pass
            self.controller_device_cb["state"] = "disabled"
            self.controller_setup_button["state"] = "disabled"
            self.start_ProController()
            for tab in (self.camera_f, self.serial_f, self.commands_f, self.notification_f):
                self.controller_nb.tab(tab, state="disabled")
            self.start_top_button["state"] = "disabled"
            self.simplecon_top_button["state"] = "disabled"

        else:  # Proconでの操作を無効化する。
            self.stop_ProController()
            self.controller_device_cb["state"] = "readonly"
            self.controller_setup_button["state"] = "normal"
            for tab in (self.camera_f, self.serial_f, self.commands_f, self.notification_f):
                self.controller_nb.tab(tab, state="normal")
            self.start_top_button["state"] = "normal"
            self.simplecon_top_button["state"] = "normal"

    def _createRecordButton(self, parent: tk.Misc) -> None:
        """
        RecordボタンをManual Controlタブの右下に置く
        parent: ボタンを置く枠
        """
        button = ttk.Button(parent)
        button.configure(text="Record", width="10", command=self.toggleRecord)
        button.grid(column="0", columnspan="2", padx=(4, 13), pady="4", row="1", sticky="e")
        self.record_buttons.append(button)
        self.record_button_tooltips.append(
            ToolTip(
                button,
                "手動操作(キーボード・画面上のコントローラー・マウス・タッチ・procon)の記録を開始・終了します。"
                "記録中は文字が赤くなり、終了時に自動化スクリプトを出力します。"
                "コマンド実行中は記録できず、記録中はコマンドを開始できません",
            )
        )

    def configureRecordButtons(self, **options: object) -> None:
        """
        すべての Record ボタンの設定を変える
        options: ボタンの configure に渡す設定(state、style など)
        """
        for button in self.record_buttons:
            button.configure(**options)

    def toggleRecord(self) -> None:
        """
        Recordボタン: 手動操作の記録の開始・終了を切り替える
        """
        if self.record_service.is_recording():
            self.stopRecord()
            return
        try:
            recorder = self.record_service.start()
        except RecordError as e:
            print(e)
            return
        print(f"操作記録を開始しました。生ログ: {recorder.raw_log_path}")
        self.configureRecordButtons(style="Recording.TButton")

    def stopRecord(self) -> None:
        """
        記録を終了し、自動化スクリプトを出力する
        """
        result = self.record_service.stop()
        self.configureRecordButtons(style="TButton")
        if not result.recorded:
            return
        if result.error is not None:
            print(f"操作記録の変換に失敗しました。生ログ: {result.raw_log_path}")
        elif result.path is None:
            print("操作が記録されなかったため、自動化スクリプトは出力しませんでした。")
        else:
            print(f"操作記録を出力しました: {result.path}")

    def isRecording(self) -> bool:
        """
        操作記録中ならメッセージを表示してTrueを返す(記録中はコマンドを開始できない)
        """
        if self.ser.recording:
            print("操作記録中はコマンドを開始できません。Recordボタンを押して記録を終了してください。")
            return True
        return False

    def closingController(self) -> None:
        """Controller Simulator のウィンドウを閉じる(ウィンドウの × ボタン。開いていないときは、何もしない)"""
        if self.controller is None:
            return
        self.controller.destroy()
        self.controller = None

    def setSoftwareControllerLayout(self, *event: tk.Event) -> None:
        """
        メイン画面のSoftware-Controllerを、選択中のレイアウトで作り直す
        (レイアウトを選んだとき、起動時、コントローラーの色を変えたとき)
        """
        name = self.software_controller_layout.get()
        # 以前のレイアウト名で保存されている場合は、今の名前に読み替える
        name = COMPACT_LAYOUT_ALIASES.get(name, name)
        if name not in COMPACT_LAYOUTS:
            name = DEFAULT_COMPACT_LAYOUT
        if name != self.software_controller_layout.get():
            self.software_controller_layout.set(name)
        self.software_controller_layout_cb.selection_clear()
        if self.softcon_panel is not None:
            # 入力中・固定中の入力を離してから作り直す
            self.softcon_panel.destroy()
            self.softcon_panel = None
        # タッチ画面ありのレイアウトには、タッチスクリーンの範囲のカメラ画像を表示する
        self.softcon_panel = COMPACT_LAYOUTS[name](
            self.root,
            self.ser,
            parent=self.softcon_frame,
            touch_image_source=self.getTouchscreenImage,
            key=self.keys_software_controller,
            on_keyboard=self.openSwitchKeyboard,
        )
        if self.keyboard is not None:
            # キーボード操作中にレイアウトを変えた場合は、そのゲーム機のキーの対応に切り替える
            self.keyboard.reloadKeyMap(self.keyboardConsole())

    def holdForceEnd(self) -> None:
        """
        hold状態を強制的に解除する
        (holdを示す色も変える)
        """
        if self.softcon_panel is not None:
            self.softcon_panel.set_hold_mode(False)
