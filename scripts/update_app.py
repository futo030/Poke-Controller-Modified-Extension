#!/usr/bin/env -S uv run --script

from tkinter import messagebox
from pathlib import Path

from pokecontrollerext.updater import (
    PokeControllerUpdater,
    PokeControllerUpdaterCheckoutBranchException,
)


def _update_repository() -> None:
    root = Path(__file__).parent.parent

    updater = PokeControllerUpdater(root=root)
    try:
        if not updater.has_changes():
            return

        if messagebox.askyesno(
            title="更新確認",
            message="ローカルとリモートで差分があります。更新しますか？",
            detail="詳細",
        ):
            try:
                updater.backup()
                updater.update()
            except Exception as e:
                logger.error(f"Error while updating repository: {e}")
                messagebox.showinfo(
                    title="更新確認",
                    message="更新に失敗しました。\n手動でGitリポジトリを最新に更新してください。"
                )
                return
            messagebox.showinfo(
                title="更新確認",
                message="更新が完了しました。",
            )
    except PokeControllerUpdaterCheckoutBranchException as e:
        messagebox.showinfo(
            title="更新確認",
            message=f"ブランチの切り替えに失敗しました: {e}\n手動でGitリポジトリを最新に更新してください。",
        )
    finally:
        updater.checkout_original_branch()


if __name__ == '__main__':
    _update_repository()
