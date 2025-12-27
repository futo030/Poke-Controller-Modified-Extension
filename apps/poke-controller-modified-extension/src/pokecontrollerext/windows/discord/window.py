import tkinter as tk
from typing import Any

from pokecontroller.core.notification import DiscordConfig, DiscordNotifier

from pokecontrollerext.app.translation import t
from pokecontrollerext.singletons.app.model import get_app_model
from pokecontrollerext.singletons.runtime.runtime_info import get_app_runtime_info
from pokecontrollerext.widgets.button import Button
from pokecontrollerext.widgets.entry import Entry
from pokecontrollerext.widgets.frame import Frame
from pokecontrollerext.widgets.label import Label
from pokecontrollerext.widgets.separator import Separator
from pokecontrollerext.widgets.window import Window


class DiscordSettingsWindow(Window):
    def __init__(
        self,
        master: tk.Misc,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, *args, **kwargs)
        self.title(t("discord.title"))

        self._runtime_info = get_app_runtime_info()
        self._model = get_app_model()

        base_dir = self._runtime_info.base_dir
        profile = self._runtime_info.profile
        config_path = base_dir / "profiles" / profile / "discord_token.ini"
        self._config = DiscordConfig(path=config_path)

        self._config_section = section = "DISCORD_WEBHOOK"
        self._webhook_url = tk.StringVar(
            value=self._config.get_webhook_url(section=section),
        )
        self._username = tk.StringVar(
            value=self._config.get_username(section=section),
        )
        self._avatar_url = tk.StringVar(
            value=self._config.get_avatar_url(section=section),
        )

        self.build_ui()

    def build_ui(self) -> None:
        frame = Frame(self)

        # title
        title_label = Label(frame, text=t("discord.title"))
        title_label.pack(expand=True, anchor=tk.CENTER, padx=5, pady=5)

        # fields
        for label_text, entry_var in [
            (t("discord.webhook_url"), self._webhook_url),
            (t("discord.username"), self._username),
            (t("discord.avatar_url"), self._avatar_url),
        ]:
            row = Frame(frame)
            label = Label(row, text=label_text, width=10)
            entry = Entry(row, textvariable=entry_var)
            label.pack(side=tk.LEFT)
            entry.pack(side=tk.LEFT, expand=True, fill=tk.X)
            row.pack(expand=True, fill=tk.BOTH, padx=4, pady=2)

        # test
        test_row = Frame(frame)
        test_button = Button(
            test_row, text=t("discord.test"), command=self._on_test_pressed
        )
        test_button.pack(side=tk.RIGHT, padx=5)
        test_row.pack(anchor=tk.E, padx=5)

        # separator
        Separator(frame, orient=tk.HORIZONTAL).pack(
            expand=True, fill=tk.X, padx=5, pady=5
        )

        # ok/cancel buttons
        buttons_row = Frame(frame)
        ok_button = Button(buttons_row, text=t("ok"), command=self._on_ok_pressed)
        cancel_button = Button(
            buttons_row, text=t("cancel"), command=self._on_cancel_pressed
        )
        ok_button.pack(side=tk.RIGHT, padx=4)
        cancel_button.pack(side=tk.RIGHT, padx=4)
        buttons_row.pack(expand=True, padx=5, pady=(10, 4))

        frame.pack(expand=True, fill=tk.BOTH)

    def _on_test_pressed(self) -> None:
        self._test_notify()

    def _on_ok_pressed(self) -> None:
        self._save_config()
        self.destroy()

    def _on_cancel_pressed(self) -> None:
        self.destroy()

    def _test_notify(self) -> None:
        self._assign_config()
        notifier = DiscordNotifier(config=self._config)
        notifier.notify(message=f"Test({t('discord.title')})")

    def _save_config(self) -> None:
        self._assign_config()
        self._config.save()

    def _assign_config(self) -> None:
        section = self._config_section
        self._config.set_webhook_url(
            section=section, webhook_url=self._webhook_url.get()
        )
        self._config.set_username(section=section, username=self._username.get())
        self._config.set_avatar_url(section=section, avatar_url=self._avatar_url.get())
