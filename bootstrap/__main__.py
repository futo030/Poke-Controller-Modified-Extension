"""
起動の入口(PokeConExtension.bat などから、.venv の Python で実行する)

    python -m bootstrap launch [Window.py の引数]    環境をそろえ、更新を確かめてから、本体を起動する
    python -m bootstrap monitor [Monitor.py の引数]  環境をそろえてから、補助ツール(モニター)を起動する
    python -m bootstrap add-library [名前 ...]       ライブラリを .venv に足す(名前を省くと、入力を求める)
    python -m bootstrap remove-library [名前 ...]    足したライブラリを、一覧と .venv から外す(名前を省くと、入力を求める)
    python -m bootstrap list-libraries               今の環境に入っているライブラリを、版と一緒に表示する
    python -m bootstrap sync                         環境をそろえ直す
"""
from __future__ import annotations

import os
import subprocess
import sys

from bootstrap import added_libraries, environment, library_list, uv_tool
from bootstrap.relaunch import RELAUNCHED

APP_DIR = "SerialController"
UPDATE_CHECKER = os.path.join(APP_DIR, "PokeConUpdateChecker.py")


def confirm(message: str) -> bool:
    """コンソールで尋ねる(Enter だけなら「いいえ」)"""
    print(message)
    try:
        return input("[y/N]: ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def prepare(root: str, force: bool = False) -> bool:
    """環境をそろえる。そろえられなかったら、理由を表示して False"""
    try:
        if force:
            failed = environment.sync(root, uv_tool.ensure(root, confirm))
        else:
            failed = environment.ensure(root, confirm)
    except uv_tool.UvError as e:
        uv_tool.say(str(e))
        return False
    if failed:
        uv_tool.say(environment.describe_failures(failed))
    return True


def run(root: str, script: str, arguments: list, cwd: str) -> int:
    """.venv の Python でスクリプトを実行して、終了コードを返す"""
    python = environment.venv_python(root)
    if not os.path.isfile(python):
        python = sys.executable
    return subprocess.call([python, script, *arguments], cwd=cwd, env={**os.environ, RELAUNCHED: "1"})


def launch(root: str, arguments: list) -> int:
    """本体を起動する(環境をそろえる → 更新の確認 → 更新で設定が変わっていれば、そろえ直す → 起動)"""
    if not prepare(root) and not os.path.isfile(environment.venv_python(root)):
        return 1
    run(root, UPDATE_CHECKER, [], cwd=root)
    prepare(root)
    return run(root, "Window.py", arguments, cwd=os.path.join(root, APP_DIR))


def monitor(root: str, arguments: list) -> int:
    """補助ツール(モニター)を起動する"""
    if not prepare(root) and not os.path.isfile(environment.venv_python(root)):
        return 1
    return run(root, "Monitor.py", arguments, cwd=os.path.join(root, APP_DIR))


def add_library(root: str, names: list) -> int:
    """ライブラリの名前を requirements-user.txt に足して、.venv に入れる"""
    if not names:
        print("追加するライブラリの名前を入力してください(複数のときは、空白で区切ります)。")
        try:
            names = input("> ").split()
        except EOFError:
            names = []
    if not names:
        print("名前が入力されなかったので、何もしませんでした。")
        return 1
    # 今回、新しく足す名前(入れられなかったら、一覧に残さない。名前の間違いが、残り続けないようにする)
    known = {added_libraries.requirement_name(line) for line in environment.user_requirements(root)}
    new_names = [name for name in dict.fromkeys(added_libraries.requirement_name(name) for name in names) if name not in known]
    added_libraries.write_user_requirements(root, names)
    try:
        failed = environment.sync(root, uv_tool.ensure(root, confirm))
    except uv_tool.UvError as e:
        added_libraries.remove_user_requirements(root, new_names)
        uv_tool.say(str(e))
        return 1
    if failed:
        uv_tool.say(environment.describe_failures(failed))
    not_added = [name for name, _ in failed if added_libraries.requirement_name(name) in new_names]
    if not_added:
        added_libraries.remove_user_requirements(root, not_added)
        environment.mark_synced(root)
        uv_tool.say(f"入れられなかったもの({', '.join(not_added)})は、一覧({added_libraries.USER_REQUIREMENTS})に残していません。名前を確かめてください。")
    added = [name for name in new_names if name not in not_added]
    if added:
        uv_tool.say(f"追加しました: {', '.join(added)}")
    return 1 if not_added else 0


def remove_library(root: str, names: list) -> int:
    """足したライブラリを、requirements-user.txt と .venv から外す(本体が使うライブラリは、外さない)"""
    listed = [added_libraries.requirement_name(line) for line in environment.user_requirements(root)]
    if not listed:
        print(f"自分で足したライブラリは、ありません({added_libraries.USER_REQUIREMENTS} が空です)。")
        return 0
    if not names:
        print("自分で足したライブラリ:")
        for name in listed:
            print(f"  {name}")
        print("外すライブラリの名前を入力してください(複数のときは、空白で区切ります)。")
        try:
            names = input("> ").split()
        except EOFError:
            names = []
    if not names:
        print("名前が入力されなかったので、何もしませんでした。")
        return 1
    removed = added_libraries.remove_user_requirements(root, names)
    unknown = [name for name in names if added_libraries.requirement_name(name) not in removed]
    if unknown:
        print(f"一覧にない名前です(何もしていません): {', '.join(unknown)}")
    if not removed:
        return 1
    project = set(library_list.project_requirements(root))
    targets = [name for name in removed if name not in project]
    try:
        failed = environment.uninstall(root, uv_tool.ensure(root, confirm), targets) if targets else []
    except uv_tool.UvError as e:
        failed = [(name, str(e)) for name in targets]
    environment.mark_synced(root)
    uv_tool.say(f"一覧から外しました: {', '.join(removed)}")
    if failed:
        uv_tool.say(".venv からは、外せませんでした(一覧からは外してあります)。")
        uv_tool.say("\n".join(f"- {name}\n    {reason}" for name, reason in failed))
    return 0


def main(arguments: list) -> int:
    root = environment.repository_dir()
    command, rest = (arguments[0], arguments[1:]) if arguments else ("launch", [])
    if command == "launch":
        return launch(root, rest)
    if command == "monitor":
        return monitor(root, rest)
    if command == "add-library":
        return add_library(root, rest)
    if command == "remove-library":
        return remove_library(root, rest)
    if command == "list-libraries":
        uv_tool.say(library_list.report(root))
        return 0
    if command == "sync":
        return 0 if prepare(root, force=True) else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
