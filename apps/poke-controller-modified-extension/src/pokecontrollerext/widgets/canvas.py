import tkinter as tk
from typing import Any

type Font = (
    str
    | list[Any]
    | tuple[str]
    | tuple[str, int]
    | tuple[str, int, str]
    | tuple[str, int, list[str] | tuple[str, ...]]
)


class Canvas(tk.Canvas):
    def draw_rect(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        *,
        outline: str,
        tag: str,
        width: float = 1.0,
        ratio: tuple[float, float] | None = None,
        delete_after_ms: int | None = 100,
    ) -> None:
        rat = ratio if ratio is not None else (1.0, 1.0)
        self.create_rectangle(
            start[0] * rat[0],
            start[1] * rat[1],
            end[0] * rat[0],
            end[1] * rat[1],
            width=width,
            outline=outline,
            tags=tag,
        )
        if delete_after_ms is not None:
            self.after(delete_after_ms, self.delete_tagged_item, tag)

    def draw_circle(
        self,
        center: tuple[int, int],
        radius: int,
        *,
        outline: str,
        tag: str,
        width: float = 1.0,
        ratio: tuple[float, float] | None = None,
        delete_after_ms: int | None = 100,
    ) -> None:
        rat = ratio if ratio is not None else (1.0, 1.0)
        self.create_oval(
            (center[0] - radius) * rat[0],
            (center[1] - radius) * rat[1],
            (center[0] + radius) * rat[0],
            (center[1] + radius) * rat[1],
            width=width,
            outline=outline,
            tags=tag,
        )
        if delete_after_ms is not None:
            self.after(delete_after_ms, self.delete_tagged_item, tag)

    def draw_text(
        self,
        start: tuple[int, int],
        text: str,
        *,
        font: Font,
        color: str,
        tag: str,
        ratio: tuple[float, float] | None = None,
        delete_after_ms: int | None = 100,
    ) -> None:
        rat = ratio if ratio is not None else (1.0, 1.0)
        self.create_text(
            start[0] * rat[0],
            start[1] * rat[1],
            text=text,
            font=font,
            fill=color,
            tags=tag,
        )
        if delete_after_ms is not None:
            self.after(delete_after_ms, self.delete_tagged_item, tag)

    def delete_tagged_item(self, tag: str) -> None:
        self.delete(tag)
