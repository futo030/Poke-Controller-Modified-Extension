import logging
from collections.abc import Buffer
from dataclasses import dataclass

import serial
from serial.tools import list_ports

logger = logging.getLogger(__name__)

LINESEP = "\r\n"


@dataclass
class SerialPort:
    """シリアルポートの情報を保持するデータクラス.

    Attributes:
        path: シリアルポートのデバイスパス.
        name: シリアルポートの名前.
        description: シリアルポートの説明.
    """

    path: str
    name: str
    description: str


def get_serial_ports() -> list[SerialPort]:
    """システムで利用可能なシリアルポートのリストを取得します.

    Returns:
        利用可能なシリアルポート情報のリスト.
    """
    return [
        SerialPort(
            path=port.device,
            name=port.name,
            description=port.description,
        )
        for port in list_ports.comports()
    ]


class Serial:
    """シリアル通信を管理するクラス.

    シリアルポートの開閉とデータ送信をサポートします。
    """

    def __init__(self) -> None:
        """Serialインスタンスを初期化します."""
        self._serial: serial.Serial | None = None

    @property
    def is_opened(self) -> bool:
        """シリアルポートが開いているかどうかを取得します.

        Returns:
            ポートが開いている場合はTrue、それ以外はFalse.
        """
        if (s := self._serial) is None:
            return False
        return s.is_open  # type: ignore[no-any-return]

    def open(self, port_path: str, baud_rate: int) -> None:
        """シリアルポートを開きます.

        既に開いているポートがあれば先に閉じてから、
        指定されたパスとボーレートで新しいポートを開きます。

        Args:
            port_path: シリアルポートのデバイスパス.
            baud_rate: 通信速度（ボーレート）.
        """
        self.close()
        self._serial = serial.Serial(port_path, baud_rate)

    def close(self) -> None:
        """シリアルポートを閉じます.

        ポートが開いていない場合は何もしません。
        """
        if (s := self._serial) is None:
            logger.debug("Serial port is not opened")
            return
        if s.is_open:
            logger.debug(f"Closing serial port: {s.port}")
            s.close()
            logger.debug(f"Serial port closed: {s.port}")
        self._serial = None

    def write(self, data: Buffer) -> None:
        """シリアルポートにデータを書き込みます.

        ポートが開いていない場合は何もしません。

        Args:
            data: 書き込むデータ.
        """
        if (s := self._serial) is None:
            return

        if s.is_open:
            s.write(data)

    def write_line(self, line: str) -> None:
        """シリアルポートに1行のテキストを書き込みます.

        行末に改行コード（\\r\\n）を自動的に追加します。

        Args:
            line: 書き込むテキスト行.
        """
        self.write(f"{line}{LINESEP}".encode("utf-8"))
