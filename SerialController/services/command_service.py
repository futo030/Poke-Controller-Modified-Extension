#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
コマンド(自動化スクリプト)の読み込みと実行の管理

画面(tkinter)には触れない。画面側は、状態が変わったときに呼ばれる on_state_changed で表示を合わせる。
    IDLE     : 実行していない
    RUNNING  : 実行中
    STOPPING : 停止を頼んで、コマンドが終わるのを待っている

コマンドが終わったことの知らせ(Pythonコマンドは実行スレッドから、画面のスレッドへの受け渡しを通って届く)を
受けて IDLE に戻すので、on_state_changed は、画面のスレッドで呼ばれる。
"""
from __future__ import annotations

import sys
from datetime import datetime
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING, Callable

import Utility as util
from CommandLoader import CombinedLoader, CommandLoader
from Commands import McuCommandBase, PythonCommandBase
from Commands.CommandBase import Command
from services import command_catalog, command_usage
from services.run_list import RunListLoader

if TYPE_CHECKING:
    from CommandLoader import CommandEntry
    from Commands.Sender import Sender

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

IDLE = "idle"
RUNNING = "running"
STOPPING = "stopping"

PYTHON = "Python"
MCU = "Mcu"
# コマンドの種類ごとの、置き場所と基底クラス
COMMAND_TYPES = {
    PYTHON: ("Commands/PythonCommands", PythonCommandBase.PythonCommand),
    MCU: ("Commands/McuCommands", McuCommandBase.McuCommand),
}
# 追加の機能(--ext)が足す、コマンドの読み込み先。種類ごとに「読み込み先を作る関数」を並べる
# (読み込み先は、load / reload / findEntry / getCommandClass を持つもの。一覧には、元のコマンドの後ろに並ぶ)
EXTRA_LOADERS = {PYTHON: [], MCU: []}


class CommandLoadError(Exception):
    """コマンドのファイルを読み込めなかった(文法の誤り、import の失敗など)"""

    def __init__(self, entry: CommandEntry):
        """entry: 読み込めなかったコマンドの情報(self.entry に残す)"""
        super().__init__(f"Failed to load command: {entry.module_name}")
        self.entry = entry


class CommandService:
    """コマンドの一覧の読み込みと、実行の対象のコマンドの用意・開始・停止・一時停止をまとめる"""

    def __init__(
        self,
        get_camera: Callable[[], object],
        get_gui: Callable[[], object],
        on_state_changed: Callable[[str], None] | None = None,
    ):
        """
        get_camera / get_gui: 画像認識を使うコマンドに渡す、カメラとプレビュー(認識した位置の表示先)を返す関数
        on_state_changed: 状態(IDLE / RUNNING / STOPPING)が変わったときに呼ぶ関数
        """
        self._get_camera = get_camera
        self._get_gui = get_gui
        self._on_state_changed = on_state_changed
        self.state = IDLE
        self.loaders = {}
        self.commands = {PYTHON: [], MCU: []}
        # 最後に用意したコマンド(種類ごと)と、実行の対象のコマンド
        self.current_by_type = {PYTHON: None, MCU: None}
        self.current = None
        # 実行中のコマンドを開始した時刻(まだ開始していなければ None。終わった後も、次に開始するまで残る)
        self.started_at = None

    # ---------------------------------------------------------------- 一覧

    def load(self) -> None:
        """
        コマンドの一覧のみ取得する(モジュールは、実行・読み直しのときに必要なものだけ import する)
        """
        self.loaders = {
            command_type: CommandLoader(util.ospath(path), base_class)
            for command_type, (path, base_class) in COMMAND_TYPES.items()
        }
        # 保存してある実行リスト(コマンドの連続実行)は、Python コマンドの一覧の後ろに出す。
        # 追加の機能が足した読み込み先は、その種類の一覧に、さらに続けて出す
        for command_type, factories in EXTRA_LOADERS.items():
            extras = [RunListLoader(self)] if command_type == PYTHON else []
            extras += [factory() for factory in factories]
            if extras:
                self.loaders[command_type] = CombinedLoader(self.loaders[command_type], *extras)
        self.commands = {command_type: loader.load() for command_type, loader in self.loaders.items()}
        self.current_by_type = {PYTHON: None, MCU: None}
        self.current = None

    def reload(self) -> None:
        """
        コマンドの一覧を取得し直す
        """
        self.commands = {command_type: loader.reload() for command_type, loader in self.loaders.items()}

    # ---------------------------------------------------------------- 使用頻度

    def record_usage(self, command_type: str, name: str) -> None:
        """
        そのコマンドを実行した回数を、1 つ増やす(一覧にない名前のときは、何もしない)
        command_type: 種別("Python" / "Mcu"。"py" などの書き方も受け付ける)、name: 一覧の名前
        """
        command_type = command_catalog.normalize_command_type(command_type)
        loader = self.loaders.get(command_type)
        entry = loader.findEntry(name) if loader is not None else None
        if entry is not None:
            command_usage.record(command_type, entry)

    def usage_counts(self, command_type: str) -> dict:
        """その種別の一覧のコマンドについて、{一覧の名前: 実行した回数} を返す(ほかのウィンドウで実行した分も含む)"""
        return command_usage.counts_of(command_type, self.commands.get(command_type, []))

    # ---------------------------------------------------------------- 用意

    def needs_import(self, command_type: str, name: str, reload: bool = False) -> bool:
        """
        そのコマンドを用意するときに、モジュールの読み込みが起きるか(まだ読み込んでいない、または読み込み直す)。
        読み込みに時間がかかるスクリプトがあるので、画面が、読み込み中の表示を出すかを決めるのに使う
        """
        loader = self.loaders.get(command_type)
        entry = loader.findEntry(name) if loader is not None else None
        module_name = getattr(entry, "module_name", None)
        if not module_name:
            return False
        return reload or module_name not in sys.modules

    def find_class(self, command_type: str, name: str, reload: bool = False) -> type | None:
        """
        コマンド名に対応するクラスを返す(その名前のコマンドが無い場合はNone)。
        モジュールが未 import の場合(reload=True の場合は常に)、そのモジュールと必要なモジュールのみ import する。
        読み込めなかった場合は CommandLoadError
        """
        loader = self.loaders[command_type]
        entry = loader.findEntry(name)
        if entry is None:
            print(f"Command '{name}' is not found.")
            _logger.error(f"Command '{name}' is not found.")
            return None
        try:
            return loader.getCommandClass(entry, reload=reload)
        except Exception:
            _logger.exception(f"Failed to load command: {entry.module_name}")
            print(f"Failed to load command: {entry.module_name}")
            raise CommandLoadError(entry)

    def create(self, command_type: str, command_class: type) -> Command:
        """
        コマンドのインスタンスを作る(画像認識を使う Python コマンドには、カメラとプレビューを渡す)
        """
        if command_type != PYTHON:
            return command_class()
        # pythonコマンドは画像認識を使うかどうかで分岐している
        if issubclass(command_class, PythonCommandBase.ImageProcPythonCommand):
            try:  # 画像認識の際に認識位置を表示する引数追加。互換性のため従来のはexceptに。
                return command_class(self._get_camera(), self._get_gui())
            except TypeError:
                return command_class(self._get_camera())
            except Exception:
                return command_class(self._get_camera())
        return command_class()

    def assign(self, command_type: str, name: str, reload: bool = False) -> bool:
        """
        実行の対象のコマンドを用意する。用意できたか(その名前のコマンドが無い場合はFalse)を返す
        """
        command_class = self.find_class(command_type, name, reload)
        if command_class is None:
            return False
        self.set_current(command_type, self.create(command_type, command_class))
        return True

    def set_current(self, command_type: str, command: Command) -> None:
        """用意したコマンドを、その種類の最後のコマンドと、実行の対象として覚える"""
        self.current_by_type[command_type] = command
        self.current = command

    # ---------------------------------------------------------------- 実行

    @property
    def is_running(self) -> bool:
        """実行中か(停止を頼んで、終わるのを待っている間を含む)"""
        return self.state != IDLE

    @property
    def can_pause(self) -> bool:
        """一時停止できるコマンドか(Mcuコマンドはマイコン側で動くため、一時停止できない)"""
        # (CAN_PAUSE = False のコマンドも、一時停止できない。別のプログラムに処理を任せるコマンドなど)
        return isinstance(self.current, PythonCommandBase.PythonCommand) and getattr(self.current, "CAN_PAUSE", True)

    def start(self, ser: Sender, output_page: int) -> None:
        """
        用意したコマンドを実行する。
        ser: 送信に使う Sender、output_page: コマンドの出力先のページ
        """
        Command.cur_command_name = self.current.NAME
        # 開始時のページを、コマンドの出力先として記録する
        Command.output_page = output_page
        self.started_at = datetime.now()
        self.current.start(ser, self._finished)
        self._set_state(RUNNING)

    def stop(self, ser: Sender) -> None:
        """
        実行中のコマンドに停止を頼む(コマンドが終わると IDLE になる)
        """
        Command.isPause = False
        self._set_state(STOPPING)
        self.current.end(ser)

    def pause(self) -> None:
        """実行中のコマンドを一時停止する(Command.isPause を立てる。コマンドは、それを確かめた所で止まる)"""
        Command.isPause = True

    def resume(self) -> None:
        """一時停止を解く"""
        Command.isPause = False

    def _finished(self) -> None:
        """コマンドが終わったときに呼ばれる(IDLE に戻す)"""
        self._set_state(IDLE)

    def _set_state(self, state: str) -> None:
        """状態を変えて、on_state_changed に知らせる"""
        self.state = state
        if self._on_state_changed is not None:
            self._on_state_changed(state)
