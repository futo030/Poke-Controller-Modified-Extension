import shutil
import tkinter as tk
import tkinter.messagebox as messagebox
from typing import Any

from pokecontrollerext.app.translation import t
from pokecontrollerext.singletons.app.model import get_app_model
from pokecontrollerext.singletons.runtime.runtime_info import get_app_runtime_info
from pokecontrollerext.widgets.button import Button
from pokecontrollerext.widgets.checkbutton import Checkbutton
from pokecontrollerext.widgets.frame import Frame
from pokecontrollerext.widgets.label import Label
from pokecontrollerext.widgets.separator import Separator
from pokecontrollerext.widgets.window import Window

BAT_CONTENT = """python SerialController/PokeConUpdateChecker.py
cd SerialController
python Window.py --profile {profile}
pause
"""


class NewProfileWindow(Window):
    def __init__(
        self,
        master: tk.Misc,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, *args, **kwargs)
        self.title(t("new_profile.title"))

        self._runtime_info = get_app_runtime_info()
        self._model = get_app_model()

        self._profile = tk.StringVar()
        self._should_create_bat = tk.BooleanVar(value=True)
        self._should_copy_current_profile = tk.BooleanVar(value=True)

        self.build_ui()

    def build_ui(self) -> None:
        frame = Frame(self)

        # title
        title_label = Label(frame, text=t("new_profile.title"))
        title_label.pack(expand=True, anchor=tk.CENTER, padx=5, pady=5)

        # profile name
        profile_frame = Frame(frame)
        profile_label = Label(
            profile_frame,
            width=10,
            text=t("new_profile.profile"),
            tooltip=t("new_profile.profile.tooltip"),
        )
        profile_entry = tk.Entry(profile_frame, textvariable=self._profile)
        profile_label.pack(side=tk.LEFT)
        profile_entry.pack(side=tk.LEFT, expand=True, fill=tk.X)
        profile_frame.pack(expand=True, fill=tk.X, padx=2, pady=2)

        # bat
        bat_frame = Frame(frame)
        bat_check = Checkbutton(
            bat_frame,
            text=t("new_profile.bat"),
            tooltip=t("new_profile.bat.tooltip"),
            variable=self._should_create_bat,
        )
        bat_check.pack(expand=True, fill=tk.X)
        bat_frame.pack(expand=True, fill=tk.X, padx=2, pady=2)

        # copy
        copy_frame = Frame(frame)
        copy_check = Checkbutton(
            copy_frame,
            text=t("new_profile.copy"),
            tooltip=t("new_profile.copy.tooltip"),
            variable=self._should_copy_current_profile,
        )
        copy_check.pack(expand=True, fill=tk.X)
        copy_frame.pack(expand=True, fill=tk.X, padx=2, pady=2)

        # separator
        Separator(frame, orient=tk.HORIZONTAL).pack(
            expand=True, fill=tk.X, padx=5, pady=5
        )

        # ok/cancel buttons
        buttons_row = Frame(frame)
        ok_button = Button(
            buttons_row, text=t("new_profile.create"), command=self._on_ok_pressed
        )
        cancel_button = Button(
            buttons_row, text="Cancel", command=self._on_cancel_pressed
        )
        ok_button.pack(side=tk.RIGHT, padx=4)
        cancel_button.pack(side=tk.RIGHT, padx=4)
        buttons_row.pack(expand=True, padx=5, pady=(10, 4))

        frame.pack(expand=True, fill=tk.BOTH)

    def _on_ok_pressed(self) -> None:
        if not self._profile.get():
            messagebox.showerror(
                title=t("new_profile.title"),
                message=t("new_profile.message.empty_profile_name"),
            )
            return

        profile_path = self._runtime_info.base_dir / "profiles" / self._profile.get()
        if profile_path.exists():
            messagebox.showerror(
                title=t("new_profile.title"),
                message=t("new_profile.message.profile_already_exists"),
            )
            return

        if self._should_create_bat.get():
            self._create_bat()
        if self._should_copy_current_profile.get():
            self._copy_current_profile()
        else:
            self._create_new_profile_dir()
        messagebox.showinfo(
            title=t("new_profile.title"),
            message=t("new_profile.message.created"),
        )
        self.destroy()

    def _on_cancel_pressed(self) -> None:
        self.destroy()

    def _create_new_profile_dir(self) -> None:
        profile_dir = self._runtime_info.base_dir / "profiles" / self._profile.get()
        if not profile_dir.exists():
            profile_dir.mkdir(parents=True, exist_ok=True)

    def _create_bat(self) -> None:
        base_dir = self._runtime_info.base_dir.parent
        profile = self._profile.get()
        bat_path = base_dir / f"ExecutePokeConModified-Extension_{profile}.bat"
        bat_content = BAT_CONTENT.format(profile=self._profile.get())
        bat_path.write_text(bat_content, encoding="utf-8")

    def _copy_current_profile(self) -> None:
        profiles_dir = self._runtime_info.base_dir / "profiles"
        current_profile_dir = profiles_dir / self._runtime_info.profile
        new_profile_dir = profiles_dir / self._profile.get()
        shutil.copytree(current_profile_dir, new_profile_dir)
