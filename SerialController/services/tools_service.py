#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
こまごました操作: スクリーンショットの保存、座標と色の確認、ファイルやフォルダを開く、
通知の確認、実行履歴の削除、プロファイルの追加、ヘルプの文章(バージョン・更新履歴など)

画面(tkinter)には触れない。できない場合は ToolError(メッセージは、そのまま表示できる文)を送出する。
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import threading
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING, Any, Sequence

import Constant
import ControllerColors
import Profile
import Utility as util
from Camera import CAPTURE_DIR
from DiscordNotify import Discord_Notify
from LineNotify import Line_Notify
from services import introduction_store, update_check

if TYPE_CHECKING:
    from services.app_core import AppCore

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

SERIAL_CONTROLLER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(SERIAL_CONTROLLER_DIR)
# 名前を付けて保存するスクリーンショットの保存先(テンプレート画像の置き場所)
TEMPLATE_DIR = os.path.join(SERIAL_CONTROLLER_DIR, "Template")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp")
GITHUB_URL = "https://github.com/futo030/Poke-Controller-Modified-Extension"
GUIDE_URL = "https://pokecontroller.info/"
QUESTION_TITLE = (
    "--------------------------質問をする際の注意事項--------------------------\n"
    "・質問の前に自分なりにドキュメントを読むなど各自調査を実施してください。\n"
    "・項目すべてを記入してください。\n"
    "・個人を誹謗中傷するような記述はしないでください。"
)
QUESTION_NOTE = (
    "添付資料を準備してください。(以下は一例です。)\n"
    "・動作の動画\n"
    "・Poke-Conのログ\n"
    "・コマンドプロンプト(コンソール)の画面\n"
    "エラーが十分に出力されていることをご確認ください。"
)


class ToolError(Exception):
    """その操作はできない(メッセージは、そのまま表示できる文)"""


def check_relative_name(name: str) -> str:
    """
    保存先のフォルダの中の名前として使えるかを確かめて返す(「/」でフォルダを分けられる。外には出られない)
    画像の拡張子は除いて返す。使えない名前は ToolError
    """
    name = str(name).strip().replace("\\", "/")
    for extension in IMAGE_EXTENSIONS:
        if name.lower().endswith(extension):
            name = name[: -len(extension)]
    parts = name.split("/")
    if name == "" or any(
        part.strip() in ("", ".", "..") or any(character in part for character in ':*?"<>|\r\n\0') for part in parts
    ):
        raise ToolError('ファイルの名前に使えない文字があります。(: * ? " < > | と、「..」は使えません)')
    return "/".join(part.strip() for part in parts)


def is_image_file(path: str) -> bool:
    """画像の拡張子(IMAGE_EXTENSIONS)の、実際にあるファイルか"""
    return path.lower().endswith(IMAGE_EXTENSIONS) and os.path.isfile(path)


def open_with_system(path: str, choose_app: bool = False) -> None:
    """
    ファイルを、既定のアプリで開く(choose_app: 開くアプリを選ぶ画面を表示する。Windows のみ)
    """
    system = platform.system()
    if system == "Windows":
        if choose_app:
            subprocess.Popen(["rundll32.exe", "shell32.dll,OpenAs_RunDLL", path])
        else:
            os.startfile(path)
    elif system == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def open_folder(directory: str, select: str | None = None) -> None:
    """
    フォルダを開く(select: そのファイルを選んだ状態にする。Windows のみ)
    """
    system = platform.system()
    if system == "Windows":
        if select is not None:
            subprocess.Popen(f'explorer /select,"{select}"')
        else:
            subprocess.Popen(f'explorer "{directory}"')
    elif system == "Darwin":
        subprocess.Popen(["open", directory])
    else:
        subprocess.Popen(["xdg-open", directory])


class ToolsService:
    """
    スクリーンショットの保存、ファイルを開く、通知の確認、履歴の削除、プロファイルの追加、ヘルプの文章など。
    座標は、画面(JSON など)から届くので、型を決めずに受け取り(Any)、数値に変えてから使う
    """

    def __init__(self, core: AppCore):
        """
        core: アプリ本体(AppCore)
        """
        self.core = core

    # ================================================================ スクリーンショット

    def save_capture(self, area: Sequence[Any] | None = None, name: str | None = None) -> None:
        """
        カメラ画像を保存する。
        area: 保存する範囲(カメラ画像の上の座標 [x1, y1, x2, y2]。None なら全体)
        name: 名前を付けて保存する場合の名前(テンプレート画像の置き場所に保存する。None なら、日時の名前で Captures に保存する)
        映像が無い場合、範囲が読めない・小さすぎる場合、名前が使えない場合は ToolError
        """
        camera = self.core.camera
        if camera.image_bgr is None:
            raise ToolError("カメラの映像が無いため、保存できません。")
        crop_ax = None
        if area is not None:
            try:
                x1, y1, x2, y2 = (int(round(float(v))) for v in area)
            except (TypeError, ValueError):
                raise ToolError("保存する範囲の指定が正しくありません。")
            width, height = camera.capture_size
            x1, x2 = sorted((min(max(x1, 0), width), min(max(x2, 0), width)))
            y1, y2 = sorted((min(max(y1, 0), height), min(max(y2, 0), height)))
            if x2 <= x1 or y2 <= y1:
                raise ToolError("保存する範囲が小さすぎます。")
            crop_ax = [x1, y1, x2, y2]
        filename = None
        if name is not None:
            filename = os.path.join(TEMPLATE_DIR, *check_relative_name(name).split("/"))
        camera.saveCapture(filename=filename, crop=None if crop_ax is None else 1, crop_ax=crop_ax)

    def pixel_info(self, x: Any, y: Any) -> None:
        """
        カメラ画像の、その位置の座標と色を出力画面に表示する(映像が無い場合と、画像の外の位置は、座標だけ)
        x, y: カメラ画像の上の座標(数値として読めない場合は ToolError)
        """
        frame = self.core.camera.image_bgr
        try:
            x, y = int(float(x)), int(float(y))
        except (TypeError, ValueError):
            raise ToolError("位置の指定が正しくありません。")
        print(f"Mouse down: Capture ({x}, {y})")
        _logger.info(f"Mouse down: Capture ({x}, {y})")
        if frame is None or not (0 <= y < frame.shape[0] and 0 <= x < frame.shape[1]):
            return
        blue, green, red = (int(v) for v in frame[y, x][:3])
        print(f"Color [R: {red}, G: {green}, B: {blue}]")

    def open_capture_folder(self) -> None:
        """スクリーンショットの保存先(Captures)のフォルダーを開く(無ければ作る)"""
        directory = os.path.abspath(CAPTURE_DIR)
        os.makedirs(directory, exist_ok=True)
        _logger.debug(f"Open folder: '{directory}'")
        open_folder(directory)

    def send_image(self, target: str) -> None:
        """
        今のカメラ画像を、通知先(line / discord)へ送る(別のスレッドで送る。送れなくても、ログに残すだけ)
        target が "line" / "discord" でない場合は ToolError
        """
        if target not in ("line", "discord"):
            raise ToolError(f"送り先に指定できない値です: {target}")
        src = self.core.camera.readFrame()

        def send() -> None:
            """画像を送る(スレッドの中身)"""
            try:
                if target == "line":
                    Line_Notify().send_message("---Manual---", src, "token")
                else:
                    Discord_Notify().send_message(notification_message="---Manual---", image=src)
            except Exception as e:
                _logger.error(f"Failed to send the image: {e}")

        threading.Thread(target=send, name="SendImage", daemon=True).start()

    # ================================================================ ファイルを開く

    def _image_path(self, path: str) -> str:
        """画像のファイルの絶対パスを返す(画像のファイルでない・無い場合は ToolError)"""
        path = os.path.abspath(str(path))
        if not is_image_file(path):
            raise ToolError(f"ファイルが見つかりません: {path}")
        return path

    def open_image(self, path: str, choose_app: bool = False) -> None:
        """
        保存した画像を開く(開けるのは画像のファイルだけ)
        choose_app: 開くアプリを選ぶ画面を表示する(Windows のみ)。開けない場合は ToolError
        """
        path = self._image_path(path)
        _logger.debug(f"Open file: '{path}'")
        try:
            open_with_system(path, choose_app)
        except OSError as e:
            _logger.error(f"Failed to open the file: {e}")
            raise ToolError(f"ファイルを開けませんでした: {path}")

    def open_image_folder(self, path: str) -> None:
        """保存した画像のあるフォルダーを開く(Windows では、その画像を選んだ状態にする)"""
        path = self._image_path(path)
        open_folder(os.path.dirname(path), select=path)

    def command_file(self, command_type: str, name: str) -> str:
        """
        コマンドが書かれたファイルの絶対パス(見つからない場合は ToolError)
        command_type: 種別("Python" / "Mcu"。"py" などの書き方も受け付ける)、name: コマンドの名前
        """
        from services import command_catalog

        command_type = command_catalog.normalize_command_type(command_type)
        loader = self.core.commands.loaders.get(command_type)
        entry = None if loader is None else loader.findEntry(name)
        if entry is None or not os.path.isfile(entry.file_path):
            raise ToolError(f"'{name}' のファイルが見つかりません。(Reloadで一覧を更新してください)")
        return os.path.abspath(entry.file_path)

    def open_command_file(self, command_type: str, name: str, how: str = "file") -> None:
        """
        コマンドのファイルを開く。how: "file"(エディタで開く) / "with"(アプリを選んで開く) / "folder"(フォルダを開く)
        """
        path = self.command_file(command_type, name)
        _logger.debug(f"Open file: '{path}'")
        try:
            if how == "folder":
                open_folder(os.path.dirname(path), select=path)
            elif how == "with":
                open_with_system(path, choose_app=True)
            else:
                util.open_text_file(path)
        except OSError as e:
            _logger.error(f"Failed to open the file: {e}")
            raise ToolError(f"Open file: ファイルを開けませんでした。({path})")

    def command_mtimes(self) -> dict:
        """
        コマンドの種別 -> {コマンドの名前: ファイルの更新日時}(更新日時での並び替えに使う)
        """
        result = {}
        for command_type, entries in self.core.commands.commands.items():
            times = {}
            for entry in entries:
                try:
                    times[entry.name] = os.path.getmtime(getattr(entry, "file_path", ""))
                except OSError:
                    times[entry.name] = 0.0
            result[command_type] = times
        return result

    def command_usage(self) -> dict:
        """
        コマンドの種別 -> {コマンドの名前: 実行した回数}(使用頻度での並び替えに使う。ほかのウィンドウで実行した分も含む)
        """
        from services import command_usage

        return {
            command_type: command_usage.counts_of(command_type, entries)
            for command_type, entries in self.core.commands.commands.items()
        }

    # ================================================================ 実行履歴

    def delete_history(self, command_type: str, name: str) -> None:
        """
        実行した履歴から、そのコマンドを消して保存する(無い場合は ToolError)
        command_type: 種別("Python" / "Mcu"。"py" などの書き方も受け付ける)
        """
        from services import command_catalog

        normalize = command_catalog.normalize_command_type
        wanted = normalize(command_type)
        history = self.core.settings.command_history
        before = len(history)
        history[:] = [h for h in history if not (normalize(h["class"]) == wanted and h["name"] == name)]
        if len(history) == before:
            raise ToolError("その履歴はありません。")
        self.core.settings.save()
        self.core._notify("command")

    def clear_history(self) -> None:
        """実行した履歴を、すべて消して保存する"""
        self.core.settings.command_history.clear()
        self.core.settings.save()
        self.core._notify("command")

    # ================================================================ 通知の確認

    def send_windows_notification(self) -> None:
        """
        Windows の通知を、テストとして1つ出す(plyer が無い場合と、出せない場合は ToolError)
        """
        try:
            from plyer import notification
        except Exception:
            raise ToolError('"plyer" is not installed.')
        try:
            notification.notify(
                title=f"{Constant.NAME} ver.{Constant.VERSION} (profile:{self.core.profile})",
                message="Notification Test",
                timeout=5,
            )
        except Exception as e:
            _logger.error(f"Failed to send the notification: {e}")
            raise ToolError(f"通知を出せませんでした: {e}")
        print("Windows の通知を送りました。(Notification Test)")

    def check_line(self) -> None:
        """
        LINE のトークンで接続できるかを確かめ、結果を出力画面に表示する
        """
        try:
            line = Line_Notify()
            print(line)
            line.getRateLimit()
        except Exception as e:
            _logger.warning(f"LINE API check failed: {e}")
            print("LINE API Check: N/A")

    def check_discord(self) -> None:
        """Discord の通知先に接続できるかを確かめ、結果を出力画面に表示する"""
        try:
            discord = Discord_Notify()
            print(discord)
            discord.getRateLimit()
        except Exception as e:
            _logger.warning(f"Discord API check failed: {e}")
            print("DISCORD API Check: N/A")

    # ================================================================ 本体の色のプリセット

    def save_color_preset(self, controller_type: str, name: str) -> None:
        """
        今の本体の色を、プリセットとして書き出す(name: 拡張子なしの名前)
        種類が違う場合、名前が使えない場合、書き出せない場合は ToolError
        """
        if controller_type not in ControllerColors.CONTROLLER_TYPES:
            raise ToolError(f"コントローラーの種類に指定できない値です: {controller_type}")
        name = check_relative_name(name)
        if "/" in name:
            raise ToolError("プリセットの名前に「/」は使えません。")
        path = os.path.join(ControllerColors.USER_PRESET_DIR, name + ".json")
        try:
            os.makedirs(ControllerColors.USER_PRESET_DIR, exist_ok=True)
            ControllerColors.save_preset_file(path, controller_type, ControllerColors.get_colors(controller_type))
        except OSError as e:
            raise ToolError(f"書き出せませんでした。({e})")
        print(f"Controller Color: プリセットを書き出しました。({path})")
        self.core._notify("settings")

    # ================================================================ プロファイル

    def profiles(self) -> dict:
        """今のプロファイル、プロファイルの名前の一覧、読み取り専用で起動しているか"""
        return {"current": self.core.profile, "names": Profile.list_profiles(), "read_only": Profile.is_read_only()}

    def add_profile(self, name: str, copy_current: bool = True, bat_kind: str | None = None) -> str:
        """
        プロファイルと、そのプロファイルで起動する bat ファイルを作る。知らせる文を返す
        copy_current: 今のプロファイルの設定を写すか(False なら、フォルダーは、そのプロファイルで起動したときに作られる)
        bat_kind: bat の形(Profile.BAT_UV / BAT_CLASSIC)。指定がなければ、uv の環境があるかどうかで決める
        名前が使えない場合は ToolError
        """
        name = str(name).strip()
        error = Profile.check_profile_name(name)
        if error is not None:
            raise ToolError(error)
        bat_path = Profile.create_profile_bat(name, bat_kind)
        new_path = os.path.join(SERIAL_CONTROLLER_DIR, "profiles", name)
        if copy_current:
            shutil.copytree(os.path.join(SERIAL_CONTROLLER_DIR, "profiles", self.core.profile), new_path)
            Profile.add_profile_priority(name)
        message = f"プロファイル「{name}」を追加しました。"
        if copy_current:
            message += "(今のプロファイルの設定を写しました)"
        if bat_path is not None:
            message += f"\n起動用のファイル: {bat_path}"
        message += f"\nWeb 版で使うには、--profile {name} を付けて起動し直してください。"
        print(message)
        self.core._notify("settings")
        return message

    # ================================================================ ヘルプ

    def set_introduction_hidden(self, hidden: bool) -> None:
        """
        Web ブラウザ版の機能紹介を、起動時に表示しない(hidden=False なら、また表示する)設定にして保存する
        """
        try:
            introduction_store.set_hidden(bool(hidden), introduction_store.WEB)
        except OSError as e:
            _logger.error(f"Failed to save the introduction state: {e}")
            raise ToolError(f"保存できませんでした: {e}")
        self.core._notify("settings")

    def diagnostics_context(self) -> dict:
        """環境の診断に渡す、今の状態(プロファイル、シリアル、カメラ、コマンドの数、ログのファイル)"""
        import PokeConLogger

        core = self.core
        settings = getattr(core, "settings", None)
        sender = getattr(core, "sender", None)
        port = getattr(settings, "com_port_name", "") or ""
        if not port and getattr(settings, "com_port", "") not in ("", None):
            port = f"COM{settings.com_port}"
        commands = getattr(getattr(core, "commands", None), "commands", {})
        return {
            "app": f"{Constant.NAME} ver.{Constant.VERSION}",
            "profile": getattr(core, "profile", ""),
            "read_only": Profile.is_read_only(),
            "command_counts": {command_type: len(entries) for command_type, entries in commands.items()},
            "log_file": PokeConLogger.log_file_path(),
            "serial_connected": bool(sender is not None and sender.isOpened()),
            "serial_port": port,
            "data_format": getattr(settings, "serial_data_format_name", ""),
            "camera_opened": getattr(getattr(core, "camera", None), "image_bgr", None) is not None,
            "camera_name": f"Camera ID {getattr(settings, 'camera_id', '')}",
            "capture_size": getattr(settings, "capture_size", ""),
        }

    def diagnostics_text(self) -> str:
        """
        環境の診断の結果の文章(必要なライブラリ・フォルダー・機器の状態を調べる。調べるだけで、何も変えない)
        """
        return self.diagnostics_texts()[0]

    def diagnostics_texts(self) -> tuple:
        """環境の診断の結果の文章を、(そのままのもの, フォルダーの場所を隠したもの)で返す(同じ 1 回の診断から作る)"""
        from services import diagnostics

        items = diagnostics.diagnose(self.diagnostics_context())
        return diagnostics.to_text(items), diagnostics.to_text(items, mask=True)

    @staticmethod
    def _read_root_file(name: str, label: str) -> str:
        """リポジトリ直下のファイルの中身を返す(UTF-8、だめなら cp932 で読む。開けない場合は ToolError。label: メッセージに出す名前)"""
        for encoding in ("utf-8", "cp932"):
            try:
                with open(os.path.join(ROOT_DIR, name), "r", encoding=encoding) as file:
                    return file.read()
            except UnicodeDecodeError:
                continue
            except OSError:
                break
        raise ToolError(f"{label}が開けません。")

    def changelog_text(self) -> str:
        """更新履歴(changelog.txt)の文章"""
        return self._read_root_file("changelog.txt", "changelog.txt")

    def license_text(self) -> str:
        """ライセンス(LICENSE)の文章"""
        return self._read_root_file("LICENSE", "LICENSEファイル")

    def question_defaults(self) -> dict:
        """
        質問テンプレートの初期値(最後に実行したコマンドの名前と制作者)
        """
        command = self.core.commands.current
        program_name = getattr(command, "NAME", "") or ""
        filename = getattr(command, "FILENAME", None)
        if filename:
            program_name = f"{program_name} ({filename})"
        return {"title": QUESTION_TITLE, "program": program_name, "developer": getattr(command, "DEVELOPER", "") or ""}

    def question_text(self, program: str, developer: str, question: str, tried: str) -> str:
        """
        問い合わせ用の文章を作って、出力画面に表示する。文章を返す(空の項目がある場合は ToolError)
        """
        values = [str(value) for value in (program, developer, question, tried)]
        if any(value.strip() == "" for value in values):
            raise ToolError("項目すべてを記入してください。")
        text = "---------------------------ここからコピペ---------------------------\n"
        text += f"■プログラム名\n{values[0]}\n"
        text += f"■製作者様\n{values[1]}\n"
        text += f"■使用ツール\n{Constant.NAME} {Constant.VERSION}\n"
        if platform.system() == "Darwin":
            text += f"■OS\n{platform.mac_ver()}(Mac)\n"
        else:
            text += f"■OS\n{platform.platform()}\n"
        text += f"■Python version\n{sys.version.split(' ')[0]}\n"
        text += f"■質問内容(詳しくご記述ください。)\n{values[2]}\n"
        text += f"■試したこと(詳しくご記述ください。)\n{values[3]}\n"
        text += "---------------------------ここまでコピペ---------------------------"
        print(text)
        return text

    def check_update(self) -> str:
        """
        更新があるかを確かめる(git で管理しているフォルダの場合)。"0": 最新 / "1": 更新あり / "-1": 確認できない
        """
        return update_check.check(ROOT_DIR)

    def state(self) -> dict:
        """
        画面に表示する状態のうち、この機能の分
        """
        return {
            "mtimes": self.command_mtimes(),
            "usage": self.command_usage(),
            "profiles": self.profiles(),
            "links": {"github": GITHUB_URL, "guide": GUIDE_URL},
            "windows": platform.system() == "Windows",
            # uv の環境(.venv)があるか(プロファイルを足すときに、起動用の bat の形を選べる)
            "uv_environment": Profile.has_uv_environment(),
            # 起動時に機能紹介を表示するか(紹介文があり、今の内容を「今後は表示しない」にしていない)
            "show_introduction": introduction_store.should_show_at_startup(introduction_store.WEB),
        }
