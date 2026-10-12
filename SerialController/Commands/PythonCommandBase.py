#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import TYPE_CHECKING

from abc import abstractclassmethod
from typing import Any, Callable, List, Tuple, Optional
import threading
import time
from time import sleep
import random
from logging import getLogger, DEBUG, NullHandler

# ロガーの設定は1回だけ行う
# (インスタンスを作るたびにaddHandlerすると、ハンドラが増え続けてメモリを使い、ログの出力も遅くなる)
_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True
import configparser
import os
import os.path
import datetime
import string
import traceback

try:
    from plyer import notification

    flag_import_plyer = True
except Exception:
    flag_import_plyer = False
from services.settings_store import AppSettings
from ImageProcessing import ImageProcessing, crop_image, getImage, opneImage
from ImageProcessing import getInterframeDiff as _getInterframeDiff

from LineNotify import Line_Notify
from DiscordNotify import Discord_Notify, DEFAULT_WEBHOOK as DEFAULT_DISCORD_WEBHOOK
from Commands import CommandBase
from Commands.Keys import KeyPress
from Commands import SwitchKeyboard
from Commands.SwitchKeyboard import KEY
from Commands.transport import get_transport, keyboard_transport_names
from UiDispatcher import UiDispatcher
import OutputLinks
import Utility

if TYPE_CHECKING:
    from GuiAssets import CaptureArea
    from Camera import Camera
    from Commands.Sender import Sender
    from Commands.Keys import Button, Hat, Direction, Touchscreen


# 待機時に、残りがこの時間(秒)になるまではsleepし、残りはビジーループで合わせる
# (ビジーループ中はGILを取り合い、メインスレッドの処理を遅くするため最小限にする)
SPIN_MARGIN = 0.002


def precise_sleep(duration: float) -> None:
    """
    指定時間(秒)待機する
    大部分をsleepで待ち、終わり際だけビジーループで精度を合わせる
    """
    end_time = time.perf_counter() + duration
    remaining = duration - SPIN_MARGIN
    if remaining > 0:
        sleep(remaining)
    while time.perf_counter() < end_time:
        pass


# 長い待機の途中で、止める指示を確かめる間隔(秒)
# (待つ時間がこの2倍以下のときは、途中では確かめず、待ち終わってから確かめる)
STOP_POLL_INTERVAL = 0.1
# 一時停止中に、再開・停止・変数の表示の要求を確認する間隔(秒)
PAUSE_POLL_INTERVAL = 0.1
# 一時停止中の「Show variables」で、1回に表示する変数の数
VARIABLES_PER_PAGE = 10
# 変数の値を表示するときの、最大の文字数(これより長い値は省略する)
VARIABLE_VALUE_MAX_LENGTH = 200
# 自動化スクリプトのフォルダ(一時停止した位置は、このフォルダ内のファイルの行を表示する)
PYTHON_COMMANDS_DIR = os.path.normcase(
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "PythonCommands"))
)
# 変数の一覧に表示しない、ツールが使う変数
HIDDEN_VARIABLES = (
    "isRunning",
    "message_dialogue",
    "socket0",
    "mqtt0",
    "keys",
    "thread",
    "alive",
    "postProcess",
    "Line",
    "Discord",
    "_logger",
    "camera",
    "gui",
    "ImgProc",
    "_pause_session",
    "_show_variables_requested",
    "_variables_shown",
)

# スクリプト開始/終了時刻の表示形式
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
# スクリプト開始時に表示する、前のログとの区切り線
SEPARATOR_LINE = "-" * 40


def format_elapsed_time(seconds: float) -> str:
    """
    経過時間(秒)を H:MM:SS.mmm 形式の文字列に変換する
    """
    total_ms = int(round(seconds * 1000))
    hours, rem = divmod(total_ms, 3600 * 1000)
    minutes, rem = divmod(rem, 60 * 1000)
    secs, ms = divmod(rem, 1000)
    return f"{hours}:{minutes:02d}:{secs:02d}.{ms:03d}"


# the class For notifying stop signal is sent from Main window
class StopThread(Exception):
    """コマンドを止めるための例外(止める指示が出た後の checkIfAlive が出す。do_safe が受けて、終了の処理をする)"""

    pass


# Python command


class PythonCommand(CommandBase.Command):
    """
    自動化スクリプト(Python コマンド)の基底クラス。

    スクリプトは、このクラスを継承して do() に処理を書き、press / hold / wait などを呼んで入力を送る。
    do() は専用のスレッドで動き、止める指示は、待つ関数の中で StopThread として届く
    """

    def __init__(self) -> None:
        """実行していない状態で作る(入力を送る KeyPress は、実行を始めるときに作る)"""
        super(PythonCommand, self).__init__()
        self._logger = _logger

        self.keys = None
        self.thread = None
        self.alive = True
        self.postProcess = None
        # 一時停止の回数(古い「Show variables」のリンクを区別する)、変数の表示の要求、表示した変数の数
        self._pause_session = 0
        self._show_variables_requested = False
        self._variables_shown = 0
        # PressKeyで押したままにしているキー(終了時に離す)
        self._keyboard_pressed = []
        try:
            self.Line = Line_Notify()
        except Exception:
            self.Line = None
        self.Discord = Discord_Notify()

    def pausedecorator(func: Callable[..., None]) -> Callable[..., None]:
        """
        一時停止を実現するためのデコレータです。
        関数の処理が終わった後に、一時停止が要求されていれば一時停止します。
        (付けた関数の戻り値は捨てるので、値を返さない関数に使う)
        """

        def inner(self: PythonCommand, *args: Any, **kwargs: Any) -> None:
            """元の関数を呼び、その後で、一時停止が要求されていれば待つ"""
            func(self, *args, **kwargs)
            self.waitWhilePaused()

        return inner

    def waitWhilePaused(self) -> None:
        """
        一時停止が要求されていれば、再開(Restart)されるまで待つ。
        一時停止した位置を表示し、「Show variables」のリンクで変数を表示できるようにする。
        待っている間に止める指示が出た場合は StopThread
        """
        if not self.isPause:
            return
        self._pause_session += 1
        self._show_variables_requested = False
        self._variables_shown = 0
        self._printPausePosition()
        while self.isPause:
            sleep(PAUSE_POLL_INTERVAL)
            self.checkIfAlive()
            if self._show_variables_requested:
                self._show_variables_requested = False
                self._printVariables()

    def _printPausePosition(self) -> None:
        """
        一時停止した位置(自動化スクリプトのファイル・行・関数・その行のコード)を、呼び出しの順に表示する。
        ファイルの位置はリンクにし、クリックでそのファイルを開く
        """
        frames = [
            frame
            for frame in traceback.extract_stack()
            if os.path.normcase(os.path.abspath(frame.filename)).startswith(PYTHON_COMMANDS_DIR + os.sep)
        ]
        lines = ["一時停止しました:"]
        for index, frame in enumerate(frames):
            path = os.path.abspath(frame.filename)
            name = os.path.relpath(path, PYTHON_COMMANDS_DIR).replace(os.sep, "/")
            location = OutputLinks.link(
                f"{name} {frame.lineno}行目", lambda path=path, line=frame.lineno: self._openFile(path, line)
            )
            code = (frame.line or "").strip()
            lines.append(f"  {'→ ' if index > 0 else ''}{location} ({frame.name}): {code}")
        print("\n".join(lines))
        print(self._showVariablesLink("Show variables"))

    @staticmethod
    def _openFile(path: str, line: int) -> None:
        """ファイルを、エディターで開く(line: 開く行。開けない場合は、その旨を表示する)"""
        try:
            Utility.open_text_file(path, line)
        except OSError:
            print(f"ファイルを開けませんでした: {path}")

    def _showVariablesLink(self, label: str) -> str:
        """
        押すと、まだ表示していない変数を次の VARIABLES_PER_PAGE 個表示するリンク(1回だけ押せる)
        label: リンクの文字。戻り値: 出力に書くと、リンクになる文字列
        """
        session = self._pause_session

        def request() -> None:
            """変数の表示を頼む(リンクを作ったときの一時停止が続いている場合のみ)"""
            # メインスレッドから呼ばれる。表示はスクリプトのスレッドで行う(GUIに負荷をかけない)
            if not self.alive or not self.isPause or self._pause_session != session:
                print("変数は、一時停止中のみ表示できます。")
                return
            self._show_variables_requested = True

        return OutputLinks.link(label, request, once=True)

    @staticmethod
    def _formatValue(value: object) -> str:
        """
        変数の値を表示用の文字列にする(画像などの配列は型と大きさだけ、長い値は省略する)
        """
        if type(value).__name__ == "ndarray":
            return f"ndarray shape={getattr(value, 'shape', '?')} dtype={getattr(value, 'dtype', '?')}"
        text = str(value)
        if len(text) > VARIABLE_VALUE_MAX_LENGTH:
            text = text[:VARIABLE_VALUE_MAX_LENGTH] + f"...(省略。全体で{len(text)}文字)"
        return text

    def _printVariables(self) -> None:
        """
        まだ表示していない変数を、VARIABLES_PER_PAGE 個表示する。残りがあれば「Show more variables」のリンクを出す
        """
        items = [(k, v) for k, v in vars(self).items() if k not in HIDDEN_VARIABLES]
        if not items:
            print("(表示できる変数はありません)")
            return
        start = self._variables_shown
        page = items[start : start + VARIABLES_PER_PAGE]
        self._variables_shown = start + len(page)
        lines = [f"--------内部変数 ({start + 1}~{self._variables_shown} / {len(items)})--------"]
        lines += [f"{k} = {self._formatValue(v)}" for k, v in page]
        print("\n".join(lines))
        if self._variables_shown < len(items):
            print(self._showVariablesLink("Show more variables"))

    def show_var(self) -> None:
        """
        一時停止時に内部変数の一覧を表示します。
        表示対象は自動化スクリプト側でselfにて定義した変数のみです。
        """
        var_dict = vars(self)  # 重い
        del_dict = HIDDEN_VARIABLES
        print("--------内部変数一覧--------")
        for k, v in var_dict.items():
            if k not in del_dict:
                print(k, "=", v)
        print("----------------------------")

    @abstractclassmethod
    def do(self) -> None:
        """
        自動化スクリプト側でオーバーライトされるため、処理の記述はありません。
        """
        pass

    def do_safe_with_output_page(self, ser: Sender, output_page: int) -> None:
        """
        出力先ページ(Start時にアクティブだったページ)をスレッドに登録してdo_safeを実行します。
        output_page: 出力先のページ(0 始まり)
        """
        self.register_output_thread(output_page)
        try:
            self.do_safe(ser)
        finally:
            self.unregister_output_thread()

    def do_safe(self, ser: Sender) -> None:
        """
        自動化スクリプト実行準備→実行→終了処理を順番に行います。
        StopThread(終了・停止)は、正常な終わりとして扱い、終了の通知を送ります。
        それ以外の例外は、内容を表示して入力を離し、ここで止めます(外へは出しません)。
        """
        if self.keys is None:
            self.keys = KeyPress(ser)
            self.keys.init_hat()

        global flag_import_plyer
        started = None
        ended = None
        try:
            if self.alive:
                started = self._print_script_start()
                try:
                    self._do_with_start_notification()
                finally:
                    # 終了通知(LINE/Discord等)の送信時間は実行時間に含めない
                    ended = (datetime.datetime.now(), time.perf_counter())
        except StopThread:
            print("-- finished successfully. --")
            self._logger.info("Command finished successfully")
            if self.isWinNotEnd:
                if flag_import_plyer:
                    notification.notify(
                        title=f"{self.app_name} (profile:{self.profilename})",
                        message=f"{self.cur_command_name} finished.",
                        timeout=5,
                    )
                else:
                    print('"plyer" is not installed.')
            if self.isLineNotEnd:
                self.LINE_text(f"{self.app_name} (profile:{self.profilename})\n{self.cur_command_name} finished.")
            if self.isDiscordNotEnd:
                self._discordNotify(f"{self.app_name} (profile:{self.profilename})\n{self.cur_command_name} finished.")
        except Exception as e:
            if self.keys is None:
                self.keys = KeyPress(ser)
                self.keys.init_hat()
            print("Interrupt:cmd(黒い画面)を確認してください。")
            print(e)
            self._logger.warning("Command stopped unexpectedly")
            import traceback

            traceback.print_exc()
            self.keys.end()
            self.alive = False
        finally:
            # キーボードのキーを押したまま終わらないようにする
            self._releaseKeyboardKeys()
            if started is not None:
                self._print_script_end(started, ended)

    def _do_with_start_notification(self) -> None:
        """
        開始通知を行い、自動化スクリプトを実行します。
        (do() が最後まで進んだ場合も、finish() が StopThread を出して終わります)
        """
        if self.isWinNotStart:
            if flag_import_plyer:
                notification.notify(
                    title=f"{self.app_name} (profile:{self.profilename})",
                    message=f"{self.cur_command_name} started.",
                    timeout=5,
                )
            else:
                print('"plyer" is not installed.')
        if self.isLineNotStart:
            self.LINE_text(f"{self.app_name} (profile:{self.profilename})\n{self.cur_command_name} started.")
        if self.isDiscordNotStart:
            self._discordNotify(f"{self.app_name} (profile:{self.profilename})\n{self.cur_command_name} started.")
        self.do()
        self.finish()

    def _print_script_start(self) -> Tuple[datetime.datetime, float]:
        """
        スクリプトの開始時刻を標準出力に表示し、(開始時刻, 計測開始値)を返します。
        """
        start_dt = datetime.datetime.now()
        # 前のログとの区切り
        print(SEPARATOR_LINE)
        print(f"スクリプト開始: {self.cur_command_name}")
        print(f"開始時刻: {start_dt.strftime(TIME_FORMAT)}")
        return start_dt, time.perf_counter()

    def _print_script_end(
        self, started: Tuple[datetime.datetime, float], ended: Tuple[datetime.datetime, float] | None = None
    ) -> None:
        """
        スクリプトの開始/終了時刻と実行時間を標準出力に表示します。
        started / ended: (時刻, time.perf_counter() の値)。ended が None なら、今を終了時刻にします。
        """
        start_dt, start_count = started
        if ended is None:
            ended = (datetime.datetime.now(), time.perf_counter())
        end_dt, end_count = ended
        print(f"スクリプト終了: {self.cur_command_name}")
        print(f"開始時刻: {start_dt.strftime(TIME_FORMAT)}")
        print(f"終了時刻: {end_dt.strftime(TIME_FORMAT)}")
        print(f"実行時間: {format_elapsed_time(end_count - start_count)}")

    def start(self, ser: Sender, postProcess: Callable[[], None] | None) -> None:
        """
        自動化スクリプトをスレッドに割り当てて実行します。
        postProcess: 終わったときに、画面のスレッドで呼ぶ関数(Start ボタンを戻す処理など。None: 呼ばない)
        """
        self.alive = True
        self.socket0.alive = True
        self.mqtt0.alive = True
        self.postProcess = postProcess
        ImageProcPythonCommand.template_path_name = "./Template/"
        if not self.thread:
            self.thread = threading.Thread(
                target=self.do_safe_with_output_page, args=(ser, self.output_page)
            )
            self.thread.start()

    def end(self, ser: Sender) -> None:
        """
        コマンドを止めるよう頼む(Socket / MQTT の受信の待ちも、やめさせる)。
        すでに止める指示が出ている場合は、ここで終了の処理をして StopThread を出す
        """
        self.socket0.alive = False
        self.mqtt0.alive = False
        self.sendStopRequest()

    def sendStopRequest(self) -> None:
        """
        止める指示を出す(alive を False にする。実際に止まるのは、スクリプトが次に待つ関数を呼んだとき)。
        すでに指示が出ている場合は、ここで終了の処理をして StopThread を出す
        """
        if self.checkIfAlive():  # try if we can stop now
            self.alive = False
            print("-- sent a stop request. --")
            self._logger.info("Sending stop request")
        if self.socket0.flag_socket:
            self.socket_disconnect()

    # NOTE: Use this function if you want to get out from a command loop by yourself
    def finish(self) -> None:
        """
        自動化スクリプトを終了します。(自動化スクリプト内で意図的に終了したい場合に使用。)
        入力を離し、StopThread を出すので、この後の処理は実行されません。
        """
        self.alive = False
        self.socket0.alive = False
        self.mqtt0.alive = False
        self.end(self.keys.ser)

    # press button at duration times(s)
    @pausedecorator
    def press(
        self, buttons: Button | Hat | Direction | Touchscreen | list, duration: float = 0.1, wait: float = 0.1
    ) -> None:
        """
        ボタンを押す。
        buttons: Button、Hat、Direction、Touchscreen、または、それらのリスト(同時に押す)
        duration: 押している時間(秒)
        wait: 離した後に待つ時間(秒)
        """
        # 押している途中で一時停止すると、押したままになるので、待つ間は一時停止しない(離した後に一時停止する)
        self.keys.input(buttons)
        self._sleep(duration)
        self.keys.inputEnd(buttons)
        self._sleep(wait)

    # press button at duration times(s) repeatedly
    def pressRep(
        self,
        buttons: Button | Hat | Direction | Touchscreen | list,
        repeat: int,
        duration: float = 0.1,
        interval: float = 0.1,
        wait: float = 0.1,
    ) -> None:
        """
        ボタンを複数回押す。
        buttons: press と同じ
        repeat: 押す回数
        duration: 1 回に押している時間(秒)
        interval: 離してから、次に押すまでの時間(秒)
        wait: 最後に離した後に待つ時間(秒)
        """
        for i in range(0, repeat):
            self.press(buttons, duration, 0 if i == repeat - 1 else interval)
        self.wait(wait)

    # add hold buttons
    @pausedecorator
    def hold(self, buttons: Button | Hat | Direction | Touchscreen | list, wait: float = 0.1) -> None:
        """
        ボタンを押したままの状態にする。
        buttons: press と同じ。wait: 押した後に待つ時間(秒)
        """
        self.keys.hold(buttons)
        self._sleep(wait)

    # release holding buttons
    @pausedecorator
    def holdEnd(self, buttons: Button | Hat | Direction | Touchscreen | list) -> None:
        """
        ボタンを離した状態にする。
        buttons: press と同じ(hold で押したままにしたもの)
        """
        self.keys.holdEnd(buttons)
        self.checkIfAlive()

    # change holding stick direction / hat without releasing
    @pausedecorator
    def holdChange(self, buttons: Button | Hat | Direction | Touchscreen | list, wait: float = 0.1) -> None:
        """
        押したままのスティックの向き・倒し量、Hatの向きを、離さずに切り替える。
        (holdEnd→holdでは一度ニュートラルに戻るため)
        同じスティック・Hatを押したままにしていない場合はholdと同じ。
        buttons: press と同じ(タッチの位置も切り替えられる)。wait: 切り替えた後に待つ時間(秒)
        """
        self.keys.holdChange(buttons)
        self._sleep(wait)

    def _sleep(self, wait: float) -> None:
        """
        指定時間待機する(一時停止はしない。停止の要求は確認する)
        """
        self._sleepStoppable(wait)

    def _sleepStoppable(self, wait: float) -> None:
        """
        指定時間待機してから、止める指示を確かめる。
        長い待機では、待っている途中にも STOP_POLL_INTERVAL ごとに確かめ、指示が出ていれば、そこで終了する(StopThread)。
        待ち終わる時刻は、途中で確かめない場合と同じ(終わり際は precise_sleep で合わせる)
        """
        duration = float(wait)
        end_time = time.perf_counter() + duration
        remaining = duration
        while remaining > STOP_POLL_INTERVAL * 2:
            sleep(STOP_POLL_INTERVAL)
            self.checkIfAlive()
            remaining = end_time - time.perf_counter()
        precise_sleep(remaining)
        self.checkIfAlive()

    # do nothing at wait time(s)
    @pausedecorator
    def short_wait(self, wait: float) -> None:
        """
        指定時間待機する。(wait: 秒。今は wait() と同じ動き)
        """
        self._sleepStoppable(wait)

    # do nothing at wait time(s)
    @pausedecorator
    def wait(self, wait: float) -> None:
        """
        指定時間待機する。(wait: 秒。待った後に、止める指示と、一時停止を確かめる。
        長い待機では、待っている途中でも、止める指示があれば、そこで終了する)
        """
        self._sleepStoppable(wait)

    ############### キーボード入力 ###############
    # マイコンをキーボードとしても認識させて、Switchに文字やキーを打つ。
    # キーボード機能に対応したファームウェアが必要(CH552-SERIAL は v2.4 以上。詳細は SwitchKeyboard.py)
    def _keyboardSteps(self, kind: str, value: str | int | None = None) -> list | None:
        """
        キーボード入力の手順(送るものと、待つ時間の並び)を、今のData Formatの送信方式から得る。
        キーボード入力を使えないData Formatの場合は、1回だけ知らせてNoneを返す
        (kind と value は、送信方式の keyboard_steps と同じ)
        """
        format_name = KeyPress.serial_data_format_name
        steps = get_transport(format_name).keyboard_steps(kind, value)
        if steps is None and not getattr(self, "_keyboard_format_warned", False):
            self._keyboard_format_warned = True
            names = " / ".join(keyboard_transport_names())
            print(f"キーボード入力は、Data Format が {names} の場合のみ使えます。(現在: {format_name})")
            self._logger.warning(f"Keyboard input is not available in the data format '{format_name}'.")
        return steps

    def _keyboardSend(self, kind: str, value: str | int | None = None) -> bool:
        """
        キーボード入力を送り、マイコンが打ち終わるまで待つ(送れないData Formatの場合は送らずFalseを返す)

        kind: "init" / "text" / "Key" / "Press" / "Release"(送信方式の keyboard_steps と同じ)
        value: "text" では打つ文字列、キーの操作ではキーの数値
        """
        steps = self._keyboardSteps(kind, value)
        if steps is None:
            return False
        for item, seconds in steps:
            self.keys.ser.send_keyboard(item)
            # 打っている間、マイコンは次のデータを受け取れないので、打ち終わるまで待つ(一時停止はしない)
            self._sleep(seconds)
        return True

    def KeyBoard_Init(self) -> None:
        """
        キーボード入力を始める前に呼ぶ(キーボード画面が表示されたときに1回)。
        コントローラーを無入力の状態にし、押したままのキーを離す。
        Switch側の入力モード(かな・カナ・英数)は変えない
        """
        self._releaseKeyboardKeys()
        self._keyboardSend("init")
        self.waitWhilePaused()

    def TypeString(self, text: str) -> bool:
        """
        半角の文字列をキーボードで打つ(改行なし)。
        半角以外の文字が含まれる場合は、何も送らずFalseを返す。
        かなを入力する場合は、Switch側をローマ字入力のモードにして、ローマ字を渡す(例: "neko")
        """
        text = str(text)
        invalid = SwitchKeyboard.find_invalid_characters(text)
        if invalid:
            # 改行などの表示できない文字は、\n のような表記にする
            shown = " ".join(c if c.isprintable() else repr(c)[1:-1] for c in invalid)
            print(f"TypeString: 半角以外の文字は入力できません: {shown} (入力文字列: {text!r})")
            self._logger.warning(f"TypeString: not half-width characters: {invalid}")
            return False
        unsupported = [c for c in SwitchKeyboard.UNSUPPORTED_ON_SWITCH if c in text]
        if unsupported:
            print(f"TypeString: Switchでは入力できない可能性がある文字です: {' '.join(unsupported)}")
            self._logger.warning(f"TypeString: may not be typed on Switch: {unsupported}")
        result = self._keyboardSend("text", text)
        self.waitWhilePaused()
        return result

    def TypeStringln(self, text: str) -> bool:
        """
        半角の文字列をキーボードで打ち、最後にEnterを押す
        """
        if not self.TypeString(text):
            return False
        self.TypeKey(KEY.ENTER)
        return True

    def _keyboardKey(self, action: str, keyvalue: int, show_value: bool) -> int | None:
        """
        キーを操作する行を送る。送った数値を返す(送らなかった場合はNone)
        action: "Key" / "Press" / "Release"。keyvalue: KEY か数値。show_value: 操作とキーの名前を表示するか
        """
        name = SwitchKeyboard.key_name(keyvalue)
        if show_value:
            print(f"{action}: {name}")
        code = int(keyvalue)
        if not self._keyboardSend(action, code):
            return None
        return code

    def TypeKey(self, keyvalue: int, show_value: bool = False) -> None:
        """
        キーを1回押して離す(keyvalue: KEY.ENTER など。show_value: 押したキーを表示するか)
        """
        self._keyboardKey("Key", keyvalue, show_value)
        self.waitWhilePaused()

    def PressKey(self, keyvalue: int, show_value: bool = False) -> None:
        """
        キーを押したままにする(ReleaseKeyで離す。離さないままコマンドが終わった場合は、終了時に離す)
        keyvalue: KEY.ENTER など。show_value: 押したキーを表示するか
        """
        code = self._keyboardKey("Press", keyvalue, show_value)
        if code is not None and code not in self._keyboard_pressed:
            self._keyboard_pressed.append(code)
        self.waitWhilePaused()

    def ReleaseKey(self, keyvalue: int, show_value: bool = False) -> None:
        """
        押したままのキーを離す(keyvalue: KEY.ENTER など。show_value: 離したキーを表示するか)
        """
        code = self._keyboardKey("Release", keyvalue, show_value)
        if code in self._keyboard_pressed:
            self._keyboard_pressed.remove(code)
        self.waitWhilePaused()

    def _releaseKeyboardKeys(self) -> None:
        """
        PressKeyで押したままのキーをすべて離す(コマンドの終了時にも呼ばれるので、例外は出さない)
        """
        pressed, self._keyboard_pressed = getattr(self, "_keyboard_pressed", []), []
        for keyvalue in pressed:
            try:
                steps = get_transport(KeyPress.serial_data_format_name).keyboard_steps("Release", keyvalue) or []
                for item, seconds in steps:
                    self.keys.ser.send_keyboard(item)
                    precise_sleep(seconds)
            except Exception as e:
                self._logger.warning(f"Failed to release the keyboard key {keyvalue}: {e}")

    def checkIfAlive(self) -> bool:
        """
        Aliveフラグの状態を確認する。
        AliveフラグがFalseなら終了処理を行う。
        戻り値: Alive なら True。False の場合は、入力を離し、postProcess を画面のスレッドに頼んでから、
                StopThread を出す(値は返らない)
        """
        if not self.alive:
            self.keys.end()
            self.keys = None
            self.thread = None

            if self.postProcess is not None:
                # GUIの後処理(ボタン状態の復帰等)はメインスレッドで行う(完了は待たない)
                UiDispatcher.post(self.postProcess)
                self.postProcess = None

            # raise exception for exit working thread
            self._logger.info("Exit from command successfully")
            raise StopThread("exit successfully")
        else:
            return True

    # direct serial
    def direct_serial(self, serialcommands: list, waittime: list) -> None:
        """
        シリアルの行を、入力の合成を経由せずに、順に送る(Default の形式の行を、自分で組み立てて送る場合に使う)

        serialcommands: 送る行(文字列)のリスト(行末の改行は、付いていても取り除く)
        waittime: それぞれの行を送る前に待つ秒数のリスト(短い方の長さまで送る)
        """
        # 余計なものが付いている可能性があるので確認して削除する
        checkedcommands = []
        for row in serialcommands:
            checkedcommands.append(row.replace("\r", "").replace("\n", ""))
        self.keys.serialcommand_direct_send(checkedcommands, waittime)

    # Reload COM port (temporary function)
    def reload_com_port(self) -> None:
        """
        COM ポートを開き直す(開いていれば閉じてから、設定ファイルのポート・ボーレートで開く)。
        開けなかった場合は、Sender がその旨を表示する(例外は出さない)
        """
        if self.keys.ser.isOpened():
            print("Port is already opened and being closed.")
            self.keys.ser.closeSerial()
            # self.keyPress = None (ここでNoneはNGなはず)
            self.reload_com_port()
        else:
            com_port, com_port_name, baud_rate = self._load_com_port_settings()
            if self.keys.ser.openSerial(com_port, com_port_name, baud_rate):
                print("COM Port " + str(com_port) + " connected successfully")
                self._logger.debug("COM Port " + str(com_port) + " connected successfully")
                # self.keyPress = None (ここでNoneはNGなはず)

    @staticmethod
    def _load_com_port_settings() -> Tuple[int, str, int]:
        """
        設定ファイルからCOMポートの設定を読み込む
        戻り値: (ポートの番号, ポートの名前, ボーレート)
        """
        if not os.path.isfile(AppSettings.SETTING_PATH):
            # 設定ファイルが無い場合は作る(AppSettings は画面の部品を使わないので、どのスレッドからでも呼べる)
            AppSettings()
        setting = configparser.ConfigParser()
        setting.optionxform = str
        setting.read(AppSettings.SETTING_PATH, encoding="utf-8")
        general = setting["General Setting"]
        return general.getint("com_port"), general.get("com_port_name"), general.getint("baud_rate")

    def LINE_text(self, txt: str, token: str = "token") -> None:
        """
        LINE にテキストを通知する(送れなくても、例外は出さない)
        txt: 送る文。token: 設定ファイルに書いてある、トークンの名前
        """
        # 送信
        try:
            self.Line.send_message(txt, token=token)
        except Exception:
            pass

    def _discordNotify(self, content: str) -> bool:
        """
        開始・終了の通知を、既定の通知先(DISCORD_WEBHOOK)に送る。送信できたかを返す。
        Notification タブで選んだ画像(画面 / ウィンドウ全体)を付ける。画像を取り出せないときは、文字だけを送る
        """
        provider = type(self)._notification_image
        image = None
        if provider is not None:
            try:
                image = provider()
            except Exception as e:
                self._logger.warning(f"Failed to get the image for the notification: {e}")
        if image is None:
            return self.discord_text(content)
        keys = self._discordKeys(0, DEFAULT_DISCORD_WEBHOOK, None)
        if keys is None:
            return False
        try:
            return bool(self.Discord.send_message(notification_message=content, image=image, keys=keys))
        except Exception:
            return False

    def _discordKeys(self, index: int, keys: str | list, name: str | None) -> str | list | None:
        """
        discord_text / discord_image の送り先を決める(送り先が無い場合はNone)。
        name・keys は通知先の名前(同じ役割)で、index(0始まりの番号)より優先する。
        keys にリストや "ALL" を渡した場合は、そのまま複数の通知先に送る
        戻り値: 通知先の名前、名前のリスト、または "ALL"
        """
        if name is None and keys != DEFAULT_DISCORD_WEBHOOK:
            if not isinstance(keys, str) or keys == "ALL":
                return keys
            name = keys
        return self.Discord.resolve(index, name)

    def discord_text(
        self, content: str = "", index: int = 0, keys: str | list = DEFAULT_DISCORD_WEBHOOK, name: Optional[str] = None
    ) -> bool:
        """
        Discordにテキストを通知する。
        content: 送る文
        index: 通知先の番号(0始まり。0は DISCORD_WEBHOOK、1以降は設定ファイルに書かれている順)
        keys / name: 通知先の名前(どちらで指定しても同じ)。index より優先する。
                     その名前の通知先が無い場合は、index の通知先に送る
        戻り値: 送信できたか
        """
        keys = self._discordKeys(index, keys, name)
        if keys is None:
            return False
        try:
            return bool(self.Discord.send_message(notification_message=content, keys=keys))
        except Exception:
            return False


# crop_fmt に文字列で指定できる値
CROP_FORMAT_NAMES = ("", "1", "2", "3", "4", "11", "12", "13", "14")


def generateRandomCharacter(n: int) -> str:
    """
    指定数のランダムな文字列を生成する(半角の英字と数字で、n 文字)
    Contributor: kochan (敬称略)
    """
    c = string.ascii_lowercase + string.ascii_uppercase + string.digits
    return "".join([random.choice(c) for _ in range(n)])


def convertCv2Format(crop_fmt: int | str = "", crop: List[int] = []) -> Tuple[List[int], List[int]]:
    """
    リストをopencv/pillow形式に対応するよう変換する。
    ・Pillow形式
    x軸(横軸),y軸(縦軸),画像の左上が原点
    crop_fmt=1: [x軸始点, y軸始点, x軸終点, y軸終点] (res_pillowとして出力されるリスト)
    crop_fmt=2: [x軸始点, y軸始点, トリミング後の画像のサイズ(横), トリミング後の画像のサイズ(縦)]
    crop_fmt=3: [x軸始点, x軸終点, y軸始点, y軸終点]
    crop_fmt=4: [x軸始点, トリミング後の画像のサイズ(横), y軸始点, トリミング後の画像のサイズ(縦)]
    ・opencv形式(y, xの順番)
    crop_fmt=11: [y軸始点, x軸始点, y軸終点, x軸終点]
    crop_fmt=12: [y軸始点, x軸始点, トリミング後の画像のサイズ(縦), トリミング後の画像のサイズ(横)]
    crop_fmt=13: [y軸始点, y軸終点, x軸始点, x軸終点] (res_cv2として出力されるリスト)
    crop_fmt=14: [y軸始点, トリミング後の画像のサイズ(縦), x軸始点, トリミング後の画像のサイズ(横)]
    上のどれでもない crop_fmt(省略時の "" を含む)は、crop_fmt=1 と同じ扱い。
    戻り値: (res_cv2, res_pillow)。crop が空・要素が足りない場合は、どちらも空のリスト(トリミングしない)
    """

    try:
        # pillow形式
        if crop_fmt == 1 or crop_fmt == "1":
            res_cv2 = [crop[1], crop[3], crop[0], crop[2]]
        elif crop_fmt == 2 or crop_fmt == "2":
            res_cv2 = [crop[1], crop[1] + crop[3], crop[0], crop[0] + crop[2]]
        elif crop_fmt == 3 or crop_fmt == "3":
            res_cv2 = [crop[2], crop[3], crop[0], crop[1]]
        elif crop_fmt == 4 or crop_fmt == "4":
            res_cv2 = [crop[2], crop[2] + crop[3], crop[0], crop[0] + crop[1]]
        # opencv形式
        elif crop_fmt == 11 or crop_fmt == "11":
            res_cv2 = [crop[0], crop[2], crop[1], crop[3]]
        elif crop_fmt == 12 or crop_fmt == "12":
            res_cv2 = [crop[0], crop[0] + crop[2], crop[1], crop[1] + crop[3]]
        elif crop_fmt == 13 or crop_fmt == "13":
            res_cv2 = [crop[0], crop[1], crop[2], crop[3]]
        elif crop_fmt == 14 or crop_fmt == "14":
            res_cv2 = [crop[0], crop[0] + crop[1], crop[2], crop[2] + crop[3]]
        else:
            res_cv2 = [crop[1], crop[3], crop[0], crop[2]]
        res_pillow = [res_cv2[2], res_cv2[0], res_cv2[3], res_cv2[1]]
    except Exception:
        res_cv2 = []
        res_pillow = []

    return res_cv2, res_pillow


class ImageProcPythonCommand(PythonCommand):
    """
    画像認識を使う自動化スクリプトの基底クラス(キャプチャーの画像の取得、テンプレートマッチング、画像の通知など)。

    template_path_name / capture_path_name: テンプレート画像と、保存するキャプチャーの、既定のフォルダー
    """

    template_path_name = "./Template/"
    capture_path_name = "./Captures/"

    def __init__(self, cam: Camera, gui: CaptureArea | None = None) -> None:
        """
        cam: キャプチャーの画像を読むカメラ
        gui: 四角形や文字を重ねて表示する、プレビューの画面(ImgRect / ImgText を持つもの。
             Web ブラウザ版では、同じ関数を持つ別のクラス)。None: Command.canvas を使う
        """
        super(ImageProcPythonCommand, self).__init__()

        self._logger = _logger

        self.camera = cam
        self.gui = gui

    def pausedecorator2(func: Callable[..., Any]) -> Callable[..., Any]:
        """
        一時停止を実現するためのデコレータです(画像認識の関数に使用します)。
        一時停止が要求されていれば、一時停止してから処理します。
        (処理の後に一時停止すると、再開後に、一時停止する前の画面で判定した結果を返すことになるため)
        """

        def inner(self: ImageProcPythonCommand, *args: Any, **kwargs: Any) -> Any:
            """一時停止が要求されていれば待ってから、元の関数を呼び、その戻り値を返す"""
            self.waitWhilePaused()
            return func(self, *args, **kwargs)

        return inner

    # 戻り値が3つある関数用(処理は pausedecorator2 と同じ)
    pausedecorator3 = pausedecorator2

    def get_filespec(self, filename: str, mode: str = "t") -> str:
        """
        画像ファイルの保存パスを取得する。

        入力が絶対パスの場合は、modeに合わせて、`template_path_name/capture_path_name`につなげずに返す。

        Args:
            filename (str): 保存名／保存パス
            mode (str): 相対パスの種類("t": テンプレートのフォルダー、"c": キャプチャーのフォルダー。
                        それ以外: フォルダーをつなげない)

        Returns:
            str: フォルダーをつなげたパス
        """
        if os.path.isabs(filename):
            return filename
        elif mode == "c":
            return os.path.join(self.capture_path_name, filename)
        elif mode == "t":
            return os.path.join(self.template_path_name, filename)
        else:
            return filename

    def setTemplateDir(self, path: str) -> None:
        """
        テンプレート画像のフォルダーを変える(すべての画像認識コマンドで共通。
        コマンドを始めるたびに、既定の "./Template/" に戻る)
        """
        ImageProcPythonCommand.template_path_name = path

    def getInterframeDiff(
        self,
        frame1: ImageProcessing.image_type,
        frame2: ImageProcessing.image_type,
        frame3: ImageProcessing.image_type,
        threshold: float,
    ) -> ImageProcessing.image_type:
        """
        フレーム間差分により2値化された画像を取得する(連続する3枚の画像で、動いた部分が白くなる)
        frame1 - frame3: 続けて取った 3 枚の画像。threshold: 2 値化のしきい値(0 - 255)
        """
        return _getInterframeDiff(frame1, frame2, frame3, threshold)

    def getCameraImage(self, crop_fmt: int | str = "", crop: List[int] = []) -> ImageProcessing.image_type | None:
        """
        カメラから画像データを取得する
        crop_fmt / crop: トリミングの範囲と、その書き方(convertCv2Format を参照。省略時はトリミングしない)
        戻り値: BGR の画像(カメラの画像を取れない場合は None)
        """
        # crop_fmtに応じてcropの中身を並び替える
        crop_cv2, _ = convertCv2Format(crop_fmt=crop_fmt, crop=crop)

        # カメラの画像を取得
        src = self.camera.readFrame()

        # トリミング
        cropped_image = crop_image(src, crop=crop_cv2)

        return cropped_image

    def openImage(self, filename: str, mode: str = "t") -> ImageProcessing.image_type | None:
        """
        指定されたパスの画像データを取得する
        filename / mode: get_filespec と同じ。戻り値: BGR の画像(読めない場合は、その旨を表示して None)
        """
        image = getImage(self.get_filespec(filename, mode=mode), mode="color")
        return image

    @pausedecorator2
    def isContainTemplate(
        self,
        template_path: str | ImageProcessing.image_type,
        threshold: float = 0.7,
        use_gray: bool = True,
        show_value: bool = False,
        show_position: bool = True,
        show_only_true_rect: bool = True,
        ms: float = 2000,
        crop_fmt: int | str = "",
        crop: List[int] = [],
        mask_path: str | ImageProcessing.image_type | None = None,
        use_gpu: bool = False,
        BGR_range: Optional[dict] = None,
        threshold_binary: Optional[int] = None,
        crop_template: List[int] = [],
        show_image: bool = False,
        color: List[str] = ["blue", "red", "orange"],
    ) -> bool:
        """
        現在のスクリーンショットと指定した画像のテンプレートマッチングを行います。
        色の違いを考慮しないのであればパフォーマンスの点からuse_grayをTrueにしてグレースケール画像を使うことを推奨します。

        template_path: テンプレート画像のパス(テンプレートのフォルダーから)。画像(ndarray)も渡せる
        threshold: 類似度のしきい値(類似度が、これより大きければ True)
        use_gray: グレースケールにして比べるか
        show_value: 類似度を表示するか(画面の設定で、常に表示することもできる)
        show_position: 見つけた位置を、プレビューに四角形で表示するか
        show_only_true_rect: True では、見つかった場合だけ四角形を表示する
        ms: 四角形を表示する時間(ミリ秒)
        crop_fmt / crop: スクリーンショットの中の、探す範囲と、その書き方(convertCv2Format を参照)
        mask_path: マスク画像のパス(画像も渡せる)。None: マスクを使わない
        use_gpu: GPU を使うか(マスクは使えない)
        BGR_range: use_gray が False のとき、{"lower": [B, G, R], "upper": [B, G, R]} の色の範囲で 2 値化する
        threshold_binary: 2 値化のしきい値(0 - 255)。None: 2 値化しない
        crop_template: テンプレート画像を切り出す範囲(書き方は crop_fmt)
        show_image: 加工した後のスクリーンショットを、ウィンドウに表示するか(確認用。キーを押すまで止まる)
        color: 四角形の色 [見つかった場合, 見つからなかった場合, 探した範囲]
        戻り値: 見つかったか
        """

        # crop_fmtに応じてcropの中身を並び替える
        crop_cv2, crop_pillow = convertCv2Format(crop_fmt=crop_fmt, crop=crop)
        crop_template_cv2, _ = convertCv2Format(crop_fmt=crop_fmt, crop=crop_template)

        # カメラの画像を取得
        src = self.camera.readFrame()

        # テンプレート画像を取得
        if isinstance(template_path, ImageProcessing.image_type):
            template_image = template_path
        else:
            template_image = getImage(self.get_filespec(template_path, mode="t"), mode="color")

        # マスク画像を取得
        if isinstance(mask_path, ImageProcessing.image_type):
            mask_image = mask_path
        else:
            mask_image = (
                getImage(self.get_filespec(mask_path, mode="t"), mode="binary") if mask_path is not None else None
            )

        # テンプレートマッチング
        res, max_loc, width, height, max_val = ImageProcessing(use_gpu=use_gpu).isContainTemplate(
            src,
            template_image,
            mask_image=mask_image,
            threshold=threshold,
            use_gray=use_gray,
            crop=crop_cv2,
            BGR_range=BGR_range,
            threshold_binary=threshold_binary,
            crop_template=crop_template_cv2,
            show_image=show_image,
        )

        # テンプレートマッチングの結果(類似度)を表示する
        if show_value or self.isSimilarity:
            tm_mode = "NCC" if mask_path is not None else "ZNCC"
            print(f"{template_path} {tm_mode} value: {max_val}")

        # canvasに検出位置を表示
        if show_position:
            if crop_pillow != []:
                max_loc = list(max_loc)
                max_loc[0] += crop_pillow[0]
                max_loc[1] += crop_pillow[1]
            tag = str(time.perf_counter()) + str(random.random())
            if res:
                self.displayRectangle(max_loc, width, height, tag, ms, color=[color[0], color[2]], crop=crop_pillow)
            elif not show_only_true_rect:
                self.displayRectangle(max_loc, width, height, tag, ms, color=[color[1], color[2]], crop=crop_pillow)
            else:
                pass

        return res

    @pausedecorator3
    def isContainTemplate_max(
        self,
        template_path_list: List[str | ImageProcessing.image_type],
        threshold: float = 0.7,
        use_gray: bool = True,
        show_value: bool = False,
        show_position: bool = True,
        show_only_true_rect: bool = True,
        ms: float = 2000,
        crop_fmt: int | str = "",
        crop: List[int] = [],
        mask_path_list: List[str | ImageProcessing.image_type] = [],
        BGR_range: Optional[dict] = None,
        threshold_binary: Optional[int] = None,
        crop_template: List[int] = [],
        show_image: bool = False,
        color: List[str] = ["blue", "red", "orange"],
    ) -> Tuple[int, List[float], List[bool]]:
        """
        # 現在のスクリーンショットと指定した複数の画像のテンプレートマッチングを行います。
        # 相関値が最も大きい値となった画像のインデックス、各画像のテンプレートマッチングの閾値、閾値判定結果を返します。
        # 色の違いを考慮しないのであればパフォーマンスの点からuse_grayをTrueにしてグレースケール画像を使うことを推奨します。

        template_path_list: テンプレート画像のパス(または画像)のリスト
        mask_path_list: マスク画像のパス(または画像)のリスト(空: マスクを使わない)
        そのほかの引数は isContainTemplate と同じ(GPU は使わない)
        戻り値: (類似度が最も大きい画像の番号, 画像ごとの類似度のリスト, 画像ごとの、しきい値を超えたかのリスト)
        """

        # crop_fmtに応じてcropの中身を並び替える
        crop_cv2, crop_pillow = convertCv2Format(crop_fmt=crop_fmt, crop=crop)
        crop_template_cv2, _ = convertCv2Format(crop_fmt=crop_fmt, crop=crop_template)

        # カメラの画像を取得
        src = self.camera.readFrame()

        # テンプレート画像を取得
        template_image_list = []
        for i in template_path_list:
            if isinstance(i, ImageProcessing.image_type):
                template_image_list.append(i)
            else:
                template_image_list.append(getImage(self.get_filespec(i, mode="t"), mode="color"))

        # マスク画像を取得
        mask_image_list = []
        if mask_path_list is not None:
            for i in mask_path_list:
                if isinstance(i, ImageProcessing.image_type):
                    mask_image_list.append(i)
                else:
                    mask_image_list.append(getImage(self.get_filespec(i, mode="t"), mode="binary"))

        # テンプレートマッチング
        max_idx, max_val_list, max_loc_list, width_list, height_list, judge_list = ImageProcessing(
            use_gpu=False
        ).isContainTemplate_max(
            src,
            template_image_list,
            mask_image_list=mask_image_list,
            threshold=threshold,
            use_gray=use_gray,
            crop=crop_cv2,
            BGR_range=BGR_range,
            threshold_binary=threshold_binary,
            crop_template=crop_template_cv2,
            show_image=show_image,
        )

        # テンプレートマッチングの結果(類似度)を表示する
        if show_value or self.isSimilarity:
            tm_mode = "ZNCC" if (mask_path_list == [] or mask_path_list is None) else "NCC"
            for template_path, max_val in zip(template_path_list, max_val_list):
                print(f"{template_path} {tm_mode} value: {max_val}")

        # canvasに検出位置を表示
        if show_position:
            if crop_pillow != []:
                max_loc_list[max_idx] = list(max_loc_list[max_idx])
                max_loc_list[max_idx][0] += crop_pillow[0]
                max_loc_list[max_idx][1] += crop_pillow[1]
            tag = str(time.perf_counter()) + str(random.random())
            if True in judge_list:
                self.displayRectangle(
                    max_loc_list[max_idx],
                    width_list[max_idx],
                    height_list[max_idx],
                    tag,
                    ms,
                    color=[color[0], color[2]],
                    crop=crop_pillow,
                )
            elif not show_only_true_rect:
                self.displayRectangle(
                    max_loc_list[max_idx],
                    width_list[max_idx],
                    height_list[max_idx],
                    tag,
                    ms,
                    color=[color[1], color[2]],
                    crop=crop_pillow,
                )
            else:
                pass

        return max_idx, max_val_list, judge_list

    @pausedecorator2
    def isContainTemplateGPU(
        self,
        template_path: str | ImageProcessing.image_type,
        threshold: float = 0.7,
        use_gray: bool = True,
        show_value: bool = False,
        show_position: bool = True,
        show_only_true_rect: bool = True,
        ms: float = 2000,
        crop_fmt: int | str = "",
        crop: List[int] = [],
        mask_path: str | ImageProcessing.image_type | None = None,
        BGR_range: Optional[dict] = None,
        threshold_binary: Optional[int] = None,
        crop_template: List[int] = [],
        show_image: bool = False,
        color: List[str] = ["blue", "red", "orange"],
    ) -> bool:
        """
        現在のスクリーンショットと指定した画像のテンプレートマッチングを行います。
        テンプレートマッチングにGPUを使用します。
        色の違いを考慮しないのであればパフォーマンスの点からuse_grayをTrueにしてグレースケール画像を使うことを推奨します。
        引数と戻り値は isContainTemplate と同じ(use_gpu は、常に True)
        """
        # テンプレートマッチング
        res = self.isContainTemplate(
            template_path,
            threshold=threshold,
            use_gray=use_gray,
            show_value=show_value,
            show_position=show_position,
            show_only_true_rect=show_only_true_rect,
            ms=ms,
            crop_fmt=crop_fmt,
            crop=crop,
            mask_path=mask_path,
            use_gpu=True,
            BGR_range=BGR_range,
            threshold_binary=threshold_binary,
            crop_template=crop_template,
            show_image=show_image,
            color=color,
        )

        return res

    @pausedecorator2
    def isContainedImage(
        self,
        image_path: str | ImageProcessing.image_type,
        threshold: float = 0.7,
        use_gray: bool = True,
        show_value: bool = False,
        show_position: bool = True,
        show_only_true_rect: bool = True,
        ms: float = 2000,
        crop_fmt: int | str = "",
        crop: List[int] = [],
        mask_path: str | ImageProcessing.image_type | None = None,
        use_gpu: bool = False,
        BGR_range: Optional[dict] = None,
        threshold_binary: Optional[int] = None,
        crop_template: List[int] = [],
        show_image: bool = False,
        color: List[str] = ["blue", "red", "orange"],
    ) -> bool:
        """
        指定した画像に対して現在のスクリーンショットから生成したテンプレート画像を用いてテンプレートマッチングを行います。
        色の違いを考慮しないのであればパフォーマンスの点からuse_grayをTrueにしてグレースケール画像を使うことを推奨します。

        image_path: 探される側の画像のパス(テンプレートのフォルダーから)。画像(ndarray)も渡せる
        crop: image_path の画像の中の、探す範囲
        crop_template: スクリーンショットから、テンプレートとして切り出す範囲(四角形も、この位置に表示する)
        そのほかの引数と戻り値は isContainTemplate と同じ
        """

        # crop_fmtに応じてcropの中身を並び替える
        crop_cv2, crop_pillow = convertCv2Format(crop_fmt=crop_fmt, crop=crop)
        crop_template_cv2, crop_template_pillow = convertCv2Format(crop_fmt=crop_fmt, crop=crop_template)

        # カメラの画像を取得
        template_image = self.camera.readFrame()

        # テンプレートマッチング対象画像を取得
        if isinstance(image_path, ImageProcessing.image_type):
            image = image_path
        else:
            image = getImage(self.get_filespec(image_path, mode="t"), mode="color")

        # マスク画像を取得
        if isinstance(mask_path, ImageProcessing.image_type):
            mask_image = mask_path
        else:
            mask_image = (
                getImage(self.get_filespec(mask_path, mode="t"), mode="binary") if mask_path is not None else None
            )

        # テンプレートマッチング
        res, _, width, height, max_val = ImageProcessing(use_gpu=use_gpu).isContainTemplate(
            image,
            template_image,
            mask_image=mask_image,
            threshold=threshold,
            use_gray=use_gray,
            crop=crop_cv2,
            BGR_range=BGR_range,
            threshold_binary=threshold_binary,
            crop_template=crop_template_cv2,
            show_image=show_image,
        )

        # テンプレートマッチングの結果(類似度)を表示する
        if show_value or self.isSimilarity:
            tm_mode = "NCC" if mask_path is not None else "ZNCC"
            print(f"capture_image {tm_mode} value: {max_val}")

        # canvasに検出位置を表示
        if show_position:
            tag = str(time.perf_counter()) + str(random.random())
            # crop_template を省略したとき(スクリーンショットの全体がテンプレート)は、左上の角から表示する
            position = crop_template_pillow[0:2] if len(crop_template_pillow) >= 2 else [0, 0]
            if res:
                self.displayRectangle(position, width, height, tag, ms, color=[color[0], color[2]], crop=[])
            elif not show_only_true_rect:
                self.displayRectangle(position, width, height, tag, ms, color=[color[1], color[2]], crop=[])
            else:
                pass

        return res

    def displayRectangle(
        self,
        max_loc: tuple | list,
        width: int,
        height: int,
        tag: str | None = None,
        ms: float = 2000,
        color: List[str] = ["blue", "orange"],
        crop_fmt: int | str = "",
        crop: List[int] = [],
    ) -> None:
        """
        GUIの画面に四角形を表示します。
        互換性維持のため、gui/canvas(元をたどると同じ変数)の両方に対応します。

        max_loc: 四角形の左上の位置 (x, y)(キャプチャーの画像の座標)
        width / height: 四角形の大きさ
        tag: 四角形に付ける名前(None: ランダムな文字列)
        ms: 表示する時間(ミリ秒)
        color: [四角形の色, crop の範囲の色]
        crop_fmt / crop: 一緒に表示する範囲と、その書き方(convertCv2Format を参照。省略時は表示しない)
        (gui を渡していない場合は、画面のガイドの表示がオンのときだけ表示する)
        """
        # crop_fmtに応じてcropの中身を並び替える
        _, crop_pillow = convertCv2Format(crop_fmt=crop_fmt, crop=crop)

        top_left = max_loc
        bottom_right = (top_left[0] + width + 1, top_left[1] + height + 1)
        if self.gui is not None:
            canvas = self.gui
        else:
            canvas = self.canvas

        if tag is None:
            tag = generateRandomCharacter(10)

        if self.gui is not None or self.isGuide:
            if crop_pillow != []:
                canvas.ImgRect(*crop_pillow[0:2], *crop_pillow[2:4], outline=color[1], tag=tag, ms=int(ms), flag=False)
            canvas.ImgRect(*top_left, *bottom_right, outline=color[0], tag=tag, ms=int(ms))
        else:
            pass

    def displayText(
        self,
        position: tuple | list,
        txt: str,
        tag: str | None = None,
        ms: int = 2000,
        font: str = "UD デジタル 教科書体 NP-B",
        fontsize: int = 20,
        color: str = "black",
    ) -> None:
        """
        GUIの画面に文字を表示します。

        position: 文字の位置 (x, y)(キャプチャーの画像の座標)
        txt: 表示する文字
        tag: 文字に付ける名前(None: ランダムな文字列)
        ms: 表示する時間(ミリ秒)
        font / fontsize / color: フォントの名前、大きさ、色
        (gui を渡していない場合は、画面のガイドの表示がオンのときだけ表示する)
        """
        if self.gui is not None:
            canvas = self.gui
        else:
            canvas = self.canvas

        ft = (font, fontsize)

        if tag is None:
            tag = generateRandomCharacter(10)

        if self.gui is not None or self.isGuide:
            canvas.ImgText(position[0], position[1], txt=txt, tag=tag, ms=int(ms), ft=ft, color=color)
        else:
            pass

    def saveCapture(
        self, filename: str | None = None, crop_fmt: int | str = "", crop: List[int] = [], mode: bool = True
    ) -> None:
        """
        画面をキャプチャします。
        (camera.saveCaptureと同じ機能。)

        filename: 保存する名前(拡張子 .png は、自動で付く)。None や空: 今の日時
        crop_fmt / crop: 保存する範囲と、その書き方(convertCv2Format を参照。省略時は全体)
        mode: True: キャプチャーのフォルダーに保存する。False: filename を、そのままパスとして使う
        """

        # crop_fmtに応じてcropの中身を並び替える
        crop_cv2, _ = convertCv2Format(crop_fmt=crop_fmt, crop=crop)

        # カメラの画像を取得
        src = self.camera.readFrame()

        # ファイル名を設定する
        if filename is None or filename == "":
            dt_now = datetime.datetime.now()
            filename = dt_now.strftime("%Y-%m-%d_%H-%M-%S") + ".png"
        else:
            filename = filename + ".png"
        if mode:
            save_path = self.get_filespec(filename, mode="c")
        else:
            save_path = self.get_filespec(filename, mode="n")

        # 画像を保存する
        ImageProcessing().saveImage(src, filename=save_path, crop=crop_cv2)

    def popupImage(self, crop_fmt: int | str = "", crop: List[int] = [], title: str = "image") -> None:
        """
        popupで画像を表示する(今のキャプチャーの画像。キーを押すまで、スクリプトは止まる)
        crop_fmt / crop: 表示する範囲と、その書き方(convertCv2Format を参照)。title: ウィンドウの名前
        """
        # crop_fmtに応じてcropの中身を並び替える
        crop_cv2, _ = convertCv2Format(crop_fmt=crop_fmt, crop=crop)

        # カメラの画像を取得
        src = self.camera.readFrame()

        opneImage(src, crop=crop_cv2, title=title)

    def LINE_image(self, txt: str, crop_fmt: int | str = "", crop: List[int] = [], token: str = "token") -> None:
        """
        Lineにテキストと画像を通知します。(送れなくても、例外は出しません)
        txt: 送る文。crop_fmt / crop: 送る画像の範囲と、その書き方(convertCv2Format を参照)
        token: 設定ファイルに書いてある、トークンの名前
        """
        # crop_fmtに応じてcropの中身を並び替える
        crop_cv2, _ = convertCv2Format(crop_fmt=crop_fmt, crop=crop)

        # カメラの画像を取得
        src = self.camera.readFrame()

        # トリミング
        cropped_image = crop_image(src, crop=crop_cv2)

        # 送信
        try:
            self.Line.send_message(txt, cropped_image, token)
        except Exception:
            pass

    def discord_image(
        self,
        content: str = "",
        index: int = 0,
        crop_fmt: int | str = "",
        crop: List[int] = [],
        keys: str | list = DEFAULT_DISCORD_WEBHOOK,
        name: Optional[str] = None,
    ) -> bool:
        """
        Discordにテキストと画像を通知する。
        content: 送る文
        crop_fmt / crop: 送る画像の範囲と、その書き方(convertCv2Format を参照。省略時は全体)
        index: 通知先の番号(0始まり。0は DISCORD_WEBHOOK、1以降は設定ファイルに書かれている順)
        keys / name: 通知先の名前(どちらで指定しても同じ)。index より優先する。
                     その名前の通知先が無い場合は、index の通知先に送る
        戻り値: 送信できたか
        """
        # discord_image(content, index, name) の順で通知先の名前を渡された場合(crop_fmt には無い文字列)
        if isinstance(crop_fmt, str) and crop_fmt not in CROP_FORMAT_NAMES:
            name, crop_fmt = crop_fmt, ""
        # crop_fmtに応じてcropの中身を並び替える
        crop_cv2, _ = convertCv2Format(crop_fmt=crop_fmt, crop=crop)

        # カメラの画像を取得
        src = self.camera.readFrame()

        # トリミング
        cropped_image = crop_image(src, crop=crop_cv2)

        keys = self._discordKeys(index, keys, name)
        if keys is None:
            return False
        try:
            return bool(self.Discord.send_message(notification_message=content, image=cropped_image, keys=keys))
        except Exception:
            return False
