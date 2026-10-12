#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
実行リスト(コマンドの連続実行)

画面(tkinter)には触れない。
- 実行リストは、コマンドを並べたもの。上から順に実行する(行ごとに、繰り返す回数と、制限時間を持てる)
- プロファイルごとに、設定ファイルと同じフォルダーの run_lists.json に保存する
- 保存した実行リストは、Python コマンドの一覧に「名前 (実行リスト)」として並び、ふつうのコマンドと同じように
  開始・停止・一時停止できる(RunListLoader が一覧に足し、RunListCommand が、中のコマンドを順に動かす)
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING, Any

from CommandLoader import CommandEntry
from Commands import PythonCommandBase
from Commands.CommandBase import Command
from Commands.PythonCommandBase import PythonCommand, StopThread
from services.settings_store import AppSettings

if TYPE_CHECKING:
    from services.command_service import CommandService

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

FILE_NAME = "run_lists.json"
FORMAT_VERSION = 1
PYTHON = "Python"
MCU = "Mcu"
COMMAND_TYPES = (PYTHON, MCU)
# コマンドの一覧に出すときに、名前の後ろに付ける文字と、付けるタグ
NAME_SUFFIX = " (実行リスト)"
LIST_TAG = "@実行リスト"
NAME_MAX_LENGTH = 50
REPEAT_MAX = 9999
LIMIT_MAX_MINUTES = 60 * 24 * 7
INTERVAL_MAX_SECONDS = 3600
# エラーで終わったコマンドがあったとき: リストを中止する / 次のコマンドへ進む
ON_ERROR_STOP = "stop"
ON_ERROR_NEXT = "next"
ON_ERRORS = (ON_ERROR_STOP, ON_ERROR_NEXT)
# リスト全体の繰り返しの回数で、「Stop を押すまで繰り返す」を表す値
LOOP_FOREVER = 0


@dataclass
class RunItem:
    """実行リストの 1 行"""

    command_type: str  # "Python" / "Mcu"
    name: str  # コマンドの一覧に出ている名前
    repeat: int = 1  # 続けて実行する回数
    limit_minutes: float | None = None  # 制限時間(分)。過ぎたら、止めて次へ進む。None: 終わるまで待つ


@dataclass
class RunList:
    """実行リスト"""

    name: str
    items: list = field(default_factory=list)
    interval_seconds: float = 1.0  # コマンドとコマンドの間に待つ時間(秒)
    on_error: str = ON_ERROR_STOP
    loops: int = 1  # リスト全体を繰り返す回数(LOOP_FOREVER: Stop を押すまで)

    @property
    def display_name(self) -> str:
        """コマンドの一覧に出す名前"""
        return self.name + NAME_SUFFIX


def lists_path() -> str:
    """今のプロファイルの、実行リストのファイルの場所(設定ファイルと同じフォルダー)"""
    return os.path.join(os.path.dirname(os.path.abspath(AppSettings.SETTING_PATH)), FILE_NAME)


def is_list_name(command_type: str, name: str) -> bool:
    """コマンドの一覧の名前が、実行リストのものか(実行リストの中に、実行リストは入れられない)"""
    return command_type == PYTHON and name.endswith(NAME_SUFFIX)


# ---------------------------------------------------------------- 確かめる


def check_name(name: str, others: list | tuple = ()) -> str:
    """実行リストの名前を確かめる。使えないときは、その理由(使えるときは空文字)。others: ほかの実行リストの名前"""
    text = name.strip()
    if not text:
        return "名前を入力してください。"
    if len(text) > NAME_MAX_LENGTH:
        return f"名前は {NAME_MAX_LENGTH} 文字までにしてください。"
    if any(ord(c) < 0x20 or c == "\x7f" for c in text):
        return "名前に、改行やタブは使えません。"
    if text in others:
        return f"「{text}」という名前の実行リストが、すでにあります。"
    return ""


def check_item(item: RunItem) -> str:
    """実行リストの 1 行を確かめる。使えないときは、その理由(使えるときは空文字)"""
    if item.command_type not in COMMAND_TYPES:
        return f"コマンドの種類が正しくありません({item.command_type})。"
    if not item.name:
        return "コマンドを選んでください。"
    if is_list_name(item.command_type, item.name):
        return "実行リストの中に、実行リストは入れられません。"
    if not isinstance(item.repeat, int) or isinstance(item.repeat, bool) or not 1 <= item.repeat <= REPEAT_MAX:
        return f"回数は 1 〜 {REPEAT_MAX} の整数にしてください。"
    if item.limit_minutes is None:
        if item.command_type == MCU:
            return "Mcu コマンドは、終わったことが分からないので、制限時間を入れてください。"
    elif not 0 < item.limit_minutes <= LIMIT_MAX_MINUTES:
        return f"制限時間は、0 より大きく {LIMIT_MAX_MINUTES} 分までにしてください。"
    return ""


def check_list(run_list: RunList, others: list | tuple = ()) -> str:
    """実行リスト全体を確かめる。使えないときは、初めに見つかった理由(使えるときは空文字)"""
    error = check_name(run_list.name, others)
    if error:
        return error
    if not run_list.items:
        return "コマンドを 1 つ以上、足してください。"
    for index, item in enumerate(run_list.items, start=1):
        error = check_item(item)
        if error:
            return f"{index} 行目: {error}"
    if not 0 <= run_list.interval_seconds <= INTERVAL_MAX_SECONDS:
        return f"コマンドの間の待ち時間は、0 〜 {INTERVAL_MAX_SECONDS} 秒にしてください。"
    if run_list.on_error not in ON_ERRORS:
        return "エラーのときの動きが正しくありません。"
    if not isinstance(run_list.loops, int) or isinstance(run_list.loops, bool) or not 0 <= run_list.loops <= REPEAT_MAX:
        return f"リスト全体の繰り返しは、0(Stop を押すまで)〜 {REPEAT_MAX} の整数にしてください。"
    return ""


def parse_number(text: str, allow_empty: bool = False) -> float | None:
    """入力欄の文字を数にする(空のときは、allow_empty なら None。数でない・空で不可なら ValueError)"""
    text = text.strip()
    if not text:
        if allow_empty:
            return None
        raise ValueError("empty")
    value = float(text)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError("not a finite number")
    return value


# ---------------------------------------------------------------- 読み書き


def _to_dict(run_list: RunList) -> dict:
    """ファイルに書く形にする"""
    return {
        "name": run_list.name,
        "interval_seconds": run_list.interval_seconds,
        "on_error": run_list.on_error,
        "loops": run_list.loops,
        "items": [
            {"type": item.command_type, "name": item.name, "repeat": item.repeat, "limit_minutes": item.limit_minutes}
            for item in run_list.items
        ],
    }


def _from_dict(data: dict) -> RunList:
    """ファイルから読んだものを、実行リストにする(形が違うときは KeyError / TypeError / ValueError)"""
    items = []
    for row in data["items"]:
        limit = row.get("limit_minutes")
        items.append(
            RunItem(
                command_type=str(row["type"]),
                name=str(row["name"]),
                repeat=int(row.get("repeat", 1)),
                limit_minutes=None if limit is None else float(limit),
            )
        )
    return RunList(
        name=str(data["name"]).strip(),
        items=items,
        interval_seconds=float(data.get("interval_seconds", 1.0)),
        on_error=str(data.get("on_error", ON_ERROR_STOP)),
        loops=int(data.get("loops", 1)),
    )


def load_lists(path: str | None = None) -> list:
    """
    保存してある実行リストを読む(ファイルがない・読めないときは、空)。
    使えない内容のリスト(名前の重なりを含む)は、ログに残して飛ばす
    """
    path = path or lists_path()
    try:
        with open(path, encoding="utf-8") as file:
            rows = json.load(file)["lists"]
    except FileNotFoundError:
        return []
    except (OSError, ValueError, KeyError, TypeError) as error:
        _logger.warning(f"Failed to read the run lists: {error}")
        return []
    result = []
    for row in rows if isinstance(rows, list) else []:
        try:
            run_list = _from_dict(row)
            error = check_list(run_list, [other.name for other in result])
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            error = repr(e)
        if error:
            _logger.warning(f"A run list is skipped: {error}")
            continue
        result.append(run_list)
    return result


def save_lists(run_lists: list, path: str | None = None) -> None:
    """実行リストを書く(別の名前で書いてから置き換える。書けないときは OSError)"""
    path = path or lists_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.{os.getpid()}.tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as file:
            json.dump({"version": FORMAT_VERSION, "lists": [_to_dict(r) for r in run_lists]}, file, ensure_ascii=False, indent=1)
        os.replace(temporary, path)
    finally:
        try:
            os.remove(temporary)
        except OSError:
            pass


def describe_limit(minutes: float | None) -> str:
    """制限時間の表示(None は空文字)"""
    if minutes is None:
        return ""
    return f"{minutes:g} 分"


# ---------------------------------------------------------------- コマンドの一覧に足す


class RunListLoader:
    """保存してある実行リストを、コマンドの一覧に足す読み込み先(CombinedLoader に渡す)"""

    def __init__(self, service: CommandService):
        """service: コマンドの読み込みと用意を行うもの(実行リストの中のコマンドを、用意するのに使う)"""
        self._service = service
        self._lists = {}
        self._entries = []

    def load(self) -> list:
        """保存してある実行リストを読み、一覧に出す項目にして返す"""
        path = lists_path()
        self._lists = {run_list.display_name: run_list for run_list in load_lists(path)}
        self._entries = [
            CommandEntry(name=name, tags=[LIST_TAG], module_name="", class_name="", file_path=path)
            for name in self._lists
        ]
        return self._entries

    def reload(self) -> list:
        """読み直す"""
        return self.load()

    def findEntry(self, name: str) -> CommandEntry | None:
        """一覧の名前から、項目を探す(なければ None)"""
        return next((entry for entry in self._entries if entry.name == name), None)

    def getCommandClass(self, entry: CommandEntry, reload: bool = False) -> type:
        """その実行リストを動かすコマンドのクラスを作って返す(なくなっていれば ImportError)"""
        run_list = self._lists.get(entry.name)
        if run_list is None:
            raise ImportError(f"Run list '{entry.name}' is not found")
        return type(
            "SavedRunListCommand",
            (RunListCommand,),
            {"NAME": entry.name, "TAGS": list(entry.tags), "RUN_LIST": run_list, "SERVICE": self._service},
        )


class RunListCommand(PythonCommand):
    """実行リストの中のコマンドを、上から順に動かすコマンド"""

    NAME = "実行リスト"
    RUN_LIST: RunList | None = None
    SERVICE: Any = None

    def __init__(self) -> None:
        """実行リストと、コマンドを用意するものは、クラスに入れてある(RunListLoader.getCommandClass)"""
        super().__init__()
        # 今動かしている、中のコマンド(Python コマンドのときだけ。止める指示を伝えるために覚える)
        self._child = None
        self._child_lock = threading.Lock()

    def end(self, ser: Any) -> None:
        """止める指示: 今動かしている中のコマンドにも伝える(リスト全体を止める)"""
        with self._child_lock:
            child = self._child
            if child is not None:
                child.alive = False
        super().end(ser)

    def do(self) -> None:
        """実行リストを、上から順に実行する"""
        run_list = self.RUN_LIST
        if run_list is None or not run_list.items:
            print("実行リストが空です。")
            return
        steps = [(item, count) for item in run_list.items for count in range(1, item.repeat + 1)]
        loop = 0
        while run_list.loops == LOOP_FOREVER or loop < run_list.loops:
            loop += 1
            if run_list.loops != 1:
                total = "Stop を押すまで" if run_list.loops == LOOP_FOREVER else f"{run_list.loops} 周"
                print(f"[実行リスト] {loop} 周目({total})")
            for index, (item, count) in enumerate(steps, start=1):
                repeat = f"({count}/{item.repeat} 回目)" if item.repeat > 1 else ""
                limit = f" 制限時間 {describe_limit(item.limit_minutes)}" if item.limit_minutes is not None else ""
                print(f"[実行リスト] {index}/{len(steps)}: {item.name}{repeat}{limit}")
                ok = self._run_item(item)
                # 止める指示が出ていれば、ここで終わる(リスト全体を止める)
                self.checkIfAlive()
                if not ok and run_list.on_error == ON_ERROR_STOP:
                    print("[実行リスト] エラーがあったので、ここで中止します。")
                    return
                last = index == len(steps) and run_list.loops != LOOP_FOREVER and loop == run_list.loops
                if not last and run_list.interval_seconds > 0:
                    self.wait(run_list.interval_seconds)
        print("[実行リスト] すべて終わりました。")

    def _run_item(self, item: RunItem) -> bool:
        """
        1 つのコマンドを、終わるまで(または制限時間まで)動かす。エラーなく終わったかを返す
        (制限時間で止めた場合と、Stop で止めた場合も True)
        """
        if is_list_name(item.command_type, item.name):
            print("[実行リスト] 実行リストの中の実行リストは、実行しません。")
            return False
        try:
            command_class = self.SERVICE.find_class(item.command_type, item.name)
            if command_class is None:
                print(f"[実行リスト] コマンドが見つかりません: {item.name}")
                return False
            child = self.SERVICE.create(item.command_type, command_class)
        except Exception as error:
            print(f"[実行リスト] コマンドを用意できませんでした: {item.name}({error})")
            return False
        list_name = Command.cur_command_name
        Command.cur_command_name = child.NAME
        try:
            if isinstance(child, PythonCommand):
                return self._run_python(child, item)
            return self._run_other(child, item)
        finally:
            Command.cur_command_name = list_name

    def _run_python(self, child: PythonCommand, item: RunItem) -> bool:
        """Python コマンドを、このスレッドの中で動かす(開始・終了の表示と通知は、単独で実行するときと同じ)"""
        outcome = {"error": False, "timed_out": False}
        original_do = child.do

        def do() -> None:
            """中のコマンドの do()。例外で終わったことを、覚えておく(表示と後始末は、do_safe が行う)"""
            try:
                original_do()
            except StopThread:
                raise
            except Exception:
                outcome["error"] = True
                raise

        def time_is_up() -> None:
            """制限時間: 中のコマンドだけを止める(リストは、次へ進む)"""
            outcome["timed_out"] = True
            child.alive = False

        child.do = do
        child.keys = self.keys
        child.alive = True
        child.socket0.alive = True
        child.mqtt0.alive = True
        child.postProcess = None
        PythonCommandBase.ImageProcPythonCommand.template_path_name = "./Template/"
        timer = None
        if item.limit_minutes is not None:
            timer = threading.Timer(item.limit_minutes * 60, time_is_up)
            timer.daemon = True
        with self._child_lock:
            self._child = child
            # (用意している間に、止める指示が出ていた場合)
            if not self.alive:
                child.alive = False
        try:
            if timer is not None:
                timer.start()
            child.do_safe(self.keys.ser)
        finally:
            if timer is not None:
                timer.cancel()
            with self._child_lock:
                self._child = None
            # 中のコマンドが、入力の受け渡しを手放していても、リストの分は残す
            child.keys = None
        if outcome["timed_out"]:
            print(f"[実行リスト] 制限時間({describe_limit(item.limit_minutes)})になったので、止めました。")
        return not outcome["error"]

    def _run_other(self, child: Any, item: RunItem) -> bool:
        """Mcu コマンドを始め、制限時間まで待ってから止める(Mcu コマンドは、終わったことが分からない)"""
        if item.limit_minutes is None:
            print("[実行リスト] Mcu コマンドには、制限時間が要ります。")
            return False
        ser = self.keys.ser
        print("Start " + child.NAME)
        child.start(ser, None)
        try:
            self.wait(item.limit_minutes * 60)
        finally:
            child.end(ser)
            print("Stop " + child.NAME)
        return True
