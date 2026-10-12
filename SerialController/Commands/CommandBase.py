#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Callable, Iterator, List, TYPE_CHECKING

from abc import ABCMeta, abstractclassmethod
from contextlib import contextmanager
import os
import threading

from services.dialogue_store import (
    generate_new_dialogue_list,
    save_dialogue_settings,
    get_settings_list,
    check_widget_name,
)
from ExternalTools import SocketCommunications, MQTTCommunications

if TYPE_CHECKING:
    from Commands.Sender import Sender

# CommandBaseにGUIに関連する関数を集約する。
# print/widget/socket/mqtt関連


class Command:
    """
    すべてのコマンド(Python コマンド、Mcu コマンドなど)の基底クラス。

    画面に関わる関数(ログ画面への出力、ダイアログ、Socket / MQTT の通信)を、ここに集めてある。
    クラスの変数(text_area_1、canvas、isPause など)は、画面側が起動時や実行時に書き込む、全コマンド共通の値
    """

    __metaclass__ = ABCMeta
    text_area_1 = None
    text_area_2 = None
    stdout_destination = "1"
    pos_dialogue_buttons = "2"
    # ダイアログの表示方法: (command, title, message, desc, need, mode, pos) -> 入力結果
    # 画面側が起動時に登録する(未登録の場合は、tkinter のダイアログを使う)
    dialogue_handler = None
    isPause = False
    canvas = None
    isGuide = False
    isSimilarity = False
    isImage = False
    isWinNotStart = False
    isWinNotEnd = False
    isLineNotStart = False
    isLineNotEnd = False
    isDiscordNotStart = False
    isDiscordNotEnd = False
    # Discord の開始・終了の通知に付ける画像を返す関数(画面が設定する。None なら、文字だけを送る)
    _notification_image = None
    app_name = ""
    cur_command_name = ""
    profilename = None
    # Startボタン押下時にアクティブだった出力ページ(0始まり)
    output_page = 0
    # コマンド実行スレッドのident -> 出力ページ
    _thread_output_pages = {}
    _thread_output_pages_lock = threading.Lock()
    # output_to_page()で一時的に指定された出力ページ(スレッド毎)
    _output_page_override = threading.local()

    def __init__(self) -> None:
        """実行していない状態で作る(Socket と MQTT の通信の入れ物も、ここで作る)"""
        self.isRunning = False

        self.message_dialogue = None
        self.socket0 = SocketCommunications()
        self.mqtt0 = MQTTCommunications("")

    @abstractclassmethod
    def start(self, ser: Sender, postProcess: Callable[[], None] | None = None) -> None:
        """
        コマンドを始める(子クラスが実装する)

        ser: 入力を送る相手
        postProcess: コマンドが終わったときに呼ぶ関数(画面の Start ボタンを戻す処理など。None: 呼ばない)
        """
        pass

    @abstractclassmethod
    def end(self, ser: Sender) -> None:
        """コマンドを終える(子クラスが実装する)"""
        pass

    def checkIfAlive(self) -> bool | None:
        """
        コマンドを止める指示が出ていないかを確かめる(この基底クラスでは、何もしない。
        PythonCommand は、止める指示が出ていれば StopThread を出し、出ていなければ True を返す)
        """
        pass

    def finish(self) -> None:
        """
        コマンドを自分から終える(ダイアログをキャンセルしたときなどに呼ばれる)。
        この基底クラスでは、何もしない(呼んだ側は、そのまま先へ進む)。
        PythonCommand は、入力を離して StopThread を出し、コマンドをそこで止める
        """
        pass

    ############### output page functions ###############
    @classmethod
    def register_output_thread(cls, page: int) -> None:
        """
        現在のスレッドの出力先ページを登録する
        """
        with cls._thread_output_pages_lock:
            cls._thread_output_pages[threading.get_ident()] = page

    @classmethod
    def unregister_output_thread(cls) -> None:
        """
        現在のスレッドの出力先ページの登録を解除する
        """
        with cls._thread_output_pages_lock:
            cls._thread_output_pages.pop(threading.get_ident(), None)

    @classmethod
    @contextmanager
    def output_to_page(cls, page: int | None) -> Iterator[None]:
        """
        withブロック内の現在のスレッドからの出力先ページを一時的に指定する
        (メインスレッドから実行中コマンドのページに出力する場合など)
        page: 出力先のページ(0 始まり)。None は、指定しない(元の決め方に従う)
        """
        prev = getattr(cls._output_page_override, "page", None)
        cls._output_page_override.page = page
        try:
            yield
        finally:
            cls._output_page_override.page = prev

    @classmethod
    def get_output_page_for_current_thread(cls) -> int | None:
        """
        現在のスレッドの出力先ページを返す
        - output_to_page()で指定中: 指定されたページ
        - コマンド実行スレッド: Start時にアクティブだったページ
        - コマンドが生成したサブスレッド: 実行中コマンドのページ
        - メインスレッドなど: None(アクティブなページに出力)
        """
        page = getattr(cls._output_page_override, "page", None)
        if page is not None:
            return page
        if threading.current_thread() is threading.main_thread():
            return None
        with cls._thread_output_pages_lock:
            page = cls._thread_output_pages.get(threading.get_ident())
            if page is None and cls._thread_output_pages:
                page = list(cls._thread_output_pages.values())[-1]
        return page

    @staticmethod
    def _write_text_area(text_area: object, mode: str, txt: str = "") -> None:
        """
        ログ画面に書き込む
        text_area: 書き込む先。enqueue(mode, txt) を持つもの(出力のチャンネルなど)か、tkinter の Text
                   (画面なしでも使うので、型は object)
        mode: ['w'/'a'/'d'] 'w'上書き, 'a'追記, 'd'削除
        """
        if hasattr(text_area, "enqueue"):
            # キューに積むだけで戻る(反映はメインスレッドが行う)
            text_area.enqueue(mode, txt)
            return
        # Textウィジェットが直接設定されている場合
        text_area.config(state="normal")
        if mode in ["w", "d"]:
            text_area.delete("1.0", "end")
        if mode in ["w", "a"]:
            text_area.insert("end", txt)
        text_area.config(state="disable")
        text_area.see("end")

    ############### print functions ###############
    def print_s(self, *objects: object, sep: str = " ", end: str = "\n") -> None:
        """標準出力に出力する(print と同じ。出力先のログ画面は、画面の設定で決まる)"""
        print(*objects, sep=sep, end=end)

    def print_t1(self, *objects: object, sep: str = " ", end: str = "\n") -> None:
        """
        上側のログ画面に文字列を出力する(書き込めない場合は、標準出力に出す)
        """
        try:
            txt = sep.join([str(obj) for obj in objects]) + end
            self._write_text_area(self.text_area_1, "a", txt)
        except Exception:
            print(*objects, sep=sep, end=end)

    def print_t2(self, *objects: object, sep: str = " ", end: str = "\n") -> None:
        """
        下側のログ画面に文字列を出力する(書き込めない場合は、標準出力に出す)
        """
        try:
            txt = sep.join([str(obj) for obj in objects]) + end
            self._write_text_area(self.text_area_2, "a", txt)
        except Exception:
            print(*objects, sep=sep, end=end)

    def print_t(self, *objects: object, sep: str = " ", end: str = "\n") -> None:
        """
        標準出力先として割り当てられていない方のログ画面に文字列を出力する
        """
        if self.stdout_destination == "1":
            self.print_t2(*objects, sep=sep, end=end)
        elif self.stdout_destination == "2":
            self.print_t1(*objects, sep=sep, end=end)

    def print_ts(self, *objects: object, sep: str = " ", end: str = "\n") -> None:
        """
        標準出力先として割り当てられている方のログ画面に文字列を出力する
        """
        if self.stdout_destination == "1":
            self.print_t1(*objects, sep=sep, end=end)
        elif self.stdout_destination == "2":
            self.print_t2(*objects, sep=sep, end=end)

    def print_t1b(self, mode: str, *objects: object, sep: str = " ", end: str = "\n") -> None:
        """
        上側のログ画面に文字列を出力する(書き込めない場合は、何もしない)
        mode: ['w'/'a'/'d'] 'w'上書き, 'a'追記, 'd'削除
        """
        try:
            txt = sep.join([str(obj) for obj in objects]) + end
            self._write_text_area(self.text_area_1, mode, txt)
        except Exception:
            pass

    def print_t2b(self, mode: str, *objects: object, sep: str = " ", end: str = "\n") -> None:
        """
        下側のログ画面に文字列を出力する(書き込めない場合は、何もしない)
        mode: ['w'/'a'/'d'] 'w'上書き, 'a'追記, 'd'削除
        """
        try:
            txt = sep.join([str(obj) for obj in objects]) + end
            self._write_text_area(self.text_area_2, mode, txt)
        except Exception:
            pass

    def print_tb(self, mode: str, *objects: object, sep: str = " ", end: str = "\n") -> None:
        """
        標準出力先として割り当てられていない方のログ画面に文字列を出力する
        mode: ['w'/'a'/'d'] 'w'上書き, 'a'追記, 'd'削除
        """
        if self.stdout_destination == "1":
            self.print_t2b(mode, *objects, sep=sep, end=end)
        elif self.stdout_destination == "2":
            self.print_t1b(mode, *objects, sep=sep, end=end)

    def print_tbs(self, mode: str, *objects: object, sep: str = " ", end: str = "\n") -> None:
        """
        標準出力先として割り当てられている方のログ画面に文字列を出力する
        mode: ['w'/'a'/'d'] 'w'上書き, 'a'追記, 'd'削除
        """
        if self.stdout_destination == "1":
            self.print_t1b(mode, *objects, sep=sep, end=end)
        elif self.stdout_destination == "2":
            self.print_t2b(mode, *objects, sep=sep, end=end)

    def _open_dialogue(
        self, title: str, message: int | str | list, desc: str | None = None, need: type = list, mode: int = 0
    ) -> list | dict | bool:
        """
        ダイアログを表示して入力結果を返す(表示は、画面側が登録した dialogue_handler が行う)
        message: mode=0 は項目名(またはそのリスト)、mode=1 は部品の定義のリスト
        need: 戻り値の型(list または dict)
        戻り値: 入力結果。キャンセルした場合は False
        """
        handler = Command.dialogue_handler
        if handler is None:
            from ui.dialogue import open_dialogue as handler

        return handler(self, title, message, desc=desc, need=need, mode=mode, pos=int(self.pos_dialogue_buttons))

    def dialogue(
        self, title: str, message: int | str | list, desc: str | None = None, need: type = list
    ) -> list | dict:
        """
        保存機能なしのダイアログ(Entryのみ)
        title: ダイアログのウインドウ名
        message: Refer to PokeConDialogue.py
        desc: description
        need: 出力する形式
        キャンセルした場合は self.finish() を呼ぶ(PythonCommand では、コマンドがそこで止まる)
        """
        # ダイアログ呼び出し
        ret = self._open_dialogue(title, message, desc=desc, need=need)
        if not ret:
            self.finish()
        else:
            return ret

    def dialogue6widget(
        self, title: str, dialogue_list: list, desc: str | None = None, need: type = list
    ) -> list | dict:
        """
        保存機能なしのダイアログ
        title: ダイアログのウインドウ名
        dialogue_list: Refer to PokeConDialogue.py
        desc: description
        need: 出力する形式
        ウィジェット名が重複している場合と、キャンセルした場合は self.finish() を呼ぶ
        """
        # ウィジェット名重複チェック
        if check_widget_name(dialogue_list):
            pass
        else:
            print("ウィジェット名に重複があります。重複しない名称を設定してください。")
            self.finish()

        # ダイアログ呼び出し
        ret = self._open_dialogue(title, dialogue_list, desc=desc, need=need, mode=1)

        if not ret:
            self.finish()
        else:
            return ret

    def dialogue6widget_save_settings(
        self, title: str, dialogue_list: list, filename: str, desc: str | None = None, need: type = list
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
            print(
                "ウィジェット名に重複があります。重複しない名称を設定してください。"
                f"また、「{reserved_name[0]}」および「{reserved_name[1]}」のウィジェット名は使用できません。"
            )
            self.finish()

        if check_widget_name(dialogue_list):
            pass
        else:
            print("ウィジェット名に重複があります。重複しない名称を設定してください。")
            self.finish()

        # ディレクトリがない場合は作成
        if not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
            print("設定ファイル保存用ディレクトリを作成しました。")

        # 過去の履歴を初期値に反映
        new_dialogue_list = generate_new_dialogue_list(dialogue_list, filename)

        # ダイアログ呼び出し
        ret = self._open_dialogue(title, new_dialogue_list, desc=desc, need=need, mode=1)

        if not ret:
            self.finish()
        else:
            # [ok]選択時に入力履歴を保存
            save_dialogue_settings(new_dialogue_list, ret, filename)
            return ret

    def dialogue6widget_select_settings(
        self, title: str, dialogue_list: list, dirname: str, desc: str | None = None, need: type = list
    ) -> list | dict:
        """
        保存した設定を選択して呼び出すタイプのダイアログ
        title: ダイアログのウインドウ名
        dialogue_list: Refer to PokeConDialogue.py
        dirname: 設定を保存するディレクトリのパス(絶対パス)
        desc: description
        need: 出力する形式
        """
        reserved_name = ["[PokeCon]設定ファイル名", "[PokeCon]設定を保存"]
        # ウィジェット名重複チェック
        if check_widget_name(dialogue_list, except_name=reserved_name):
            pass
        else:
            print(
                "ウィジェット名に重複があります。重複しない名称を設定してください。"
                f"また、「{reserved_name[0]}」および「{reserved_name[1]}」のウィジェット名は使用できません。"
            )
            self.finish()

        # 設定ファイル名リスト生成
        settings_list = get_settings_list(dirname)

        # GUI画面表示
        ret = self.dialogue6widget(
            "Select Preset", [["Combo", "---設定ファイル選択---", settings_list, "(選択して下さい)"]]
        )

        # ディレクトリがない場合は作成
        if not os.path.exists(dirname):
            os.makedirs(dirname)
            print("設定ファイル保存用ディレクトリを作成しました。")

        filename = os.path.join(dirname, f"{ret[0]}.json")
        if not os.path.exists(filename):
            print("設定ファイルを選択しなかったのでデフォルト値で起動します。")
            filename = None
        else:
            pass

        # 過去の履歴を初期値に反映
        new_dialogue_list = generate_new_dialogue_list(dialogue_list, filename)

        # 設定保存用のウィジェットを追加
        new_dialogue_list.append(["Entry", "[PokeCon]設定ファイル名", ""])
        new_dialogue_list.append(["Check", "[PokeCon]設定を保存", False])

        # ダイアログ呼び出し
        ret = self._open_dialogue(title, new_dialogue_list, desc=desc, need=need, mode=1)

        if not ret:
            self.finish()
        else:
            # 設定保存用のウィジェット関連の要素を削除
            if need is list:
                preset_name = ret[-2]
                save_preset = ret[-1]
                ret = ret[:-2]
            else:
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
        """socket 通信を続けるかの印(socket0.alive)を切り替える。False にすると、受信の待ちをやめる"""
        self.socket0.alive = flag

    def socket_change_ipaddr(self, addr: str) -> None:
        """
        IPアドレスを変更する
        return:なし
        addr|str:IPアドレス
        """
        self.socket0.change_ipaddr(addr)

    def socket_change_port(self, port: int) -> None:
        """
        ポート番号を変更する
        return:なし
        port|int:ポート番号
        """
        self.socket0.change_port(port)

    def socket_connect(self) -> None:
        """
        socket通信用のserverと接続する
        return:なし
        """
        self.socket0.sock_connect()

    def socket_disconnect(self) -> None:
        """
        socket通信用のserverから切断する
        return:なし
        """
        self.socket0.sock_disconnect()

    def socket_receive_message(self, header: str, show_msg: bool = False) -> str | None:
        """
        socketを用いて先頭が特定の文字列であるメッセージを受信する
        return output|str:受信した文字列(受信できずに切断・中断した場合は None)
        header|str:受信したい文字列(先頭)
        show_msg|bool:受信した文字列を出力する
        """
        output = self.socket0.receive_message(header, show_msg=show_msg)
        self.checkIfAlive()
        return output

    def socket_receive_message2(self, headerlist: List[str], show_msg: bool = False) -> str | None:
        """
        socketを用いて先頭が特定の文字列(複数設定可能)であるメッセージを受信する
        return output|str:受信した文字列(受信できずに切断・中断した場合は None)
        headerlist|list[str]:受信したい文字列(先頭)のリスト
        show_msg|bool:受信した文字列を出力する
        """
        output = self.socket0.receive_message2(headerlist, show_msg=show_msg)
        self.checkIfAlive()
        return output

    def socket_transmit_message(self, message: str) -> None:
        """
        socketを用いてメッセージを送信する
        return:なし
        message|str:送信するメッセージ
        """
        self.socket0.transmit_message(message)
        self.checkIfAlive()

    ############### MQTT functions ###############
    def mqtt_change_broker_address(self, broker_address: str) -> None:
        """
        brokerアドレスを変更する
        return:なし
        broker_address|str:brokerアドレス
        """
        self.mqtt0.broker_address = broker_address

    def mqtt_change_id(self, id: str) -> None:
        """
        IDを変更する
        return:なし
        id|str:ID
        """
        self.mqtt0.id = id

    def mqtt_change_pub_token(self, pub_token: str) -> None:
        """
        pub用tokenを変更する
        return:なし
        pub_token|str:pub用token
        """
        self.mqtt0.pub_token = pub_token

    def mqtt_change_sub_token(self, sub_token: str) -> None:
        """
        sub用tokenを変更する
        return:なし
        sub_token|str:sub用token
        """
        self.mqtt0.sub_token = sub_token

    def mqtt_change_clientId(self, clientId: str) -> None:
        """
        接続者名を変更する
        return:なし
        clientId|str:接続者名
        """
        self.mqtt0.clientId = clientId

    def mqtt_receive_message(self, roomid: str, header: str, show_msg: bool = False) -> str | None:
        """
        MQTTを用いて先頭が特定の文字列であるメッセージを受信する
        return output|str:受信した文字列(受信できずに中断した場合は None、通信の例外では "")
        roomid|str:ROOM ID(topic)
        header|str:受信したい文字列(先頭)
        show_msg|bool:受信した文字列を出力する
        """
        output = self.mqtt0.receive_message(roomid, header, show_msg=show_msg)
        self.checkIfAlive()
        return output

    def mqtt_receive_message2(self, roomid: str, headerlist: List[str], show_msg: bool = False) -> str | None:
        """
        MQTTを用いて先頭が特定の文字列(複数設定可能)であるメッセージを受信する
        return output|str:受信した文字列(受信できずに中断した場合は None、通信の例外では "")
        roomid|str:ROOM ID(topic)
        headerlist|list[str]:受信したい文字列(先頭)のリスト
        show_msg|bool:受信した文字列を出力する
        """
        output = self.mqtt0.receive_message2(roomid, headerlist, show_msg=show_msg)
        self.checkIfAlive()
        return output

    def mqtt_transmit_message(self, roomid: str, message: str) -> None:
        """
        MQTTを用いてメッセージを送信する
        return:なし
        roomid|str:ROOM ID(topic)
        message|str:送信するメッセージ
        """
        self.mqtt0.transmit_message(roomid, message)
        self.checkIfAlive()


if __name__ == "__main__":
    pass
