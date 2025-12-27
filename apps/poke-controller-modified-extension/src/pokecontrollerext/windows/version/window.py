import importlib.metadata
import platform
import sys
import tkinter as tk
import tomllib
from typing import Any

from pokecontrollerext.app.translation import t
from pokecontrollerext.singletons.runtime.app_info import get_app_info
from pokecontrollerext.singletons.runtime.runtime_info import get_app_runtime_info
from pokecontrollerext.widgets.button import Button
from pokecontrollerext.widgets.frame import Frame
from pokecontrollerext.widgets.label import Label
from pokecontrollerext.widgets.window import Window


class VersionWindow(Window):
    def __init__(
        self,
        master: tk.Misc,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, *args, **kwargs)
        self.title(t("version.title"))

        self._app_info = get_app_info()
        self._runtime_info = get_app_runtime_info()

        self.build_ui()

    def build_ui(self) -> None:
        frame = Frame(self)

        outputs = (
            f"■{self._app_info.name}",
            self._app_info.version,
            "",
            "■OS",
            platform.platform(),
            "",
            "■Python Version",
            sys.version.split(" ")[0],
            "",
            "■Libraries Version",
            "\n".join(
                [
                    f"{lib}: {version}"
                    for lib, version in self._get_libraries_versions().items()
                ]
            ),
            "",
        )
        content = Label(frame, text="\n".join(outputs))
        content.pack(expand=True, fill=tk.BOTH)

        # ok/cancel buttons
        buttons_row = Frame(frame)
        ok_button = Button(buttons_row, text="OK", command=self._on_ok_pressed)
        ok_button.pack(side=tk.RIGHT, padx=4)
        buttons_row.pack(expand=True, padx=5, pady=(10, 4))

        frame.pack(expand=True, fill=tk.BOTH)

    def _on_ok_pressed(self) -> None:
        self.destroy()

    def _get_libraries_versions(self) -> dict[str, str]:
        libraries = self._parse_libraries()

        versions: dict[str, str] = {}
        for lib in libraries:
            try:
                versions[lib] = importlib.metadata.version(lib)
            except importlib.metadata.PackageNotFoundError:
                versions[lib] = "Not installed"
        return versions

    def _parse_libraries(self) -> list[str]:
        libraries = []
        project_dir = self._runtime_info.base_dir.parent
        pyproject_path = project_dir / "pyproject.toml"
        pp = tomllib.loads(pyproject_path.read_text(encoding="utf-8-sig"))
        for lib in pp["project"]["dependencies"]:
            if lib.startswith("poke-controller"):
                continue
            libraries.append(lib.split(">=")[0])
        return libraries
