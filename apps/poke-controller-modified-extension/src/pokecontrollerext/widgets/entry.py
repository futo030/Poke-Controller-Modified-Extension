import tkinter as tk
import tkinter.ttk as ttk
from typing import Any, Literal, overload

from pokecontrollerext.widgets.mixins.tooltip import TooltipMixIn

type SizeType = Literal["xs", "s", "md", "l", "xl"]


class Entry(TooltipMixIn, ttk.Entry):
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

    @overload
    def configure(
        self, cnf: dict[str, Any] | None = ..., **kwargs: Any
    ) -> Any | None: ...

    @overload
    def configure(self, cnf: str) -> tuple[str, str, str, Any, Any]: ...

    def configure(self, cnf: str | dict[str, Any] | None = None, **kwargs: Any) -> Any:
        if cnf is not None:
            kwargs["cnf"] = cnf
        if "style" not in kwargs:
            size = kwargs.get("size", self._pokecon_size)
            style = self._construct_style(size)
            if style != self._pokecon_style:
                self._pokecon_size = size
                self._pokecon_style = style
                kwargs["style"] = style
        if "tooltip" in kwargs:
            self.set_tooltip(kwargs.pop("tooltip"))

        super().configure(**kwargs)

    @staticmethod
    def _construct_style(size: SizeType) -> str:
        styles = ["PokeController"]
        if size != "md":
            styles.append(size.capitalize())
        styles.append("TEntry")
        return ".".join(styles)
