#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手動操作の記録の開始と終了

画面(tkinter)には触れない。記録そのものは Commands/InputRecorder.py、送信への組み込みは Sender が行う。
"""
from __future__ import annotations

from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING, Callable, NamedTuple

from Commands.InputRecorder import InputRecorder

if TYPE_CHECKING:
    from Commands.Sender import Sender

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

SOURCE_NAME = "手動操作"


class RecordError(Exception):
    """記録を開始できない(メッセージは、そのまま表示できる文)"""


class RecordResult(NamedTuple):
    """
    記録を終了した結果
    """

    recorded: bool  # 記録していたか(していなかった場合は、ほかの値は使わない)
    path: str | None = None  # 出力した自動化スクリプト(操作が無かった場合や、変換に失敗した場合は None)
    raw_log_path: str | None = None  # 生ログ
    error: Exception | None = None  # 変換に失敗した場合の例外


class RecordService:
    """手動操作の記録を始める・終える(記録できる状態かを確かめてから、Sender に組み込む)"""

    def __init__(self, sender: Sender, is_command_running: Callable[[], bool], raw_log_dir: str):
        """
        sender: 送信に使う Sender、is_command_running: コマンドを実行中かを返す関数、raw_log_dir: 生ログの保存先
        """
        self.sender = sender
        self._is_command_running = is_command_running
        self.raw_log_dir = raw_log_dir

    def is_recording(self) -> bool:
        """記録中か"""
        return self.sender.recording

    def start(self) -> InputRecorder:
        """
        記録を始める。始められない場合は RecordError を送出する
        """
        if self._is_command_running():
            raise RecordError("コマンド実行中は操作記録を開始できません。")
        if not self.sender.isOpened():
            raise RecordError("シリアルが接続されていないため、操作記録を開始できません。")
        recorder = InputRecorder(source_name=SOURCE_NAME, raw_log_dir=self.raw_log_dir)
        try:
            recorder.start()
        except OSError as e:
            _logger.error(f"Failed to start recording: {e}")
            raise RecordError(f"操作記録を開始できませんでした: {e}")
        self.sender.start_recording(recorder)
        return recorder

    def stop(self) -> RecordResult:
        """
        記録を終了し、自動化スクリプトを出力する(記録していなかった場合と、失敗した場合も、例外にせず結果で返す)
        """
        recorder = self.sender.stop_recording()
        if recorder is None:
            return RecordResult(False)
        try:
            path = recorder.stop()
        except Exception as e:
            _logger.error(f"Failed to write the record: {e}")
            return RecordResult(True, None, recorder.raw_log_path, e)
        if path is not None:
            _logger.info(f"Record is saved: {path}")
        return RecordResult(True, path, recorder.raw_log_path)
