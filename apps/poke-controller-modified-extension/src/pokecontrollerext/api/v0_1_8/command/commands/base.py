import logging
import os
import tkinter as tk
from abc import ABC, abstractmethod
from typing import Callable, Literal, Never, overload

from pokecontrollerext.api.v0_1_8.command.sender import Sender
from pokecontrollerext.api.v0_1_8.external_tools import (
    MQTTCommunications,
    SocketCommunications,
)
from pokecontrollerext.api.v0_1_8.widgets.dialogue import (
    Message,
    MessageMode1,
    PokeConDialogue,
    check_widget_name,
    generate_new_dialogue_list,
    get_settings_list,
    save_dialogue_settings,
)

PostProcess = Callable[[], None]

logger = logging.getLogger(__name__)


class Command(ABC):
    NAME: str = ""
    text_area_1: tk.Text | None = None
    text_area_2: tk.Text | None = None
    stdout_destination: str = "1"
    pos_dialogue_buttons: str = "2"
    isPause = False
    canvas: tk.Canvas | None = None
    isGuide = False
    isSimilarity = False
    isImage = False
    isWinNotStart = False
    isWinNotEnd = False
    isLineNotStart = False
    isLineNotEnd = False
    isDiscordNotStart = False
    isDiscordNotEnd = False
    app_name = ""
    cur_command_name = ""
    profilename: str | None = None

    def __init__(self) -> None:
        self.isRunning = False

        self.message_dialogue: tk.Toplevel | None = None
        self.socket0: SocketCommunications | None = None
        self.mqtt0: MQTTCommunications | None = None

    @abstractmethod
    def start(
        self,
        ser: Sender,
        postProcess: PostProcess | None = None,
    ) -> None:
        pass

    @abstractmethod
    def end(
        self,
        ser: Sender,
    ) -> None:
        pass

    @abstractmethod
    def finish(self) -> Never:
        pass

    @abstractmethod
    def checkIfAlive(self) -> bool:
        pass

    ############### print functions ###############
    def print_s(self, *objects: object, sep: str = " ", end: str = "\n") -> None:
        logger.info(f"{sep.join((str(obj) for obj in objects))}{end}")

    def print_t1(self, *objects: object, sep: str = " ", end: str = "\n") -> None:
        """
        上側のログ画面に文字列を出力する
        """
        if (text_area := self.text_area_1) is None:
            logger.error("text_area_1 is not initialized.")
            return
        self._print_t(text_area, "a", *objects, sep=sep, end=end)

    def print_t2(self, *objects: object, sep: str = " ", end: str = "\n") -> None:
        """
        下側のログ画面に文字列を出力する
        """
        if (text_area := self.text_area_2) is None:
            logger.error("text_area_2 is not initialized.")
            return
        self._print_t(text_area, "a", *objects, sep=sep, end=end)

    def print_t(self, *objects: object, sep: str = " ", end: str = "\n") -> None:
        if self.stdout_destination == "1":
            self.print_t2(*objects, sep=sep, end=end)
        elif self.stdout_destination == "2":
            self.print_t1(*objects, sep=sep, end=end)

    def print_t1b(
        self,
        mode: Literal["w", "a", "d"],
        *objects: object,
        sep: str = " ",
        end: str = "\n",
    ) -> None:
        """
        上側のログ画面に文字列を出力する
        mode: ['w'/'a'/'d'] 'w'上書き, 'a'追記, 'd'削除
        """
        if (text_area := self.text_area_1) is None:
            logger.error("text_area_1 is not initialized.")
            return
        self._print_t(text_area, mode, *objects, sep=sep, end=end)

    def print_t2b(
        self,
        mode: Literal["w", "a", "d"],
        *objects: object,
        sep: str = " ",
        end: str = "\n",
    ) -> None:
        """
        下側のログ画面に文字列を出力する
        mode: ['w'/'a'/'d'] 'w'上書き, 'a'追記, 'd'削除
        """
        if (text_area := self.text_area_2) is None:
            logger.error("text_area_2 is not initialized.")
            return
        self._print_t(text_area, mode, *objects, sep=sep, end=end)

    def print_tb(
        self,
        mode: Literal["w", "a", "d"],
        *objects: object,
        sep: str = " ",
        end: str = "\n",
    ) -> None:
        """
        標準出力先として割り当てられていない方のログ画面に文字列を出力する
        mode: ['w'/'a'/'d'] 'w'上書き, 'a'追記, 'd'削除
        """
        if self.stdout_destination == "1":
            self.print_t2b(mode, *objects, sep=sep, end=end)
        elif self.stdout_destination == "2":
            self.print_t1b(mode, *objects, sep=sep, end=end)

    def print_tbs(
        self,
        mode: Literal["w", "a", "d"],
        *objects: object,
        sep: str = " ",
        end: str = "\n",
    ) -> None:
        """
        標準出力先として割り当てられている方のログ画面に文字列を出力する
        mode: ['w'/'a'/'d'] 'w'上書き, 'a'追記, 'd'削除
        """
        if self.stdout_destination == "1":
            self.print_t1b(mode, *objects, sep=sep, end=end)
        elif self.stdout_destination == "2":
            self.print_t2b(mode, *objects, sep=sep, end=end)

    ############### dialogue functions ###############
    @overload
    def dialogue(
        self,
        title: str,
        message: Message,
        desc: str | None = None,
        need: type[list] = list,
    ) -> list[bool | int | float | str]: ...

    @overload
    def dialogue(
        self,
        title: str,
        message: Message,
        desc: str | None = None,
        need: type[dict] = ...,
    ) -> dict[str, bool | int | float | str]: ...

    def dialogue(
        self,
        title: str,
        message: Message,
        desc: str | None = None,
        need: type[list] | type[dict] = list,
    ) -> list[bool | int | float | str] | dict[str, bool | int | float | str]:
        """
        保存機能なしのダイアログ(Entryのみ)
        title: ダイアログのウインドウ名
        message: Refer to PokeConDialogue.py
        desc: description
        need: 出力する形式
        """
        # ダイアログ呼び出し
        self.message_dialogue = tk.Toplevel()
        ret = PokeConDialogue(
            self.message_dialogue,
            title,
            message,
            desc=desc,
            pos=int(self.pos_dialogue_buttons),
        ).ret_value(need)
        self.message_dialogue = None

        if not ret:
            self.finish()
        return ret

    @overload
    def dialogue6widget(
        self,
        title: str,
        dialogue_list: list,
        desc: str | None = None,
        need: type[list] = list,
    ) -> list[bool | int | float | str]: ...

    @overload
    def dialogue6widget(
        self,
        title: str,
        dialogue_list: list,
        desc: str | None = None,
        need: type[dict] = ...,
    ) -> dict[str, bool | int | float | str]: ...

    def dialogue6widget(
        self,
        title: str,
        dialogue_list: list,
        desc: str | None = None,
        need: type[list] | type[dict] = list,
    ) -> list[bool | int | float | str] | dict[str, bool | int | float | str]:
        """
        保存機能なしのダイアログ
        title: ダイアログのウインドウ名
        dialogue_list: Refer to PokeConDialogue.py
        desc: description
        need: 出力する形式
        """
        # ウィジェット名重複チェック
        if check_widget_name(dialogue_list):
            pass
        else:
            logger.error(
                "ウィジェット名に重複があります。重複しない名称を設定してください。"
            )
            self.finish()

        # ダイアログ呼び出し
        self.message_dialogue = tk.Toplevel()
        ret = PokeConDialogue(
            self.message_dialogue,
            title,
            dialogue_list,
            desc=desc,
            mode=1,
            pos=int(self.pos_dialogue_buttons),
        ).ret_value(need)
        self.message_dialogue = None

        if not ret:
            self.finish()
        else:
            return ret

    def dialogue6widget_save_settings(
        self,
        title: str,
        dialogue_list: list,
        filename: str,
        desc: str | None = None,
        need: type = list,
    ) -> list | dict:
        """
        前の設定を呼び出すタイプのダイアログ
        title: ダイアログのウインドウ名
        dialogue_list: Refer to PokeConDialogue.py
        filename: 前の設定を保存するファイルのパス(絶対パス)
        desc: description
        need: 出力する形式
        """

        reserved_name = ["[PokeCon]設定ファイル名", "[PokeCon]設定を保存"]
        # ウィジェット名重複チェック
        if check_widget_name(dialogue_list, except_name=reserved_name):
            pass
        else:
            logger.error(
                "ウィジェット名に重複があります。重複しない名称を設定してください。"
                f"また、「{reserved_name[0]}」および「{reserved_name[1]}」のウィジェット名は使用できません。"
            )
            self.finish()

        if check_widget_name(dialogue_list):
            pass
        else:
            logger.error(
                "ウィジェット名に重複があります。重複しない名称を設定してください。"
            )
            self.finish()

        # ディレクトリがない場合は作成
        if not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
            logger.info("設定ファイル保存用ディレクトリを作成しました。")

        # 過去の履歴を初期値に反映
        new_dialogue_list = generate_new_dialogue_list(dialogue_list, filename)

        # ダイアログ呼び出し
        self.message_dialogue = tk.Toplevel()
        ret = PokeConDialogue(
            self.message_dialogue,
            title,
            new_dialogue_list,
            desc=desc,
            mode=1,
            pos=int(self.pos_dialogue_buttons),
        ).ret_value(need)
        self.message_dialogue = None

        if not ret:
            self.finish()
        else:
            # [ok]選択時に入力履歴を保存
            save_dialogue_settings(new_dialogue_list, ret, filename)
            return ret

    @overload
    def dialogue6widget_select_settings(
        self,
        title: str,
        dialogue_list: MessageMode1,
        dirname: str,
        desc: str | None = None,
        need: type[list] = list,
    ) -> list[bool | int | float | str]: ...

    @overload
    def dialogue6widget_select_settings(
        self,
        title: str,
        dialogue_list: MessageMode1,
        dirname: str,
        desc: str | None = None,
        need: type[dict] = ...,
    ) -> dict[str, bool | int | float | str]: ...

    def dialogue6widget_select_settings(
        self,
        title: str,
        dialogue_list: MessageMode1,
        dirname: str,
        desc: str | None = None,
        need: type[list] | type[dict] = list,
    ) -> list[bool | int | float | str] | dict[str, bool | int | float | str]:
        """
        保存した設定を選択して呼び出すタイプのダイアログ
        title: ダイアログのウインドウ名
        dialogue_list: Refer to PokeConDialogue.py
        filename: 設定を保存するディレクトリのパス(絶対パス)
        desc: description
        need: 出力する形式
        """
        if need is list[bool | int | float | str]:
            return self.dialogue6widget_select_settings_list(
                title, dialogue_list, dirname, desc
            )
        elif need is dict[str, bool | int | float | str]:
            return self.dialogue6widget_select_settings_dict(
                title, dialogue_list, dirname, desc
            )
        else:
            self.finish()

    def dialogue6widget_select_settings_list(
        self,
        title: str,
        dialogue_list: MessageMode1,
        dirname: str,
        desc: str | None = None,
    ) -> list[bool | int | float | str]:
        reserved_name = ["[PokeCon]設定ファイル名", "[PokeCon]設定を保存"]
        # ウィジェット名重複チェック
        if check_widget_name(dialogue_list, except_name=reserved_name):
            pass
        else:
            logger.error(
                "ウィジェット名に重複があります。重複しない名称を設定してください。"
                f"また、「{reserved_name[0]}」および「{reserved_name[1]}」のウィジェット名は使用できません。"
            )
            self.finish()

        # 設定ファイル名リスト生成
        settings_list = get_settings_list(dirname)

        # GUI画面表示
        widget = self.dialogue6widget(
            "Select Preset",
            [["Combo", "---設定ファイル選択---", settings_list, "(選択して下さい)"]],
        )

        # ディレクトリがない場合は作成
        if not os.path.exists(dirname):
            os.makedirs(dirname)
            logger.info("設定ファイル保存用ディレクトリを作成しました。")

        filename: str | None = os.path.join(dirname, f"{widget[0]}.json")
        if filename is not None and not os.path.exists(filename):
            logger.info("設定ファイルを選択しなかったのでデフォルト値で起動します。")
            filename = None

        # 過去の履歴を初期値に反映
        new_dialogue_list: MessageMode1 = generate_new_dialogue_list(
            dialogue_list, filename
        )

        # 設定保存用のウィジェットを追加
        entry_widget: list[str] = ["Entry", "[PokeCon]設定ファイル名", ""]
        new_dialogue_list.append(entry_widget)
        check_widget: list[bool | str] = ["Check", "[PokeCon]設定を保存", False]
        new_dialogue_list.append(check_widget)

        # ダイアログ呼び出し
        self.message_dialogue = tk.Toplevel()
        ret = PokeConDialogue(
            self.message_dialogue,
            title,
            new_dialogue_list,
            desc=desc,
            mode=1,
            pos=int(self.pos_dialogue_buttons),
        ).ret_value(list)
        self.message_dialogue = None

        if not isinstance(ret, list):
            self.finish()

        # 設定保存用のウィジェット関連の要素を削除
        preset_name = ret[-2]
        save_preset = ret[-1]
        ret = ret[:-2]

        # [ok]選択時に入力履歴を保存
        if save_preset and preset_name != "":
            filename = os.path.join(dirname, f"{preset_name}.json")
            save_dialogue_settings(new_dialogue_list[:-2], ret, filename)
        filename = os.path.join(dirname, "前回の設定.json")
        save_dialogue_settings(new_dialogue_list[:-2], ret, filename)
        return ret

    def dialogue6widget_select_settings_dict(
        self,
        title: str,
        dialogue_list: MessageMode1,
        dirname: str,
        desc: str | None = None,
    ) -> dict[str, bool | int | float | str]:
        reserved_name = ["[PokeCon]設定ファイル名", "[PokeCon]設定を保存"]
        # ウィジェット名重複チェック
        if check_widget_name(dialogue_list, except_name=reserved_name):
            pass
        else:
            logger.error(
                "ウィジェット名に重複があります。重複しない名称を設定してください。"
                f"また、「{reserved_name[0]}」および「{reserved_name[1]}」のウィジェット名は使用できません。"
            )
            self.finish()

        # 設定ファイル名リスト生成
        settings_list = get_settings_list(dirname)

        # GUI画面表示
        widget = self.dialogue6widget(
            "Select Preset",
            [["Combo", "---設定ファイル選択---", settings_list, "(選択して下さい)"]],
        )

        # ディレクトリがない場合は作成
        if not os.path.exists(dirname):
            os.makedirs(dirname)
            logger.info("設定ファイル保存用ディレクトリを作成しました。")

        filename: str | None = os.path.join(dirname, f"{widget[0]}.json")
        if filename is not None and not os.path.exists(filename):
            logger.info("設定ファイルを選択しなかったのでデフォルト値で起動します。")
            filename = None

        # 過去の履歴を初期値に反映
        new_dialogue_list: MessageMode1 = generate_new_dialogue_list(
            dialogue_list, filename
        )

        # 設定保存用のウィジェットを追加
        entry_widget: list[str] = ["Entry", "[PokeCon]設定ファイル名", ""]
        new_dialogue_list.append(entry_widget)
        check_widget: list[bool | str] = ["Check", "[PokeCon]設定を保存", False]
        new_dialogue_list.append(check_widget)

        # ダイアログ呼び出し
        self.message_dialogue = tk.Toplevel()
        ret = PokeConDialogue(
            self.message_dialogue,
            title,
            new_dialogue_list,
            desc=desc,
            mode=1,
            pos=int(self.pos_dialogue_buttons),
        ).ret_value(dict)
        self.message_dialogue = None

        if not isinstance(ret, dict):
            self.finish()

        # 設定保存用のウィジェット関連の要素を削除
        preset_name = ret["[PokeCon]設定ファイル名"]
        save_preset = ret["[PokeCon]設定を保存"]
        ret.pop("[PokeCon]設定ファイル名")
        ret.pop("[PokeCon]設定を保存")

        # [ok]選択時に入力履歴を保存
        if save_preset and preset_name != "":
            filename = os.path.join(dirname, f"{preset_name}.json")
            save_dialogue_settings(new_dialogue_list[:-2], ret, filename)
        filename = os.path.join(dirname, "前回の設定.json")
        save_dialogue_settings(new_dialogue_list[:-2], ret, filename)
        return ret

    ############### Socket functions ###############
    def socket_change_alive(self, flag: bool) -> None:
        if (socket := self.socket0) is None:
            logger.error("Socket client is not initialized.")
            return

        socket.alive = flag

    def socket_change_ipaddr(self, addr: str) -> None:
        """
        IPアドレスを変更する
        return:なし
        addr|str:IPアドレス
        """
        if (socket := self.socket0) is None:
            logger.error("Socket client is not initialized.")
            return

        socket.change_ipaddr(addr)

    def socket_change_port(self, port: int) -> None:
        """
        ポート番号を変更する
        return:なし
        port|int:ポート番号
        """
        if (socket := self.socket0) is None:
            logger.error("Socket client is not initialized.")
            return

        socket.change_port(port)

    def socket_connect(self) -> None:
        """
        socket通信用のserverと接続する
        return:なし
        """
        if (socket := self.socket0) is None:
            logger.error("Socket client is not initialized.")
            return

        socket.sock_connect()

    def socket_disconnect(self) -> None:
        """
        socket通信用のserverから切断する
        return:なし
        """
        if (socket := self.socket0) is None:
            logger.error("Socket client is not initialized.")
            return
        socket.sock_disconnect()

    def socket_receive_message(self, header: str, show_msg: bool = False) -> str | None:
        """
        socketを用いて先頭が特定の文字列であるメッセージを受信する
        return output|str:受信した文字列
        header|str:受信したい文字列(先頭)
        show_msg|bool:受信した文字列を出力する
        """
        if (socket := self.socket0) is None:
            logger.warning("Socket client is not initialized.")
            return None

        output = socket.receive_message(header, show_msg=show_msg)
        self.checkIfAlive()
        return output

    def socket_receive_message2(
        self, headerlist: list[str], show_msg: bool = False
    ) -> str | None:
        """
        socketを用いて先頭が特定の文字列(複数設定可能)であるメッセージを受信する
        return output|str:受信した文字列
        headerlist|list[str]:受信したい文字列(先頭)のリスト
        show_msg|bool:受信した文字列を出力する
        """
        if (socket := self.socket0) is None:
            logger.warning("Socket client is not initialized.")
            return None
        output = socket.receive_message2(headerlist, show_msg=show_msg)
        self.checkIfAlive()
        return output

    def socket_transmit_message(self, message: str) -> None:
        """
        socketを用いてメッセージを送信する
        return:なし
        message|str:送信するメッセージ
        """
        if (socket := self.socket0) is None:
            logger.error("Socket client is not initialized.")
            return

        socket.transmit_message(message)
        self.checkIfAlive()

    ############### MQTT functions ###############
    def mqtt_change_broker_address(self, broker_address: str) -> None:
        """
        brokerアドレスを変更する
        return:なし
        broker_address|str:brokerアドレス
        """
        if (mqtt := self.mqtt0) is None:
            logger.error("MQTT client is not initialized.")
        else:
            mqtt.broker_address = broker_address  # type: ignore[misc]

    def mqtt_change_id(self, id: str) -> None:
        """
        IDを変更する
        return:なし
        id|str:ID
        """
        if (mqtt := self.mqtt0) is None:
            logger.error("MQTT client is not initialized.")
        else:
            mqtt.id = id  # type: ignore[misc]

    def mqtt_change_pub_token(self, pub_token: str) -> None:
        """
        pub用tokenを変更する
        return:なし
        pub_token|str:pub用token
        """
        if (mqtt := self.mqtt0) is None:
            logger.error("MQTT client is not initialized.")
        else:
            mqtt.pub_token = pub_token

    def mqtt_change_sub_token(self, sub_token: str) -> None:
        """
        sub用tokenを変更する
        return:なし
        sub_token|str:sub用token
        """
        if (mqtt := self.mqtt0) is None:
            logger.error("MQTT client is not initialized.")
        else:
            mqtt.sub_token = sub_token

    def mqtt_change_clientId(self, clientId: str) -> None:
        """
        接続者名を変更する
        return:なし
        clientId|str:接続者名
        """
        if (mqtt := self.mqtt0) is None:
            logger.error("MQTT client is not initialized.")
        else:
            mqtt.clientId = clientId

    def mqtt_receive_message(
        self,
        roomid: str,
        header: str,
        show_msg: bool = False,
    ) -> str | None:
        """
        MQTTを用いて先頭が特定の文字列であるメッセージを受信する
        return output|str:受信した文字列
        roomid|str:ROOM ID(topic)
        header|str:受信したい文字列(先頭)
        show_msg|bool:受信した文字列を出力する
        """
        if (mqtt := self.mqtt0) is None:
            logger.warning("MQTT client is not initialized.")
            return None

        output = mqtt.receive_message(roomid, header, show_msg=show_msg)
        self.checkIfAlive()
        return output

    def mqtt_receive_message2(
        self,
        roomid: str,
        headerlist: list[str],
        show_msg: bool = False,
    ) -> str | None:
        """
        MQTTを用いて先頭が特定の文字列(複数設定可能)であるメッセージを受信する
        return output|str:受信した文字列
        roomid|str:ROOM ID(topic)
        headerlist|list[str]:受信したい文字列(先頭)のリスト
        show_msg|bool:受信した文字列を出力する
        """
        if (mqtt := self.mqtt0) is None:
            logger.warning("MQTT client is not initialized.")
            return None

        output = mqtt.receive_message2(roomid, headerlist, show_msg=show_msg)
        self.checkIfAlive()
        return output

    def mqtt_transmit_message(self, roomid: str, message: str) -> None:
        """
        MQTTを用いてメッセージを送信する
        return:なし
        roomid|str:ROOM ID(topic)
        message|str:送信するメッセージ
        """
        if (mqtt := self.mqtt0) is None:
            logger.error("MQTT client is not initialized.")
        else:
            mqtt.transmit_message(roomid, message)

        self.checkIfAlive()

    ############### protected methods ###############
    def _print_t(
        self,
        text_area: tk.Text,
        mode: Literal["w", "a", "d"],
        *objects: object,
        sep: str = " ",
        end: str = "\n",
    ) -> None:
        """
        text_area(ログ画面)に文字列を出力する
        mode: ['w'/'a'/'d'] 'w'上書き, 'a'追記, 'd'削除
        """
        txt = f"{sep.join([str(obj) for obj in objects])}{end}"
        try:
            text_area.config(state=tk.NORMAL)
            if mode in ["w", "d"]:
                text_area.delete("1.0", "end")
            if mode == "w":
                text_area.insert("1.0", txt)
            elif mode == "a":
                text_area.insert("end", txt)
            text_area.config(state=tk.DISABLED)
            text_area.see("end")
        except Exception:
            logger.error(txt)
