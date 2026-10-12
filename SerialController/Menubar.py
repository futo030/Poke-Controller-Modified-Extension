#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import cv2
import tkinter as tk
from tkinter import messagebox
import os
import platform
import configparser
import shutil

from KeyConfig import PokeKeycon
from LineNotify import Line_Notify
from DiscordNotify import Discord_Notify
from DiscordSettingWindow import DiscordSettingWindow
from PokeConShowInfo import PokeConQuestionDialogue, PokeConChangeLog, PokeConCopyright
from services import update_check
from PokeConDialogue import PokeConDialogue
from Profile import add_profile_priority, check_profile_name, create_profile_bat
import Profile
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING
import webbrowser
import Theme

if TYPE_CHECKING:
    from Window import PokeControllerApp


class PokeController_Menubar(tk.Menu):
    """
    メイン画面のメニューバー(ファイル / コマンド / 表示 / 接続 / 操作 / ツール / 設定 / ヘルプ)
    """

    def __init__(self, master: PokeControllerApp, **kw: object):
        """
        master: アプリ本体(メニューから呼ぶ処理と、画面の部品を持つ)
        kw: tk.Menu に渡す設定
        (作るときに、LINE と Discord の通知先の確認も行い、結果を出力画面に表示する)
        """
        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

        self.master = master
        # tk.Menu.__init__でself.masterがrootに上書きされるため、アプリ本体への参照を保持する
        self.app = master
        self.pokeconname = self.master.pokeconname
        self.pokeconversion = self.master.pokeconversion
        self.root = self.master.root
        self.ser = self.master.ser
        self.preview = self.master.preview
        self.show_size_cb = self.master.show_size_cb
        self.keyboard = self.master.keyboard
        self.settings = self.master.settings
        self.camera = self.master.camera
        self.profile = self.master.profile
        self.cur_command = self.master.cur_command

        self.key_config = None
        self.line = None
        self.discord = None
        self.discord_setting_window = None

        tk.Menu.__init__(self, self.root, **kw)
        # メニューバーの項目。それぞれ、Alt と一緒に () の中のキーを押すと開く
        self.menu_file = self._addMenu("ファイル", "F")
        self.menu_command = self._addMenu("コマンド", "C")
        self.menu_view = self._addMenu("表示", "V")
        self.menu_connect = self._addMenu("接続", "N")
        self.menu_operate = self._addMenu("操作", "O")
        self.menu_tool = self._addMenu("ツール", "T")
        self.menu_setting = self._addMenu("設定", "S")
        self.help = self._addMenu("ヘルプ", "H")

        self.AssignMenuCommand()
        self.LineTokenSetting()
        self.DiscordSetting()

    def _addMenu(self, label: str, key: str) -> tk.Menu:
        """
        メニューバーに項目を足す。label の後ろに (key) を付け、Alt + key で開けるようにする
        """
        menu = tk.Menu(self, tearoff="false")
        self.add(tk.CASCADE, menu=menu, label=f"{label}({key})", underline=len(label) + 1)
        return menu

    def _invoke(self, name: str) -> None:
        """
        メイン画面のボタン(app の属性 name)を押したのと同じ動作をする。
        ボタンが無い・押せない状態(disabled)のときは、何もしない
        """
        button = getattr(self.app, name, None)
        if button is not None:
            button.invoke()

    def AssignMenuCommand(self) -> None:
        """各メニューに項目を足し、選んだときに呼ぶ処理を結び付ける(作るときに1回だけ呼ぶ)"""
        self._logger.debug("Assigning menu command")
        app = self.app
        invoke = self._invoke

        # ---- ファイル
        menu = self.menu_file
        menu.add("command", label="プロファイルを追加...", command=self.GenerateNewBat)
        menu.add("separator")
        menu.add("command", label="Captures フォルダを開く", command=app.OpenCaptureDir)
        menu.add("command", label="コマンドのフォルダを開く", command=app.OpenCommandDir)
        menu.add("separator")
        menu.add("command", label="終了", command=self.exit)

        # ---- コマンド
        menu = self.menu_command
        menu.add("command", label="開始", accelerator="F6", command=lambda: app.StartCommandWithF6(None))
        menu.add("command", label="停止", accelerator="Esc", command=lambda: app.StopCommandWithEsc(None))
        menu.add("command", label="一時停止 / 再開", command=lambda: invoke("pause_button"))
        menu.add("separator")
        menu.add("command", label="再読み込み", accelerator="F5", command=lambda: app.ReloadCommandWithF5(None))
        menu.add("separator")
        menu.add("command", label="タグを編集...", command=app.openTagEditor)
        menu.add("separator")
        menu.add("command", label="実行リスト (連続実行)...", command=app.openRunLists)
        menu.add("command", label="開始と停止の予約...", command=app.openSchedule)

        # ---- 表示
        menu = self.menu_view
        menu.add("command", label="ミニ画面 / 通常の画面", command=app.toggleMiniMode)
        menu.add("command", label="右側のパネルの位置を切り替え", command=app.toggleSidePanel)
        menu.add("separator")
        # テーマ(配色)
        self.menu_theme = tk.Menu(menu, tearoff="false")
        self.theme_var = tk.StringVar(value=Theme.current())
        self.buildThemeMenu()
        menu.add("cascade", menu=self.menu_theme, label="テーマ")
        menu.add("separator")
        menu.add("command", label="画面のリセット", command=self.ResetWindowSize)

        # ---- 接続
        menu = self.menu_connect
        menu.add("command", label="シリアルを接続し直す", command=lambda: invoke("reload_com_port_button"))
        menu.add("command", label="シリアルを切断", command=lambda: invoke("disconnect_com_port_button"))
        menu.add("command", label="シリアルの機器の一覧を更新", command=lambda: invoke("scan_device_button"))
        menu.add("separator")
        menu.add("command", label="カメラを開き直す", command=lambda: invoke("reload_button"))
        menu.add("command", label="カメラの機器の一覧を更新", command=lambda: invoke("scan_camera_button"))

        # ---- 操作
        menu = self.menu_operate
        # Macでは、画面の表示中にキー入力の受け付けを開始・停止できないため、次回の起動時に反映する(Manual Control タブと同じ)
        keyboard_command = app.activateKeyboard if platform.system() != "Darwin" else app.noticeKeyboardSetting
        menu.add_checkbutton(label="キーボードで操作", variable=app.is_use_keyboard, command=keyboard_command)
        menu.add_checkbutton(
            label="コントローラーで操作", variable=app.is_use_Pro_Controller, command=app.mode_change_Pro_Controller
        )
        menu.add("separator")
        menu.add("command", label="Controller Simulator を開く", command=app.createControllerWindow)
        menu.add("command", label="Keyboard を開く", command=app.openSwitchKeyboard)
        menu.add("command", label="操作の記録を開始 / 停止", command=app.toggleRecord)
        menu.add("separator")
        menu.add("command", label="すべての入力を離す", command=app.releaseAllInputs)

        # ---- ツール
        menu = self.menu_tool
        menu.add("command", label="Capture (画像を保存)", command=lambda: invoke("capture_button"))
        menu.add("command", label="Screenshot (ウィンドウ全体を保存)", command=lambda: invoke("screenshot_button"))
        menu.add("command", label="Discord に画像を送信", command=lambda: invoke("discord_button"))
        menu.add("command", label="Discord にウィンドウ全体を送信", command=app.sendDiscordWindowImage)
        menu.add("separator")
        menu.add("command", label="Output をクリア", command=app.clearOutputs)
        menu.add("separator")
        menu.add("command", label="Discord の通知先を確認", command=self.DiscordSetting)
        menu.add("command", label="LINE の通知先を確認", command=self.LineTokenSetting)
        menu.add("command", label="Windows の通知をテスト", command=app.sendWinNotfication)
        menu.add("separator")
        menu.add("command", label="新しい自動化スクリプトをつくる", command=app.openScriptCreator)

        # ---- 設定
        menu = self.menu_setting
        menu.add("command", label="キーコンフィグ...", command=self.OpenKeyConfig)
        menu.add("command", label="コントローラーの色...", command=app.openControllerColorSettings)
        menu.add("command", label="コントローラーのボタンの割り当て...", command=app.openControllerSetup)
        menu.add("separator")
        menu.add("command", label="Discord の通知先...", command=self.DiscordSettingAssignment)
        menu.add("command", label="LINE の通知先...", command=self.LineTokenAssignment)

        # ---- ヘルプ
        menu = self.help
        # このツールの説明
        menu.add("command", label="Instruction Manual", command=app.openManual)
        menu.add("command", label="機能紹介", command=app.openIntroduction)
        menu.add("command", label="更新履歴", command=self.OpenChangeLog)
        menu.add("separator")
        # 外部のページ
        menu.add("command", label="Poke-Controller Guide", command=self.OpenGuide)
        menu.add("command", label="GitHub", command=self.OpenGithub)
        menu.add("command", label="Wiki", command=self.OpenWiki)
        menu.add("command", label="不具合の報告・要望 (Issues)", command=self.OpenIssues)
        menu.add("separator")
        # 問い合わせ・更新
        menu.add("command", label="質問テンプレート", command=self.output_question)
        menu.add("command", label="環境の診断", command=app.openDiagnostics)
        menu.add("command", label="アップデート確認", command=self.CheckUpdate)
        menu.add("separator")
        menu.add("command", label="LICENSE", command=self.OpenLicense)

    def LineTokenAssignment(self) -> None:
        """
        設定 > LINE の通知先...: トークンを入力するダイアログを開き、入力された場合は、
        プロファイルの line_token.ini に保存して、通知先を確認し直す
        """
        self.message_dialogue = tk.Toplevel()
        ret = PokeConDialogue(self.message_dialogue, "LINE の通知先", "Token").ret_value(list)
        self.message_dialogue = None
        # Cancel した場合は、リストではなく False が返る
        if ret:
            token_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "profiles", self.profile, "line_token.ini"
            )
            token_file = configparser.ConfigParser(comment_prefixes="#", allow_no_value=True)
            token_file["LINE"] = {"token": ret[0]}
            with open(token_path, "w", encoding="utf-8") as file:
                token_file.write(file)
            os.chmod(path=token_path, mode=0o777)
            self._logger.debug("Assign Line Token")
            self.LineTokenSetting()
        else:
            pass

    def DiscordSettingAssignment(self) -> None:
        """
        Discordの通知先の設定画面を開く(すでに開いている場合は前面に出す)
        """
        if self.discord_setting_window is not None and self.discord_setting_window.isOpen():
            self.discord_setting_window.lift()
            return
        setting_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "profiles", self.profile, "discord_token.ini"
        )
        self.discord_setting_window = DiscordSettingWindow(self.root, setting_path, on_saved=self.DiscordSetting)

    def LineTokenSetting(self) -> None:
        """ツール > LINE の通知先を確認(と起動時): 設定を読み込み、通知先の状態を出力画面に表示する(失敗しても何もしない)"""
        self._logger.debug("Show line API")
        if self.line is None:
            try:
                self.line = Line_Notify()
                print(self.line)
                self.line.getRateLimit()
            except Exception:
                pass
        self.line = None
        # LINE.send_text_n_image("CAPTURE")

    def DiscordSetting(self) -> None:
        """ツール > Discord の通知先を確認(と起動時、通知先を保存・削除した後): 設定を読み込み、通知先の状態を出力画面に表示する"""
        self._logger.debug("Show Discord Webhook API")
        if self.discord is None:
            self.discord = Discord_Notify()
        try:
            print(self.discord)
            self.discord.getRateLimit()
        except Exception:
            print("DISCORD API Check: N/A")
        self.discord = None

    def GenerateNewBat(self) -> None:
        """
        ファイル > プロファイルを追加...: 名前を入力するダイアログを開き、そのプロファイルで起動する bat ファイルを作る
        Copy Profile にチェックがある場合は、今のプロファイルのフォルダを、新しいプロファイルとしてコピーする
        (名前が使えない場合は、警告を表示して作らない)
        """
        self.message_dialogue = tk.Toplevel()
        fields = [["Entry", "Profile Name", ""], ["Check", "Copy Profile", True]]
        if Profile.has_uv_environment():
            # uv の環境では、起動用の bat の形を選べる
            labels = [Profile.BAT_LABELS[Profile.BAT_UV], Profile.BAT_LABELS[Profile.BAT_CLASSIC]]
            fields.append(["Radio", "Batch File", labels, labels[0]])
        ret = PokeConDialogue(self.message_dialogue, "プロファイルを追加", fields, mode=1).ret_value(list)
        self.message_dialogue = None
        # Cancel した場合は、リストではなく False が返る
        if ret:
            # 名前に使えない文字がある場合や、同じ名前のプロファイルがある場合は作らない
            ret[0] = ret[0].strip()
            error = check_profile_name(ret[0])
            if error is not None:
                messagebox.showwarning("プロファイルを追加", error)
                return
            kinds = {label: kind for kind, label in Profile.BAT_LABELS.items()}
            create_profile_bat(ret[0], kinds.get(ret[2]) if len(ret) > 2 else None)
            new_profile_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles", ret[0])
            if not os.path.exists(new_profile_path):
                if ret[1]:
                    current_profile_path = os.path.join(
                        os.path.dirname(os.path.abspath(__file__)), "profiles", self.profile
                    )
                    shutil.copytree(current_profile_path, new_profile_path)
                    # --auto で起動するときの優先度は最も低くする
                    add_profile_priority(ret[0])
                else:
                    pass
            else:
                pass
        else:
            pass

    def OpenKeyConfig(self) -> None:
        """設定 > キーコンフィグ...: キーコンフィグの画面を開く(すでに開いている場合は、フォーカスを移す)"""
        self._logger.debug("Open KeyConfig window")
        if self.key_config is not None:
            self.key_config.focus_force()
            return

        # メイン画面のSoftware-Controllerのレイアウトのゲーム機のタブを、最初に表示する
        kc_window = PokeKeycon(
            self.root, initial_console=self.app.keyboardConsole(), on_saved=self.app.reloadKeyboard
        )
        kc_window.protocol("WM_DELETE_WINDOW", self.closingKeyConfig)
        self.key_config = kc_window

    def closingKeyConfig(self) -> None:
        """キーコンフィグの画面を閉じる(× ボタン、OK、キャンセル)"""
        self._logger.debug("Close KeyConfig window")
        self.key_config.destroy()
        self.key_config = None

    def buildThemeMenu(self) -> None:
        """
        表示 > テーマ の中身を作り直す(起動時と、利用者が足したテーマを読み込み直した後)。
        元からあるテーマ、利用者が足したテーマ(themes フォルダー)、テーマを足すための項目 の順に並べる
        """
        menu = self.menu_theme
        menu.delete(0, "end")
        self.theme_var.set(Theme.saved_theme_id())
        user_ids = Theme.user_theme_ids()
        for theme_id in Theme.theme_ids():
            if theme_id in user_ids:
                continue
            menu.add_radiobutton(
                label=Theme.theme_name(theme_id),
                value=theme_id,
                variable=self.theme_var,
                command=lambda: self.app.changeTheme(self.theme_var.get()),
            )
            # デフォルト / 暗いテーマ / 明るいテーマ の間に区切り線
            if theme_id in ("default", "dark_charcoal"):
                menu.add_separator()
        if user_ids:
            menu.add_separator()
            for theme_id in user_ids:
                menu.add_radiobutton(
                    label=Theme.theme_name(theme_id),
                    value=theme_id,
                    variable=self.theme_var,
                    command=lambda: self.app.changeTheme(self.theme_var.get()),
                )
        menu.add_separator()
        menu.add_command(label="テーマを作る / 編集する...", command=self.app.openThemeEditor)
        menu.add_command(label="テーマを読み込み直す", command=self.app.reloadUserThemes)
        menu.add_command(label="テーマのフォルダーを開く", command=self.app.openThemeFolder)

    def ResetWindowSize(self) -> None:
        """表示 > 画面のリセット: 初めて起動したときの配置に戻す"""
        self._logger.debug("Reset window size")
        self.app.resetShowSize()

    def OpenGithub(self) -> None:
        """ヘルプ > GitHub: リポジトリのページを、ブラウザの新しいタブで開く"""
        webbrowser.open("https://github.com/futo030/Poke-Controller-Modified-Extension", 2)

    def OpenWiki(self) -> None:
        """ヘルプ > Wiki: Wiki のページを、ブラウザの新しいタブで開く"""
        webbrowser.open("https://github.com/futo030/Poke-Controller-Modified-Extension/wiki", 2)

    def OpenIssues(self) -> None:
        """ヘルプ > 不具合の報告・要望 (Issues): Issues のページを、ブラウザの新しいタブで開く"""
        webbrowser.open("https://github.com/futo030/Poke-Controller-Modified-Extension/issues", 2)

    def OpenGuide(self) -> None:
        """ヘルプ > Poke-Controller Guide: 解説サイトを、ブラウザの新しいタブで開く"""
        webbrowser.open("https://pokecontroller.info/", 2)

    def OpenChangeLog(self) -> None:
        """ヘルプ > 更新履歴: 更新履歴を表示するウィンドウを開く"""
        PokeConChangeLog(tk.Toplevel())

    def CheckUpdate(self) -> None:
        """
        ヘルプ > アップデート確認: 確認のうえ、リポジトリに更新があるかを調べて、結果を表示する
        (更新がある場合は、GitHub のページを開く)
        """
        window = tk.Toplevel()
        window.withdraw()  # メインウィンドウを非表示にする
        try:
            res = messagebox.askyesno(
                title="更新確認", message="Poke-Controller Modified Extension の更新を確認しますか?"
            )
            if res:
                res_check = update_check.check()
                if res_check == "0":
                    res = tk.messagebox.showinfo(title="更新確認", message="更新はありませんでした。")
                elif res_check == "1":
                    res = tk.messagebox.showinfo(
                        title="更新確認", message="最新版が公開されています。Githubのページを開きます。"
                    )
                    self.OpenGithub()
                else:
                    res = tk.messagebox.showwarning(title="更新確認", message="確認できませんでした。")
        finally:
            # 隠したウィンドウを残さない
            window.destroy()

    def OpenLicense(self) -> None:
        """ヘルプ > LICENSE: ライセンスを表示するウィンドウを開く"""
        PokeConCopyright(tk.Toplevel())

    def output_question(self) -> None:
        """ヘルプ > 質問テンプレート: 質問に必要な情報(環境、設定、最後に実行したコマンドなど)を入力する画面を開く"""
        # コマンドは起動時ではなく実行時に読み込まれるため、最新の実行コマンドを参照する
        PokeConQuestionDialogue(tk.Toplevel(), command=self.app.cur_command).output_text()

    def exit(self) -> None:
        """
        ファイル > 終了: ウィンドウの × ボタンと同じ処理(PokeControllerApp.exit)で、アプリケーションを終了する
        (確認のうえ、操作の記録・コントローラーでの操作・キーボードの受け付け・音声・カメラを止め、
        シリアルポートを切断し、画面の今の設定を保存する)
        """
        self._logger.debug("Close Menubar")
        app_exit = getattr(self.app, "exit", None)
        if callable(app_exit):
            app_exit()
            return
        # メイン画面なしで、このメニューだけを使っている場合(以前からの処理)
        if self.ser.isOpened():
            self.ser.closeSerial()
            print("serial disconnected")

        # stop listening to keyboard events
        if self.keyboard is not None:
            self.keyboard.stop()
            self.keyboard = None

        # save settings
        self.settings.save()

        self.camera.destroy()
        cv2.destroyAllWindows()
        self.master.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    widget = PokeController_Menubar(root)
    widget.pack(expand=True, fill="both")
    root.mainloop()
