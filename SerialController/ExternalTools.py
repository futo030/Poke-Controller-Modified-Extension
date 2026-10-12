#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import configparser
import os
import time
import socket
import datetime
from typing import Any, Callable

try:
    import paho.mqtt
    import paho.mqtt.client as mqtt

    print(f"paho-mqtt {paho.mqtt.__version__} is installed. You can use MQTTCommunications class.")
    isMQTT = True
except Exception:
    print("paho-mqtt is not installed. You can't use MQTTCommunications class.")
    isMQTT = False


def generate_token_file(filename: str) -> None:
    """
    Socket / MQTT の接続先を書く設定ファイルを、初期値(トークンなどは空)で作る(フォルダーが無ければ作る)
    filename: 作るファイルのパス(すでにある場合は上書きする)
    """
    dirname = os.path.dirname(filename)
    if not os.path.isdir(dirname):
        os.makedirs(dirname)
        print(f"mkdir: '{dirname}'")
    token_file = configparser.ConfigParser(comment_prefixes="#", allow_no_value=True)
    token_file["SOCKET"] = {"addr": "127.0.0.1", "port": "49152"}
    token_file["MQTT"] = {"broker_address": "", "id": "", "fullaccess_token": "", "readonly_token": ""}
    with open(filename, "w", encoding="utf-8") as file:
        token_file.write(file)
    os.chmod(path=filename, mode=0o777)
    print("Generate external token file")


# socket通信用class
class SocketCommunications:
    """
    Socket 通信(ほかのプログラムと、文字のメッセージをやり取りする)。
    SOCKET_TOKEN_PATH: 接続先の設定ファイルの場所(プロファイルを切り替えるときに、クラスの値を書き換える)
    alive: 受信を続けるか(False にすると、受信の待ちをやめて切断する。コマンドの停止時に使う)
    """

    SOCKET_TOKEN_PATH = os.path.join(os.path.dirname(__file__), "profiles", "default", "external_token.ini")

    def __init__(self):
        """
        初期設定(設定ファイルの [SOCKET] から、接続先のアドレスとポート番号を読む。まだ接続はしない)
        return:なし
        """
        super(SocketCommunications, self).__init__()
        self.alive = False
        self.flag_socket = False

        # SOCKET設定
        self.token_file = configparser.ConfigParser(comment_prefixes="#", allow_no_value=True)
        self.open_file_with_utf8()
        token_list = {key: self.token_file["SOCKET"][key] for key in self.token_file["SOCKET"]}
        # token_num = len(token_list)

        self.IPADDR = token_list["addr"]
        self.PORT = int(token_list["port"])

    def open_file_with_utf8(self) -> None:  # line_notify.pyからの流用
        """
        utf-8 のファイルを BOM ありかどうかを自動判定して読み込む(ファイルがない場合は、初期値のファイルを作る)
        return:なし
        """
        if not os.path.isfile(self.SOCKET_TOKEN_PATH):
            generate_token_file(self.SOCKET_TOKEN_PATH)

        is_with_bom = self.is_utf8_file_with_bom(self.SOCKET_TOKEN_PATH)

        encoding = "utf-8-sig" if is_with_bom else "utf-8"
        self.token_file.read(self.SOCKET_TOKEN_PATH, encoding)

    def is_utf8_file_with_bom(self, filename: str) -> bool:  # line_notify.pyからの流用
        """
        utf-8 ファイルが BOM ありかどうかを判定する
        return bool:BOM ありか(空のファイルの場合は False)
        filename|str:ファイル名
        """
        with open(filename, encoding="utf-8") as file:
            return file.readline().startswith("\ufeff")

    def change_ipaddr(self, addr: str) -> None:
        """
        IPアドレスを変更する
        return:なし
        addr|str:IPアドレス
        """
        self.IPADDR = addr

    def change_port(self, port: int) -> None:
        """
        ポート番号を変更する(次の sock_connect から使われる)
        return:なし
        port|int:ポート番号
        """
        self.PORT = int(port)
        # 以前は self.port にだけ入れていた(接続には使われていなかった)。参照している場合に備えて残す
        self.port = port

    def sock_connect(self) -> None:
        """
        socket通信用のserverと接続する(接続できた場合は flag_socket が True になる。できなくても例外にしない)
        return:なし
        """
        try:
            self.sock = socket.socket(socket.AF_INET)
            self.sock.connect((self.IPADDR, self.PORT))
            self.sock.settimeout(3.0)  # タイムアウト時間
            self.flag_socket = True
        except ConnectionRefusedError:
            print("[error]serverが起動されていません")
        except OSError:
            pass

    # socket切断
    def sock_disconnect(self) -> None:
        """
        socket通信用のserverから切断する
        return:なし
        """
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
            self.sock.close()
            self.flag_socket = False
        except ConnectionRefusedError:
            print("[error]serverが起動されていません")
        except OSError:
            pass

    def receive_message(self, header: str, show_msg: bool = False) -> str | None:
        """
        socketを用いて先頭が特定の文字列であるメッセージを受信する(届くまで待つ)
        return output|str:受信した文字列(切断された場合と、alive が False になった場合は None)
        header|str:受信したい文字列(先頭)
        show_msg|bool:受信した文字列を出力する
        """
        # 待機文字列print出力
        print(f"[socket:wait]:{header}")

        # 出力初期値設定
        output = None

        while True:
            try:
                # 受信する
                data = self.sock.recv(1024)
                if data == b"":
                    break
                message = data.decode("utf-8")

                # 先頭の文字列がheaderと一致するかを確認する
                if message[0 : len(header)] == header:
                    print(f"[socket:recv]:{message}")
                    output = message
                    break
                elif show_msg:  # ログ出力
                    print(f"[socket:recv]:{message}")
                if not self.alive:
                    break
            except ConnectionResetError:
                break
            except socket.timeout:  # timeout時,self.aliveを確認する
                if not self.alive:
                    break
            except ConnectionRefusedError:
                print("[error]serverが起動されていません")
                break
            except OSError:
                break

        # stopを押した場合にsocketを切断する
        if not self.alive:
            # socket切断
            self.sock_disconnect()

        return output

    def receive_message2(self, headerlist: list[str], show_msg: bool = False) -> str | None:
        """
        socketを用いて先頭が特定の文字列(複数設定可能)であるメッセージを受信する(届くまで待つ)
        return output|str:受信した文字列(切断された場合と、alive が False になった場合は None)
        headerlist|list[str]:受信したい文字列(先頭)のリスト
        show_msg|bool:受信した文字列を出力する
        """
        # 待機文字列print出力
        header0 = ""
        for i in headerlist:
            header0 += i + ","
        print(f"[socket:wait]:{header0}")

        # 出力初期値設定
        output = None

        while True:
            try:
                # 受信する
                data = self.sock.recv(1024)
                if data == b"":
                    break
                message = data.decode("utf-8")

                # messageとheaderlist内の先頭の文字列が一致するかを確認する
                for header in headerlist:
                    if message[0 : len(header)] == header:
                        print(f"[socket:recv]:{message}")
                        output = message
                if output:
                    break
                if show_msg:  # ログ出力
                    print(f"[socket:recv]:{message}")
                if not self.alive:
                    break
            except ConnectionResetError:
                break
            except socket.timeout:  # timeout時,self.aliveを確認する
                if not self.alive:
                    break
            except ConnectionRefusedError:
                print("[error]serverが起動されていません")
                break
            except OSError:
                break

        # stopを押した場合にsocketを切断する
        if not self.alive:
            # socket切断
            self.sock_disconnect()

        return output

    def transmit_message(self, message: str) -> None:
        """
        socketを用いてメッセージを送信する(接続していない場合は、例外になる)
        return:なし
        message|str:送信するメッセージ
        """
        # 送信する
        self.sock.send(message.encode("utf-8"))
        print(f"[socket:send]:{message}")


# global変数(MQTT受信用)
receive_msg = None


# MQTT通信用class
class MQTTCommunications:
    """
    MQTT 通信(broker を通して、文字のメッセージをやり取りする。paho-mqtt が要る)。
    MQTT_TOKEN_PATH: 接続先の設定ファイルの場所(プロファイルを切り替えるときに、クラスの値を書き換える)
    alive: 受信を続けるか(False にすると、受信の待ちをやめる。コマンドの停止時に使う)
    """

    MQTT_TOKEN_PATH = os.path.join(os.path.dirname(__file__), "profiles", "default", "external_token.ini")

    def __init__(self, clientId: str):
        """
        初期設定(設定ファイルの [MQTT] から、接続先と ID・トークンを読む。まだ接続はしない)
        return:なし
        clientId|str:接続者名(重複してもよい)
        """
        super(MQTTCommunications, self).__init__()
        self.alive = False

        # MQTT設定
        self.token_file = configparser.ConfigParser(comment_prefixes="#", allow_no_value=True)
        self.open_file_with_utf8()
        token_list = {key: self.token_file["MQTT"][key] for key in self.token_file["MQTT"]}
        # token_num = len(token_list)

        self.broker_address = token_list["broker_address"]
        self.id = token_list["id"]
        fullaccess_token = token_list["fullaccess_token"]
        readonly_token = token_list["readonly_token"]

        if fullaccess_token != "":
            self.pub_token = fullaccess_token
            self.sub_token = fullaccess_token
        elif readonly_token != "":
            self.pub_token = None
            self.sub_token = readonly_token
        else:
            self.pub_token = None
            self.sub_token = None

        self.clientId = clientId
        self.receive_msg = -1

    def exceptiondecorator(func: Callable) -> Callable:
        """
        MQTTのライブラリがインストールされていない場合を想定したデコレータです。
        実行した場合にログを出力します。
        (func の中で例外が出た場合に、メッセージを表示して "" を返すようにする。
        paho-mqtt が入っていない場合は、その旨を、入っている場合は、例外の内容を表示する)
        """

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            """func を呼び、その戻り値を返す(例外が出た場合は "")"""
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if not isMQTT:
                    print("paho-mqtt may not be installed. Please make sure paho-mqtt is installed.")
                else:
                    # 接続先の間違い、通信の失敗など(原因が分かるように、内容を表示する)
                    print(f"[mqtt:error]:{type(e).__name__}: {e}")
                return ""

        return wrapper

    def _new_client(self) -> mqtt.Client:
        """
        broker と通信するためのクライアントを作る(まだ接続はしない)。
        paho-mqtt 2.x では、初めの引数にコールバックの版を渡す必要がある(1.x では、接続者名だけを渡す)
        """
        if hasattr(mqtt, "CallbackAPIVersion"):
            return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, self.clientId)
        return mqtt.Client(self.clientId)

    def open_file_with_utf8(self) -> None:  # line_notify.pyからの流用
        """
        utf-8 のファイルを BOM ありかどうかを自動判定して読み込む(ファイルがない場合は、初期値のファイルを作る)
        return:なし
        """
        if not os.path.isfile(self.MQTT_TOKEN_PATH):
            generate_token_file(self.MQTT_TOKEN_PATH)

        is_with_bom = self.is_utf8_file_with_bom(self.MQTT_TOKEN_PATH)

        encoding = "utf-8-sig" if is_with_bom else "utf-8"
        self.token_file.read(self.MQTT_TOKEN_PATH, encoding)

    def is_utf8_file_with_bom(self, filename: str) -> bool:  # line_notify.pyからの流用
        """
        utf-8 ファイルが BOM ありかどうかを判定する
        return bool:BOM ありか(空のファイルの場合は False)
        filename|str:ファイル名
        """
        with open(filename, encoding="utf-8") as file:
            return file.readline().startswith("\ufeff")

    def change_broker_address(self, broker_address: str) -> None:
        """
        brokerアドレスを変更する
        return:なし
        broker_address|str:brokerアドレス
        """
        self.broker_address = broker_address

    def change_id(self, id: str) -> None:
        """
        IDを変更する
        return:なし
        id|str:ID
        """
        self.id = id

    def change_pub_token(self, pub_token: str) -> None:
        """
        pub用tokenを変更する
        return:なし
        pub_token|str:pub用token
        """
        self.pub_token = pub_token

    def change_sub_token(self, sub_token: str) -> None:
        """
        sub用tokenを変更する
        return:なし
        sub_token|str:sub用token
        """
        self.sub_token = sub_token

    def change_clientId(self, clientId: str) -> None:
        """
        接続者名を変更する
        return:なし
        clientId|str:接続者名
        """
        self.clientId = clientId

    def on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        """
        メッセージを受信する(受信した文字を、モジュールの変数 receive_msg に入れる)
        return:なし
        client,userdata,msgはいいように設定してくれる
        """
        global receive_msg
        # print(f"ROOM ID: {msg.topic} message: {msg.payload.decode('utf-8')}")
        receive_msg = msg.payload.decode("utf-8")

    @exceptiondecorator
    def receive_message(self, roomid: str, header: str, show_msg: bool = False) -> str | None:
        """
        MQTTを用いて先頭が特定の文字列であるメッセージを受信する(届くまで待つ)
        return output|str:受信した文字列(alive が False になった場合は None。接続できないなどの例外の場合は "")
        roomid|str:ROOM ID(topic)
        header|str:受信したい文字列(先頭)
        show_msg|bool:受信した文字列を出力する
        """
        # 待機文字列print出力
        print(f"[mqtt:wait]:{header}")

        global receive_msg
        output = None
        header_date = int(datetime.datetime.today().strftime("%Y%m%d%H%M%S%f"))
        message = -1

        # brokerと接続する
        self.client = self._new_client()
        self.client.username_pw_set(self.id, self.sub_token)
        self.client.connect(self.broker_address, 1883)
        self.client.subscribe(roomid)
        self.client.on_message = self.on_message

        while True:
            try:
                # brokerからメッセージを引き抜く
                self.client.loop_start()
                time.sleep(1.0)
                self.client.loop_stop()
                if receive_msg:
                    if header_date < int(receive_msg[1:21]):
                        header_date = int(receive_msg[1:21])
                        message = receive_msg[22:]
                        # 先頭の文字列がheaderと一致するかを確認する
                        if message[0 : len(header)] == header:
                            output = message
                            print(f"[mqtt:recv]:{message}")
                            break
                        elif show_msg:  # ログ出力
                            print(f"[mqtt:recv]:{message}")

                # stop押下時にwhileから抜ける
                if not self.alive:
                    break
            except Exception:
                break

        self.client.disconnect()

        return output

    @exceptiondecorator
    def receive_message2(self, roomid: str, headerlist: list[str], show_msg: bool = False) -> str | None:
        """
        MQTTを用いて先頭が特定の文字列(複数設定可能)であるメッセージを受信する(届くまで待つ)
        return output|str:受信した文字列(alive が False になった場合は None。接続できないなどの例外の場合は "")
        roomid|str:ROOM ID(topic)
        headerlist|list[str]:受信したい文字列(先頭)のリスト
        show_msg|bool:受信した文字列を出力する
        """
        # 待機文字列print出力
        header0 = ""
        for i in headerlist:
            header0 += i + ","
        print(f"[mqtt:wait]:{header0}")

        global receive_msg
        output = None
        header_date = int(datetime.datetime.today().strftime("%Y%m%d%H%M%S%f"))
        message = -1

        # brokerと接続する
        self.client = self._new_client()
        self.client.username_pw_set(self.id, self.sub_token)
        self.client.connect(self.broker_address, 1883)
        self.client.subscribe(roomid)
        self.client.on_message = self.on_message

        while True:
            try:
                # brokerからメッセージを引き抜く
                self.client.loop_start()
                time.sleep(1.0)
                self.client.loop_stop()
                if receive_msg:
                    if header_date < int(receive_msg[1:21]):
                        header_date = int(receive_msg[1:21])
                        message = receive_msg[22:]
                        # messageとheaderlist内の先頭の文字列が一致するかを確認する
                        for header in headerlist:
                            if message[0 : len(header)] == header:
                                output = message
                                print(f"[mqtt:recv]:{message}")
                        if output:
                            break
                        elif show_msg:  # ログ出力
                            print(f"[mqtt:recv]:{message}")

                # stop押下時にwhileから抜ける
                if not self.alive:
                    break
            except Exception:
                break

        self.client.disconnect()

        return output

    @exceptiondecorator
    def transmit_message(self, roomid: str, message: str) -> None:
        """
        MQTTを用いてメッセージを送信する(pub用tokenが無い場合は、送らずにメッセージを表示する)
        return:なし
        roomid|str:ROOM ID(topic)
        message|str:送信するメッセージ
        """
        # メッセージ更新判定に日時情報を使用する
        header_date = datetime.datetime.today().strftime("[%Y%m%d%H%M%S%f]")
        if self.pub_token:
            self.client = self._new_client()
            self.client.username_pw_set(self.id, self.pub_token)
            self.client.connect(self.broker_address, 1883)
            message0 = header_date + message
            self.client.publish(roomid, message0)
            print(f"[mqtt:send]:{message}")
            self.client.disconnect()
        else:
            # 接続していないので、切断もしない
            print("token error(readonly)")
