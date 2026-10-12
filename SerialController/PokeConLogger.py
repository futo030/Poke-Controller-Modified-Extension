#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This code has copied from https://qiita.com/Esfahan/items/275b0f124369ccf8cf18

ログの出力先: コンソールと、ファイル(./log/log_プロファイル名_起動日時.log)。
ファイルの名前にプロファイルの名前を入れるので、ファイルは、プロファイルが決まってから作る(set_profile)。
それまでのログは、覚えておいて、ファイルを作ったときに書き出す。
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import re
import datetime as dt
from logging import Formatter, StreamHandler, getLogger, DEBUG

now = dt.datetime.now()
time = now.strftime("%Y%m%d-%H%M%S")

LOG_DIR = "./log"
LOG_FORMAT = "%(asctime)s %(name)s %(funcName)s [%(levelname)s]: %(message)s"
# プロファイルが決まるまでに、覚えておくログの件数(超えた分は、古い方から捨てる)
EARLY_RECORDS_MAX = 2000
# DEBUG のログを出さないライブラリ(urllib3 は、接続先の URL をそのまま書く。Discord の Webhook の URL は、それ自体が秘密の値)
QUIET_LOGGERS = ("urllib3",)
# ファイルの名前に使えない文字(プロファイルの名前に入っていた場合は、_ に置き換える)
_UNSAFE_CHARACTERS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

mapping = {
    "TRACE": " trace ]",
    "DEBUG": " \x1b[0;36mdebug\x1b[0m ",
    "INFO": "  \x1b[0;32minfo\x1b[0m ",
    "WARNING": "  \x1b[0;33mwarn\x1b[0m ",
    "WARN": "  \x1b[0;33mwarn\x1b[0m ",
    "ERROR": "\x1b[0;31m error \x1b[0m",
    "ALERT": "\x1b[0;37;41m alert \x1b[0m",
    "CRITICAL": "\x1b[0;37;41m alert \x1b[0m",
}

# プロファイルが決まるまでのログを覚えておくハンドラーと、今のログのファイルの場所(まだ作っていなければ None)
_early_handler: EarlyRecords | None = None
_log_file_path: str | None = None


class ColorfulHandler(logging.StreamHandler):
    """ログのレベルの名前に、色を付けて出力する(今は使っていない)"""

    def emit(self, record: logging.LogRecord) -> None:
        """レベルの名前を、色を付けた文字に置き換えてから出力する(mapping に無い名前は KeyError)"""
        record.levelname = mapping[record.levelname]
        super().emit(record)


class EarlyRecords(logging.Handler):
    """ログのファイルを作るまでの間、記録を覚えておくハンドラー"""

    def __init__(self, capacity: int = EARLY_RECORDS_MAX):
        """capacity: 覚えておく件数(超えた分は、古い方から捨てる)"""
        super().__init__(DEBUG)
        self.capacity = capacity
        self.records: list = []

    def emit(self, record: logging.LogRecord) -> None:
        """記録を覚える"""
        self.records.append(record)
        if len(self.records) > self.capacity:
            del self.records[: len(self.records) - self.capacity]


def log_file_name(profile: str) -> str:
    """ログのファイルの名前(log_プロファイル名_起動日時.log。名前に使えない文字は、_ に置き換える)"""
    safe = _UNSAFE_CHARACTERS.sub("_", str(profile)).strip() or "_"
    return f"log_{safe}_{time}.log"


def log_file_path() -> str | None:
    """今のログのファイルの場所(まだ作っていなければ None)"""
    return _log_file_path


def root_logger(profile: str | None = None) -> logging.Logger:
    """
    ルートのロガーに、コンソールへの出力を足して返す。レベルは DEBUG にする。./log フォルダーが無い場合は、作る。
    profile を渡した場合は、ファイル(./log/log_プロファイル名_起動日時.log)への出力も足す。
    渡さない場合は、set_profile を呼ぶまで、記録を覚えておく(プロファイルを、起動した後に選ぶ場合)
    """
    global _early_handler
    # logging.basicConfig(handlers=[ColorfulHandler()], level=logging.DEBUG)
    # root loggerを取得
    logger = getLogger()

    # handlerを作成しフォーマッターを設定
    # handler = ColorfulHandler()
    handler = StreamHandler()
    handler.setFormatter(Formatter(LOG_FORMAT))

    # (ログのフォルダーが無ければ、作る)
    os.makedirs(LOG_DIR, exist_ok=True)

    # loggerにhandlerを設定、イベント捕捉のためのレベルを設定
    logger.addHandler(handler)
    # log levelを設定
    logger.setLevel(DEBUG)
    for name in QUIET_LOGGERS:
        getLogger(name).setLevel(logging.INFO)
    if profile is not None:
        set_profile(profile)
    elif _early_handler is None and _log_file_path is None:
        _early_handler = EarlyRecords()
        logger.addHandler(_early_handler)
    return logger


def set_profile(profile: str) -> str | None:
    """
    プロファイルが決まったとき: ログのファイル(./log/log_プロファイル名_起動日時.log)を作り、ルートのロガーに足す。
    それまでに覚えておいた記録も、ファイルに書く。作ったファイルの場所を返す
    (すでに作っている場合は、何もしないで、その場所を返す。作れないときは、コンソールに知らせて None)
    """
    global _early_handler, _log_file_path
    if _log_file_path is not None:
        return _log_file_path
    logger = getLogger()
    path = os.path.join(LOG_DIR, log_file_name(profile))
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
    except OSError as error:
        logger.warning(f"Failed to create the log file: {error}")
        return None
    file_handler.setFormatter(Formatter(LOG_FORMAT))
    early, _early_handler = _early_handler, None
    if early is not None:
        logger.removeHandler(early)
        for record in early.records:
            file_handler.handle(record)
        early.records = []
    logger.addHandler(file_handler)
    _log_file_path = os.path.abspath(path)
    return _log_file_path
