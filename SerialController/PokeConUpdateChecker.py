#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime
import tkinter as tk
from tkinter import messagebox
import webbrowser

from services import release_update, update_check

TITLE = "更新確認"
# この版から、uv の環境(.venv)が必要になる
UV_REQUIRED_FROM = (0, 3, 0)
UPDATE_NOTICE = (
    "【注意1】\n"
    "以下のディレクトリ内のファイルは更新されません。\n"
    "・PythonCommands (Samplesディレクトリを除く)\n"
    "・Template (Samplesディレクトリを除く)\n"
    "・Captures\n"
    "・Controller_Log\n"
    "・profiles\n"
    "【注意2】\n"
    "更新対象のファイルのうちユーザーが手動で更新したファイルはoldディレクトリに移動されます。"
)


def backup_path(folder: str, path: str) -> str:
    """
    手元で変更したファイル(path)を退避する先のパスを返す。
    同じ名前のファイルが別のフォルダーにあっても重ならないように、folder の中に、元のフォルダーの並びのまま置く
    (ドライブ名や、先頭の区切り、".." は取り除く)
    """
    parts = [part for part in os.path.normpath(path).replace("\\", "/").split("/") if part not in ("", ".", "..")]
    parts = [part for part in parts if not part.endswith(":")]
    return os.path.join(folder, *parts)


class PokeConUpdateCheck(object):
    """更新の確認と取得(起動用の bat ファイルから、アプリの前に実行する)"""

    def __init__(self, mode: str = "0"):
        """mode: 使っていない。リポジトリの場所(SerialController の 1 つ上)を覚え、その場所を表示する"""
        self.pokecon_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        print(self.pokecon_path)

    def check_repository_updates(self) -> str:
        """更新があるかを確かめる。"0": 最新 / "1": 更新あり / "-1": 確認できない(通信できない等)"""
        return update_check.check(self.pokecon_path)

    def uses_git(self) -> bool:
        """git で取得したフォルダーで、git を使えるか(使えなければ、Release の ZIP で更新する)"""
        if not os.path.isdir(os.path.join(self.pokecon_path, ".git")):
            return False
        try:
            # GitPython は、git 本体が見つからないと、読み込みの時点で ImportError になる
            import git  # noqa: F401
        except ImportError:
            return False
        return True

    def get_conflicting_files(self) -> list[str]:
        """
        更新を取得する(git pull)。手元で変更したファイルがあって取得できない場合は、そのファイルの一覧を返す
        (取得できた場合は、空のリスト)。ほかの理由で取得できなかった場合は、例外を送出する
        """
        # GitPython は、使うときに読み込む(git が入っていなくても、このファイルを読み込めるようにする)
        from git import Repo, GitCommandError

        repo = Repo(self.pokecon_path)
        try:
            repo.git.pull()
            print("更新完了")
        except GitCommandError as e:
            error_output = e.stderr or ""
            print(e)
            start_text = "Your local changes to the following files would be overwritten by merge"
            end_text = "Please commit your changes or stash them before you merge."
            if start_text not in error_output or end_text not in error_output:
                raise
            conflicting_files_text = error_output[error_output.index(start_text) : error_output.index(end_text)]
            return [file.strip() for file in conflicting_files_text.splitlines()[1:] if file.strip()]
        return []

    def git_pull(self) -> None:
        """更新を取得する(git pull)。取得できなければ、例外を送出する"""
        from git import Repo

        Repo(self.pokecon_path).git.pull()
        print("更新完了")

    def update_with_git(self) -> None:
        """git pull で更新する(手元で変更したファイルは、old/日時/ に退避してから)。できなければ、例外を送出する"""
        conflicting_files = self.get_conflicting_files()
        if not conflicting_files:
            return
        pathname = os.path.join(self.pokecon_path, "old", datetime.today().strftime("%Y%m%d%H%M%S"))
        os.makedirs(pathname)
        for name in conflicting_files:
            source = os.path.join(self.pokecon_path, name)
            filename = backup_path(pathname, name)
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            shutil.copy2(source, filename)
            if os.path.exists(filename):
                os.remove(source)
        self.git_pull()

    def update_with_zip(self, release: update_check.Release) -> release_update.Result:
        """Release の ZIP で更新する(git を使わない)。できなければ release_update.UpdateError"""
        return release_update.update(
            self.pokecon_path, update_check.zip_url(update_check.current_tag()), release.zip_url
        )


def uv_environment_ready(repository_dir: str) -> bool:
    """uv の環境(.venv)があるか"""
    name = os.path.join("Scripts", "python.exe") if os.name == "nt" else os.path.join("bin", "python")
    return os.path.isfile(os.path.join(repository_dir, ".venv", name))


def offer_migration(repository_dir: str, parent: tk.Misc, required: bool = False) -> bool:
    """uv の環境(.venv)への移行を尋ねる(以前からの Python で動いているときだけ。0.3.0 で消す)。移行したら True"""
    sys.path.insert(0, repository_dir)
    try:
        from bootstrap import migrate

        return migrate.offer(repository_dir, parent, required=required)
    except Exception as e:
        # 移行できなくても、今までの環境で起動する
        print(f"uv の環境への移行を確かめられませんでした: {e}")
        return False
    finally:
        sys.path.pop(0)


def run_update(checker: PokeConUpdateCheck, release: update_check.Release, parent: tk.Misc) -> None:
    """更新を行い、結果を表示する"""
    try:
        if checker.uses_git():
            checker.update_with_git()
            messagebox.showinfo(title=TITLE, message="更新が完了しました。", parent=parent)
            return
        result = checker.update_with_zip(release)
    except Exception as e:
        print(f"更新に失敗しました: {e}")
        messagebox.showerror(
            title=TITLE,
            message="更新に失敗しました。\nGitHub のページから、必要なファイルをダウンロードしてください。",
            detail=str(e),
            parent=parent,
        )
        webbrowser.open(release.url, 2)
        return
    lines = []
    if result.backup_dir:
        lines.append(f"手元で変更されていたファイル({len(result.plan.backup)} 件)は、次のフォルダーに退避しました。\n{result.backup_dir}")
    if result.failed:
        lines.append("次のファイルは、入れ替えられませんでした(アプリを閉じてから、もう一度更新してください)。")
        lines.extend(f"・{name}" for name, _ in result.failed[:10])
        messagebox.showwarning(title=TITLE, message="更新は、一部だけ完了しました。", detail="\n".join(lines), parent=parent)
    else:
        messagebox.showinfo(title=TITLE, message="更新が完了しました。", detail="\n".join(lines), parent=parent)


def main() -> None:
    parser = argparse.ArgumentParser(description="Switch/GC automation support software using Python")
    parser.add_argument("--msgbox", "-m", help="show_msgbox", action="store_true")
    args = parser.parse_args()

    root = tk.Tk()
    root.withdraw()  # メインウィンドウを非表示にする
    checker = PokeConUpdateCheck()
    repository_dir = checker.pokecon_path
    if not args.msgbox or messagebox.askyesno(title=TITLE, message="Poke-Controller Modified Extension の更新を確認しますか?"):
        try:
            release = update_check.find_update()
        except update_check.UpdateCheckError as e:
            print(f"更新を確認できませんでした: {e}")
            if args.msgbox:
                messagebox.showwarning(title=TITLE, message="確認できませんでした。")
        else:
            if release is None:
                print("最新の版です。")
                if args.msgbox:
                    messagebox.showinfo(title=TITLE, message="更新はありませんでした。")
            elif release.version >= UV_REQUIRED_FROM and not uv_environment_ready(repository_dir):
                # 取得してから起動できなくなるのを防ぐ: 先に、uv の環境へ移行してもらう
                if offer_migration(repository_dir, root, required=True):
                    messagebox.showinfo(
                        title=TITLE, message=f"最新版({release.tag})は、次に起動したときに更新できます。", parent=root
                    )
            elif messagebox.askyesno(
                title=TITLE, message=f"最新版({release.tag})が公開されています。更新しますか?", detail=UPDATE_NOTICE
            ):
                run_update(checker, release, root)
    offer_migration(repository_dir, root)


if __name__ == "__main__":
    # uv の環境(.venv)があれば、その Python で起動し直す(以前からの起動用のファイルのため。0.3.0 で消す)
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from bootstrap.relaunch import run_in_venv

        run_in_venv()
    except ImportError:
        pass
    finally:
        sys.path.pop(0)
    main()
