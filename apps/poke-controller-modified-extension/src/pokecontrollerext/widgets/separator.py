import tkinter as tk
import tkinter.ttk as ttk
from typing import Any, Literal

type OrientType = Literal["horizontal", "vertical"]


class Separator(ttk.Separator):
    def __init__(
        self,
        master: tk.Misc,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self._pokecon_orient = orient = kwargs.pop("orient", "vertical")
        self._pokecon_style = self._construct_style(orient)
        kwargs["style"] = self._pokecon_style
        kwargs["orient"] = orient
        super().__init__(master, *args, **kwargs)

    @staticmethod
    def _construct_style(orient: str) -> str:
        return f"PokeController.{orient.capitalize()}.TSeparator"
