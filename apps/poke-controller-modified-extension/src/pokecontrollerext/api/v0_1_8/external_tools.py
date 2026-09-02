import datetime
import logging
import socket
import time
from functools import wraps
from pathlib import Path
from typing import Callable

from pokecontroller.utils.config import Config

try:
    import paho.mqtt
    import paho.mqtt.client as mqtt

    print(
        f"paho-mqtt {paho.mqtt.__version__} is installed. You can use MQTTCommunications class."
    )
    isMQTT = True
except Exception:  # noqa
    print("paho-mqtt is not installed. You can't use MQTTCommunications class.")
    isMQTT = False

logger = logging.getLogger(__name__)


def generate_token_file(filename: str) -> None:
    _ = ExternalToolsConfig(path=Path(filename))


class ExternalToolsConfig(Config):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self._initialize()

    def get_ipaddr(self) -> str:
        return self["SOCKET"]["addr"]

    def set_ipaddr(self, addr: str) -> None:
        self["SOCKET"]["addr"] = addr

    def get_port(self) -> int:
        return int(self["SOCKET"]["port"])

    def set_port(self, port: int) -> None:
        self["SOCKET"]["port"] = str(port)

    def get_broker_address(self) -> str:
        return self["MQTT"]["broker_address"]

    def set_broker_address(self, broker_address: str) -> None:
        self["MQTT"]["broker_address"] = broker_address

    def get_id(self) -> str:
        return self["MQTT"]["id"]

    def set_id(self, _id: str) -> None:
        self["MQTT"]["id"] = _id

    def get_fullaccess_token(self) -> str:
        return self["MQTT"]["fullaccess_token"]

    def set_fullaccess_token(self, fullaccess_token: str) -> None:
        self["MQTT"]["fullaccess_token"] = fullaccess_token

    def get_readonly_token(self) -> str:
        return self["MQTT"]["readonly_token"]

    def set_readonly_token(self, readonly_token: str) -> None:
        self["MQTT"]["readonly_token"] = readonly_token

    def get_socket_options(self) -> dict[str, str]:
        return {option: self["SOCKET"][option] for option in self["SOCKET"]}

    def _initialize(self) -> None:
        try:
            self.load()
        except FileNotFoundError:
            self._generate()

    def _generate(self) -> None:
        self["SOCKET"] = {"addr": "127.0.0.1", "port": "49152"}
        self["MQTT"] = {
            "broker_address": "",
            "id": "",
            "fullaccess_token": "",
            "readonly_token": "",
        }
        self.save(chmod=0o777, create_directory=True)
        logger.info("External token file generated")


def exceptiondecorator[**P, R](
    func: Callable[P, R],
) -> Callable[P, R | None]:
    """
    MQTTのライブラリがインストールされていない場合を想定したデコレータです。
    実行した場合にログを出力します。
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
        try:
            return func(*args, **kwargs)
        except Exception:  # noqa
            logger.warning(
                "paho-mqtt may not be installed. Please make sure paho-mqtt is installed."
            )
            return None

    return wrapper


# socket通信用class
class SocketCommunications:
    SOCKET_TOKEN_PATH: str = ""

    def __init__(self) -> None:
        """
        初期設定
        return:なし
        """
        self.alive = False
        self.flag_socket = False

        # SOCKET設定
        self.token_file = ExternalToolsConfig(path=Path(self.SOCKET_TOKEN_PATH))
        self.sock: socket.socket | None = None

    @property
    def IPADDR(self) -> str:  # noqa
        return self.token_file.get_ipaddr()

    @property
    def PORT(self) -> int:  # noqa
        return self.token_file.get_port()

    def change_ipaddr(self, addr: str) -> None:
        """
        IPアドレスを変更する
        return:なし
        addr|str:IPアドレス
        """
        self.token_file.set_ipaddr(addr)

    def change_port(self, port: int) -> None:
        """
        ポート番号を変更する
        return:なし
        port|int:ポート番号
        """
        self.token_file.set_port(port)

    def sock_connect(self) -> None:
        """
        socket通信用のserverと接続する
        return:なし
        """
        try:
            self.sock = sock = socket.socket(socket.AF_INET)
            sock.connect((self.IPADDR, self.PORT))
            sock.settimeout(3.0)  # タイムアウト時間
            self.flag_socket = True
        except ConnectionRefusedError:
            logger.error("[error]serverが起動されていません")
        except OSError:
            pass

    # socket切断
    def sock_disconnect(self) -> None:
        """
        socket通信用のserverから切断する
        return:なし
        """
        try:
            if (sock := self.sock) is not None:
                sock.shutdown(socket.SHUT_RDWR)
                sock.close()
        except ConnectionRefusedError:
            logger.error("[error]serverが起動されていません")
        except OSError:
            pass
        finally:
            self.flag_socket = False

    def receive_message(self, header: str, show_msg: bool = False) -> str | None:
        """
        socketを用いて先頭が特定の文字列であるメッセージを受信する
        return output|str:受信した文字列
        header|str:受信したい文字列(先頭)
        show_msg|bool:受信した文字列を出力する
        """
        if (sock := self.sock) is None:
            return None

        # 待機文字列print出力
        logger.info(f"[socket:wait]:{header}")

        # 出力初期値設定
        output: str | None = None

        while True:
            try:
                # 受信する
                data = sock.recv(1024)
                if data == b"":
                    break
                message = data.decode("utf-8")

                # 先頭の文字列がheaderと一致するかを確認する
                if message[0 : len(header)] == header:
                    logger.info(f"[socket:recv]:{message}")
                    output = message
                    break
                elif show_msg:  # ログ出力
                    logger.info(f"[socket:recv]:{message}")
                if not self.alive:
                    break
            except ConnectionResetError:
                break
            except socket.timeout:  # timeout時,self.aliveを確認する
                if not self.alive:
                    break
            except ConnectionRefusedError:
                logger.error("[error]serverが起動されていません")
                break
            except OSError:
                break

        # stopを押した場合にsocketを切断する
        if not self.alive:
            # socket切断
            self.sock_disconnect()

        return output

    def receive_message2(
        self,
        headerlist: list[str],
        show_msg: bool = False,
    ) -> str | None:
        """
        socketを用いて先頭が特定の文字列(複数設定可能)であるメッセージを受信する
        return output|str:受信した文字列
        headerlist|list[str]:受信したい文字列(先頭)のリスト
        show_msg|bool:受信した文字列を出力する
        """
        if (sock := self.sock) is None:
            return None

        # 待機文字列print出力
        header0 = ",".join(headerlist)
        logger.info(f"[socket:wait]:{header0}")

        # 出力初期値設定
        output = None

        while True:
            try:
                # 受信する
                data = sock.recv(1024)
                if data == b"":
                    break
                message = data.decode("utf-8")

                # messageとheaderlist内の先頭の文字列が一致するかを確認する
                for header in headerlist:
                    if message[0 : len(header)] == header:
                        logger.info(f"[socket:recv]:{message}")
                        output = message
                if output:
                    break
                if show_msg:  # ログ出力
                    logger.info(f"[socket:recv]:{message}")
                if not self.alive:
                    break
            except ConnectionResetError:
                break
            except socket.timeout:  # timeout時,self.aliveを確認する
                if not self.alive:
                    break
            except ConnectionRefusedError:
                logger.error("[error]serverが起動されていません")
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
        socketを用いてメッセージを送信する
        return:なし
        message|str:送信するメッセージ
        """
        # 送信する
        if (sock := self.sock) is None:
            logger.warning("socket is not connected.")
            return

        sock.send(message.encode("utf-8"))
        logger.info(f"[socket:send]:{message}")


# global変数(MQTT受信用)
receive_msg: str | None = None


# MQTT通信用class
class MQTTCommunications:
    MQTT_TOKEN_PATH = ""

    def __init__(
        self,
        clientId: str,  # noqa
    ) -> None:
        """
        初期設定
        return:なし
        name|str:接続者名(重複してもよい)
        """
        self.alive = False

        # MQTT設定
        self.token_file = ExternalToolsConfig(path=Path(self.MQTT_TOKEN_PATH))

        fullaccess_token = self.token_file.get_fullaccess_token()
        readonly_token = self.token_file.get_readonly_token()
        self.pub_token: str | None = None
        self.sub_token: str | None = None
        if fullaccess_token != "":
            self.pub_token = fullaccess_token
            self.sub_token = fullaccess_token
        elif readonly_token != "":
            self.sub_token = readonly_token

        self.clientId: str = clientId
        self.client: mqtt.Client | None = None
        self.receive_msg = -1

    @property
    def broker_address(self) -> str:
        return self.token_file.get_broker_address()

    @property
    def id(self) -> str:
        return self.token_file.get_id()

    def change_broker_address(self, broker_address: str) -> None:
        """
        brokerアドレスを変更する
        return:なし
        broker_address|str:brokerアドレス
        """
        self.token_file.set_broker_address(broker_address)

    def change_id(
        self,
        id: str,  # noqa
    ) -> None:
        """
        IDを変更する
        return:なし
        id|str:ID
        """
        self.token_file.set_id(id)

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

    def change_clientId(  # noqa
        self,
        clientId: str,  # noqa
    ) -> None:
        """
        接続者名を変更する
        return:なし
        clientId|str:接続者名
        """
        self.clientId = clientId

    # noinspection PyMethodMayBeStatic
    def on_message(  # type: ignore[no-untyped-def]
        self,
        client,  # type: ignore[no-untyped-def, unused-ignore]
        userdata,  # type: ignore[no-untyped-def, unused-ignore]
        msg: mqtt.MQTTMessage,
    ) -> None:
        """
        メッセージを受信する
        return:なし
        client,userdata,msgはいいように設定してくれる
        """
        global receive_msg
        # print(f"ROOM ID: {msg.topic} message: {msg.payload.decode('utf-8')}")
        receive_msg = msg.payload.decode("utf-8")

    @exceptiondecorator
    def receive_message(
        self, roomid: str, header: str, show_msg: bool = False
    ) -> str | None:
        """
        MQTTを用いて先頭が特定の文字列であるメッセージを受信する
        return output|str:受信した文字列
        roomid|str:ROOM ID(topic)
        header|str:受信したい文字列(先頭)
        show_msg|bool:受信した文字列を出力する
        """
        # 待機文字列print出力
        logger.info(f"[mqtt:wait]:{header}")

        global receive_msg
        output: str | None = None
        header_date = int(datetime.datetime.today().strftime("%Y%m%d%H%M%S%f"))

        # brokerと接続する
        self.client = mqtt.Client(client_id=self.clientId)
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
                if receive_msg is not None:
                    if header_date < int(receive_msg[1:21]):
                        header_date = int(receive_msg[1:21])
                        message = receive_msg[22:]
                        # 先頭の文字列がheaderと一致するかを確認する
                        if message[0 : len(header)] == header:
                            output = message
                            logger.info(f"[mqtt:recv]:{message}")
                            break
                        elif show_msg:  # ログ出力
                            logger.info(f"[mqtt:recv]:{message}")

                # stop押下時にwhileから抜ける
                if not self.alive:
                    break
            except Exception:  # noqa
                break

        self.client.disconnect()

        return output

    @exceptiondecorator
    def receive_message2(
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
        # 待機文字列print出力
        header0 = ""
        for i in headerlist:
            header0 += i + ","
        logger.info(f"[socket:wait]:{header0}")

        global receive_msg
        output = None
        header_date = int(datetime.datetime.today().strftime("%Y%m%d%H%M%S%f"))

        # brokerと接続する
        self.client = mqtt.Client(client_id=self.clientId)
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
                                logger.info(f"[mqtt:recv]:{message}")
                        if output:
                            break
                        elif show_msg:  # ログ出力
                            logger.info(f"[mqtt:recv]:{message}")

                # stop押下時にwhileから抜ける
                if not self.alive:
                    break
            except Exception:  # noqa
                break

        self.client.disconnect()

        return output

    @exceptiondecorator
    def transmit_message(self, roomid: str, message: str) -> None:
        """
        MQTTを用いてメッセージを送信する
        return:なし
        roomid|str:ROOM ID(topic)
        message|str:送信するメッセージ
        """
        # メッセージ更新判定に日時情報を使用する
        header_date = datetime.datetime.today().strftime("[%Y%m%d%H%M%S%f]")
        if self.pub_token:
            self.client = mqtt.Client(client_id=self.clientId)
            self.client.username_pw_set(self.id, self.pub_token)
            self.client.connect(self.broker_address, 1883)
            message0 = header_date + message
            self.client.publish(roomid, message0)
            logger.info(f"[mqtt:send]:{message}")
        else:
            logger.info("token error(readonly)")

        if (c := self.client) is not None:
            c.disconnect()
