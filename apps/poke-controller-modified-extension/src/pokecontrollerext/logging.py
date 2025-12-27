import tomllib

from pokecontroller.utils import logging as logginglib

# @formatter:off (for PyCharm)
# fmt: off
# language=TOML
DEFAULT_TOML: str = """
# 注意:
# Python標準のloggingモジュールにおけるロギング設定を理解している場合のみ編集してください。
# また、アプリケーションのデフォルトの設定は将来変更される可能性があります。
# See: https://docs.python.org/ja/3.12/howto/logging.html

version = 1
disable_existing_loggers = false

# formatters
[formatters.pokeconExtension]
class = "pokecontroller.utils.logging.StandardFormatter"
format = "%(asctime)s [%(levelname)8s] %(name)s.%(class)s#%(funcName)s: %(message)s"
datefmt = "%Y-%m-%d %H:%M:%S"

[formatters.pokeconExtensionColored]
class = "pokecontroller.utils.logging.ColoredFormatter"
format = "%(asctime)s [%(levelname)8s] %(name)s.%(class)s#%(funcName)s: %(message)s"
datefmt = "%Y-%m-%d %H:%M:%S"

# handlers
[handlers.pokeconExtensionConsole]
class = "logging.StreamHandler"
level = "INFO"
formatter = "pokeconExtensionColored"
stream = "ext://sys.stdout"

[handlers.pokeconExtensionFile]
class = "logging.handlers.TimedRotatingFileHandler"
level = "WARNING"
formatter = "pokeconExtension"
filters = []
filename = "log/pokecon-modified-extension.log"
when = "midnight"
backupCount = 10
encoding = "utf-8"

[handlers.pokeconExtensionCommandsFile]
class = "logging.handlers.TimedRotatingFileHandler"
level = "WARNING"
formatter = "pokeconExtension"
filters = []
filename = "log/pokecon-modified-extension-commands.log"
when = "midnight"
backupCount = 10
encoding = "utf-8"

# loggers
[loggers.pokecontroller]
level = "INFO"
handlers = ["pokeconExtensionFile"]

[loggers.pokecontrollerext]
level = "INFO"
handlers = ["pokeconExtensionFile"]

[loggers.Commands]
level = "INFO"
handlers = ["pokeconExtensionCommandsFile"]

[root]
level = "WARNING"
handlers = ["pokeconExtensionConsole"]
""".strip()
# fmt: on
# @formatter:on


def setup_logging(
    config_path: str | None = None,
    *,
    debug: bool | None = None,
    show_config: bool = False,
) -> None:
    """
    Python標準のloggingモジュールを設定する

    Args:
        config_path: 設定ファイル(toml形式)のパス
        debug: Trueの場合、登録済みのLogger、HandlerをロギングレベルをDEBUGレベルに設定する
        show_config: Trueの場合、現在の設定を標準出力に表示します
    """
    logginglib.setup_logging(
        config_path=config_path,
        defaults=tomllib.loads(DEFAULT_TOML),
        debug=debug,
        show_config=show_config,
    )
