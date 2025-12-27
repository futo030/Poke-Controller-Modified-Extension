import tkinter as tk
import tkinter.ttk as ttk
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from pokecontroller.utils import platform
from pokecontroller.utils.collection import deep_merge


@dataclass
class ComponentStyle:
    base: dict[str, Any] = field(default_factory=dict)
    variants: dict[str, dict[str, Any]] = field(default_factory=dict)
    sizes: dict[str, dict[str, Any]] = field(default_factory=dict)
    orient: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self, class_name: str) -> dict[str, Any]:
        result: dict[str, Any] = {f"PokeController.T{class_name}": self.base}

        axes = (
            ("V", self.variants),
            ("S", self.sizes),
            ("O", self.orient),
        )

        for r in range(1, len(axes) + 1):
            for combo in combinations(range(len(axes)), r):
                self._generate_styles(result, class_name, axes, combo)

        return result

    def _generate_styles(
        self,
        result: dict[str, Any],
        class_name: str,
        axes: Any,
        indices: tuple[int, ...],
    ) -> None:
        selected = [axes[i] for i in indices]

        def recurse(idx: int, names: list[str], styles: list[dict[str, Any]]) -> None:
            if idx == len(selected):
                if styles:
                    key = f"{'.'.join(names)}.T{class_name}"
                    merged = self.base
                    for style in styles:
                        merged = deep_merge(merged, style)
                    result[key] = merged
                return
            _, axis_dict = selected[idx]
            for name, style in axis_dict.items():
                if style:
                    recurse(idx + 1, names + [name.capitalize()], styles + [style])

        recurse(0, ["PokeController"], [])


@dataclass
class StyleSettings:
    button: ComponentStyle = field(default_factory=ComponentStyle)
    label: ComponentStyle = field(default_factory=ComponentStyle)
    entry: ComponentStyle = field(default_factory=ComponentStyle)
    combobox: ComponentStyle = field(default_factory=ComponentStyle)
    spinbox: ComponentStyle = field(default_factory=ComponentStyle)
    radiobutton: ComponentStyle = field(default_factory=ComponentStyle)
    checkbutton: ComponentStyle = field(default_factory=ComponentStyle)
    scale: ComponentStyle = field(default_factory=ComponentStyle)
    frame: ComponentStyle = field(default_factory=ComponentStyle)
    labelframe: ComponentStyle = field(default_factory=ComponentStyle)
    scrollbar: ComponentStyle = field(default_factory=ComponentStyle)
    separator: ComponentStyle = field(default_factory=ComponentStyle)

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.button.to_dict("Button"),
            **self.label.to_dict("Label"),
            **self.entry.to_dict("Entry"),
            **self.combobox.to_dict("Combobox"),
            **self.spinbox.to_dict("Spinbox"),
            **self.radiobutton.to_dict("Radiobutton"),
            **self.checkbutton.to_dict("Checkbutton"),
            **self.scale.to_dict("Scale"),
            **self.frame.to_dict("Frame"),
            **self.labelframe.to_dict("Labelframe"),
            **self.scrollbar.to_dict("Scrollbar"),
            **self.separator.to_dict("Separator"),
        }


class StyleManager:
    """Poke-Controllerのttkウィジェットのスタイルを管理するクラス"""

    _root: tk.Tk
    _style: ttk.Style
    _os_name: str
    _base_style: StyleSettings
    _theme_styles: dict[str, StyleSettings]

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._style = ttk.Style(self._root)
        self._os_name = platform.get_name()
        self._theme_styles = {}
        self._initialize_styles()
        self._setup_all_themes()

    @property
    def root(self) -> tk.Tk:
        return self._root

    @property
    def style(self) -> ttk.Style:
        return self._style

    @property
    def os_name(self) -> str:
        return self._os_name

    def change_theme(self, theme: str) -> None:
        self._style.theme_use(theme)

    def get_themes(self) -> tuple[str, ...]:
        return self._style.theme_names()

    def _initialize_styles(self) -> None:
        self._initialize_base_styles()
        if platform.is_windows():
            self._initialize_styles_for_windows()
        elif platform.is_macos():
            self._initialize_styles_for_macos()
        elif platform.is_linux():
            self._initialize_styles_for_linux()
        else:
            raise RuntimeError(f"Unsupported OS: {self._os_name}")

    def _setup_all_themes(self) -> None:
        for theme, settings in self._theme_styles.items():
            s = deep_merge(self._base_style.to_dict(), settings.to_dict())
            self._style.theme_settings(theme, s)

    def _initialize_base_styles(self) -> None:
        bg = "#dcdad5"
        self._base_style = StyleSettings(
            button=ComponentStyle(),
            label=ComponentStyle(
                base={
                    "configure": {
                        "background": bg,
                    },
                },
            ),
            entry=ComponentStyle(),
            combobox=ComponentStyle(
                base={
                    "configure": {
                        "state": "readonly",
                    },
                },
            ),
            spinbox=ComponentStyle(),
            radiobutton=ComponentStyle(),
            checkbutton=ComponentStyle(
                base={
                    "configure": {
                        "background": bg,
                    },
                },
            ),
            scale=ComponentStyle(
                orient={
                    "horizontal": {
                        "configure": {"padx": 0, "pady": 0},
                    },
                    "vertical": {
                        "configure": {"padx": 0, "pady": 0},
                    },
                },
            ),
            frame=ComponentStyle(
                base={
                    "configure": {
                        "background": bg,
                    },
                },
            ),
            labelframe=ComponentStyle(
                base={
                    "configure": {
                        "background": bg,
                    },
                },
            ),
            scrollbar=ComponentStyle(
                orient={
                    "horizontal": {
                        "configure": {"padx": 0, "pady": 0},
                    },
                    "vertical": {
                        "configure": {"padx": 0, "pady": 0},
                    },
                },
            ),
            separator=ComponentStyle(),
        )

    def _initialize_styles_for_windows(self) -> None:
        self._theme_styles = {
            "clam": StyleSettings(),
            "default": StyleSettings(),
            "alt": StyleSettings(),
            "classic": StyleSettings(),
        }

    def _initialize_styles_for_macos(self) -> None:
        self._theme_styles = {
            "aqua": StyleSettings(),
            "clam": StyleSettings(),
            "default": StyleSettings(),
            "alt": StyleSettings(),
            "classic": StyleSettings(),
        }

    def _initialize_styles_for_linux(self) -> None:
        self._theme_styles = {
            "clam": StyleSettings(),
            "default": StyleSettings(),
            "alt": StyleSettings(),
            "classic": StyleSettings(),
        }
