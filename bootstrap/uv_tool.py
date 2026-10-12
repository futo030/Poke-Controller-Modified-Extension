"""
uv を探す・入れる・呼ぶ

使うのは、pip に結び付いていない uv だけ(Python の Scripts フォルダーに入っているものは、その Python と一緒に消えるので使わない)。
探す順: 公式のスクリプトが残した記録(uv-receipt.json)の場所 → 既定の場所 → PATH。
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
from typing import Callable, Sequence

WINDOWS = os.name == "nt"
UV_NAME = "uv.exe" if WINDOWS else "uv"
# uv を呼ぶときに足す環境変数
#   UV_SYSTEM_CERTS: 証明書は、OS の一覧を使う(ウイルス対策ソフトが HTTPS の通信を調べている PC では、uv の持つ一覧だと、どこにも接続できない)
UV_ENVIRONMENT = {"UV_SYSTEM_CERTS": "1"}
# 公式の導入スクリプト(利用者のフォルダーに入る。管理者の権限は要らない)
INSTALL_COMMAND = (
    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "irm https://astral.sh/uv/install.ps1 | iex"]
    if WINDOWS
    else ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"]
)


def say(text: str) -> None:
    """進み具合を表示する(uv の出力と順番が入れ替わらないように、すぐに書き出す)"""
    print(text, flush=True)


class UvError(Exception):
    """uv を用意できない・uv の実行に失敗した(メッセージは、そのまま表示できる文)"""


def receipt_path(environ: dict | None = None) -> str:
    """公式のスクリプトが、入れた場所を記録するファイル"""
    environ = os.environ if environ is None else environ
    if WINDOWS:
        return os.path.join(environ.get("LOCALAPPDATA", ""), "uv", "uv-receipt.json")
    config = environ.get("XDG_CONFIG_HOME") or os.path.join(environ.get("HOME", ""), ".config")
    return os.path.join(config, "uv", "uv-receipt.json")


def official_candidates(environ: dict | None = None) -> list:
    """公式のスクリプトで入れた uv がある(はずの)場所: 記録にある場所と、既定の場所"""
    environ = os.environ if environ is None else environ
    folders = []
    try:
        with open(receipt_path(environ), encoding="utf-8") as file:
            folders.append(json.load(file)["install_prefix"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    home = environ.get("USERPROFILE" if WINDOWS else "HOME", "")
    if home:
        folders.append(os.path.join(home, ".local", "bin"))
    return [os.path.join(folder, UV_NAME) for folder in dict.fromkeys(folders) if folder]


def is_pip_installed(path: str) -> bool:
    """pip で入れた uv か(Python のフォルダーか仮想環境の中にある、または、近くに uv のインストールの記録がある)"""
    folder = os.path.dirname(os.path.abspath(path))
    parent = os.path.dirname(folder)
    if os.path.basename(folder).lower() not in ("scripts", "bin"):
        return False
    python_names = ("python.exe",) if WINDOWS else ("python", "python3")
    if any(os.path.isfile(os.path.join(where, name)) for where in (parent, folder) for name in python_names):
        return True
    if os.path.isfile(os.path.join(parent, "pyvenv.cfg")):
        return True
    patterns = [os.path.join(parent, "site-packages"), os.path.join(parent, "Lib", "site-packages"),
                os.path.join(parent, "lib", "python*", "site-packages")]  # fmt: skip
    return any(glob.glob(os.path.join(pattern, "uv-*.dist-info")) for pattern in patterns)


def find_uv(environ: dict | None = None) -> str | None:
    """使える uv の場所(pip に結び付いていないもの)。なければ None"""
    environ = os.environ if environ is None else environ
    for path in official_candidates(environ):
        if os.path.isfile(path):
            return path
    for folder in environ.get("PATH", "").split(os.pathsep):
        path = os.path.join(folder.strip('"'), UV_NAME)
        if folder and os.path.isfile(path) and not is_pip_installed(path):
            return path
    return None


def is_official(path: str, environ: dict | None = None) -> bool:
    """公式のスクリプトで入れた uv か(uv self update で更新できる)"""
    target = os.path.normcase(os.path.abspath(path))
    return any(os.path.normcase(os.path.abspath(candidate)) == target for candidate in official_candidates(environ))


def parse_version(text: str) -> tuple:
    """「uv 0.13.0 (4ecd0eff2 2026-10-09)」「0.12.22」などから、(0, 13, 0) の形を取り出す。読めなければ ()"""
    found = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(part) for part in found.groups()) if found else ()


def required_version(repository_dir: str) -> tuple:
    """pyproject.toml の [tool.uv] required-version(「>=0.12.22」の形)の版。書いていなければ ()"""
    try:
        with open(os.path.join(repository_dir, "pyproject.toml"), encoding="utf-8") as file:
            found = re.search(r'^required-version\s*=\s*"\s*>=\s*([\d.]+)\s*"', file.read(), re.MULTILINE)
    except OSError:
        return ()
    return parse_version(found.group(1)) if found else ()


def uv_environment(environ: dict | None = None) -> dict:
    """uv を呼ぶときの環境変数(利用者が設定している値は、そのまま使う)"""
    return {**UV_ENVIRONMENT, **(os.environ if environ is None else environ)}


def run(uv: str, arguments: Sequence[str], cwd: str | None = None, capture: bool = False) -> subprocess.CompletedProcess:
    """uv を実行する。capture: 出力を画面に出さずに受け取る(失敗の理由を、後で表示するため)"""
    options = {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace"} if capture else {}
    return subprocess.run([uv, *arguments], cwd=cwd, env=uv_environment(), **options)


def version(uv: str) -> tuple:
    """その uv の版。調べられなければ ()"""
    try:
        return parse_version(run(uv, ["--version"], capture=True).stdout)
    except OSError:
        return ()


def install(log: Callable[[str], None] = say) -> str:
    """公式のスクリプトで uv を入れて、その場所を返す(入れてよいかは、呼び出し側が先に尋ねる)"""
    log("uv をインストールしています...")
    try:
        done = subprocess.run(INSTALL_COMMAND)
    except OSError as e:
        raise UvError(f"uv のインストールを始められませんでした: {e}") from e
    path = find_uv()
    if done.returncode != 0 or path is None:
        raise UvError("uv をインストールできませんでした。https://docs.astral.sh/uv/ の手順で入れてから、もう一度実行してください。")
    return path


def ensure(repository_dir: str, confirm: Callable[[str], bool], log: Callable[[str], None] = say) -> str:
    """
    使える uv を用意して、その場所を返す。
    - なければ、confirm で尋ねてから、公式のスクリプトで入れる
    - 古ければ、公式のスクリプトで入れたものは uv self update で更新する(それ以外は、利用者に更新を頼む)
    用意できなければ UvError
    """
    uv = find_uv()
    if uv is None:
        if not confirm("uv(Python と、必要なライブラリを用意する道具)が見つかりません。\n公式サイトからダウンロードして、インストールしますか?"):
            raise UvError("uv がないので、環境を用意できません。")
        uv = install(log)
    needed = required_version(repository_dir)
    if needed and version(uv) < needed:
        text = ".".join(str(part) for part in needed)
        if not is_official(uv):
            raise UvError(f"uv が古いので、環境を用意できません({text} 以上が必要です)。uv を更新してから、もう一度実行してください。\n場所: {uv}")
        log(f"uv を更新しています({text} 以上が必要です)...")
        if run(uv, ["self", "update"]).returncode != 0 or version(uv) < needed:
            raise UvError(f"uv を更新できませんでした({text} 以上が必要です)。「uv self update」を実行してから、もう一度実行してください。")
    return uv
