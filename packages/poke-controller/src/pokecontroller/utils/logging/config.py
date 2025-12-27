import logging
import logging.config
import os
import sys
import tomllib
from pathlib import Path
from typing import Any


def setup_logging(
    config_path: str | None = None,
    defaults: dict[str, Any] | None = None,
    *,
    debug: bool | None = None,
    show_config: bool = False,
) -> None:
    """
    Python標準のloggingモジュールを設定する

    Args:
        config_path: 設定ファイル(toml形式)のパス
        defaults: デフォルト設定の辞書
        debug: Trueの場合、登録済みのLogger、HandlerをロギングレベルをDEBUGレベルに設定する
        show_config: Trueの場合、現在の設定を標準出力に表示します
    """
    if config_path is None:
        _apply_defaults(defaults=defaults)
    elif Path(config_path).exists():
        _load_from_file(config_path)
    else:
        raise FileNotFoundError(f"Logging config file not found: {config_path}")

    if _should_enable_debug(debug=debug):
        _enable_debug_mode()

    if show_config:
        show_current_config()


def show_current_config() -> None:
    """現在のロギング設定を標準出力に表示します.

    ルートロガー、登録済みロガー、各ハンドラー、フィルター、
    フォーマッターの情報を整形して表示します。
    """
    print("\n" + "=" * 60)
    print("Logging Configuration")
    print("=" * 60)

    # Root logger
    root_logger = logging.getLogger()
    print("\n[Root Logger]")
    print(f"  Level: {logging.getLevelName(root_logger.level)}")
    print(f"  Handlers: {len(root_logger.handlers)}")
    print(f"  Filters: {len(root_logger.filters)}")

    # Root logger's filters
    if root_logger.filters:
        for i, filter_obj in enumerate(root_logger.filters):
            _print_filter(filter_obj, i, indent=4)

    # Root logger's handlers
    for i, handler in enumerate(root_logger.handlers):
        _print_handler(handler, i, indent=4)

    # Registered loggers
    logger_dict = logging.Logger.manager.loggerDict
    actual_loggers = {
        name: obj
        for name, obj in logger_dict.items()
        if isinstance(obj, logging.Logger)
    }

    if actual_loggers:
        print(f"\n[Registered Loggers] ({len(actual_loggers)} total)")
        for logger_name in sorted(actual_loggers.keys()):
            logger = logging.getLogger(logger_name)
            print(f"  '{logger_name}'")
            print(f"    Level: {logging.getLevelName(logger.level)}")
            print(f"    Propagate: {logger.propagate}")
            print(f"    Filters: {len(logger.filters)}")

            # Logger's filters
            if logger.filters:
                for i, filter_obj in enumerate(logger.filters):
                    _print_filter(filter_obj, i, indent=6)

            # Logger's handlers
            if logger.handlers:
                print(f"    Handlers: {len(logger.handlers)}")
                for i, handler in enumerate(logger.handlers):
                    _print_handler(handler, i, indent=6)

    print("=" * 60 + "\n")


def _load_from_file(config_path: str, encoding: str | None = "utf-8-sig") -> None:
    """設定ファイルから設定を読み込む"""
    with open(config_path, mode="rb", encoding=encoding) as f:
        config = tomllib.load(f)
        logging.config.dictConfig(config)


def _apply_defaults(defaults: dict[str, Any] | None = None) -> None:
    """デフォルト設定を適用"""
    if defaults is not None:
        logging.config.dictConfig(defaults)


def _should_enable_debug(debug: bool | None = None) -> bool:
    """デバッグモードを有効にすべきか判定"""

    # 明示的に指定された場合はそれに従う
    if debug is not None:
        return debug

    # 環境変数をチェック
    if os.getenv("DEBUG", "").lower() in ("1", "true", "yes"):
        return True

    # -X dev フラグをチェック
    if sys.flags.dev_mode:
        return True

    return False


def _enable_debug_mode(base_logger_name: str | None = None) -> None:
    """すべてのロガーをDEBUGレベルに設定"""

    # base logger
    base_logger = logging.getLogger(name=base_logger_name)
    base_logger.setLevel(logging.DEBUG)

    # all handers
    for handler in base_logger.handlers:
        handler.setLevel(logging.DEBUG)

    # all loggers
    for logger_name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        for handler in logger.handlers:
            handler.setLevel(logging.DEBUG)

    logging.getLogger(__name__).debug(
        "Debug mode enabled: All loggers set to DEBUG level."
    )


def _print_handler(handler: logging.Handler, index: int, indent: int = 0) -> None:
    """ハンドラー情報を表示"""
    prefix = " " * indent
    print(f"{prefix}[{index}] {handler.__class__.__name__}")
    print(f"{prefix}    Level: {logging.getLevelName(handler.level)}")

    # ファイルハンドラーの場合はファイル名も表示
    if hasattr(handler, "baseFilename"):
        print(f"{prefix}    File: {handler.baseFilename}")

    # ストリームハンドラーの場合はストリーム情報
    if hasattr(handler, "stream"):
        stream = handler.stream
        if hasattr(stream, "name"):
            print(f"{prefix}    Stream: {stream.name}")
        else:
            print(f"{prefix}    Stream: {type(stream).__name__}")

    # フォーマッター情報
    if handler.formatter:
        _print_formatter(handler.formatter, indent=indent + 4)
    else:
        print(f"{prefix}    Formatter: None")

    # フィルター情報
    if handler.filters:
        print(f"{prefix}    Filters: {len(handler.filters)}")
        for i, filter_obj in enumerate(handler.filters):
            _print_filter(filter_obj, i, indent=indent + 6)
    else:
        print(f"{prefix}    Filters: 0")


def _print_formatter(formatter: logging.Formatter, indent: int = 0) -> None:
    """フォーマッター情報を表示"""
    prefix = " " * indent
    print(f"{prefix}Formatter: {formatter.__class__.__name__}")

    # フォーマット文字列
    if hasattr(formatter, "_fmt"):
        fmt = formatter._fmt
    else:
        fmt = None

    if fmt:
        print(f"{prefix}  Format: {fmt}")

    # 日付フォーマット
    if formatter.datefmt:
        print(f"{prefix}  DateFormat: {formatter.datefmt}")

    # カスタムフォーマッターの追加属性（ColoredFormatterなど）
    if hasattr(formatter, "use_colors"):
        print(f"{prefix}  UseColors: {formatter.use_colors}")


def _print_filter(filter_obj: Any, index: int, indent: int = 0) -> None:
    """フィルター情報を表示"""
    prefix = " " * indent

    # フィルタークラス名
    filter_class = filter_obj.__class__.__name__
    print(f"{prefix}[{index}] {filter_class}")

    # 標準のFilterの場合はnameを表示
    if isinstance(filter_obj, logging.Filter) and hasattr(filter_obj, "name"):
        if filter_obj.name:
            print(f"{prefix}    Name: {filter_obj.name}")

    # カスタムフィルターの場合、主要な属性を表示
    # __dict__から内部属性(_で始まるもの)を除外して表示
    custom_attrs = {
        k: v
        for k, v in filter_obj.__dict__.items()
        if not k.startswith("_") and k != "name"
    }
    if custom_attrs:
        for key, value in custom_attrs.items():
            value_str = str(value)
            print(f"{prefix}    {key}: {value_str}")
