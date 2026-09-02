import logging
import threading
import time
from abc import ABC, abstractmethod
from time import sleep
from typing import Callable, Never

from pokecontrollerext.api.v0_1_8.command.commands.base import (
    Command,
    PostProcess,
)
from pokecontrollerext.api.v0_1_8.command.commands.python.decorators import (
    pausable,
)
from pokecontrollerext.api.v0_1_8.command.keys import (
    ButtonLike,
    KeyPress,
)
from pokecontrollerext.api.v0_1_8.command.sender import Sender
from pokecontrollerext.api.v0_1_8.notification.discord import (
    Discord_Notify,
)
from pokecontrollerext.api.v0_1_8.notification.line import (
    Line_Notify,
)
from pokecontrollerext.api.v0_1_8.settings import GuiSettings
from pokecontrollerext.singletons.app.command import get_app_command_state

try:
    from plyer import notification

    flag_import_plyer = True
except ImportError:
    flag_import_plyer = False

logger = logging.getLogger(__name__)


class StopThread(Exception):
    pass


class PythonCommand(Command, ABC):
    def __init__(self) -> None:
        super().__init__()
        self._command_state = get_app_command_state()

        self.keys: KeyPress | None = None
        self.thread: threading.Thread | None = None
        self.alive = True
        self.isPause = False
        self.postProcess: PostProcess | None = None
        self.Line: Line_Notify | None = None
        self.Discord: Discord_Notify | None = None
        try:
            self.Line = Line_Notify()
        except Exception:
            pass
        try:
            self.Discord = Discord_Notify()
        except Exception:
            pass

    @abstractmethod
    def do(self) -> None:
        """
        自動化スクリプト側でオーバーライトされるため、処理の記述はありません。
        """
        pass

    def do_safe(self, ser: Sender) -> None:
        """
        自動化スクリプト実行準備→実行→終了処理を順番に行います。
        """
        if self.keys is None:
            self.keys = keys = KeyPress(ser)
            keys.init_hat()

        def do_after_notify() -> None:
            if self.alive:
                self._notify_when_started()
                self.do()

        self._call_safe(ser, do_after_notify)
        self._call_safe(ser, self.finish)
        self._call_safe(ser, self._notify_when_ended)
        self._command_state.finish()

    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        """
        自動化スクリプトをスレッドに割り当てて実行します。
        """
        self._command_state.start()
        self.alive = True
        if (socket := self.socket0) is not None:
            socket.alive = True
        if (mqtt := self.mqtt0) is not None:
            mqtt.alive = True
        self.postProcess = postProcess
        if self.thread is None:
            self.thread = thread = threading.Thread(
                target=self.do_safe,
                args=(ser,),
            )
            thread.start()

    def end(self, ser: Sender | None = None) -> Never:
        if (socket := self.socket0) is not None:
            socket.alive = False
        if (mqtt := self.mqtt0) is not None:
            mqtt.alive = False
        self.sendStopRequest()
        logger.info("Exit from command successfully")
        raise StopThread("exit successfully")

    def finish(self) -> Never:
        """
        自動化スクリプトを終了します。(自動化スクリプト内で意図的に終了したい場合に使用。)
        """
        self.alive = False
        self.end()

    def checkIfAlive(self) -> bool:
        """
        Aliveフラグの状態を確認する。
        AliveフラグがFalseなら終了処理を行う。
        """
        if self.alive:
            return True

        if (keys := self.keys) is None:
            logger.warning("keys is None")
        else:
            keys.end()
            self.keys = None

        self.thread = None

        if (proc := self.postProcess) is not None:
            proc()
            self.postProcess = None
        else:
            logger.info("postProcess is None")

        # raise exception for exit working thread
        logger.info("Exit from command successfully")
        raise StopThread("exit successfully")

    def sendStopRequest(self) -> None:
        if self.checkIfAlive():  # try if we can stop now
            self.alive = False
            print("-- sent a stop request. --")
            logger.info("Sending stop request")
        if (socket := self.socket0) is None:
            logger.warning("socket0 client is not initialized.")
        elif socket.flag_socket:
            self.socket_disconnect()

    def show_var(self) -> None:
        """
        一時停止時に内部変数の一覧を表示します。
        表示対象は自動化スクリプト側でselfにて定義した変数のみです。
        """
        var_dict = vars(self)  # 重い
        del_dict = [
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
        ]
        print("--------内部変数一覧--------")
        for k, v in var_dict.items():
            if k not in del_dict:
                print(k, "=", v)
        print("----------------------------")

    @pausable
    def press(
        self,
        buttons: ButtonLike | list[ButtonLike],
        duration: float = 0.1,
        wait: float = 0.1,
    ) -> None:
        """
        ボタンを押す。
        """
        if (keys := self.keys) is None:
            logger.warning("keys is None")
        else:
            keys.input(buttons)
            self.wait(duration)
            keys.inputEnd(buttons)
            self.wait(wait)
        self.checkIfAlive()

    def pressRep(
        self,
        buttons: ButtonLike | list[ButtonLike],
        repeat: int,
        duration: float = 0.1,
        interval: float = 0.1,
        wait: float = 0.1,
    ) -> None:
        """
        ボタンを複数回押す。
        """
        for i in range(0, repeat):
            self.press(buttons, duration, 0 if i == repeat - 1 else interval)
        self.wait(wait)

    @pausable
    def hold(
        self,
        buttons: ButtonLike | list[ButtonLike],
        wait: float = 0.1,
    ) -> None:
        """
        ボタンを押したままの状態にする。
        """
        if (keys := self.keys) is None:
            logger.warning("keys is None")
        else:
            keys.hold(buttons)
        self.wait(wait)

    def holdEnd(
        self,
        buttons: ButtonLike | list[ButtonLike],
    ) -> None:
        """
        ボタンを離した状態にする。
        """
        if (keys := self.keys) is None:
            logger.warning("keys is None")
        else:
            keys.holdEnd(buttons)
        self.checkIfAlive()

    @pausable
    def short_wait(self, wait: float) -> None:
        """
        指定時間待機する。
        """
        current_time = time.perf_counter()
        while time.perf_counter() < current_time + wait:
            pass
        self.checkIfAlive()

    @pausable
    def wait(self, wait: float) -> None:
        """
        指定時間待機する。
        """
        if float(wait) > 0.1:
            sleep(wait)
        else:
            current_time = time.perf_counter()
            while time.perf_counter() < current_time + wait:
                pass
        self.checkIfAlive()

    def direct_serial(self, serialcommands: list, waittime: list) -> None:
        if (keys := self.keys) is None:
            logger.warning("keys is None")
            return

        # 余計なものが付いている可能性があるので確認して削除する
        checkedcommands = [
            row.replace("\r", "").replace("\n", "") for row in serialcommands
        ]
        keys.serialcommand_direct_send(checkedcommands, waittime)

    # temporary function
    def reload_com_port(self) -> None:
        if (keys := self.keys) and keys.ser.isOpened():
            logger.info("Port is already opened and being closed.")
            keys.ser.closeSerial()
            # self.keyPress = None (ここでNoneはNGなはず)
            self.reload_com_port()
        else:
            settings = GuiSettings()
            port = settings.com_port.get()
            port_name = settings.com_port_name.get()
            baud_rate = settings.baud_rate.get()
            if (keys := self.keys) and keys.ser.openSerial(
                port,
                port_name,
                baud_rate,
            ):
                print(f"COM Port {port} connected successfully")
                logger.debug(f"COM Port {port} connected successfully")
                # self.keyPress = None (ここでNoneはNGなはず)

    def LINE_text(self, txt: str, token: str = "token") -> None:
        # 送信
        if (line := self.Line) is None:
            logger.warning("Line is not initialized.")
            return
        try:
            line.send_message(txt, token=token)
        except Exception:
            logger.error("failed to send LINE message.")
            pass

    def discord_text(
        self, content: str = "", index: int = 0, keys: str = "DISCORD_WEBHOOK"
    ) -> None:
        # webhook_urlのindex指定とkey設定
        if index != 0 and keys == "DISCORD_WEBHOOK":
            keys = f"DISCORD_WEBHOOK{index}"
        elif index == 0 and keys != "DISCORD_WEBHOOK":
            pass
        elif index != 0 and keys != "DISCORD_WEBHOOK":
            keys = f"DISCORD_WEBHOOK{index}"
        else:
            pass

        # 送信
        if (notifier := self.Discord) is not None:
            try:
                notifier.send_message(notification_message=content, keys=keys)
            except Exception:
                pass

    def _notify_when_started(self) -> None:
        global flag_import_plyer
        title = f"{self.app_name} (profile:{self.profilename})"
        message = f"{self.cur_command_name} started."
        if self.isWinNotStart:
            if flag_import_plyer:
                notification.notify(
                    title=title,
                    message=message,
                    timeout=5,
                )
            else:
                print('"plyer" is not installed.')
        if self.isLineNotStart:
            self.LINE_text(f"{title}\n{message}")
        if self.isDiscordNotStart:
            self.discord_text(f"{title}\n{message}")

    def _notify_when_ended(self) -> None:
        global flag_import_plyer
        title = f"{self.app_name} (profile:{self.profilename})"
        message = f"{self.cur_command_name} finished."
        if self.isWinNotEnd:
            if flag_import_plyer:
                notification.notify(
                    title=title,
                    message=message,
                    timeout=5,
                )
            else:
                print('"plyer" is not installed.')
        if self.isLineNotEnd:
            self.LINE_text(f"{title}\n{message}")
        if self.isDiscordNotEnd:
            self.discord_text(f"{title}\n{message}")

    def _call_safe(self, sender: Sender, func: Callable[[], None]) -> None:
        try:
            func()
        except StopThread:
            print("-- stopped successfully. --")
            logger.info("Command stopped successfully")
        except Exception as e:
            if self.keys is None:
                self.keys = keys = KeyPress(sender)
                keys.init_hat()
            logger.warning("Interrupt:cmd(黒い画面)を確認してください。")
            logger.warning(e)
            logger.warning("Command stopped unexpectedly")
            import traceback

            traceback.print_exc()
            self.keys.end()
            self.alive = False
