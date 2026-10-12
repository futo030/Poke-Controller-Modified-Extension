#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
環境の診断: このアプリを動かすのに必要なものが、そろっているかを調べる

画面(tkinter)には触れない。調べるだけで、何も変えない(書き込めるかは、小さなファイルを作って、すぐ消して確かめる)。
画面は、今の状態(接続しているか、カメラが映っているか など)を context に入れて diagnose() を呼び、結果の一覧を表示する。
"""
from __future__ import annotations

import importlib.metadata
import os
import platform
import re
import shutil
import struct
import sys
import tempfile
from dataclasses import dataclass

SERIAL_CONTROLLER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPOSITORY_DIR = os.path.dirname(SERIAL_CONTROLLER_DIR)
# 結果の種類
OK = "OK"
WARNING = "注意"
ERROR = "NG"
INFO = "情報"
# なくても動くライブラリ: (名前, ないときに使えない機能)
OPTIONAL_LIBRARIES = (
    ("sounddevice", "音声の取り込み(Audio タブ)"),
    ("ftd2xx", "FTDI で直結する基板の Data Format"),
    ("fastapi", "Web ブラウザ版"),
    ("uvicorn", "Web ブラウザ版"),
    ("websockets", "Web ブラウザ版"),
)
# マスクしてコピーするときに、隠した場所の代わりに入れる文字
MASK = "***"
# OneDrive のフォルダーの場所が入っている環境変数
ONEDRIVE_VARIABLES = ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")
# この版から、uv の環境(.venv)が必要になる
UV_REQUIRED_VERSION = "0.3.0"
# 入っていないと起動できない・主な機能が使えないライブラリ(ほかは、ないと一部の機能が使えない)
CORE_LIBRARIES = ("opencv-python", "pyserial", "Pillow", "numpy", "pynput")
# 空きがこれより少ないと、注意にする(バイト)
DISK_FREE_WARNING = 1024 ** 3
# ログのファイルがこれより多いと、注意にする
LOG_FILES_WARNING = 1000
# 動作を確かめている Python の版(これより古いと、注意にする)
PYTHON_MINIMUM = (3, 10)


@dataclass
class Item:
    """診断の結果の 1 行"""

    level: str  # OK / WARNING / ERROR / INFO
    title: str
    detail: str = ""


def _writable(folder: str) -> str:
    """フォルダーに書き込めるかを確かめる。書き込めないときは、その理由(書き込めるときは空文字)"""
    if not os.path.isdir(folder):
        return "フォルダーがありません"
    try:
        handle, path = tempfile.mkstemp(prefix=".pokecon_check_", dir=folder)
        os.close(handle)
        os.remove(path)
        return ""
    except OSError as error:
        return str(error)


def requirement_names(path: str | None = None) -> list | None:
    """requirements.txt に書いてあるライブラリの名前(版の指定は除く)。読めないときは None"""
    path = path or os.path.join(REPOSITORY_DIR, "requirements.txt")
    try:
        with open(path, encoding="utf-8") as file:
            lines = file.readlines()
    except OSError:
        return None
    names = []
    for line in lines:
        name = line.split("#", 1)[0].strip()
        for separator in ("==", ">=", "<=", "~=", "!=", ">", "<", ";", "["):
            name = name.split(separator, 1)[0].strip()
        if name:
            names.append(name)
    return names


def _version(name: str) -> str | None:
    """入っているライブラリの版(入っていなければ None)"""
    try:
        return importlib.metadata.version(name)
    except Exception:
        return None


def check_python() -> list:
    """Python と OS"""
    version = platform.python_version()
    bits = struct.calcsize("P") * 8
    items = [Item(INFO, "OS", platform.platform())]
    detail = f"{version}({bits} bit) {sys.executable}"
    if sys.version_info < PYTHON_MINIMUM:
        need = ".".join(str(n) for n in PYTHON_MINIMUM)
        items.append(Item(WARNING, "Python", f"{detail} / {need} 以上で動作を確かめています"))
    elif bits != 64:
        items.append(Item(WARNING, "Python", f"{detail} / 64 bit 版で動作を確かめています"))
    else:
        items.append(Item(OK, "Python", detail))
    return items


def in_uv_environment(prefix: str | None = None, repository_dir: str = REPOSITORY_DIR) -> bool:
    """uv の環境(リポジトリ直下の .venv)の Python で動いているか"""
    prefix = os.path.normcase(os.path.realpath(sys.prefix if prefix is None else prefix))
    return prefix == os.path.normcase(os.path.realpath(os.path.join(repository_dir, ".venv")))


def check_environment(prefix: str | None = None, repository_dir: str = REPOSITORY_DIR) -> list:
    """ライブラリを入れている環境(uv の環境か、以前からの環境か)"""
    if in_uv_environment(prefix, repository_dir):
        return [Item(OK, "環境", "uv の環境(.venv)。ライブラリを足すときは、PokeConExtension_AddLibrary.bat を使います")]
    if os.path.isdir(os.path.join(repository_dir, ".venv")):
        return [Item(WARNING, "環境", "uv の環境(.venv)がありますが、別の Python で動いています")]
    return [Item(INFO, "環境", f"以前からの環境(PC の Python と pip)。ver.{UV_REQUIRED_VERSION} 以降は、uv の環境が必要になります")]


def check_libraries(requirements_path: str | None = None) -> list:
    """必要なライブラリと、なくても動くライブラリ"""
    names = requirement_names(requirements_path)
    if names is None:
        return [Item(WARNING, "ライブラリ", "requirements.txt を読めないので、確かめられません")]
    items = []
    missing_core = [name for name in names if name in CORE_LIBRARIES and _version(name) is None]
    missing = [name for name in names if name not in CORE_LIBRARIES and _version(name) is None]
    installed = [f"{name} {_version(name)}" for name in names if _version(name) is not None]
    if missing_core:
        items.append(Item(ERROR, "必要なライブラリ", "入っていません: " + ", ".join(missing_core)))
    if missing:
        items.append(Item(WARNING, "ライブラリ", "入っていません(一部の機能が使えません): " + ", ".join(missing)))
    if not missing_core and not missing:
        items.append(Item(OK, "ライブラリ", f"requirements.txt の {len(names)} 個が、すべて入っています"))
    items.append(Item(INFO, "ライブラリの版", ", ".join(installed)))
    for name, feature in OPTIONAL_LIBRARIES:
        version = _version(name)
        if version is None:
            items.append(Item(INFO, f"{name}(なくても動く)", f"入っていません。使えない機能: {feature}"))
        else:
            items.append(Item(OK, f"{name}(なくても動く)", version))
    return items


def onedrive_folder(path: str, environ: dict | None = None) -> str | None:
    """
    path が OneDrive のフォルダーの中にあれば、その OneDrive のフォルダーの場所を返す(中になければ None)。
    環境変数(OneDrive など)の場所の中にあるか、途中のフォルダーの名前が「OneDrive」「OneDrive - 組織名」かで判断する
    """
    environ = os.environ if environ is None else environ
    target = os.path.normcase(os.path.abspath(path))
    for name in ONEDRIVE_VARIABLES:
        root = environ.get(name)
        if not root:
            continue
        normalized = os.path.normcase(os.path.abspath(root))
        if target == normalized or target.startswith(normalized.rstrip("\\/") + os.sep):
            return os.path.abspath(root)
    parts = os.path.abspath(path).replace("\\", "/").split("/")
    for index, part in enumerate(parts):
        lowered = part.lower()
        if lowered == "onedrive" or lowered.startswith("onedrive - "):
            return "/".join(parts[: index + 1]).replace("/", os.sep)
    return None


def check_location(base_dir: str = SERIAL_CONTROLLER_DIR, environ: dict | None = None) -> list:
    """アプリを置いている場所(OneDrive の中で動かしていないか)"""
    root = onedrive_folder(base_dir, environ)
    if root is None:
        return [Item(OK, "置いている場所", base_dir)]
    return [
        Item(
            WARNING,
            "置いている場所",
            f"OneDrive の中で動かしています({base_dir})。OneDrive が同期している間、ファイルを読み書きできず、"
            "コマンドが正常に動かないことがある、と報告されています。フォルダーごと、OneDrive の外"
            "(例: C:\\PokeCon)へ移して使うことを、おすすめします。",
        )
    ]


def check_folders(profile: str, base_dir: str = SERIAL_CONTROLLER_DIR) -> list:
    """設定・ログ・スクリプトなどのフォルダーに、書き込めるか。ディスクの空き"""
    folders = (
        ("設定(プロファイル)", os.path.join(base_dir, "profiles", profile), ERROR),
        ("ログ", os.path.join(base_dir, "log"), WARNING),
        ("スクリプト", os.path.join(base_dir, "Commands", "PythonCommands"), WARNING),
        ("テンプレート画像", os.path.join(base_dir, "Template"), WARNING),
    )
    items = []
    for title, folder, level in folders:
        reason = _writable(folder)
        if reason:
            items.append(Item(level, f"フォルダー: {title}", f"書き込めません({reason}) {folder}"))
        else:
            items.append(Item(OK, f"フォルダー: {title}", folder))
    try:
        free = shutil.disk_usage(base_dir).free
        text = f"{free / 1024 ** 3:.1f} GB"
        if free < DISK_FREE_WARNING:
            items.append(Item(WARNING, "ディスクの空き", f"{text}(少なくなっています。画像やログを保存できないことがあります)"))
        else:
            items.append(Item(OK, "ディスクの空き", text))
    except OSError as error:
        items.append(Item(INFO, "ディスクの空き", f"調べられませんでした({error})"))
    log_dir = os.path.join(base_dir, "log")
    try:
        files = [name for name in os.listdir(log_dir) if name.endswith(".log")]
        size = sum(os.path.getsize(os.path.join(log_dir, name)) for name in files)
        text = f"{len(files)} 個、合わせて {size / 1024 ** 2:.1f} MB"
        if len(files) > LOG_FILES_WARNING:
            items.append(Item(WARNING, "ログのファイル", f"{text}(多くなっています。古いものは、消してかまいません)"))
        else:
            items.append(Item(INFO, "ログのファイル", text))
    except OSError:
        pass
    return items


def list_serial_ports() -> list | None:
    """PC にあるシリアルポート [(名前, 説明), ...]。調べられないときは None"""
    try:
        from serial.tools import list_ports

        return [(port.device, port.description) for port in list_ports.comports()]
    except Exception:
        return None


def check_devices(context: dict, ports: list | None = None) -> list:
    """
    シリアルとカメラ。context: 画面が入れる、今の状態
    (serial_connected / serial_port / data_format / camera_opened / camera_name / capture_size。ないものは、調べない)
    ports: PC にあるシリアルポート(None: 今、調べる)
    """
    items = []
    if "serial_connected" in context:
        port = context.get("serial_port") or "(未設定)"
        detail = f"{port} / Data Format: {context.get('data_format', '')}"
        if context["serial_connected"]:
            items.append(Item(OK, "シリアル", f"接続しています: {detail}"))
        else:
            items.append(Item(WARNING, "シリアル", f"接続していません: {detail}(Serial タブで、ポートを選んで Reload Port)"))
    if ports is None:
        ports = list_serial_ports()
    if ports is None:
        items.append(Item(INFO, "PC にあるポート", "調べられませんでした"))
    elif ports:
        items.append(Item(INFO, "PC にあるポート", " / ".join(f"{name}: {description}" for name, description in ports)))
    else:
        items.append(Item(WARNING, "PC にあるポート", "見つかりません(機器を USB でつないでいるか、ドライバーが入っているかを確かめてください)"))
    if "camera_opened" in context:
        detail = f"{context.get('camera_name', '')} / Capture Size: {context.get('capture_size', '')}"
        if context["camera_opened"]:
            items.append(Item(OK, "カメラ", f"映像を取り込んでいます: {detail}"))
        else:
            items.append(Item(WARNING, "カメラ", f"映像を取り込んでいません: {detail}(Camera タブで、カメラを選んで Reload Camera)"))
    return items


def check_app(context: dict) -> list:
    """アプリの版・プロファイル・コマンドの数・ログのファイル"""
    items = [Item(INFO, "アプリ", f"{context.get('app', '')} / プロファイル: {context.get('profile', '')}")]
    if context.get("read_only"):
        items.append(Item(WARNING, "プロファイル", "同じプロファイルの 2 つ目のウィンドウです。このウィンドウで変えた設定は、保存されません"))
    counts = context.get("command_counts")
    if counts:
        text = " / ".join(f"{name}: {count} 個" for name, count in counts.items())
        level = OK if any(counts.values()) else WARNING
        items.append(Item(level, "コマンド", text if level == OK else f"{text}(1 つも読み込めていません)"))
    if context.get("log_file"):
        items.append(Item(INFO, "今のログ", context["log_file"]))
    return items


def diagnose(context: dict) -> list:
    """
    環境を調べて、結果の一覧を返す。
    context: 画面が入れる、今の状態(app / profile / read_only / command_counts / log_file と、check_devices の項目)
    """
    profile = str(context.get("profile") or "default")
    return (
        check_app(context) + check_python() + check_environment() + check_libraries() + check_location()
        + check_folders(profile)
        + check_devices(context)
    )


def summary(items: list) -> str:
    """結果のまとめ(NG・注意の数)"""
    errors = sum(1 for item in items if item.level == ERROR)
    warnings = sum(1 for item in items if item.level == WARNING)
    if errors:
        return f"NG が {errors} 件、注意が {warnings} 件あります。"
    if warnings:
        return f"注意が {warnings} 件あります(NG はありません)。"
    return "問題は見つかりませんでした。"


def mask_paths(text: str, base_dir: str = SERIAL_CONTROLLER_DIR, home: str | None = None) -> str:
    """
    文字の中の、フォルダーの場所を隠す(質問や報告に貼るときに、PC のユーザー名やフォルダーの名前を出さないため)。
    - アプリのフォルダー(base_dir。起動したときの、今いるフォルダー)より上の階層は、MASK に置き換える
      (例: C:\\Users\\名前\\Documents\\PokeCon\\SerialController\\log → ***\\SerialController\\log)
    - それ以外の場所に出てくる、ユーザーのフォルダー(home。None: 今のユーザーのもの)も、MASK に置き換える
      (例: Python を、ユーザーのフォルダーの中に入れている場合)
    区切りの文字(\\ と /)と、大文字と小文字の違いは、区別しない
    """
    home = os.path.expanduser("~") if home is None else home
    prefixes = {os.path.dirname(os.path.abspath(base_dir)), os.path.abspath(home) if home else ""}
    # 長い方から置き換える(片方が、もう片方の中にある場合に、長い方を先に隠す)
    for prefix in sorted((p for p in prefixes if p and len(p) > 3), key=len, reverse=True):
        parts = [re.escape(part) for part in re.split(r"[\\/]+", prefix.rstrip("\\/")) if part]
        pattern = r"[\\/]+".join(parts)
        if prefix.startswith(("/", "\\")):
            pattern = r"[\\/]+" + pattern
        text = re.sub(pattern + r"(?=[\\/]|$|[^\w.-])", lambda match: MASK, text, flags=re.IGNORECASE)
    return text


def to_text(items: list, mask: bool = False) -> str:
    """
    結果を、文字にする(質問するときに、貼り付けられる形)
    mask: フォルダーの場所を隠す(mask_paths。アプリのフォルダーより上の階層と、ユーザーのフォルダー)
    """
    lines = [summary(items), ""]
    for item in items:
        lines.append(f"[{item.level}] {item.title}: {item.detail}" if item.detail else f"[{item.level}] {item.title}")
    text = "\n".join(lines) + "\n"
    return mask_paths(text) if mask else text
