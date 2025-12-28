import logging
import tkinter as tk
import tkinter.messagebox as mb
import webbrowser
from typing import Any

from pokecontrollerext.app.settings import DEFAULT
from pokecontrollerext.app.translation import t
from pokecontrollerext.singletons.app.settings import get_app_settings
from pokecontrollerext.singletons.runtime.runtime_info import get_app_runtime_info
from pokecontrollerext.singletons.widget.catalog import (
    get_app_widget_catalog,
)
from pokecontrollerext.updater import (
    PokeControllerUpdater,
    PokeControllerUpdaterCheckoutBranchException,
)
from pokecontrollerext.windows.changelogs import ChangelogWindow
from pokecontrollerext.windows.discord import DiscordSettingsWindow
from pokecontrollerext.windows.license import LicenseWindow
from pokecontrollerext.windows.new_profile import NewProfileWindow
from pokecontrollerext.windows.question import QuestionWindow
from pokecontrollerext.windows.settings import SettingsWindow
from pokecontrollerext.windows.version import VersionWindow

logger = logging.getLogger(__name__)

GITHUB_URL = "https://github.com/futo030/Poke-Controller-Modified-Extension"
POKECONTROLLER_GUIDE_URL = "https://pokecontroller.info/"
WEBBROWSER_OPEN_IN_NEW_TAB = 2


class Menu(tk.Menu):
    def __init__(self, master: tk.Misc, *args: Any, **kwargs: Any) -> None:
        super().__init__(master, *args, **kwargs)
        self._app_settings = get_app_settings()
        self._widget_catalog = get_app_widget_catalog()
        self._runtime_info = get_app_runtime_info()
        self.build_ui()

    def build_ui(self) -> None:
        self._build_menu_cascade()
        self._build_command_cascade()
        self._build_help_cascade()

    def _build_menu_cascade(self) -> None:
        menu_cascade = tk.Menu(self, tearoff=False)
        menu_cascade.add_separator()
        menu_cascade.add_command(
            label="設定",
            command=self._on_menu_settings_pressed,
        )
        menu_cascade.add_separator()
        menu_cascade.add_command(
            label="画面サイズのリセット",
            command=self._on_menu_reset_window_size_pressed,
        )
        self.add_cascade(menu=menu_cascade, label="メニュー")

    def _build_command_cascade(self) -> None:
        command_cascade = tk.Menu(self, tearoff=False)
        command_cascade.add_command(
            label="Discord",
            command=self._on_command_discord_settings_pressed,
        )
        command_cascade.add_separator()
        command_cascade.add_command(
            label="新規プロファイル作成",
            command=self._on_command_new_profile_pressed,
        )
        command_cascade.add_separator()
        command_cascade.add_command(
            label="キーコンフィグ",
            command=self._on_command_key_config_pressed,
        )
        self.add_cascade(menu=command_cascade, label="コマンド")

    def _build_help_cascade(self) -> None:
        help_cascade = tk.Menu(self, tearoff=False)
        help_cascade.add_command(
            label="GitHub",
            command=self._on_help_github_pressed,
        )
        help_cascade.add_command(
            label="Poke-Controller Guide",
            command=self._on_help_guide_pressed,
        )
        help_cascade.add_separator()
        help_cascade.add_command(
            label="質問テンプレート",
            command=self._on_help_question_template_pressed,
        )
        help_cascade.add_separator()
        help_cascade.add_command(
            label="バージョン確認",
            command=self._on_help_version_pressed,
        )
        help_cascade.add_command(
            label="更新履歴表示",
            command=self._on_help_changelog_pressed,
        )
        help_cascade.add_command(
            label="アップデート確認",
            command=self._on_help_check_for_update_pressed,
        )
        help_cascade.add_command(
            label="ライセンス",
            command=self._on_help_license_pressed,
        )
        self.add_cascade(
            menu=help_cascade,
            label="ヘルプ",
        )

    def _on_menu_settings_pressed(self) -> None:
        self._widget_catalog.window.open_settings(self, SettingsWindow)

    def _on_menu_reset_window_size_pressed(self) -> None:
        self._app_settings.capture.size.set(DEFAULT["capture"]["size"])

    def _on_command_discord_settings_pressed(self) -> None:
        self._widget_catalog.window.open_discord_settings(self, DiscordSettingsWindow)

    def _on_command_new_profile_pressed(self) -> None:
        self._widget_catalog.window.open_new_profile(self, NewProfileWindow)

    def _on_command_key_config_pressed(self) -> None:
        pass

    # noinspection PyMethodMayBeStatic
    def _on_help_github_pressed(self) -> None:
        webbrowser.open(url=GITHUB_URL, new=WEBBROWSER_OPEN_IN_NEW_TAB)

    # noinspection PyMethodMayBeStatic
    def _on_help_guide_pressed(self) -> None:
        webbrowser.open(url=POKECONTROLLER_GUIDE_URL, new=WEBBROWSER_OPEN_IN_NEW_TAB)

    def _on_help_question_template_pressed(self) -> None:
        self._widget_catalog.window.open_question(self, QuestionWindow)

    def _on_help_version_pressed(self) -> None:
        self._widget_catalog.window.open_version(self, VersionWindow)

    def _on_help_changelog_pressed(self) -> None:
        self._widget_catalog.window.open_changelog(self, ChangelogWindow)

    def _on_help_check_for_update_pressed(self) -> None:
        repository_root = self._runtime_info.base_dir.parent
        updater = PokeControllerUpdater(root=str(repository_root))

        try:
            if not updater.has_changes():
                mb.showinfo(
                    title=t("update.title"),
                    message=t("update.message.no_changes"),
                )
                return
            if mb.askyesno(
                title=t("update.title"),
                message=t("update.message.has_changes"),
            ):
                try:
                    updater.backup()
                    updater.update()
                except Exception as e:
                    logger.error(f"Error while updating repository: {e}")
                    mb.showinfo(
                        title=t("update.title"),
                        message=t("update.message.error"),
                    )
                    return
                mb.showinfo(
                    title=t("update.title"),
                    message=t("update.message.success"),
                )
        except PokeControllerUpdaterCheckoutBranchException as e:
            mb.showinfo(
                title=t("update.title"),
                message=t("update.message.checkout_error").format(error=f"{e}"),
            )
        finally:
            updater.checkout_original_branch()

    def _on_help_license_pressed(self) -> None:
        self._widget_catalog.window.open_license(self, LicenseWindow)
