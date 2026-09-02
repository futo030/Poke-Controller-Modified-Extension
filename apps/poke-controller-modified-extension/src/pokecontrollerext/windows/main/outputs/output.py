import tkinter as tk
from typing import Any

from pokecontrollerext.widgets.frame import Frame
from pokecontrollerext.widgets.labelframe import Labelframe


class Output(Frame):
    def __init__(
        self, master: tk.Misc, output_id: int, *args: Any, **kwargs: Any
    ) -> None:
        super().__init__(master, *args, **kwargs)

        self._id: int = output_id
        self.textarea: tk.Text | None = None

        self.build_ui()

    def build_ui(self) -> None:
        labelframe = Labelframe(self, text=f"Output#{self._id}", relief=tk.GROOVE)

        # Text Area
        self.textarea = tk.Text(
            labelframe,
            width=62,
            blockcursor=True,
            insertunfocussed=tk.NONE,
            undo=False,
            maxundo=0,
            relief=tk.FLAT,
            state=tk.DISABLED,
        )
        scroll = tk.Scrollbar(
            labelframe,
            orient=tk.VERTICAL,
            command=self.textarea.yview,
        )
        self.textarea.configure(yscrollcommand=scroll.set)

        # Layout
        self.textarea.pack(expand=True, fill=tk.BOTH, side=tk.LEFT, padx=(5, 0), pady=5)
        scroll.pack(expand=False, fill=tk.Y, side=tk.LEFT, pady=5)
        labelframe.pack(expand=True, fill=tk.BOTH)
