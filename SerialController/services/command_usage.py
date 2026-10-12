#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
コマンドを実行した回数(使用頻度)の記録

コマンドの一覧を、使用頻度の順に並べるために使う。画面(tkinter)には触れない。

- 同じコマンドとして数える単位は「種別・NAME・NAME を書いてあるファイル(フォルダーを含む場所)」。
  ファイルの中身を書き換えても、同じコマンドとして数える。NAME・ファイルの名前・置いてあるフォルダーのどれかを変えると、
  別のコマンドとして数え始める。
- 記録はプロファイルに関係なく共通(profiles/command_usage.json)。複数のウィンドウを起動しても、1 つのファイルに足していく。
  ほかのウィンドウと同時に書いても回数を失わないように、書く間だけ、目印のファイル(.lock)で順番を待つ。
"""
from __future__ import annotations

import contextlib
import json
import os
import time
from logging import getLogger, DEBUG, NullHandler
from typing import TYPE_CHECKING, Iterable, Iterator

if TYPE_CHECKING:
    from CommandLoader import CommandEntry

_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True

# 記録のファイル(プロファイルに関係なく、共通)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USAGE_PATH = os.path.join(BASE_DIR, "profiles", "command_usage.json")
FORMAT_VERSION = 1
# 書く順番を待つ時間(秒)。過ぎたら、その回は数えない(コマンドの開始は止めない)
LOCK_WAIT = 0.5
LOCK_INTERVAL = 0.01
# 目印のファイルが、これより古ければ、残されたものとして消す(秒。書いている途中で強制終了された場合)
LOCK_STALE = 5.0

# 読んだ記録の控え: {ファイルの場所: ((更新日時, 大きさ), 回数の表)}
_cache: dict = {}


def usage_key(command_type: str, entry: CommandEntry) -> tuple:
    """
    同じコマンドとして数える単位(種別, NAME, ファイルの場所)を返す。
    ファイルの場所は、SerialController から見た場所を「/」で区切ったもの(例: Commands/PythonCommands/Samples/mash.py)
    entry: 一覧のコマンド(name は「NAME (フォルダー/ファイル)」の形。file_path は、ファイルの場所)
    """
    file_path = getattr(entry, "file_path", "") or ""
    return command_type, _plain_name(entry.name, file_path), _relative_path(file_path)


def _relative_path(file_path: str) -> str:
    """ファイルの場所を、SerialController から見た場所にして、「/」で区切る(SerialController の外にあるものは、そのまま)"""
    if os.path.isabs(file_path):
        try:
            relative = os.path.relpath(file_path, BASE_DIR)
        except ValueError:
            # 別のドライブにある場合
            relative = file_path
        if not relative.startswith(".."):
            file_path = relative
    return os.path.normpath(file_path).replace("\\", "/") if file_path else ""


def _plain_name(name: str, file_path: str) -> str:
    """一覧の名前から、後ろに付けた「 (フォルダー/ファイル)」を取り除いて、NAME に書いてある名前に戻す"""
    parts = os.path.splitext(file_path)[0].replace("\\", "/").split("/")
    # 付いているのは、ファイルの場所の後ろの部分(長いものから確かめる)
    for start in range(len(parts)):
        suffix = f" ({'/'.join(parts[start:])})"
        if parts[start] and name.endswith(suffix):
            return name[: -len(suffix)]
    # ファイルの場所から作った名前でない場合(追加の機能のコマンドなど)は、最後のかっこを取り除く
    if name.endswith(")") and " (" in name:
        return name[: name.rfind(" (")]
    return name


def load(path: str | None = None) -> dict:
    """
    記録を読む: {(種別, NAME, ファイルの場所): 回数}。ファイルがない・読めないときは、空
    (ファイルが変わっていなければ、前に読んだものを返す。返した表は、書き換えない)
    """
    path = path or USAGE_PATH
    try:
        stat = os.stat(path)
    except OSError:
        return {}
    stamp = (stat.st_mtime_ns, stat.st_size)
    cached = _cache.get(path)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    try:
        counts = _read(path)
    except (OSError, ValueError) as e:
        _logger.warning(f"Failed to read the command usage: {e}")
        return {}
    _cache[path] = (stamp, counts)
    return counts


def _read(path: str) -> dict:
    """記録のファイルを読む(形が違うときは ValueError)"""
    with open(path, encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict) or not isinstance(data.get("commands"), list):
        raise ValueError("unexpected format")
    counts = {}
    for row in data["commands"]:
        try:
            key = (str(row["type"]), str(row["name"]), str(row["file"]))
            count = int(row["count"])
        except (KeyError, TypeError, ValueError):
            continue
        if count > 0:
            counts[key] = counts.get(key, 0) + count
    return counts


def _write(path: str, counts: dict) -> None:
    """記録を書く(別の名前で書いてから置き換えるので、途中で止まっても、元のファイルは壊れない)"""
    rows = [
        {"type": command_type, "name": name, "file": file_name, "count": count}
        for (command_type, name, file_name), count in sorted(counts.items())
    ]
    temporary = f"{path}.{os.getpid()}.tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as file:
            json.dump({"version": FORMAT_VERSION, "commands": rows}, file, ensure_ascii=False, indent=1)
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(OSError):
            os.remove(temporary)


@contextlib.contextmanager
def _locked(path: str) -> Iterator[None]:
    """
    記録を書く順番を取る(ほかのウィンドウが書いている間は、待つ)。LOCK_WAIT 秒待っても取れないときは TimeoutError
    """
    lock_path = path + ".lock"
    deadline = time.monotonic() + LOCK_WAIT
    while True:
        try:
            handle = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except OSError:
            # ほかのウィンドウが書いている(または、消している途中)。残されたものなら、消して取り直す
            with contextlib.suppress(OSError):
                if time.time() - os.path.getmtime(lock_path) > LOCK_STALE:
                    os.remove(lock_path)
                    continue
            if time.monotonic() >= deadline:
                raise TimeoutError(lock_path)
            time.sleep(LOCK_INTERVAL)
    try:
        yield
    finally:
        os.close(handle)
        with contextlib.suppress(OSError):
            os.remove(lock_path)


def record(command_type: str, entry: CommandEntry, path: str | None = None) -> bool:
    """
    そのコマンドを実行した回数を、1 つ増やして書く。書けたかを返す(書けないときは、ログに残すだけ)
    """
    path = path or USAGE_PATH
    key = usage_key(command_type, entry)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _locked(path):
            try:
                counts = _read(path)
            except FileNotFoundError:
                counts = {}
            except ValueError:
                # 中身が壊れている場合は、別の名前で残して、新しく数え始める
                os.replace(path, path + ".broken")
                counts = {}
            counts[key] = counts.get(key, 0) + 1
            _write(path, counts)
        return True
    except (OSError, TimeoutError) as e:
        _logger.warning(f"Failed to record the command usage: {e}")
        return False


def counts_of(command_type: str, entries: Iterable[CommandEntry], path: str | None = None) -> dict:
    """その種別の一覧のコマンドについて、{一覧の名前: 実行した回数} を返す(実行したことのないものは 0)"""
    counts = load(path)
    return {entry.name: counts.get(usage_key(command_type, entry), 0) for entry in entries}
