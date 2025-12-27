import tkinter as tk
from dataclasses import dataclass
from typing import Callable

from pokecontrollerext.widgets.canvas import Canvas


@dataclass(kw_only=True)
class OutputsWidgetCatalog:
    textarea1: tk.Text | None = None
    textarea2: tk.Text | None = None

    def write(self, textarea_id: int, text: str) -> None:
        if (textarea := getattr(self, f"textarea{textarea_id}")) is not None:
            textarea.config(state=tk.NORMAL)
            textarea.delete("1.0", tk.END)
            textarea.insert("1.0", text)
            textarea.config(state=tk.DISABLED)

    def write_line(self, textarea_id: int, text: str) -> None:
        self.write(textarea_id, f"{text}\n")

    def append(self, textarea_id: int, text: str) -> None:
        if (textarea := getattr(self, f"textarea{textarea_id}")) is not None:
            textarea.config(state=tk.NORMAL)
            textarea.insert(tk.END, text)
            textarea.config(state=tk.DISABLED)

    def append_line(self, textarea_id: int, text: str) -> None:
        self.append(textarea_id, f"{text}\n")

    def clear(self, textarea_id: int) -> None:
        if (textarea := getattr(self, f"textarea{textarea_id}")) is not None:
            textarea.config(state=tk.NORMAL)
            textarea.delete("1.0", tk.END)
            textarea.config(state=tk.DISABLED)

    def clear_all(self) -> None:
        for i in [1, 2]:
            self.clear(i)


@dataclass(kw_only=True)
class CaptureWidgetCatalog:
    canvas: Canvas | None = None


@dataclass(kw_only=True)
class WindowWidgetCatalog:
    controller: tk.Toplevel | None = None
    settings: tk.Toplevel | None = None
    discord_settings: tk.Toplevel | None = None
    new_profile: tk.Toplevel | None = None
    question: tk.Toplevel | None = None
    version: tk.Toplevel | None = None
    changelog: tk.Toplevel | None = None
    license: tk.Toplevel | None = None

    def open_controller(
        self,
        master: tk.Misc,
        gen: Callable[[tk.Misc], tk.Toplevel],
    ) -> None:
        if (window := self.controller) is not None:
            if window.winfo_exists():
                window.lift()
                return
        self.controller = gen(master)
        self.controller.protocol(
            "WM_DELETE_WINDOW",
            self._on_controller_closed,
        )

    def open_settings(
        self,
        master: tk.Misc,
        gen: Callable[[tk.Misc], tk.Toplevel],
    ) -> None:
        if (window := self.settings) is not None:
            if window.winfo_exists():
                window.lift()
                return
        self.settings = gen(master)
        self.settings.protocol(
            "WM_DELETE_WINDOW",
            self._on_settings_closed,
        )

    def open_discord_settings(
        self,
        master: tk.Misc,
        gen: Callable[[tk.Misc], tk.Toplevel],
    ) -> None:
        if (window := self.discord_settings) is not None:
            if window.winfo_exists():
                window.lift()
                return
        self.discord_settings = gen(master)
        self.discord_settings.protocol(
            "WM_DELETE_WINDOW",
            self._on_discord_settings_closed,
        )

    def open_new_profile(
        self,
        master: tk.Misc,
        gen: Callable[[tk.Misc], tk.Toplevel],
    ) -> None:
        if (window := self.new_profile) is not None:
            if window.winfo_exists():
                window.lift()
                return
        self.new_profile = gen(master)
        self.new_profile.protocol(
            "WM_DELETE_WINDOW",
            self._on_new_profile_closed,
        )

    def open_question(
        self,
        master: tk.Misc,
        gen: Callable[[tk.Misc], tk.Toplevel],
    ) -> None:
        if (window := self.question) is not None:
            if window.winfo_exists():
                window.lift()
                return
        self.question = gen(master)
        self.question.protocol(
            "WM_DELETE_WINDOW",
            self._on_question_closed,
        )

    def open_version(
        self,
        master: tk.Misc,
        gen: Callable[[tk.Misc], tk.Toplevel],
    ) -> None:
        if (window := self.version) is not None:
            if window.winfo_exists():
                window.lift()
                return
        self.version = gen(master)
        self.version.protocol(
            "WM_DELETE_WINDOW",
            self._on_version_closed,
        )

    def open_changelog(
        self,
        master: tk.Misc,
        gen: Callable[[tk.Misc], tk.Toplevel],
    ) -> None:
        if (window := self.changelog) is not None:
            if window.winfo_exists():
                window.lift()
                return
        self.changelog = gen(master)
        self.changelog.protocol(
            "WM_DELETE_WINDOW",
            self._on_changelog_closed,
        )

    def open_license(
        self,
        master: tk.Misc,
        gen: Callable[[tk.Misc], tk.Toplevel],
    ) -> None:
        if (window := self.license) is not None:
            if window.winfo_exists():
                window.lift()
                return
        self.license = gen(master)
        self.license.protocol(
            "WM_DELETE_WINDOW",
            self._on_license_closed,
        )

    def _on_controller_closed(self) -> None:
        self._destroy(self.controller)
        self.controller = None

    def _on_settings_closed(self) -> None:
        self._destroy(self.settings)
        self.settings = None

    def _on_discord_settings_closed(self) -> None:
        self._destroy(self.discord_settings)
        self.discord_settings = None

    def _on_new_profile_closed(self) -> None:
        self._destroy(self.new_profile)
        self.new_profile = None

    def _on_question_closed(self) -> None:
        self._destroy(self.question)
        self.question = None

    def _on_version_closed(self) -> None:
        self._destroy(self.version)
        self.version = None

    def _on_changelog_closed(self) -> None:
        self._destroy(self.changelog)
        self.changelog = None

    def _on_license_closed(self) -> None:
        self._destroy(self.license)
        self.license = None

    def _destroy(self, window: tk.Toplevel | None) -> None:
        if window is None:
            return
        if window.winfo_exists():
            window.destroy()


@dataclass(kw_only=True)
class AppWidgetCatalog:
    outputs: OutputsWidgetCatalog
    capture: CaptureWidgetCatalog
    window: WindowWidgetCatalog
