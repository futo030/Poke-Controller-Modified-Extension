import tkinter as tk
from typing import Any

from pokecontrollerext.app.translation import t
from pokecontrollerext.singletons.runtime.runtime_info import get_app_runtime_info
from pokecontrollerext.widgets.button import Button
from pokecontrollerext.widgets.frame import Frame
from pokecontrollerext.widgets.label import Label
from pokecontrollerext.widgets.scrollable_frame import ScrollableFrame
from pokecontrollerext.widgets.window import Window


class ChangelogWindow(Window):
    def __init__(
        self,
        master: tk.Misc,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, *args, **kwargs)
        self.title(t("changelog.title"))

        self._runtime_info = get_app_runtime_info()
        self.wm_geometry("720x480")

        self.build_ui()

    def build_ui(self) -> None:
        frame = Frame(self)

        content_frame = ScrollableFrame(self)
        content = Label(content_frame.scrollable_frame, text=self._read_changelogs())
        content.pack(expand=True, fill=tk.BOTH)
        content_frame.pack(expand=True, fill=tk.BOTH)

        # ok/cancel buttons
        buttons_row = Frame(frame)
        ok_button = Button(buttons_row, text="OK", command=self._on_ok_pressed)
        ok_button.pack(padx=4)
        buttons_row.pack(padx=4, pady=4)

        frame.pack(fill=tk.BOTH)

    def _on_ok_pressed(self) -> None:
        self.destroy()

    def _read_changelogs(self) -> str:
        project_dir = self._runtime_info.base_dir.parent
        changelog_path = project_dir / "changelog.txt"
        return changelog_path.read_text(encoding="utf-8-sig")
