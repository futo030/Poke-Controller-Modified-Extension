import tkinter as tk
from dataclasses import dataclass
from typing import Any


@dataclass
class TooltipConfig:
    delay_ms: int = 500
    fade_out_ms: int = 200
    x_offset: int = 10
    y_offset: int = 10


class TooltipMixIn(tk.Misc):
    _tooltip_config: TooltipConfig = TooltipConfig()

    @classmethod
    def configure_tooltips(cls, config: TooltipConfig) -> None:
        cls._tooltip_config = config

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._tooltip_text: str | None = kwargs.pop("tooltip", None)
        self._tooltip_config_override: TooltipConfig | None = kwargs.pop(
            "tooltip_config", None
        )

        super().__init__(*args, **kwargs)

        self._tooltip_window: tk.Toplevel | None = None
        self._tooltip_schedule_id: str | None = None
        self._tooltip_hide_id: str | None = None

        if self._tooltip_text:
            self._tooltip_setup_bindings()

    def _tooltip_setup_bindings(self) -> None:
        self.bind("<Enter>", self._tooltip_on_entered, add="+")
        self.bind("<Leave>", self._tooltip_on_left, add="+")
        self.bind("<Button>", self._tooltip_on_left, add="+")

    @property
    def _tooltip_effective_config(self) -> TooltipConfig:
        return self._tooltip_config_override or self.__class__._tooltip_config

    def set_tooltip(self, text: str | None) -> None:
        was_enabled = self._tooltip_text is not None
        self._tooltip_text = text

        if not was_enabled:
            self._tooltip_setup_bindings()

        if self._tooltip_window:
            self._tooltip_hide()

    def _tooltip_on_entered(self, event: tk.Event) -> None:
        self._tooltip_cancel_scheduled()

        config = self._tooltip_effective_config
        self._tooltip_schedule_id = self.after(
            config.delay_ms,
            self._tooltip_show,
        )

    def _tooltip_on_left(self, event: tk.Event) -> None:
        self._tooltip_cancel_scheduled()

        if self._tooltip_window:
            config = self._tooltip_effective_config
            self._tooltip_hide_id = self.after(
                config.fade_out_ms,
                self._tooltip_hide,
            )

    def _tooltip_show(self) -> None:
        if not self._tooltip_text or self._tooltip_window:
            return

        self._tooltip_window = tk.Toplevel(self)
        self._tooltip_window.wm_overrideredirect(True)

        label = tk.Label(
            self._tooltip_window,
            text=self._tooltip_text,
            background="#ffffe0",
            foreground="black",
            relief=tk.SOLID,
            borderwidth=1,
            padx=5,
            pady=5,
        )
        label.pack()
        self._tooltip_place()

    def _tooltip_place(self) -> None:
        if not self._tooltip_window:
            return

        config = self._tooltip_effective_config
        x = self.winfo_rootx() + config.x_offset
        y = self.winfo_rooty() + self.winfo_height() + config.y_offset

        self._tooltip_window.update_idletasks()
        tooltip_width = self._tooltip_window.winfo_width()
        tooltip_height = self._tooltip_window.winfo_height()
        screen_width = self._tooltip_window.winfo_screenwidth()
        screen_height = self._tooltip_window.winfo_screenheight()

        if x + tooltip_width > screen_width:
            x = screen_width - tooltip_width - config.x_offset
        if y + tooltip_height > screen_height:
            y = self.winfo_rooty() - tooltip_height - config.y_offset

        self._tooltip_window.wm_geometry(f"+{x}+{y}")

    def _tooltip_hide(self) -> None:
        if self._tooltip_window:
            self._tooltip_window.destroy()
            self._tooltip_window = None

    def _tooltip_cancel_scheduled(self) -> None:
        if self._tooltip_schedule_id:
            self.after_cancel(self._tooltip_schedule_id)
            self._tooltip_schedule_id = None

        if self._tooltip_hide_id:
            self.after_cancel(self._tooltip_hide_id)
            self._tooltip_hide_id = None

    def destroy(self) -> None:
        self._tooltip_cancel_scheduled()
        self._tooltip_hide()
        super().destroy()
