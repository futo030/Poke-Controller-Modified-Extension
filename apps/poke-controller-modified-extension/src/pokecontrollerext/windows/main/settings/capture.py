import tkinter as tk
from typing import Any

from pokecontroller.core.camera import CameraInfo

from pokecontrollerext.app.translation import t
from pokecontrollerext.singletons.app.model import get_app_model
from pokecontrollerext.singletons.app.settings import get_app_settings
from pokecontrollerext.widgets.button import Button
from pokecontrollerext.widgets.checkbutton import Checkbutton
from pokecontrollerext.widgets.combobox import Combobox
from pokecontrollerext.widgets.entry import Entry
from pokecontrollerext.widgets.frame import Frame
from pokecontrollerext.widgets.label import Label
from pokecontrollerext.widgets.labelframe import Labelframe
from pokecontrollerext.widgets.separator import Separator


class CameraSettings(Frame):
    _cameras: list[CameraInfo]

    def __init__(self, master: tk.Misc, *args: Any, **kwargs: Any) -> None:
        super().__init__(master, *args, **kwargs)

        self._app_settings = get_app_settings()
        self._app_model = get_app_model()
        self._load_camera_list()

        self._name_list = [camera.name for camera in self._cameras]
        self._size_list: list[str] = self._load_camera_size_list()

        self._camera_id = self._app_settings.capture.camera_id
        self._camera_name = self._app_settings.capture.camera_name
        self._fps = self._app_settings.capture.fps
        self._size = self._app_settings.capture.size
        self._show_realtime = self._app_settings.capture.show_realtime
        self._show_matched = self._app_settings.capture.show_matched
        self._show_guide = self._app_settings.capture.show_guide

        self._register_traces()

        self.build_ui()

    def build_ui(self) -> None:
        # Create Labelframes
        camera_settings = self._build_camera_settings()
        display_settings = self._build_display_settings()

        # Layout
        camera_settings.pack(expand=False, fill=tk.BOTH, pady=4)
        display_settings.pack(expand=False, fill=tk.BOTH, pady=4)

    def _build_camera_settings(self) -> Labelframe:
        labelframe = Labelframe(self, text="Camera Settings")

        # Upper Frame
        upper_frame = Frame(labelframe)

        # Name
        name_label = Label(
            upper_frame,
            text=t("main.settings.capture.camera.name.label"),
            tooltip=t("main.settings.capture.camera.name.label.tooltip"),
            width=11,
            anchor=tk.CENTER,
        )
        name_combobox = Combobox(
            upper_frame,
            tooltip=t("main.settings.capture.camera.name.combobox.tooltip"),
            textvariable=self._camera_name,
            values=self._name_list,
        )
        if len(self._name_list) > 0:
            self._camera_name.set(self._name_list[0])

        # Lower Frame
        lower_frame = Frame(labelframe)

        # ID
        self._adjust_camera_id()
        id_label = Label(
            lower_frame,
            text=t("main.settings.capture.camera.id.label"),
            tooltip=t("main.settings.capture.camera.id.label.tooltip"),
            width=11,
            anchor=tk.W,
        )
        id_entry = Entry(
            lower_frame,
            tooltip=t("main.settings.capture.camera.id.entry.tooltip"),
            width=3,
            state=tk.DISABLED,
            textvariable=self._camera_id,
        )

        # FPS
        fps_list = [60, 45, 30, 15, 5]
        fps_label = Label(
            lower_frame,
            text=t("main.settings.capture.camera.fps.label"),
            tooltip=t("main.settings.capture.camera.fps.label.tooltip"),
        )
        fps_combobox = Combobox(
            lower_frame,
            tooltip=t("main.settings.capture.camera.fps.combobox.tooltip"),
            width=3,
            justify=tk.LEFT,
            state="readonly",
            textvariable=self._fps,
            values=[str(f) for f in fps_list],
        )

        # Size
        size_label = Label(
            lower_frame,
            text=t("main.settings.capture.camera.size.label"),
            tooltip=t("main.settings.capture.camera.size.label.tooltip"),
        )
        size_combobox = Combobox(
            lower_frame,
            tooltip=t("main.settings.capture.camera.size.combobox.tooltip"),
            width=8,
            state="readonly",
            textvariable=self._size,
            values=self._size_list,
        )
        size_combobox.current(self._size_list.index(self._size.get()))

        # Reload
        reload_button = Button(
            lower_frame,
            text=t("main.settings.capture.camera.reload"),
            tooltip=t("main.settings.capture.camera.reload.tooltip"),
            command=self._on_reload_pressed,
        )

        # Layout
        name_label.pack(expand=False, fill=tk.X, side=tk.LEFT)
        name_combobox.pack(expand=True, fill=tk.X, side=tk.LEFT)
        upper_frame.pack(expand=True, fill=tk.X, side=tk.TOP, padx=4, pady=4)

        id_label.pack(expand=False, fill=tk.X, side=tk.LEFT)
        id_entry.pack(expand=True, fill=tk.X, side=tk.LEFT)
        # noinspection DuplicatedCode
        Separator(master=lower_frame).pack(
            expand=False, fill=tk.Y, side=tk.LEFT, padx=5, pady=8
        )
        fps_label.pack(expand=False, fill=tk.X, side=tk.LEFT)
        fps_combobox.pack(expand=False, fill=tk.X, side=tk.LEFT)
        # noinspection DuplicatedCode
        Separator(master=lower_frame).pack(
            expand=False, fill=tk.Y, side=tk.LEFT, padx=5, pady=8
        )
        size_label.pack(expand=False, fill=tk.X, side=tk.LEFT)
        size_combobox.pack(expand=False, fill=tk.X, side=tk.LEFT)
        Separator(master=lower_frame).pack(
            expand=False, fill=tk.Y, side=tk.LEFT, padx=5, pady=8
        )
        reload_button.pack(expand=False, fill=tk.X, side=tk.LEFT, padx=4)
        lower_frame.pack(expand=True, fill=tk.BOTH, side=tk.TOP, padx=4, pady=4)

        return labelframe

    def _build_display_settings(self) -> Labelframe:
        labelframe = Labelframe(self, text="Display Settings")

        # Show Realtime
        show_realtime_checkbutton = Checkbutton(
            labelframe,
            text=t("main.settings.capture.display.realtime"),
            tooltip=t("main.settings.capture.display.realtime.tooltip"),
            variable=self._show_realtime,
        )

        # Show Value
        show_matched_checkbutton = Checkbutton(
            labelframe,
            text=t("main.settings.capture.display.matched"),
            tooltip=t("main.settings.capture.display.matched.tooltip"),
            variable=self._show_matched,
        )

        # Show Guide
        show_guide_checkbutton = Checkbutton(
            labelframe,
            text=t("main.settings.capture.display.guide"),
            tooltip=t("main.settings.capture.display.guide.tooltip"),
            variable=self._show_guide,
        )

        # Layout
        show_realtime_checkbutton.pack(
            expand=False, fill=tk.X, side=tk.LEFT, padx=4, pady=4
        )
        show_matched_checkbutton.pack(
            expand=False, fill=tk.X, side=tk.LEFT, padx=8, pady=4
        )
        show_guide_checkbutton.pack(
            expand=False, fill=tk.X, side=tk.LEFT, padx=4, pady=4
        )

        return labelframe

    def _load_camera_list(self) -> None:
        self._cameras = self._app_model.load_camera_list()

    def _load_camera_size_list(self) -> list[str]:
        return self._app_model.load_camera_size_list()

    def _adjust_camera_id(self) -> None:
        camera_id = 0
        for camera in self._cameras:
            if camera.name == self._camera_name.get():
                camera_id = camera.index
        self._camera_id.set(camera_id)

    def _on_reload_pressed(self) -> None:
        self._app_model.connect_camera()

    def _on_camera_name_changed(self, *_: str) -> None:
        self._adjust_camera_id()

    def _register_traces(self) -> None:
        self.register_trace("write", self._camera_name, self._on_camera_name_changed)
