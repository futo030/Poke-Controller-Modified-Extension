import tkinter as tk
import tkinter.ttk as ttk
from typing import Any, Callable, Literal


class Frame(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self._pokecon_style = self._construct_style()
        kwargs["style"] = self._pokecon_style
        super().__init__(master, *args, **kwargs)

        self._trace_ids: list[
            tuple[tk.Variable, Literal["array", "read", "write", "unset"], str]
        ] = []

    def register_trace(
        self,
        mode: Literal["write"],
        variable: tk.Variable,
        callback: Callable[[str, str, str], Any],
    ) -> None:
        self._trace_ids.append((variable, mode, variable.trace_add(mode, callback)))

    def refresh(self) -> None:
        pass

    def destroy(self) -> None:
        self._unregister_traces()
        super().destroy()

    def _unregister_traces(self) -> None:
        for variable, mode, trace_id in self._trace_ids:
            variable.trace_remove(mode, trace_id)

    @staticmethod
    def _construct_style() -> str:
        return "PokeController.TFrame"
