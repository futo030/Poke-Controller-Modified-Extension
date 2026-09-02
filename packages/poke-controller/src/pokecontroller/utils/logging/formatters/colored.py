import logging
import os
import sys

from pokecontroller.utils.logging.formatters.standard import StandardFormatter
from pokecontroller.utils.platform import is_windows

RESET = "\033[0m"
ESCAPED_LEVELS = {
    level: f"{esc}{level}{RESET}"
    for level, esc in [
        ("DEBUG", "   \033[36m"),  # Cyan
        ("INFO", "    \033[32m"),  # Green
        ("WARNING", " \033[33m"),  # Yellow
        ("ERROR", "   \033[31m"),  # Red
        ("CRITICAL", "\033[37;41m"),  # White on Red
    ]
}


class ColoredFormatter(StandardFormatter):
    """クロスプラットフォーム対応のカラーログフォーマッター.

    ANSIエスケープシーケンスを使用してログレベルに色を付けます。
    Windows 10以降ではANSI対応を自動的に有効化します。
    環境変数（NO_COLOR、FORCE_COLOR）による色の制御にも対応しています。
    """

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        use_colors: bool | None = None,
    ) -> None:
        """ColoredFormatterインスタンスを初期化します.

        Args:
            fmt: ログフォーマット文字列.
            datefmt: 日時フォーマット文字列.
            use_colors: 色を使用するかどうか. Noneの場合は自動判定します.
        """
        super().__init__(fmt=fmt, datefmt=datefmt)

        if use_colors is None:
            self.use_colors = self._should_use_colors()
        else:
            self.use_colors = use_colors

        if self.use_colors and is_windows():
            self._enable_window_ansi()

    def format(self, record: logging.LogRecord) -> str:
        """ログレコードをフォーマットします.

        色が有効な場合、ログレベル名をANSIエスケープシーケンスで装飾します。
        フォーマット後はログレコードを元の状態に戻し、他のハンドラーに
        影響を与えないようにします。

        Args:
            record: ログレコード.

        Returns:
            フォーマットされたログ文字列（色付き、または色なし）.
        """
        if not self.use_colors:
            return super().format(record)

        levelname_original = record.levelname
        if levelname_original not in ESCAPED_LEVELS:
            return super().format(record)

        record.levelname = ESCAPED_LEVELS[levelname_original]
        result = super().format(record)
        # 元に戻す(他のHandlerに影響を与えないため)
        record.levelname = levelname_original
        return result

    # noinspection PyMethodMayBeStatic
    def _should_use_colors(self) -> bool:
        """色を使用するべきか判定する"""

        if os.getenv("NO_COLOR"):
            return False
        if os.getenv("FORCE_COLOR"):
            return True
        if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
            return False
        if os.getenv("CI"):
            return False
        return True

    def _enable_window_ansi(self) -> None:
        """Windows 10以降でANSIエスケープシーケンスを有効化"""

        try:
            # Windows 10 バージョン1511以降で利用可能
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined,unused-ignore]
            # STD_OUTPUT_HANDLE = -11
            handle = kernel32.GetStdHandle(-11)  # noqa
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))  # noqa
            mode.value |= 0x0004
            kernel32.SetConsoleMode(handle, mode)  # noqa
        except Exception:  # noqa
            # 失敗しても続行(色なし)
            self.use_color = False
