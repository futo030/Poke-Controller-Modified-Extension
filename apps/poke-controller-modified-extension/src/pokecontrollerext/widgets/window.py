import tkinter as tk
from typing import Any, Callable, Literal


class Window(tk.Toplevel):
    def __init__(self, master: tk.Misc, *args: Any, **kwargs: Any) -> None:
        super().__init__(master, *args, **kwargs)
        self._trace_ids: list[
            tuple[tk.Variable, Literal["array", "read", "write", "unset"], str]
        ] = []

    def destroy(self) -> None:
        for variable, mode, trace_id in self._trace_ids:
            variable.trace_remove(mode, trace_id)
        super().destroy()

    def register_trace(
        self,
        mode: Literal["array", "read", "write", "unset"],
        variable: tk.Variable,
        callback: Callable[[str, str, str], Any],
    ) -> None:
        self._trace_ids.append((variable, mode, variable.trace_add(mode, callback)))
