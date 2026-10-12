"""
このツール用の環境(リポジトリ直下の .venv)を作る・そろえる

- 本体のライブラリ: uv.lock のとおりに入れる(uv sync)
- 利用者が足したライブラリ: requirements-user.txt の名前を、本体のライブラリの版を変えない範囲で入れる
- Python: .python-version の版(3.13 など)の、いちばん新しい細かい版にする
そろえた時点の設定ファイルの内容を .venv の中に覚えておき、変わっていなければ何もしない。
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from typing import Callable

from bootstrap import uv_tool
from bootstrap.added_libraries import USER_REQUIREMENTS

VENV = ".venv"
STAMP = ".pokecon-sync"
# 内容が変わったら、環境をそろえ直すファイル
SYNC_FILES = ("pyproject.toml", "uv.lock", ".python-version", USER_REQUIREMENTS)


def repository_dir() -> str:
    """リポジトリの場所(このフォルダーの 1 つ上)"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def venv_python(root: str) -> str:
    """.venv の Python の場所(あるかどうかは、確かめない)"""
    if os.name == "nt":
        return os.path.join(root, VENV, "Scripts", "python.exe")
    return os.path.join(root, VENV, "bin", "python")


def in_venv(root: str) -> bool:
    """今のプロセスが、このリポジトリの .venv の Python で動いているか"""
    here = os.path.normcase(os.path.realpath(sys.prefix))
    return here == os.path.normcase(os.path.realpath(os.path.join(root, VENV)))


def sync_state(root: str) -> str:
    """環境の元になるファイルの内容をまとめた値(ファイルがなければ、ないものとして数える)"""
    digest = hashlib.sha256()
    for name in SYNC_FILES:
        digest.update(name.encode("utf-8") + b"\0")
        try:
            with open(os.path.join(root, name), "rb") as file:
                # 改行コードの違い(git の設定で変わる)では、そろえ直さない
                digest.update(file.read().replace(b"\r\n", b"\n"))
        except OSError:
            digest.update(b"<missing>")
        digest.update(b"\0")
    return digest.hexdigest()


def needs_sync(root: str) -> bool:
    """環境を作る・そろえ直す必要があるか(.venv がない、または、前にそろえた後で設定ファイルが変わった)"""
    if not os.path.isfile(venv_python(root)):
        return True
    try:
        with open(os.path.join(root, VENV, STAMP), encoding="utf-8") as file:
            return file.read().strip() != sync_state(root)
    except OSError:
        return True


def python_request(root: str) -> str | None:
    """.python-version に書いてある版(「3.13」など)。読めなければ None"""
    try:
        with open(os.path.join(root, ".python-version"), encoding="utf-8") as file:
            return file.read().strip() or None
    except OSError:
        return None


def user_requirements(root: str) -> list:
    """requirements-user.txt に書いてある行(コメントと空行を除く)"""
    try:
        with open(os.path.join(root, USER_REQUIREMENTS), encoding="utf-8") as file:
            return [line.strip() for line in file if line.strip() and not line.lstrip().startswith("#")]
    except OSError:
        return []


def last_lines(text: str, count: int = 6) -> str:
    """失敗の理由として見せる、出力の終わりの数行"""
    lines = [line for line in (text or "").splitlines() if line.strip()]
    return "\n".join(lines[-count:])


def install_user_requirements(root: str, uv: str, requirements: list, log: Callable[[str], None] = uv_tool.say) -> list:
    """
    利用者が足したライブラリを、1 つずつ .venv に入れる。入らなかったものを [(名前, 理由)] で返す。
    本体のライブラリの版は、uv.lock のまま変えない(合う版がないライブラリは、入れずに理由を返す)
    """
    if not requirements:
        return []
    failed = []
    with tempfile.TemporaryDirectory() as temporary:
        constraints = os.path.join(temporary, "constraints.txt")
        exported = uv_tool.run(
            uv, ["export", "--frozen", "--no-hashes", "--no-emit-project", "-o", constraints], cwd=root, capture=True
        )
        if exported.returncode != 0:
            return [(name, last_lines(exported.stderr)) for name in requirements]
        for requirement in requirements:
            log(f"  {requirement}")
            done = uv_tool.run(
                uv, ["pip", "install", "--python", venv_python(root), "--constraints", constraints, requirement],
                cwd=root, capture=True,
            )  # fmt: skip
            if done.returncode != 0:
                failed.append((requirement, last_lines(done.stderr)))
    return failed


def sync(root: str, uv: str, log: Callable[[str], None] = uv_tool.say) -> list:
    """
    環境を作る・そろえる。利用者が足したライブラリのうち、入らなかったものを [(名前, 理由)] で返す。
    本体のライブラリを入れられなかった場合は UvError
    """
    request = python_request(root)
    if request:
        # 細かい版(3.13.15 → 3.13.16 など)は、こうしないと上がらない。.venv は、作り直さなくても新しい版で動く
        log(f"Python {request} を確かめています...")
        uv_tool.run(uv, ["python", "upgrade", request], cwd=root)
    log("必要なライブラリをそろえています(初回は、数分かかります)...")
    # --inexact: 利用者が足したライブラリを消さない
    if uv_tool.run(uv, ["sync", "--inexact"], cwd=root).returncode != 0 or not os.path.isfile(venv_python(root)):
        raise uv_tool.UvError("環境を用意できませんでした。上に表示された内容を確かめてください。")
    requirements = user_requirements(root)
    if requirements:
        log("自分で足したライブラリを入れています...")
    failed = install_user_requirements(root, uv, requirements, log)
    mark_synced(root)
    return failed


def mark_synced(root: str) -> None:
    """今の設定ファイルの内容で、環境をそろえ終えたことを覚える(次に内容が変わるまで、そろえ直さない)"""
    with open(os.path.join(root, VENV, STAMP), "w", encoding="utf-8") as file:
        file.write(sync_state(root))


def uninstall(root: str, uv: str, names: list) -> list:
    """ライブラリを .venv から外す。外せなかったものを [(名前, 理由)] で返す(入っていないものは、何もしない)"""
    failed = []
    for name in names:
        done = uv_tool.run(uv, ["pip", "uninstall", "--python", venv_python(root), name], cwd=root, capture=True)
        if done.returncode != 0:
            failed.append((name, last_lines(done.stderr)))
    return failed


def describe_failures(failed: list) -> str:
    """入らなかったライブラリの一覧を、表示用の文章にする"""
    lines = ["次のライブラリは、入れられませんでした(本体と、ほかのライブラリは、そのまま使えます)。"]
    for name, reason in failed:
        lines.append(f"- {name}")
        lines.extend(f"    {line}" for line in reason.splitlines())
    return "\n".join(lines)


def ensure(root: str, confirm: Callable[[str], bool], log: Callable[[str], None] = uv_tool.say) -> list:
    """必要なら、uv を用意して環境をそろえる。入らなかったライブラリを返す(そろえる必要がなければ、空)"""
    if not needs_sync(root):
        return []
    return sync(root, uv_tool.ensure(root, confirm, log), log)
