import tkinter as tk
import tkinter.ttk as ttk
from typing import Any, Literal, overload

from pokecontrollerext.widgets.mixins.tooltip import TooltipMixIn

type VariantType = Literal["base", "primary", "error", "success", "warning"]
type SizeType = Literal["xs", "s", "md", "l", "xl"]


class Button(TooltipMixIn, ttk.Button):
    def __init__(
        self,
        master: tk.Misc,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self._pokecon_variant = variant = kwargs.pop("variant", "base")
        self._pokecon_size = size = kwargs.pop("size", "md")
        self._pokecon_style = self._construct_style(variant, size)
        kwargs["style"] = self._pokecon_style
        super().__init__(master, *args, **kwargs)

    @overload
    def configure(
        self, cnf: dict[str, Any] | None = ..., **kwargs: Any
    ) -> Any | None: ...

    @overload
    def configure(self, cnf: str) -> tuple[str, str, str, Any, Any]: ...

    def configure(
        self,
        cnf: dict[str, Any] | str | None = None,
        **kwargs: Any,
    ) -> Any:
        if cnf is not None:
            kwargs["cnf"] = cnf
        if "style" not in kwargs:
            variant = kwargs.pop("variant", self._pokecon_variant)
            size = kwargs.pop("size", self._pokecon_size)
            style = self._construct_style(variant, size)
            if style != self._pokecon_style:
                self._pokecon_style = style
                self._pokecon_variant = variant
                self._pokecon_size = size
                kwargs["style"] = style
        if "tooltip" in kwargs:
            self.set_tooltip(kwargs.pop("tooltip"))
        return super().configure(**kwargs)

    @staticmethod
    def _construct_style(
        variant: VariantType,
        size: SizeType,
    ) -> str:
        styles = ["PokeController"]
        if size != "md":
            styles.append(size.capitalize())
        if variant != "base":
            styles.append(variant.capitalize())
        styles.append("TButton")
        return ".".join(styles)
