#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
各部品のツールチップ
"""
from __future__ import annotations

import platform
from ui.tooltip import ToolTip


class ToolTipsMixin:
    """
    各部品のツールチップ
    (PokeControllerApp に取り込んで使う。部品や設定は self の属性として、ほかのファイルと共有する)
    """

    def _buildToolTips(self) -> None:
        """
        各部品にツールチップを付ける(起動時に1回だけ呼ぶ)
        """
        # ToolTip設定
        self.start_top_button_tooltip = ToolTip(
            self.start_top_button, "自動化スクリプトを実行します"
        )
        self.simplecon_top_button_tooltip = ToolTip(
            self.simplecon_top_button, "switch用ソフトウェアコントローラを起動します"
        )
        self.clear_top_button_tooltip = ToolTip(
            self.clear_top_button, "ログ画面(output(#1)/output(#2))をクリアします"
        )
        self.screenshot_button_tooltip = ToolTip(
            self.screenshot_button,
            "アプリケーションのウィンドウ全体のスクリーンショットを、Capturesフォルダに保存します",
        )
        self.capture_button_tooltip = ToolTip(
            self.capture_button, "ゲーム画面のスクリーンショットを取得します"
        )
        self.mini_button_tooltip = ToolTip(
            self.mini_button,
            "ミニ画面と通常の画面を切り替えます。ミニ画面はプレビューを最小にし、"
            "コマンドの選択・実行と右側のパネルだけを縦に並べた、幅の狭い画面です",
        )
        self.side_panel_button_tooltip = ToolTip(
            self.side_panel_button,
            "右側のパネル(Output・Software-Controller)の位置を、押すたびに "
            "右(▶) → 下(▼) → 表示しない(✕) の順に切り替えます。通常の画面とミニ画面で、別々に覚えます",
        )
        self.open_capture_button_tooltip = ToolTip(
            self.open_capture_button,
            "スクリーンショット画像を保存するディレクトリを開きます",
        )
        # self.line_button_tooltip = ToolTip(self.line_button, "現在のゲーム画像をLineに通知します")
        self.discord_button_tooltip = ToolTip(
            self.discord_button, "現在のゲーム画像をDiscordに通知します"
        )
        self.camera_id_label_tooltip = ToolTip(
            self.camera_id_label, "使用するキャプチャデバイスのIDを設定します"
        )
        self.camera_id_entry_tooltip = ToolTip(
            self.camera_id_entry, "使用するキャプチャデバイスのID"
        )
        self.reload_button_tooltip = ToolTip(
            self.reload_button,
            "設定したキャプチャデバイス・取り込みサイズで接続を確立し、画像読み込みを開始します",
        )
        self.fps_label_tooltip = ToolTip(self.fps_label, "FPSを設定します(即時反映)")
        self.fps_cb_tooltip = ToolTip(self.fps_cb, "設定されているFPS")
        self.show_size_label_tooltip = ToolTip(
            self.show_size_label, "表示する画像のサイズを設定します(即時反映)"
        )
        self.show_size_cb_tooltip = ToolTip(
            self.show_size_cb,
            "プレビューの大きさ。候補から選ぶか、幅(例: 1000)を入力してEnterを押します"
            "(高さは取り込み画像の縦横比で決まります)。ウィンドウの枠をドラッグしても変えられます",
        )
        self.camera_name_label_tooltip = ToolTip(
            self.camera_name_label, "使用するキャプチャデバイスを設定します"
        )
        self.camera_name_cb_tooltip = ToolTip(
            self.camera_name_cb, "設定するキャプチャデバイス"
        )
        self.touch_screen_capture_size_checkbox_tooltip = ToolTip(
            self.touch_screen_capture_size_checkbox,
            "チェックを入れると、座標を取り込みサイズ(Capture Size)上の値で表示・入力します。"
            "Show Size(プレビューの大きさ)を変えても値は変わりません。"
            "チェックを外すと、Main Panel(Show Size)上の値に変換して表示します(範囲そのものは変わりません)",
        )
        self.scan_camera_button_tooltip = ToolTip(
            self.scan_camera_button,
            "カメラと音声デバイスの一覧を取得し直します。起動後に接続した機器を候補に出すときに押します。"
            "(取り込み中のカメラはそのまま。音声を取り込み中の場合は、一度止めて取り込み直します)",
        )
        self.show_windows_checkbox_tooltip = ToolTip(
            self.show_windows_checkbox,
            "チェックを入れると、他のアプリケーションのウィンドウ(Window: で始まる候補)をDeviceの候補に出します。"
            "選ぶと、そのウィンドウの画面をカメラの代わりに取り込みます(Reload Cameraで反映)。"
            "キャプチャーボードのビューアーの画面を、OBSの仮想カメラなしで取り込めます",
        )
        self.capture_size_label_tooltip = ToolTip(
            self.capture_size_label,
            "キャプチャデバイスからの取り込みサイズを設定します(Reload Cameraで反映)",
        )
        self.mjpg_checkbox_tooltip = ToolTip(
            self.mjpg_checkbox,
            "カメラの映像をMJPG(圧縮形式)で取り込みます。切り替えるとカメラを開き直します。"
            "非圧縮ではフレームレートが下がる機器で、フレームレートを上げられます。"
            "圧縮による画質の劣化が入るため、画像認識の結果に影響する場合があります",
        )
        self.capture_size_cb_tooltip = ToolTip(
            self.capture_size_cb, "設定されている取り込みサイズ"
        )
        self.show_realtime_checkbox_tooltip = ToolTip(
            self.show_realtime_checkbox,
            "画像をリアルタイムで更新する機能を有効化します\n(注意)本機能を有効化しないと画像は静止画のままとなります",
        )
        self.show_value_checkbox_tooltip = ToolTip(
            self.show_value_checkbox,
            "テンプレートマッチングの類似度をshow_valueの値によらず強制的に出力します。",
        )
        self.show_guide_checkbox_tooltip = ToolTip(
            self.show_guide_checkbox,
            "ガイド表示を有効化します\n自動化スクリプト次第で本チェックボックスは無効化される場合があります",
        )
        self.preview_gain_scale_tooltip = ToolTip(
            self.preview_gain_scale,
            "プレビュー(とタッチスクリーンの表示)の明るさを、色の値を何倍かにして変えます(100%で元のまま)\n"
            "表示だけを変えます。キャプチャー・スクリーンショット・コマンドの画像処理には影響しません",
        )
        self.preview_gamma_scale_tooltip = ToolTip(
            self.preview_gamma_scale,
            "プレビュー(とタッチスクリーンの表示)の暗い部分を明るくします(1.00で元のまま。大きいほど明るい)\n"
            "表示だけを変えます。キャプチャー・スクリーンショット・コマンドの画像処理には影響しません",
        )
        portheader = "COM" if platform.system() in ["Windows", "Darwin"] else ""
        self.com_port_label_tooltip = ToolTip(
            self.com_port_label,
            f"{portheader}ポート番号を設定します(デバイスマネージャーで確認可能です)",
        )
        self.com_port_entry_tooltip = ToolTip(
            self.com_port_entry, f"設定する{portheader}ポート番号"
        )
        self.baud_rate_label_tooltip = ToolTip(
            self.baud_rate_label, "ボーレートを設定します(switch:9600, GC:4800)"
        )
        self.baud_rate_cb_tooltip = ToolTip(self.baud_rate_cb, "設定するボーレート")
        self.reload_com_port_button_tooltip = ToolTip(
            self.reload_com_port_button,
            "設定したCOMポート番号とボーレートの情報に基づいてUSBシリアルとの接続を確立します",
        )
        self.disconnect_com_port_button_tooltip = ToolTip(
            self.disconnect_com_port_button, "USBシリアルとの接続を解除します"
        )
        self.serial_device_name_label_tooltip = ToolTip(
            self.serial_device_name_label, "使用するシリアルデバイスを設定します"
        )
        self.serial_device_name_cb_tooltip = ToolTip(
            self.serial_device_name_cb, "設定するシリアルデバイス名"
        )
        self.scan_device_button_tooltip = ToolTip(
            self.scan_device_button, "シリアルデバイスをスキャンします"
        )
        self.show_serial_checkbox_tooltip = ToolTip(
            self.show_serial_checkbox, "シリアル値を Output に出力する機能を有効化します(右側のパネルの Serial タブには、チェックに関係なく表示)"
        )
        self.simplecon_button_tooltip = ToolTip(
            self.simplecon_button, "ソフトウェアコントローラのウィンドウを開きます"
        )
        self.use_keyboard_checkbox_tooltip = ToolTip(
            self.use_keyboard_checkbox, "キーボードで操作する機能を有効化します"
        )
        self.left_stick_mouse_checkbox_tooltip = ToolTip(
            self.left_stick_mouse_checkbox,
            "ゲーム画面上で左クリックを押下した後、その状態でマウスを動かすことで左stickを動かす機能を有効化します",
        )
        self.right_stick_mouse_checkbox_tooltip = ToolTip(
            self.right_stick_mouse_checkbox,
            "ゲーム画面上で右クリックを押下した後、その状態でマウスを動かすことで右stickを動かす機能を有効化します",
        )
        self.use_pro_controller_checkbox_tooltip = ToolTip(
            self.use_pro_controller_checkbox,
            "pcに接続したproconでswitchを操作する機能を有効化します",
        )
        self.software_controller_layout_cb_tooltip = ToolTip(
            self.software_controller_layout_cb,
            "メイン画面のSoftware-Controllerのレイアウト(Switch / 3DS / DS / GameCube)を選択します。3DS / DSはタッチスクリーンの有無を選べます",
        )
        self.controller_device_cb_tooltip = ToolTip(
            self.controller_device_cb,
            "Switchの操作に使う、PCに接続中のコントローラーを選択します(番号は接続順)。"
            "Autoはプロファイルに名前が一致する、番号が最も小さいコントローラーを使います。"
            "ボタンの割り当て(ControllerProfilesフォルダのプロファイル)はコントローラー名から自動で選びます",
        )
        self.controller_setup_button_tooltip = ToolTip(
            self.controller_setup_button,
            "選択中のコントローラーのボタン割り当てを設定し、ControllerProfilesフォルダに保存します",
        )
        self.py_tv_tooltip = ToolTip(
            self.py_tv, "実行するスクリプト(python)を選択します。Tagsの見出しをクリックするとフィルタを設定できます"
        )
        self.mcu_tv_tooltip = ToolTip(
            self.mcu_tv, "実行するスクリプト(mcu)を選択します。Tagsの見出しをクリックするとフィルタを設定できます"
        )
        self.open_command_dir_button_tooltip = ToolTip(
            self.open_command_dir_button,
            "スクリプト(.py)を保存するディレクトリを開きます",
        )
        self.edit_tags_button_tooltip = ToolTip(
            self.edit_tags_button,
            "タグの編集画面を開きます(コマンドのファイルの TAGS を書き換えます)",
        )
        self.reload_command_button_tooltip = ToolTip(
            self.reload_command_button, "自動化スクリプトを再度読み込みます"
        )
        self.start_button_tooltip = ToolTip(
            self.start_button, "自動化スクリプトを実行します"
        )
        self.pause_button_tooltip = ToolTip(
            self.pause_button, "自動化スクリプトを一時停止します"
        )
        self.win_notification_start_checkbox_tooltip = ToolTip(
            self.win_notification_start_checkbox,
            "自動化スクリプト実行開始時に通知をします",
        )
        self.win_notification_end_checkbox_tooltip = ToolTip(
            self.win_notification_end_checkbox,
            "自動化スクリプト実行終了時に通知をします",
        )
        self.send_win_button_tooltip = ToolTip(
            self.send_win_button, "通知機能でテストメッセージを送信します"
        )
        self.line_notification_start_checkbox_tooltip = ToolTip(
            self.line_notification_start_checkbox,
            "自動化スクリプト実行開始時にLineで通知をします",
        )
        self.line_notification_end_checkbox_tooltip = ToolTip(
            self.line_notification_end_checkbox,
            "自動化スクリプト実行終了時にLineで通知をします",
        )
        self.send_line_button_tooltip = ToolTip(
            self.send_line_button, "Lineでテストメッセージを送信します"
        )
        self.discord_notification_start_checkbox_tooltip = ToolTip(
            self.discord_notification_start_checkbox,
            "自動化スクリプト実行開始時にDiscordで通知をします",
        )
        self.discord_notification_end_checkbox_tooltip = ToolTip(
            self.discord_notification_end_checkbox,
            "自動化スクリプト実行終了時にDiscordで通知をします",
        )
        self.send_discord_button_tooltip = ToolTip(
            self.send_discord_button, "Discordでテストメッセージを送信します"
        )
        self.area_size_scale_tooltip = ToolTip(
            self.area_size_scale, "output(#1)(上側)とoutput(#2)(下側)の比率を調整します(間の仕切り線のドラッグでも調整できます)"
        )
        self.stdout_destination_1_rb_tooltip = ToolTip(
            self.stdout_destination_1_rb, "標準出力先にoutput(#1)(上側)を設定します"
        )
        self.stdout_destination_2_rb_tooltip = ToolTip(
            self.stdout_destination_2_rb, "標準出力先にoutput(#2)(下側)を設定します"
        )
        self.outputs_text_area_1_clear_button_tooltip = ToolTip(
            self.outputs_text_area_1_clear_button, "output(#1)(上側)をクリアします"
        )
        self.outputs_text_area_2_clear_button_tooltip = ToolTip(
            self.outputs_text_area_2_clear_button, "output(#2)(下側)をクリアします"
        )
        self.select_right_frame_widget_cb_tooltip = ToolTip(
            self.select_right_frame_widget_cb,
            "右側に表示するウィジェットの種類を設定します",
        )
        self.pos_top_rb_tooltip = ToolTip(
            self.pos_top_rb, "Software-Controllerを上側に表示します"
        )
        self.pos_bottom_rb_tooltip = ToolTip(
            self.pos_bottom_rb, "Software-Controllerを下側に表示します"
        )
        self.pos_dialogue_top_rb_tooltip = ToolTip(
            self.pos_dialogue_top_rb,
            "ダイアログ起動時におけるOK/Cancelボタンを上側に表示します",
        )
        self.pos_dialogue_bottom_rb_tooltip = ToolTip(
            self.pos_dialogue_bottom_rb,
            "ダイアログ起動時におけるOK/Cancelボタンを下側に表示します",
        )
        self.pos_dialogue_both_rb_tooltip = ToolTip(
            self.pos_dialogue_both_rb,
            "ダイアログ起動時におけるOK/Cancelボタンを上下両方に表示します",
        )
