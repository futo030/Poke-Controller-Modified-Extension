import math
import tkinter as tk
from typing import Any, Literal

from pokecontrollerext.singletons.app.model import get_app_model
from pokecontrollerext.singletons.app.settings import get_app_settings
from pokecontrollerext.widgets.frame import Frame
from pokecontrollerext.windows.main.capture import CapturePane
from pokecontrollerext.windows.main.controller import ControllerPane
from pokecontrollerext.windows.main.outputs import OutputsPane
from pokecontrollerext.windows.main.settings import SettingsPane

CAPTURE = "capture"
SETTINGS = "settings"
OUTPUTS = "outputs"
CONTROLLER = "controller"

PANES = [
    (CAPTURE, CapturePane, tk.LEFT),
    (SETTINGS, SettingsPane, tk.LEFT),
    (OUTPUTS, OutputsPane, tk.RIGHT),
    (CONTROLLER, ControllerPane, tk.RIGHT),
]


class MainWindow(Frame):
    def __init__(self, master: tk.Misc, *args: Any, **kwargs: Any) -> None:
        super().__init__(master, *args, **kwargs)

        self._app_settings = get_app_settings()
        self._app_model = get_app_model()

        self._outputs_size = self._app_settings.widget.output.size_balance
        self._visible_output1 = self._app_settings.widget.output.visible_output1
        self._visible_output2 = self._app_settings.widget.output.visible_output2
        self._visible_controller = self._app_settings.widget.software_controller.visible
        self._controller_position = (
            self._app_settings.widget.software_controller.position
        )

        # for trace
        self._serial_port = self._app_settings.serial.port
        self._serial_port_name = self._app_settings.serial.port_name

        # keyboard
        self._enabled_keyboard = self._app_settings.device.keyboard.enabled

        # pro-controller
        self._enabled_pro_controller = self._app_settings.device.pro_controller.enabled

        self._panes: dict[str, Frame] = {}
        self._frames: dict[str, Frame] = {}
        self._register_traces()
        self.build_ui()

        master.after(0, self._adjust_outputs_size)

    @property
    def _outputs_pane(self) -> OutputsPane:
        # noinspection PyTypeChecker
        return self._panes[OUTPUTS]  # type: ignore[return-value]

    @property
    def _controller_pane(self) -> ControllerPane:
        # noinspection PyTypeChecker
        return self._panes[CONTROLLER]  # type: ignore[return-value]

    @property
    def _left_frame(self) -> Frame:
        return self._frames[tk.LEFT]

    @property
    def _right_frame(self) -> Frame:
        return self._frames[tk.RIGHT]

    def build_ui(self) -> None:
        # Frames
        self._frames[tk.LEFT] = Frame(self)
        self._frames[tk.RIGHT] = Frame(self)

        # Create Panes
        for name, pane_class, side in PANES:
            self._panes[name] = pane_class(self._frames[side])

        # Layout
        self._layout_left_frame()
        self._layout_right_frame()

    def _register_traces(self) -> None:
        for var, func in (
            (self._outputs_size, self._on_outputs_size_changed),
            (self._visible_output1, self._on_widget_visibility_changed),
            (self._visible_output2, self._on_widget_visibility_changed),
            (self._visible_controller, self._on_widget_visibility_changed),
            (self._controller_position, self._on_controller_position_changed),
            (self._serial_port, self._on_serial_port_changed),
            (self._enabled_keyboard, self._on_enabled_keyboard_changed),
            (self._enabled_pro_controller, self._on_enabled_pro_controller_changed),
        ):
            self.register_trace("write", var, func)

    def _layout_left_frame(self) -> None:
        self._panes[CAPTURE].pack(expand=True, fill=tk.BOTH, anchor=tk.CENTER)
        self._panes[SETTINGS].pack(expand=True, fill=tk.BOTH, pady=(4, 0))
        self._frames[tk.LEFT].pack(
            expand=True,
            fill=tk.BOTH,
            side=tk.LEFT,
            padx=4,
            pady=(0, 4),
        )

    def _layout_right_frame(self) -> None:
        def pack(
            frame: Frame,
            visible: bool,
            *,
            side: Literal["top", "left"] = tk.TOP,
            px: tuple[int, int] | int = 0,
            py: tuple[int, int] | int = 0,
        ) -> None:
            frame.pack_forget()
            if visible:
                frame.pack(expand=True, fill=tk.BOTH, side=side, padx=px, pady=py)

        # pack output frames
        output1, output2 = self._outputs_pane.outputs
        visible_output1 = self._visible_output1.get()
        visible_output2 = self._visible_output2.get()
        pack(output1, visible_output1)
        pack(output2, visible_output2, py=(4, 0) if visible_output1 else 0)

        # pack panes
        self._repack_right_panes()

        # pack right frame
        right_frame = self._right_frame
        visible_controller = self._visible_controller.get()
        visible_right_frame = visible_output1 or visible_output2 or visible_controller
        pack(right_frame, visible_right_frame, side=tk.LEFT, px=4, py=(0, 4))

    def _repack_right_panes(self) -> None:
        self._adjust_outputs_size()

        outputs_pane, controller_pane = self._outputs_pane, self._controller_pane
        outputs_pane.pack_forget()
        controller_pane.pack_forget()

        visible_outputs = self._visible_output1.get() or self._visible_output2.get()
        visible_controller = self._visible_controller.get()
        if self._controller_position.get() == "bottom":
            if visible_outputs:
                outputs_pane.pack(expand=True, fill=tk.BOTH)
            if visible_controller:
                controller_pane.pack(
                    expand=False,
                    fill=tk.BOTH,
                    pady=(4, 0) if visible_outputs else (0, 0),
                )
        else:
            if visible_controller:
                controller_pane.pack(expand=False, fill=tk.BOTH)
            if visible_outputs:
                outputs_pane.pack(
                    expand=True,
                    fill=tk.BOTH,
                    pady=(4, 0) if visible_controller else (0, 0),
                )

    def _adjust_outputs_size(self) -> None:
        output1, output2 = self._outputs_pane.outputs
        if (t1 := output1.textarea) is None or (t2 := output2.textarea) is None:
            raise RuntimeError("Outputs text areas are not initialized.")

        if (size := self._outputs_size.get()) is None:
            raise RuntimeError("Outputs size is not initialized.")

        outputs_pane_height = self._left_frame.winfo_height()
        if self._visible_controller.get():
            controller_height = self._controller_pane.winfo_height()
            outputs_pane_height -= controller_height

        shareable_height = math.floor((outputs_pane_height / 13) - 8)
        size_gravity = math.floor(size) / 100

        height1 = math.floor(shareable_height * size_gravity)
        height2 = math.floor(shareable_height * (1.0 - size_gravity))
        if (r := shareable_height - (height1 + height2)) > 0:
            if height1 > height2:
                height2 += r
            else:
                height1 += r

        t1.configure(height=height1)
        t2.configure(height=height2)

    def _on_widget_visibility_changed(self, *_: Any) -> None:
        self._layout_right_frame()

    def _on_outputs_size_changed(self, *_: Any) -> None:
        self._adjust_outputs_size()

    def _on_controller_position_changed(self, *_: Any) -> None:
        self._repack_right_panes()

    def _on_serial_port_changed(self, *_: Any) -> None:
        serial_ports = self._app_model.load_serial_ports()
        for port in serial_ports:
            if port.path == self._serial_port.get():
                self._serial_port_name.set(port.name)
        if serial_ports:
            self._serial_port_name.set(serial_ports[0].name)

    def _on_enabled_keyboard_changed(self, *_: Any) -> None:
        if self._enabled_keyboard.get():
            self._app_model.start_keyboard()
        else:
            self._app_model.stop_keyboard()

    def _on_enabled_pro_controller_changed(self, *_: Any) -> None:
        if self._enabled_pro_controller.get():
            self._app_model.start_pro_controller()
        else:
            self._app_model.stop_pro_controller()
