from contextlib import contextmanager
from typing import Generator

from pokecontroller.core.serial.serial import Serial


@contextmanager
def use_serial() -> Generator[Serial, None, None]:
    """シリアル通信をコンテキストマネージャーとして使用するための関数.

    with文で使用することで、シリアルポートの自動的なクリーンアップを保証します。

    Yields:
        Serialインスタンス.

    Examples:
        >>> with use_serial() as ser:
        ...     ser.open("/dev/ttyUSB0", 9600)
        ...     ser.write_line("Hello")
    """
    serial = Serial()
    try:
        yield serial
    finally:
        serial.close()
