#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Camera タブ: カメラの選択と取り込み、プレビューの大きさ・明るさ
"""
from __future__ import annotations

import tkinter as tk
import re
import platform
import tkinter.ttk as ttk
import tkinter.messagebox as tkmsg
from services import device_service, geometry
from Camera import (
    parse_capture_size,
    CAPTURE_SIZE_LIST,
    DEFAULT_CAPTURE_SIZE,
    DEFAULT_SHOW_SIZE,
    SHOW_SIZE_LIST,
    EXTRA_SOURCES,
)
from Commands.CommandBase import Command
from ui.constants import (
    PREVIEW_MIN_HEIGHT,
    MINI_PREVIEW_MIN_HEIGHT,
    PREVIEW_GAIN_RANGE,
    PREVIEW_GAMMA_RANGE,
    DEFAULT_PREVIEW_GAIN,
    DEFAULT_PREVIEW_GAMMA,
    DEFAULT_AREA_SIZE,
)


class CameraPanelMixin:
    """
    Camera タブ: カメラの選択と取り込み、プレビューの大きさ・明るさ
    (PokeControllerApp に取り込んで使う。部品や設定は self の属性として、ほかのファイルと共有する)
    """

    def _buildCameraTab(self) -> None:
        """
        Camera タブの部品を作る(起動時に1回だけ呼ぶ)
        """
        self.camera_f = ttk.Frame(self.controller_nb)
        # Device(カメラの選択) / Capture(取り込み) / Display(表示) の3つの枠に分ける
        self.camera_f.columnconfigure(0, weight=1)
        self.camera_settings_lf = ttk.Labelframe(self.camera_f)
        # Camera Nameのラベルは表示しない(枠の名前で分かるため。ツールチップ用に残す)
        self.camera_name_label = ttk.Label(self.camera_settings_lf)
        self.camera_name_cb = ttk.Combobox(self.camera_settings_lf)
        self.camera_name_fromDLL = tk.StringVar(value="")
        self.camera_name_cb.configure(
            state="normal", textvariable=self.camera_name_fromDLL, width="34"
        )
        self.camera_name_cb.grid(column="0", padx=(8, 4), pady="4", row="0", sticky="ew")
        self.camera_name_cb.bind("<<ComboboxSelected>>", self.set_cameraid, add="")
        # Camera IDは、カメラの名前を取得できない環境(IDを直接入力する)でのみ表示する
        self.camera_id_label = ttk.Label(self.camera_settings_lf)
        self.camera_id_label.configure(text="ID:")
        self.camera_id_label.grid(column="1", padx="4", pady="4", row="0", sticky="w")
        self.camera_id_entry = ttk.Entry(self.camera_settings_lf)
        self.camera_id = tk.IntVar(value="")
        self.camera_id_entry.configure(
            state="readonly", textvariable=self.camera_id, width="3"
        )
        self.camera_id_entry.grid(column="2", padx="4", pady="4", row="0", sticky="w")
        self.reload_button = ttk.Button(self.camera_settings_lf)
        self.reload_button.configure(text="Reload Camera")
        # 他のアプリケーションのウィンドウを、Deviceの候補に出すか(Windowsのみ)
        self.is_show_windows = tk.BooleanVar(value=False)
        self.show_windows_checkbox = ttk.Checkbutton(self.camera_settings_lf)
        self.show_windows_checkbox.configure(
            text="Windows", variable=self.is_show_windows, command=self.onShowWindowsToggled
        )
        if platform.system() == "Windows":
            self.show_windows_checkbox.grid(column="3", padx="4", pady="4", row="0", sticky="w")
        # カメラと音声デバイスの一覧を取得し直す(起動後に接続した機器を候補に出す)
        self.scan_camera_button = ttk.Button(self.camera_settings_lf)
        self.scan_camera_button.configure(text="Scan Device", command=self.scanCameraDevices)
        self.scan_camera_button.grid(column="4", padx="4", pady="4", row="0", sticky="e")
        self.reload_button.grid(column="5", padx=(4, 8), pady="4", row="0", sticky="e")
        self.reload_button.configure(command=self.openCamera)
        self.camera_settings_lf.columnconfigure(0, weight=1)
        self.camera_settings_lf.configure(text="Device")
        self.camera_settings_lf.grid(column="0", columnspan="2", padx="5", pady="3", row="0", sticky="ew")

        self.camera_capture_lf = ttk.Labelframe(self.camera_f)
        self.capture_size_label = ttk.Label(self.camera_capture_lf)
        self.capture_size_label.configure(text="Size:")
        self.capture_size_label.grid(column="0", padx=(8, 4), pady="4", row="0", sticky="w")
        self.capture_size_cb = ttk.Combobox(self.camera_capture_lf)
        self.capture_size = tk.StringVar(value="")
        self.capture_size_cb.configure(
            state="readonly",
            textvariable=self.capture_size,
            values=CAPTURE_SIZE_LIST,
            width="9",
        )
        # 取り込みサイズはReload Camera押下時に反映する(表示サイズの候補は選択時に切り替える)
        self.capture_size_cb.grid(column="1", padx="4", pady="4", row="0", sticky="w")
        self.capture_size_cb.bind(
            "<<ComboboxSelected>>", self.onCaptureSizeSelected, add=""
        )
        self.fps_label = ttk.Label(self.camera_capture_lf)
        self.fps_label.configure(text="FPS:")
        self.fps_label.grid(column="2", padx=(6, 4), pady="4", row="0", sticky="w")
        self.fps_cb = ttk.Combobox(self.camera_capture_lf)
        self.fps = tk.StringVar(value="")
        self.fps_cb.configure(
            justify="left",
            state="readonly",
            textvariable=self.fps,
            values="60 45 30 15 5",
        )
        self.fps_cb.configure(width="3")
        self.fps_cb.grid(column="3", padx="4", pady="4", row="0", sticky="w")
        self.fps_cb.bind("<<ComboboxSelected>>", self.applyFps, add="")
        # MJPG(圧縮形式)で取り込むか(切り替えるとカメラを開き直す)
        self.is_use_mjpg = tk.BooleanVar(value=False)
        self.mjpg_checkbox = ttk.Checkbutton(self.camera_capture_lf)
        self.mjpg_checkbox.configure(text="MJPG", variable=self.is_use_mjpg, command=self.onMjpgToggled)
        self.mjpg_checkbox.grid(column="4", padx="6", pady="4", row="0", sticky="w")
        self.camera_capture_lf.configure(text="Capture")
        self.camera_capture_lf.grid(column="0", padx="5", pady="3", row="1", sticky="ew")

        self.display_settings_lf = ttk.Labelframe(self.camera_f)
        self.show_size_label = ttk.Label(self.display_settings_lf)
        self.show_size_label.configure(text="Show Size:")
        self.show_size_label.grid(column="0", padx=(8, 4), pady="4", row="0", sticky="w")
        self.show_size_cb = ttk.Combobox(self.display_settings_lf)
        # 表示サイズ("幅x高さ")。コンボボックスには入力中の文字が入るので、表示用の変数(show_size_text)を分ける
        self.show_size = tk.StringVar(value="")
        self.show_size_text = tk.StringVar(value="")
        self.show_size.trace_add("write", lambda *args: self.show_size_text.set(self.show_size.get()))
        # 表示サイズの候補は取り込みサイズに応じてupdateShowSizeListで切り替える。
        # 候補にない大きさも、幅(または 幅x高さ)を入力してEnterで指定できる(高さは取り込み画像の縦横比で決まる)
        self.show_size_cb.configure(
            state="normal",
            textvariable=self.show_size_text,
            values=SHOW_SIZE_LIST[DEFAULT_CAPTURE_SIZE],
            width="9",
        )
        self.show_size_cb.grid(column="1", padx="4", pady="4", row="0", sticky="w")
        self.show_size_cb.bind("<<ComboboxSelected>>", self.applyWindowSize, add="")
        self.show_size_cb.bind("<Return>", self.applyWindowSize, add="")
        self.show_size_cb.bind("<FocusOut>", self.applyWindowSize, add="")
        # 取り込みサイズごとに最後に選択していた表示サイズ
        self.last_show_size = {}
        self.show_size_list_key = None
        self.show_realtime_checkbox = ttk.Checkbutton(self.display_settings_lf)
        self.is_show_realtime = tk.BooleanVar()  # modified
        self.show_realtime_checkbox.configure(
            text="Realtime", variable=self.is_show_realtime
        )
        self.show_realtime_checkbox.grid(column="2", padx=(6, 2), pady="4", row="0", sticky="w")
        self.show_value_checkbox = ttk.Checkbutton(self.display_settings_lf)
        self.is_show_value = tk.BooleanVar()  # modified
        self.show_value_checkbox.configure(
            text="Value", variable=self.is_show_value
        )
        self.show_value_checkbox.grid(column="3", padx="2", pady="4", row="0", sticky="w")
        self.show_value_checkbox.configure(command=self.mode_change_show_value)
        self.show_guide_checkbox = ttk.Checkbutton(self.display_settings_lf)
        self.is_show_guide = tk.BooleanVar()  # modified
        self.show_guide_checkbox.configure(
            text="Guide", variable=self.is_show_guide
        )
        self.show_guide_checkbox.grid(column="4", padx=(2, 6), pady="4", row="0", sticky="w")
        self.show_guide_checkbox.configure(command=self.mode_change_show_guide)
        self.display_settings_lf.configure(text="Display")
        self.display_settings_lf.grid(column="1", padx="5", pady="3", row="1", sticky="ew")

        # プレビューの明るさ(表示だけを変える。キャプチャー・スクリーンショット・コマンドの画像処理には影響しない)
        self.preview_brightness_lf = ttk.Labelframe(self.camera_f)
        self.preview_gain = tk.DoubleVar(value=DEFAULT_PREVIEW_GAIN)
        self.preview_gamma = tk.DoubleVar(value=DEFAULT_PREVIEW_GAMMA)
        self.preview_gain_label = ttk.Label(self.preview_brightness_lf, text="Gain:")
        self.preview_gain_label.grid(column="0", padx=(8, 4), pady="4", row="0", sticky="w")
        self.preview_gain_scale = ttk.Scale(
            self.preview_brightness_lf, from_=PREVIEW_GAIN_RANGE[0], to=PREVIEW_GAIN_RANGE[1], orient="horizontal",
            variable=self.preview_gain, command=self.applyPreviewBrightness,
        )
        self.preview_gain_scale.grid(column="1", padx="4", pady="4", row="0", sticky="ew")
        self.preview_gain_value = ttk.Label(self.preview_brightness_lf, width="5", anchor="e")
        self.preview_gain_value.grid(column="2", padx=(0, 8), pady="4", row="0", sticky="w")
        self.preview_gamma_label = ttk.Label(self.preview_brightness_lf, text="Gamma:")
        self.preview_gamma_label.grid(column="3", padx=(8, 4), pady="4", row="0", sticky="w")
        self.preview_gamma_scale = ttk.Scale(
            self.preview_brightness_lf, from_=PREVIEW_GAMMA_RANGE[0], to=PREVIEW_GAMMA_RANGE[1], orient="horizontal",
            variable=self.preview_gamma, command=self.applyPreviewBrightness,
        )
        self.preview_gamma_scale.grid(column="4", padx="4", pady="4", row="0", sticky="ew")
        self.preview_gamma_value = ttk.Label(self.preview_brightness_lf, width="4", anchor="e")
        self.preview_gamma_value.grid(column="5", padx=(0, 8), pady="4", row="0", sticky="w")
        self.preview_brightness_reset_button = ttk.Button(
            self.preview_brightness_lf, text="Reset", width="6", command=self.resetPreviewBrightness
        )
        self.preview_brightness_reset_button.grid(column="6", padx=(4, 8), pady="4", row="0", sticky="e")
        self.preview_brightness_lf.columnconfigure(1, weight=1)
        self.preview_brightness_lf.columnconfigure(4, weight=1)
        self.preview_brightness_lf.configure(text="Preview Brightness")
        self.preview_brightness_lf.grid(column="0", columnspan="2", padx="5", pady="3", row="2", sticky="ew")
        # self.camera_f.configure(height='200', width='200')    # removed
        self.camera_f.pack(side="top")
        self.controller_nb.add(self.camera_f, padding="5", sticky="nsew", text="Camera")

        # logging.debug(f'python version: {sys.version}')

    def openCamera(self) -> None:
        """
        Reload Camera ボタン(と起動時など): Camera タブの設定(MJPG・FPS・Capture Size)でカメラを開き直す
        """
        self.camera.use_mjpg = self.is_use_mjpg.get()
        # MJPGで開く場合に、カメラへ要求するフレームレート(CameraタブのFPS)
        self.camera.fps = int(self.fps.get())
        if self.capture_size.get() != "{0}x{1}".format(*self.camera.capture_size):
            # 選択中の取り込みサイズを反映してカメラを開き直す
            self.applyCaptureSize()
        else:
            self.camera.openCamera(self.camera_id.get(), self.capture_window)

    def assignCamera(self, event: tk.Event) -> None:
        """Camera ID の欄でキーを離したとき: 入力した番号のカメラの名前を、Device に表示する(Linux 以外)"""
        if platform.system() != "Linux":
            self.camera_name_fromDLL.set(self.camera_dic[self.camera_id.get()])

    def locateCameraCmbbox(self) -> bool | None:
        """
        カメラの一覧を取得して、Device の候補に入れる(起動時と Scan Device)
        Camera ID が一覧の範囲を超えている場合は 0 に戻す
        戻り値: カメラの名前を取得できない環境では False(それ以外は値を返さない。今の呼び出し元は戻り値を使わない)
        """
        listed = device_service.list_cameras()
        if listed is None:
            # カメラの名前を取得できない環境
            return False
        self.camera_dic, paths = listed
        if paths is not None:
            self.camera_paths = paths
        self.camera_name_cb["values"] = device_service.camera_labels(self.camera_dic)
        if platform.system() == "Windows":
            # カメラの後ろに、取り込めるウィンドウを並べる(一覧を開くたびに作り直す)
            self.updateWindowList()
            self.camera_name_cb.configure(postcommand=self.updateWindowList)
        dev_num = len(self.camera_dic)
        if self.camera_id.get() > dev_num - 1:
            print("Inappropriate camera ID! -> set to 0")
            self._logger.debug("Inappropriate camera ID! -> set to 0")
            self.camera_id.set(0)
            if dev_num == 0:
                print("No camera devices can be found.")
                self._logger.debug("No camera devices can be found.")

        #
        self.camera_id_entry.bind("<KeyRelease>", self.assignCamera)
        self.camera_name_cb.current(self.camera_id.get())

    def scanCameraDevices(self) -> None:
        """
        Scan Device: カメラの一覧を取得し直し、合わせて音声デバイスの一覧も更新する。
        選択中のカメラは、同じ機器が一覧にあればそのまま選び直す(番号が変わった場合は、新しい番号にする)。
        取り込み中のカメラは開き直さない(Reload Cameraで反映)
        """
        if platform.system() in ("Windows", "Darwin"):
            old_dic = self.camera_dic
            old_paths = self.camera_paths
            old_id = self.camera_id.get() if self.camera_dic is not None else None
            old_name = old_dic.get(old_id) if old_dic and not self.capture_window else None
            try:
                self.locateCameraCmbbox()
            except Exception as e:
                self.camera_dic, self.camera_paths = old_dic, old_paths
                print(f"カメラの一覧を取得できませんでした: {e}")
                self._logger.warning(f"Failed to scan camera devices: {e}")
            else:
                if old_dic is None:
                    # 起動時に一覧を作れなかった場合: 名前で選べるようにする
                    self.camera_name_cb.config(state="normal")
                names = [v for k, v in self.camera_dic.items() if k not in self.window_ids and v != "Disable"]
                if old_name is not None and old_name != self.camera_dic.get(self.camera_id.get()):
                    # 選んでいたカメラの番号が変わった(または無くなった)
                    new_ids = [k for k, v in self.camera_dic.items() if v == old_name and k not in self.window_ids]
                    if new_ids:
                        self.camera_id.set(new_ids[0])
                        self.camera_name_cb.current(list(self.camera_dic).index(new_ids[0]))
                        print(f"選択中のカメラの番号が No.{old_id} から No.{new_ids[0]} に変わりました。")
                    else:
                        print("選択中のカメラが一覧にありません。Device を選び直してください。")
                print(f"Scan Device: カメラ {len(names)} 台")
        # 音声デバイス(カメラと同じ機器の番号を付けるので、カメラの後に更新する)
        if self.audio is not None:
            if self.is_use_audio.get() and self.audio.is_running:
                # デバイスの一覧は取り込みを止めている間しか更新できないので、一度止めて取り込み直す
                self.stopAudio()
                self.refreshAudioOutputDevices()
                self.applyAudio()
            else:
                self.refreshAudioDevices()
                self.refreshAudioOutputDevices()
            print(f"Scan Device: 音声入力 {len(self.audio_device_labels)} 台")

    def updateWindowList(self) -> None:
        """
        カメラの一覧のうち、取り込めるウィンドウ(Window: ...)の候補を作り直す(カメラの候補は変えない)。
        Windowsのチェックが入っている場合のみ、候補に出す。
        選択中のウィンドウは、見つからない場合も候補に残す(ウィンドウが現れると取り込みを始める)
        """
        if self.camera_dic is None:
            return
        # 追加の映像ソース(起動時に登録されたもの)は、Windowsのチェックに関わらず候補に出す
        labels = device_service.extra_source_labels(self.is_show_windows.get(), self.capture_window)
        self.window_ids = device_service.replace_extra_sources(self.camera_dic, self.window_ids, labels)
        self.camera_name_cb["values"] = device_service.camera_labels(self.camera_dic)
        if self.capture_window:
            # ウィンドウの番号は一覧を作り直すと変わるので、選択中のウィンドウに合わせ直す
            window_id = next(k for k, v in self.window_ids.items() if v == self.capture_window)
            self.camera_id.set(window_id)
            self.camera_name_cb.current(window_id)

    def onShowWindowsToggled(self) -> None:
        """
        Windowsのチェックを切り替えたとき: Deviceの候補を作り直す。
        ウィンドウを取り込んでいる間にチェックを外した場合は、カメラ(No.0)に戻して開き直す
        """
        if self.camera_dic is None:
            return
        if not self.is_show_windows.get() and self.capture_window and self.capture_window not in EXTRA_SOURCES:
            self.capture_window = ""
            self.camera_id.set(0)
            self.updateWindowList()
            self.camera_name_cb.current(0)
            self.openCamera()
        else:
            self.updateWindowList()

    def set_cameraid(self, event: tk.Event | None = None) -> None:
        """
        Device を選んだとき: 選んだ名前に当たる番号を Camera ID に入れる(ウィンドウなどを選んだ場合は、その名前も覚える)。
        一覧にない名前の場合は、何も変えない
        """
        keys = [
            k
            for k, v in self.camera_dic.items()
            if "No." + str(k) + ": " + v == self.camera_name_cb.get()
        ]
        if not keys:
            return
        ret = keys[0]
        self.camera_id.set(ret)
        self.capture_window = self.window_ids.get(ret, "")

    def applyFps(self, event: tk.Event | None = None) -> None:
        """FPS を選んだとき: プレビューの更新の速さに反映する(MJPG で取り込んでいる場合は、カメラも開き直す)"""
        print("changed FPS to: " + self.fps.get() + " [fps]")
        self.preview.setFps(self.fps.get())
        if self.is_use_mjpg.get():
            # MJPGではカメラに要求するフレームレートにもFPSを使うので、カメラを開き直して反映する
            self.openCamera()

    def applyCaptureSize(self, event: tk.Event | None = None) -> None:
        """
        選択中の Capture Size が今の取り込みサイズと違う場合に、取り込みサイズを変えてカメラを開き直す
        (openCamera から呼ばれる。同じ場合は何もしない)
        """
        # 取り込みサイズを変更し、カメラ取り込みを再起動する
        if self.capture_size.get() == "{0}x{1}".format(*self.camera.capture_size):
            return
        self.camera.setCaptureSize(self.capture_size.get(), self.camera_id.get(), self.capture_window)

        # 表示サイズの候補は選択時に切り替え済みのため、プレビューに反映する
        self.applyShowSize()
        # Touch Screenタブの座標(取り込みサイズ上の値で表示している場合)を、新しい取り込みサイズの値にする
        if getattr(self, "preview", None) is not None:
            self.onTouchscreenCaptureSizeToggled()

    def onMjpgToggled(self) -> None:
        """
        MJPGのチェックを切り替えたとき: 画像認識に影響することを確認してから、カメラを開き直す。
        キャンセルした場合は、チェックを元に戻す。
        """
        enabled = self.is_use_mjpg.get()
        if enabled:
            change = "カメラの映像を MJPG(圧縮形式)で取り込みます。"
        else:
            change = "カメラの映像を MJPG(圧縮形式)で取り込むのをやめ、カメラの既定の形式に戻します。"
        ret = tkmsg.askokcancel(
            "確認",
            f"{change}\n\n"
            "圧縮の有無で画像がわずかに変わるため、画像認識に影響します。\n"
            "・テンプレート画像との照合(画像認識)の類似度が変わります\n"
            "・しきい値の調整や、テンプレート画像の作り直しが必要になる場合があります\n\n"
            "変更しますか？(OK を押すとカメラを開き直します)",
            icon="warning",
        )
        if not ret:
            self.is_use_mjpg.set(not enabled)
            return
        self.openCamera()

    def onCaptureSizeSelected(self, event: tk.Event | None = None) -> None:
        """
        Capture Sizeを選択したとき: 画像処理に影響することを確認してから、表示サイズの候補を切り替える。
        キャンセルした場合は、選択を元に戻す。
        """
        selected = self.capture_size.get()
        previous = self.show_size_list_key
        self.capture_size_cb.selection_clear()
        if previous is not None and selected != previous:
            ret = tkmsg.askokcancel(
                "確認",
                f"Capture Size を {previous} から {selected} に変更します。\n\n"
                "取り込む画像の大きさが変わるため、画像処理に影響します。\n"
                "・テンプレート画像との照合(画像認識)の結果が変わります\n"
                "・座標で指定している範囲(切り出し、目隠し等)がずれます\n\n"
                "変更しますか？(Reload Camera を押すと反映されます)",
                icon="warning",
            )
            if not ret:
                self.capture_size.set(previous)
                return
        self.updateShowSizeList()

    def updateShowSizeList(self, event: tk.Event | None = None) -> None:
        """
        Capture Sizeで選択中の取り込みサイズに応じて表示サイズの候補を切り替える。

        現在の表示サイズが候補に無い場合は、その取り込みサイズで最後に選択していた表示サイズ
        (無ければ既定値)に変更する。プレビューへの反映はReload Camera押下時に行う。
        """
        capture_size = self.capture_size.get()
        if self.show_size_list_key is not None:
            self.last_show_size[self.show_size_list_key] = self.show_size.get()
        self.show_size_list_key = capture_size

        self.show_size_cb["values"] = SHOW_SIZE_LIST[capture_size]
        if not self._isValidShowSize(self.show_size.get()):
            # 縦横比が取り込みサイズと合わない場合など
            self.show_size.set(
                self.last_show_size.get(capture_size, DEFAULT_SHOW_SIZE[capture_size])
            )

    def fitWindowSize(self, reset: bool = True) -> None:
        """
        ウィンドウの最小の大きさを、各領域の最小の大きさに合わせる(ウィンドウの大きさは変えない)
        中身が変わったときに呼ぶ。プレビューと出力画面の大きさも、領域に合わせ直す
        reset: 今は使っていない(以前の呼び出し方との互換のために残している)
        """
        if not getattr(self, "window_ready", False):
            # 初期化中(メニューバーを付ける前)は行わない
            return
        self._updatePaneMinSizes()
        self._schedulePreviewFit()
        self._scheduleOutputFit()

    def applyShowSize(self) -> None:
        """プレビューを、Main Panel に収まる大きさにし直す(取り込みサイズを変えた後に呼ぶ)"""
        # 取り込みサイズ(縦横比)が変わった場合などに、プレビューを Main Panel に収まる大きさにし直す
        self._schedulePreviewFit()

    ############### プレビューの大きさ ###############
    def _previewAspect(self) -> float:
        """
        プレビューの縦横比(幅/高さ)。取り込みサイズ(Capture Size)と同じ
        """
        width, height = parse_capture_size(self.capture_size.get())
        return width / height

    def previewMinHeight(self) -> int:
        """
        プレビューの高さの下限(ミニ画面では MINI_PREVIEW_MIN_HEIGHT、通常の画面では PREVIEW_MIN_HEIGHT)
        """
        return MINI_PREVIEW_MIN_HEIGHT if self.is_mini else PREVIEW_MIN_HEIGHT

    def previewSizeForHeight(self, height: float) -> tuple[int, int]:
        """
        高さから、取り込み画像の縦横比を保ったプレビューの大きさ(幅, 高さ)を求める(高さの下限は previewMinHeight)
        """
        return geometry.size_for_height(height, self._previewAspect(), self.previewMinHeight())

    def _isValidShowSize(self, text: object) -> bool:
        """
        "幅x高さ" が、今の取り込み画像の縦横比と合っていて、高さが下限以上か
        """
        return geometry.is_valid_size_text(text, self._previewAspect(), self.previewMinHeight())

    def setPreviewSize(self, width: int, height: int, fit: bool = True) -> None:
        """
        プレビューの大きさを変え、Show Size の値を合わせる。
        タッチスクリーンの範囲(プレビュー上の座標)も、同じ割合で大きさを変える
        fit: 今は使っていない(以前の呼び出し方との互換のために残している)
        """
        old_size = (self.preview.show_width, self.preview.show_height)
        self.show_size.set(f"{width}x{height}")
        self.preview.setShowsize(height, width)
        if old_size != (width, height):
            self._scaleTouchscreenArea(width, height)

    def resetShowSize(self) -> None:
        """
        メニュー > 画面のリセット: 初めて起動したときの配置に戻す
        (通常の画面・パネルは右・Widget Mode は ALL (default)・Output#1 と #2 の比率(Size)は初めの値。
         プレビューは取り込みサイズの標準の大きさ、仕切り線は中身に合わせた位置、ウィンドウは中身に合わせた大きさ)
        仕切り線の位置は、通常の画面・パネルが右の分だけ戻す
        """
        if self.is_mini:
            self.setMiniMode(False)
        self.panel_position = self.mini_panel_position = "right"
        self.right_frame_widget_mode.set("ALL (default)")
        self.mini_widget_mode.set("ALL (default)")
        self.area_size.set(DEFAULT_AREA_SIZE)
        self.replace_right_frame_widget()
        self.updateShowSizeList()
        _, height = map(int, DEFAULT_SHOW_SIZE[self.capture_size.get()].split("x"))
        self.preview_target = None
        self.setPreviewSize(*self.previewSizeForHeight(height))
        self.pane_ratios.pop(self._paneKey(), None)
        self.buildPanes()
        self._fitWindowToContent()

    def applyWindowSize(self, event: tk.Event | None = None) -> None:
        """
        Show Size: 候補から選んだ、または入力した大きさにする。
        入力は 幅(例: 1000) または 幅x高さ。高さは取り込み画像の縦横比で決める(高さの下限は PREVIEW_MIN_HEIGHT、
        上限はウィンドウが画面に収まる大きさ)
        """
        text = self.show_size_text.get()
        current = (self.preview.show_width, self.preview.show_height)
        if text == "{0}x{1}".format(*current):
            return
        if self.is_mini:
            # ミニ画面では Show Size の欄は表示しない(プレビューの大きさは、ウィンドウの枠のドラッグで変える)
            self.show_size_text.set(self.show_size.get())
            return
        match = re.fullmatch(r"\s*(\d+)\s*(?:[xX×*]\s*\d+\s*)?", text)
        if match is None or int(match.group(1)) <= 0:
            print("Show Size: 幅(例: 1000)または 幅x高さ(例: 1000x563)を入力してください。")
            self.show_size_text.set(self.show_size.get())
            return
        width, height = self.previewSizeForHeight(int(match.group(1)) / self._previewAspect())
        self.show_size_cb.selection_clear()
        if (width, height) == current:
            self.show_size_text.set(self.show_size.get())
            return
        # その大きさのプレビューが入るように、ウィンドウの大きさを変える(仕切り線の位置の比率は保つ)
        self.resizeWindowForPreview(width, height)

    def _previewBrightnessValues(self) -> tuple[int, float]:
        """
        プレビューの明るさの設定(ゲイン(%: 5% 刻み), ガンマ(0.05 刻み))
        """
        try:
            gain = int(round(float(self.preview_gain.get()) / 5.0) * 5)
            gamma = round(round(float(self.preview_gamma.get()) * 20.0) / 20.0, 2)
        except (tk.TclError, ValueError):
            gain, gamma = DEFAULT_PREVIEW_GAIN, DEFAULT_PREVIEW_GAMMA
        gain = min(max(gain, PREVIEW_GAIN_RANGE[0]), PREVIEW_GAIN_RANGE[1])
        gamma = min(max(gamma, PREVIEW_GAMMA_RANGE[0]), PREVIEW_GAMMA_RANGE[1])
        return gain, gamma

    def applyPreviewBrightness(self, *event: str) -> None:
        """
        Camera タブの Preview Brightness: プレビューとタッチスクリーンの表示の明るさを変える(表示だけ)
        event: 使わない(スライダーを動かしたときは、その値が文字で渡される。値は変数から読み直す)
        """
        gain, gamma = self._previewBrightnessValues()
        self.preview_gain_value.configure(text=f"{gain}%")
        self.preview_gamma_value.configure(text=f"{gamma:.2f}")
        self.camera.setDisplayAdjust(gain, gamma)
        if self.softcon_panel is not None and hasattr(self.softcon_panel, "refresh_touch_image"):
            self.softcon_panel.refresh_touch_image()

    def resetPreviewBrightness(self) -> None:
        """Preview Brightness の Reset ボタン: ゲインとガンマを初期値に戻す"""
        self.preview_gain.set(DEFAULT_PREVIEW_GAIN)
        self.preview_gamma.set(DEFAULT_PREVIEW_GAMMA)
        self.applyPreviewBrightness()

    def _setRawDisplay(self, raw: bool) -> None:
        """
        raw: プレビューとタッチスクリーンの表示を、明るさを変える前の画像にする(スクリーンショットの保存中)
        """
        self.preview.setShowRawDisplay(raw)
        if self.softcon_panel is not None and hasattr(self.softcon_panel, "refresh_touch_image"):
            self.softcon_panel.refresh_touch_image()

    def mode_change_show_value(self) -> None:
        """Value のチェックを切り替えたとき(と起動時): 画像認識の類似度を出力するかを Command に反映する"""
        Command.isSimilarity = self.is_show_value.get()

    def mode_change_show_guide(self) -> None:
        """Guide のチェックを切り替えたとき(と起動時): 画像認識の枠をプレビューに表示するかを Command に反映する"""
        Command.isGuide = self.is_show_guide.get()
