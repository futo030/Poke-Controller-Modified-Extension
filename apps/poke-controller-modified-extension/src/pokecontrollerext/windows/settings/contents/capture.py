import logging
import tkinter as tk
from typing import Any

from pokecontrollerext.singletons.app.model import get_app_model
from pokecontrollerext.singletons.app.settings import get_app_settings
from pokecontrollerext.widgets.components import ComponentBuilder
from pokecontrollerext.widgets.frame import Frame

logger = logging.getLogger(__name__)


class CaptureSettingsPane(Frame):
    _camera_size_scale: tk.Scale

    def __init__(self, master: tk.Misc, *args: Any, **kwargs: Any) -> None:
        super().__init__(master, *args, **kwargs)

        self._settings = get_app_settings()
        self._app_model = get_app_model()

        self._camera_id = self._settings.capture.camera_id
        self._camera_name = self._settings.capture.camera_name
        self._fps = self._settings.capture.fps
        self._camera_size = self._settings.capture.size
        self._camera_size_scale_value = tk.IntVar(
            value=int(self._camera_size.get().split("x")[0]) // 16,
        )
        self._show_realtime = self._settings.capture.show_realtime
        self._show_matched = self._settings.capture.show_matched
        self._show_guide = self._settings.capture.show_guide

        self._register_hooks()
        self.build_ui()

    def build_ui(self) -> None:
        label_width = 16
        frame = (
            ComponentBuilder(self)
            .add_frame_row()
            .add_label(text="Camera ID:", width=label_width)
            .add_combobox(
                self._camera_id,
                values=[camera.name for camera in self._app_model.load_camera_list()],
            )
            .end()
            .add_frame_row()
            .add_label(text="Camera Name:", width=label_width)
            .add_label(variable=self._camera_name)
            .end()
            .add_frame_row()
            .add_label(text="FPS:", width=label_width)
            .add_spinbox(self._fps, from_=1, to=60, disabled=self._show_realtime)
            .end()
            .add_frame_row()
            .add_label(text="Camera Size:", width=label_width)
            .add_scale(
                self._camera_size_scale_value,
                from_=1,
                to=80,
                expand=True,
                disabled=self._show_realtime,
            )
            .end()
            .add_frame_row()
            .add_label(text="Show Realtime:", width=label_width)
            .add_checkbutton(self._show_realtime, "")
            .end()
            .add_frame_row()
            .add_label(text="Show Matched:", width=label_width)
            .add_checkbutton(self._show_matched, "")
            .end()
            .add_frame_row()
            .add_label(text="Show Guide:", width=label_width)
            .add_checkbutton(self._show_guide, "")
            .end()
            .build()
        )
        frame.pack(fill=tk.BOTH, anchor=tk.CENTER)

    def _register_hooks(self) -> None:
        self.register_trace(
            "write",
            self._camera_size_scale_value,
            self._on_camera_size_scale_value_changed,
        )

    def _on_camera_size_scale_value_changed(self, *_: Any) -> None:
        if self._show_realtime.get():
            return
        scale = self._camera_size_scale_value.get()
        self._camera_size.set(f"{scale * 16}x{scale * 9}")
