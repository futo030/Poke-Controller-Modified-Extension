import logging
import tkinter as tk
from typing import Any

from pokecontrollerext.widgets.frame import Frame
from pokecontrollerext.widgets.scrollbar import Scrollbar

logger = logging.getLogger(__name__)


class ScrollableFrame(Frame):
    _canvas: tk.Canvas
    _scrollbar: Scrollbar
    _canvas_window: int
    _updating: bool

    def __init__(
        self,
        master: tk.Misc,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        width = kwargs.pop("width", None)
        super().__init__(master, *args, **kwargs)

        bg_color = (
            kwargs.pop("bg", None)
            or kwargs.pop("background", None)
            or self._get_default_bg(master)
        )
        canvas_kwargs: dict[str, Any] = {
            "highlightthickness": 0,
            "bg": bg_color,
        }
        if width is not None:
            canvas_kwargs["width"] = width
        self._canvas = tk.Canvas(self, **canvas_kwargs)
        self._scrollbar = Scrollbar(
            master,
            orient="vertical",
            command=self._canvas.yview,
        )
        self.scrollable_frame = Frame(self._canvas, *args, **kwargs)

        self._updating = False
        self.build_ui()

    def build_ui(self) -> None:
        self.scrollable_frame.bind("<Configure>", self._on_frame_configure)
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self.scrollable_frame, anchor=tk.NW
        )
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._canvas.bind(
            "<Configure>",
            self._on_canvas_configure,
        )

        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._canvas.bind("<Enter>", lambda _: self._bind_mouse_wheel())
        self._canvas.bind("<Leave>", lambda _: self._unbind_mouse_wheel())

    def refresh(self) -> None:
        self.update_idletasks()
        self._canvas.update_idletasks()
        self.scrollable_frame.update_idletasks()
        self._update_scroll_region()

    def _bind_mouse_wheel(self) -> None:
        self._canvas.bind_all("<MouseWheel>", self._on_mouse_wheel)
        self._canvas.bind_all("<Button-4>", self._on_mouse_wheel)
        self._canvas.bind_all("<Button-5>", self._on_mouse_wheel)

    def _unbind_mouse_wheel(self) -> None:
        self._canvas.unbind_all("<MouseWheel>")
        self._canvas.unbind_all("<Button-4>")
        self._canvas.unbind_all("<Button-5>")

    def _on_frame_configure(self, _: tk.Event) -> None:
        if not self._updating:
            self._update_scroll_region()

    def _on_canvas_configure(self, event: tk.Event) -> None:
        if self._updating:
            return

        self._updating = True
        try:
            self._canvas.itemconfig(
                self._canvas_window,
                width=event.width,
            )
            self._update_scroll_region()
        finally:
            self._updating = False

    def _update_scroll_region(self) -> None:
        if self._updating:
            return

        self._updating = True
        try:
            self._canvas.update_idletasks()

            bbox = self._canvas.bbox("all")

            content_height = bbox[3] - bbox[1]
            canvas_height = self._canvas.winfo_height()

            if content_height > canvas_height:
                self._canvas.configure(scrollregion=bbox)
                if not self._scrollbar.winfo_ismapped():
                    self._scrollbar.pack(side=tk.RIGHT, fill=tk.Y, before=self._canvas)
            else:
                self._canvas.configure(scrollregion=bbox)
                self._canvas.yview_moveto(0)
                if self._scrollbar.winfo_ismapped():
                    self._scrollbar.pack_forget()
        finally:
            self._updating = False
            self.update_idletasks()

    def _on_mouse_wheel(self, event: tk.Event) -> None:
        bbox = self._canvas.bbox("all")
        if bbox and bbox[3] > self._canvas.winfo_height():
            if event.num == 5 or event.delta < 0:
                self._canvas.yview_scroll(1, "units")
            if event.num == 4 or event.delta > 0:
                self._canvas.yview_scroll(-1, "units")

    def _get_default_bg(self, widget: tk.Misc) -> str:
        """親ウィジェットの背景色を取得"""
        try:
            if isinstance(widget, (tk.Frame, tk.Tk, tk.Toplevel)):
                bg = widget.cget("background")
            else:
                from tkinter import ttk

                style = ttk.Style()
                if isinstance(widget, ttk.Frame):
                    bg = (
                        style.lookup("PokeController.TFrame", "background")
                        or "SystemButtonFace"
                    )
                elif isinstance(widget, ttk.Labelframe):
                    bg = (
                        style.lookup("PokeController.TLabelframe", "background")
                        or "SystemButtonFace"
                    )
                else:
                    bg = "SystemButtonFace"

            # システムカラーをRGBに変換
            rgb = widget.winfo_rgb(bg)
            r, g, b = [x >> 8 for x in rgb]
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return "#f0f0f0"
