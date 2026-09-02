import tkinter as tk
import tkinter.ttk as ttk
from typing import Any, Literal

from pokecontrollerext.widgets.mixins.tooltip import TooltipMixIn

type SizeType = Literal["xs", "s", "md", "l", "xl"]


class Spinbox(TooltipMixIn, ttk.Spinbox):
    def __init__(
        self,
        master: tk.Misc,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self._pokecon_size = size = kwargs.pop("size", "md")
        self._pokecon_style = self._construct_style(size)
        kwargs["style"] = self._pokecon_style
        super().__init__(master, *args, **kwargs)

    def configure_style(self, *, size: SizeType) -> None:
        self._pokecon_style = self._construct_style(size)
        self.configure(style=self._pokecon_style)

    @staticmethod
    def _construct_style(size: SizeType) -> str:
        styles = ["PokeController"]
        if size != "md":
            styles.append(size.capitalize())
        styles.append("TSpinbox")
        return ".".join(styles)
