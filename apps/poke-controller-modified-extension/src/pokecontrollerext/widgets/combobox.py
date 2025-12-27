import tkinter as tk
import tkinter.ttk as ttk
from typing import Any, Literal, overload

from pokecontrollerext.widgets.mixins.tooltip import TooltipMixIn

type SizeType = Literal["xs", "s", "md", "l", "xl"]


class Combobox(TooltipMixIn, ttk.Combobox):
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

        self._disable_text_selection()

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

    def _disable_text_selection(self) -> None:
        """Disable text selection in combobox."""
        self.bind("<<ComboboxSelected>>", lambda _: self.selection_clear())
        self.bind("<Button-1>", lambda _: self.after_idle(self.selection_clear))
        self.bind("<B1-Motion>", lambda _: "break")
        self.bind("<Double-Button-1>", lambda _: "break")
        self.bind("<Triple-Button-1>", lambda _: "break")
        self.bind("<Control-a>", lambda _: "break")

    @staticmethod
    def _construct_style(size: SizeType) -> str:
        styles = ["PokeController"]
        if size != "md":
            styles.append(size.capitalize())
        styles.append("TCombobox")
        return ".".join(styles)
