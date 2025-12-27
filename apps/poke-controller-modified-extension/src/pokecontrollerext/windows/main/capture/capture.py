import cmath
import logging
import math
import time
import tkinter as tk
from collections import deque
from tkinter import filedialog
from typing import Any

import cv2
from PIL import Image, ImageTk
from pokecontroller.core import controller, image
from pokecontroller.core.controller import StickState, n3ds, switch
from pokecontroller.utils import platform
from pokecontroller.utils.math import clamp

from pokecontrollerext.singletons.app.settings import get_app_settings
from pokecontrollerext.singletons.runtime.resources import (
    get_app_resources,
)
from pokecontrollerext.singletons.runtime.runtime_info import (
    get_app_runtime_info,
)
from pokecontrollerext.singletons.widget.catalog import (
    get_app_widget_catalog,
)
from pokecontrollerext.widgets.canvas import Canvas
from pokecontrollerext.widgets.frame import Frame

logger = logging.getLogger(__name__)

type Font = (
    str
    | list[Any]
    | tuple[str]
    | tuple[str, int]
    | tuple[str, int, str]
    | tuple[str, int, list[str] | tuple[str, ...]]
)


class Capture(Frame):
    _canvas: Canvas
    _ratio: tuple[float, float]
    _image: ImageTk.PhotoImage
    _image_id: int

    _controller: switch.SwitchController | n3ds.N3dsController

    def __init__(self, master: tk.Misc, *args: Any, **kwargs: Any) -> None:
        super().__init__(master, *args, **kwargs)

        self._app_resources = get_app_resources()
        self._app_settings = get_app_settings()
        self._runtime_info = get_app_runtime_info()

        self._disabled_raw_image = image.read(
            path="../Images/disabled.png", mode="grayscale"
        )

        self._camera = self._app_resources.camera
        self._serial = self._app_resources.serial

        self._camera_id = self._app_settings.capture.camera_id
        self._fps = self._app_settings.capture.fps
        self._size = self._app_settings.capture.size
        self._show_realtime = self._app_settings.capture.show_realtime
        self._show_matched = self._app_settings.capture.show_matched
        self._show_guide = self._app_settings.capture.show_guide
        self._next_frame_time = 1000 // self._fps.get()
        self._width, self._height = self._parse_size()

        # for mouse control
        self._data_format = self._app_settings.serial.data_format
        if self._data_format.get() == "Qingpi":
            self._controller = n3ds.N3dsController(self._serial, "qingpi")
        elif self._data_format.get() == "3DS Controller":
            self._controller = n3ds.N3dsController(self._serial, "3ds controller")
        else:
            self._controller = switch.SwitchController(self._serial)
        self._mouse_right_mode = "Default"
        self._enabled_lstick_mouse = self._app_settings.device.mouse.enabled_lclick
        self._enabled_rstick_mouse = self._app_settings.device.mouse.enabled_rclick
        self._mouse_circle_radius = 60
        self._pressed_point = (0, 0)
        self._right_stick_mode = self._data_format.get()
        self._update_ratio()

        # for touchscreen support
        self._touchscreen_area = ((1, 1), (320, 240))

        # for input logging
        self._should_log_input = True
        self._input_logs: deque[tuple[float, float, float]] | None = None
        self._last_input_time: float | None = None
        self._stick_angle: float | None = None
        self._stick_mag: float | None = None

        if (disabled_raw_image := self._disabled_raw_image) is not None:
            self._disabled_image = ImageTk.PhotoImage(
                image=Image.fromarray(
                    image.resize(disabled_raw_image, self._parse_size())
                ),
            )
        else:
            self._disabled_image = ImageTk.PhotoImage()

        # for resizing
        self._after_id: str | None = None
        self._is_resizing = False
        self._is_disabled = True
        self._is_show_disabled = False

        self.build_ui()

        self._register_hooks()
        self._bind_all()
        self._update_frame()

    @property
    def _switch_controller(self) -> switch.SwitchController | None:
        if isinstance(self._controller, switch.SwitchController):
            return self._controller
        return None

    @property
    def _n3ds_controller(self) -> n3ds.N3dsController | None:
        if isinstance(self._controller, n3ds.N3dsController):
            return self._controller
        return None

    @property
    def _lstick(self) -> StickState:
        if isinstance(self._controller, n3ds.N3dsController):
            return self._controller.stick
        return self._controller.lstick

    @property
    def _rstick(self) -> StickState | None:
        if isinstance(self._controller, n3ds.N3dsController):
            return None
        return self._controller.rstick

    @property
    def frame_size(self) -> tuple[int, int]:
        return self._camera.frame_size

    def build_ui(self) -> None:
        logger.info(f"Creating new canvas: {self._width}x{self._height}")
        self._canvas = Canvas(
            self,
            width=self._width,
            height=self._height,
            cursor="tcross",
        )
        wc = get_app_widget_catalog()
        wc.capture.canvas = self._canvas
        self._image = self._disabled_image
        self._image_id = self._canvas.create_image(
            0, 0, anchor=tk.NW, image=self._image
        )
        self._is_disabled = False
        self._canvas.pack(expand=True, fill=tk.BOTH, anchor=tk.CENTER)
        logger.info("Canvas created")

    def _register_hooks(self) -> None:
        self._fps.trace_add("write", self._on_fps_changed)
        self._size.trace_add("write", self._on_size_changed)
        self._enabled_lstick_mouse.trace_add(
            "write", self._on_enable_lstick_mouse_changed
        )
        self._enabled_rstick_mouse.trace_add(
            "write", self._on_enable_rstick_mouse_changed
        )
        self._data_format.trace_add("write", self._on_serial_data_format_changed)

    def _update_frame(self) -> None:
        if self._show_realtime.get():
            self._load_frame()

        self._after_id = self.after(ms=self._next_frame_time, func=self._update_frame)

    def _draw_rect(
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
        if not self._show_realtime.get() or self._is_resizing:
            return

        self._canvas.draw_rect(
            start=start,
            end=end,
            outline=outline,
            tag=tag,
            width=width,
            ratio=ratio,
            delete_after_ms=delete_after_ms,
        )

    def _draw_circle(
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
        if not self._show_realtime.get() or self._is_resizing:
            return

        self._canvas.draw_circle(
            center=center,
            radius=radius,
            outline=outline,
            tag=tag,
            width=width,
            ratio=ratio,
            delete_after_ms=delete_after_ms,
        )

    def _draw_text(
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
        if not self._show_realtime.get() or self._is_resizing:
            return

        self._canvas.draw_text(
            start=start,
            text=text,
            font=font,
            color=color,
            tag=tag,
            ratio=ratio,
            delete_after_ms=delete_after_ms,
        )

    def _delete_tagged_item(self, tag: str) -> None:
        self._canvas.delete_tagged_item(tag)

    def _load_frame(self) -> None:
        try:
            success, frame = self._camera.read()
            if not success or frame is None:
                if self._is_disabled and self._is_show_disabled:
                    return

                self._show_disabled_image()
                return

            self._show_captured_image(frame)

        except Exception as e:
            logger.error(f"Frame load error: {e}")

    def _show_disabled_image(self) -> None:
        self._is_disabled = True
        self._image = self._disabled_image
        self._update_canvas()
        self._is_show_disabled = True

    def _show_captured_image(self, frame: image.RawImage) -> None:
        self._is_disabled = False
        frame_rgb = image.bgr_to_rgb(frame)
        frame_resized = image.resize(frame_rgb, (self._width, self._height))
        self._image = ImageTk.PhotoImage(image=Image.fromarray(frame_resized))
        self._update_canvas()
        self._is_show_disabled = False

    def _on_fps_changed(self, *_: Any) -> None:
        self._next_frame_time = 1000 // self._fps.get()

    def _on_size_changed(self, *_: Any) -> None:
        if self._show_realtime.get():
            return
        self._resize()

    def _on_enable_lstick_mouse_changed(self, *_: Any) -> None:
        if self._enabled_lstick_mouse.get():
            self._bind_mouse_left()
        else:
            self._unbind_mouse_left()

    def _on_enable_rstick_mouse_changed(self, *_: Any) -> None:
        if self._enabled_rstick_mouse.get():
            self._bind_mouse_right()
        else:
            self._unbind_mouse_right()

    def _on_serial_data_format_changed(self, *_: Any) -> None:
        data_format = self._data_format.get()
        if data_format == "Default":
            self._controller = switch.SwitchController(self._serial)
            self._unbind_ctrl_mouse_right()
        if data_format == "Qingpi":
            self._controller = n3ds.N3dsController(self._serial, "qingpi")
            self._bind_ctrl_mouse_right()
        elif data_format == "3DS Controller":
            self._controller = n3ds.N3dsController(self._serial, "3ds controller")
            self._unbind_ctrl_mouse_right()

    def _resize(self) -> None:
        # change size properties
        new_size = self._parse_size()

        logger.info(f"Resizing canvas: ({self._width}, {self._height}) -> {new_size}")

        self._width, self._height = new_size
        self._update_ratio()
        # resize disabled image
        if (disabled_raw_image := self._disabled_raw_image) is not None:
            self._disabled_image = ImageTk.PhotoImage(
                image=Image.fromarray(image.resize(disabled_raw_image, new_size)),
            )
        else:
            self._disabled_image = ImageTk.PhotoImage()
        self._is_show_disabled = False

        logger.info("Deleting image item")
        self._canvas.delete(self._image_id)

        logger.info(f"Resizing canvas to {self._width}x{self._height}")
        self._canvas.config(width=self._width, height=self._height)
        logger.info("Canvas resized")

        self.update_idletasks()
        logger.info("update_idletasks complete")

        logger.info("Recreating image item")
        self._image = self._disabled_image
        self._image_id = self._canvas.create_image(
            0, 0, anchor=tk.NW, image=self._image
        )
        logger.info("Image item recreated")

    def _parse_size(self) -> tuple[int, int]:
        width, height = self._size.get().split("x")
        return int(width), int(height)

    def _update_canvas(self) -> None:
        if not self._is_resizing:
            self._canvas.itemconfig(self._image_id, image=self._image)

    def _update_ratio(self) -> None:
        self._ratio = (
            self._width / self.frame_size[0],
            self._height / self.frame_size[1],
        )

    def _on_ctrl_alt_mouse_left_pressed(self, event: tk.Event) -> None:
        self._on_select_area_pressed(event)

    def _on_ctrl_alt_mouse_left_pressing(self, event: tk.Event) -> None:
        self._on_select_area_pressing(event)

    def _on_ctrl_alt_mouse_left_released(self, event: tk.Event) -> None:
        cropped = self._on_select_area_released(event)
        if cropped is not None:
            filename = filedialog.asksaveasfilename(
                title="名前をつけて保存",
                filetypes=[("PNG", "*.png")],
                initialdir=str(self._runtime_info.base_dir / "Template"),
                defaultextension=".png",
            )
            if filename != "":
                logger.info(f"Saving cropped image to {filename!r}")
                image.write(
                    src=cropped,
                    path=filename,
                    params=(cv2.IMWRITE_PNG_COMPRESSION, 0),
                )
            else:
                logger.info("Canceled saving cropped image")

        self._delete_tagged_item("select_area")

        self._pressed_point = (0, 0)

        if self._enabled_lstick_mouse.get():
            self._bind_mouse_left()
        if self._enabled_rstick_mouse.get():
            self._bind_mouse_right()

    def _on_ctrl_shift_mouse_left_pressed(self, event: tk.Event) -> None:
        self._on_select_area_pressed(event)

    def _on_ctrl_shift_mouse_left_pressing(self, event: tk.Event) -> None:
        self._on_select_area_pressing(event)

    def _on_ctrl_shift_mouse_left_released(self, event: tk.Event) -> None:
        cropped = self._on_select_area_released(event)
        if cropped is not None:
            image.write(
                src=cropped,
                path=str(self._runtime_info.base_dir / "Captures" / "cropped.png"),
                params=(cv2.IMWRITE_PNG_COMPRESSION, 0),
            )

        self._delete_tagged_item("select_area")

        self._pressed_point = (0, 0)

        if self._enabled_lstick_mouse.get():
            self._bind_mouse_left()
        if self._enabled_rstick_mouse.get():
            self._bind_mouse_right()

    def _on_select_area_pressed(self, event: tk.Event) -> None:
        if self._camera.frame is None:
            logger.warning("Failed to get current frame")
            return

        if self._enabled_lstick_mouse.get():
            self._unbind_mouse_left()
        if self._enabled_rstick_mouse.get():
            self._unbind_mouse_right()

        x = clamp(event.x, 0, self._width)
        y = clamp(event.y, 0, self._height)
        self._pressed_point = (x, y)
        self._delete_tagged_item("select_area")
        self._draw_rect(
            self._pressed_point,
            self._pressed_point,
            outline="red",
            width=3.0,
            tag="select_area",
            ratio=(1.0, 1.0),
            delete_after_ms=None,
        )

        cx, cy = int(x / self._ratio[0]), int(y / self._ratio[1])
        logger.info(f"Start selecting area at ({x}, {y}) / Capture ({cx}, {cy})")

    def _on_select_area_pressing(self, event: tk.Event) -> None:
        x = clamp(event.x, 0, self._width)
        y = clamp(event.y, 0, self._height)
        self._canvas.coords(
            "select_area",
            self._pressed_point[0],
            self._pressed_point[1],
            x,
            y,
        )

    def _on_select_area_released(self, event: tk.Event) -> image.RawImage | None:
        if (current_frame := self._camera.frame) is None:
            logger.warning("Failed to get current frame")
            return None

        x = clamp(event.x, 0, self._width)
        y = clamp(event.y, 0, self._height)
        sx, sy = self._pressed_point
        ex, ey = x, y
        if sx > ex:
            sx, ex = ex, sx
        if sy > ey:
            sy, ey = ey, sy

        csx, csy = int(sx / self._ratio[0]), int(sy / self._ratio[1])
        cex, cey = int(ex / self._ratio[0]), int(ey / self._ratio[1])
        logger.info(f"End selecting area at ({ex}, {ey}) / Capture ({cex}, {cey})")

        if csx == cex or csy == cey:
            logger.warning("Selected area has no size")
            return None

        try:
            return image.crop(
                src=current_frame,
                args=image.ImageCropArgs(
                    sx=csx,
                    ex=cex,
                    sy=csy,
                    ey=cey,
                ),
            )
        except Exception as e:
            logger.error(f"Failed to crop capture: {e}")

        return None

    def _on_ctrl_mouse_left_pressed(self, event: tk.Event) -> None:
        current_frame = self._camera.frame
        if current_frame is None:
            logger.warning("Failed to get current frame")
            return

        if self._enabled_lstick_mouse.get():
            self._unbind_mouse_left()

        x, y = event.x, event.y
        fx, fy = int(x / self._ratio[0]), int(y / self._ratio[1])
        pixel = current_frame[fy, fx]
        logger.info(f"Mouse down: Show ({x}, {y}) / Capture ({fx}, {fy})")
        logger.info(f"Color [R: {pixel[0]}, G: {pixel[2]}, B: {pixel[1]}]")

    def _on_ctrl_mouse_left_released(self, event: tk.Event) -> None:
        if self._enabled_lstick_mouse.get():
            self._bind_mouse_left()

    def _on_ctrl_mouse_right_pressed(self, event: tk.Event) -> None:
        if self._enabled_rstick_mouse.get():
            self._unbind_mouse_right()
        if self._enabled_lstick_mouse.get():
            self._unbind_mouse_left()

        x = clamp(event.x, 0, self._width)
        y = clamp(event.y, 0, self._height)
        self._pressed_point = (x, y)
        self._delete_tagged_item("select_area")
        self._draw_rect(
            self._pressed_point,
            self._pressed_point,
            outline="red",
            width=3.0,
            tag="select_area",
            ratio=(1.0, 1.0),
            delete_after_ms=None,
        )

    def _on_ctrl_mouse_right_pressing(self, event: tk.Event) -> None:
        x = clamp(event.x, 0, self._width)
        y = clamp(event.y, 0, self._height)
        self._canvas.coords(
            "select_area",
            self._pressed_point[0],
            self._pressed_point[1],
            x,
            y,
        )

    def _on_ctrl_mouse_right_released(self, event: tk.Event) -> None:
        sx, sy = self._pressed_point
        ex = clamp(event.x, 0, self._width)
        ey = clamp(event.y, 0, self._height)
        if sx > ex:
            sx, ex = ex, sx
        if sy > ey:
            sy, ey = ey, sy

        logger.info(f"Touchscreen Area: (({sx}, {sy}), ({ex}, {ey}))")
        self._touchscreen_area = ((sx, sy), (ex, ey))
        self._delete_tagged_item("select_area")
        self._pressed_point = (0, 0)

        if self._enabled_rstick_mouse.get():
            self._bind_mouse_right()
        if self._enabled_lstick_mouse.get():
            self._bind_mouse_left()

    def _on_mouse_left_pressed(self, event: tk.Event) -> None:
        if not self._enabled_lstick_mouse.get():
            return

        if self._enabled_rstick_mouse.get():
            self._unbind_mouse_right()

        self._canvas.config(cursor="dot")
        pressed_point = (event.x, event.y)
        self._on_switch_mouse_pressed(pressed_point)
        self._init_mouse_log()

    def _on_mouse_left_pressing(self, event: tk.Event) -> None:
        if not self._enabled_lstick_mouse.get():
            return

        pressing_point = (event.x, event.y)
        self._on_switch_mouse_pressing(
            pressing_point,
            self._lstick,
        )

    def _on_mouse_left_released(self, event: tk.Event) -> None:
        if not self._enabled_lstick_mouse.get():
            return

        released_point = (event.x, event.y)
        self._on_switch_mouse_released(
            released_point,
            self._lstick,
        )
        self._finish_mouse_log(released_point)
        self._output_mouse_log()

        if self._enabled_rstick_mouse.get():
            self._bind_mouse_right()

    def _on_mouse_right_pressed(self, event: tk.Event) -> None:
        if not self._enabled_rstick_mouse.get():
            return

        if self._enabled_lstick_mouse.get():
            self._unbind_mouse_left()

        self._canvas.config(cursor="dot")
        pressed_point = (event.x, event.y)
        if self._right_stick_mode == "Qingpi":
            self._on_qingpi_mouse_pressed(pressed_point)
        else:
            self._on_switch_mouse_pressed(pressed_point)
            self._init_mouse_log()

    def _on_mouse_right_pressing(self, event: tk.Event) -> None:
        if not self._enabled_rstick_mouse.get():
            return

        pressing_point = (event.x, event.y)
        if self._right_stick_mode == "Qingpi":
            self._on_qingpi_mouse_pressed(pressing_point)
        else:
            if (rstick := self._lstick) is not None:
                self._on_switch_mouse_pressing(
                    pressing_point,
                    rstick,
                )

    def _on_mouse_right_released(self, event: tk.Event) -> None:
        if not self._enabled_rstick_mouse.get():
            return

        released_point = (event.x, event.y)

        if self._right_stick_mode == "Qingpi":
            self._on_qingpi_mouse_released()
        else:
            if (rstick := self._lstick) is not None:
                self._on_switch_mouse_released(
                    released_point,
                    rstick,
                )
            self._finish_mouse_log(released_point)
            self._output_mouse_log()

        if self._enabled_lstick_mouse.get():
            self._bind_mouse_left()

    def _bind_all(self) -> None:
        self._bind_ctrl_mouse_left()
        self._bind_ctrl_shift_mouse_left()
        self._bind_ctrl_alt_mouse_left()
        if self._data_format.get() == "Qingpi":
            self._bind_ctrl_mouse_right()
        if self._enabled_lstick_mouse.get():
            self._bind_mouse_left()
        if self._enabled_rstick_mouse.get():
            self._bind_mouse_right()

    def _bind_ctrl_shift_mouse_left(self) -> None:
        logger.debug("Binding mouse shift left click functions")
        self._canvas.bind(
            "<Control-Shift-ButtonPress-1>", self._on_ctrl_shift_mouse_left_pressed
        )
        self._canvas.bind(
            "<Control-Shift-ButtonRelease-1>", self._on_ctrl_shift_mouse_left_released
        )
        self._canvas.bind(
            "<Control-Shift-B1-Motion>", self._on_ctrl_shift_mouse_left_pressing
        )
        logger.debug("Bound mouse shift left click functions")

    def _bind_ctrl_alt_mouse_left(self) -> None:
        logger.debug("Binding ctrl alt mouse left click functions")
        if platform.is_macos():
            self._canvas.bind(
                "<Control-Option-ButtonPress-1>", self._on_ctrl_alt_mouse_left_pressed
            )
            self._canvas.bind(
                "<Control-Option-Button1-Motion>", self._on_ctrl_alt_mouse_left_pressing
            )
            self._canvas.bind(
                "<Control-Option-ButtonRelease-1>",
                self._on_ctrl_alt_mouse_left_released,
            )
        else:
            self._canvas.bind(
                "<Control-Alt-ButtonPress-1>", self._on_ctrl_alt_mouse_left_pressed
            )
            self._canvas.bind(
                "<Control-Alt-Button1-Motion>", self._on_ctrl_alt_mouse_left_pressing
            )
            self._canvas.bind(
                "<Control-Alt-ButtonRelease-1>", self._on_ctrl_alt_mouse_left_released
            )
        logger.debug("Bound ctrl alt mouse left click functions")

    def _bind_ctrl_mouse_right(self) -> None:
        logger.debug("Binding mouse ctrl right click functions")
        self._canvas.bind("<Control-ButtonPress-3>", self._on_ctrl_mouse_right_pressed)
        self._canvas.bind(
            "<Control-Button3-Motion>", self._on_ctrl_mouse_right_pressing
        )
        self._canvas.bind(
            "<Control-ButtonRelease-3>", self._on_ctrl_mouse_right_released
        )
        logger.debug("Bound mouse ctrl right click functions")

    def _unbind_ctrl_mouse_right(self) -> None:
        logger.debug("Binding mouse ctrl right click functions")
        self._canvas.unbind("<Control-ButtonPress-3>")
        self._canvas.unbind("<Control-Button3-Motion>")
        self._canvas.unbind("<Control-ButtonRelease-3>")
        logger.debug("Bound mouse ctrl right click functions")

    def _bind_ctrl_mouse_left(self) -> None:
        logger.debug("Binding mouse ctrl left click functions")
        self._canvas.bind("<Control-ButtonPress-1>", self._on_ctrl_mouse_left_pressed)
        self._canvas.bind(
            "<Control-ButtonRelease-1>", self._on_ctrl_mouse_left_released
        )
        logger.debug("Bound mouse ctrl left click functions")

    def _bind_mouse_left(self) -> None:
        logger.debug("Binding mouse left functions")
        self._canvas.bind("<ButtonPress-1>", self._on_mouse_left_pressed)
        self._canvas.bind("<Button1-Motion>", self._on_mouse_left_pressing)
        self._canvas.bind("<ButtonRelease-1>", self._on_mouse_left_released)
        logger.debug("Bound mouse left functions")

    def _unbind_mouse_left(self) -> None:
        logger.debug("Unbinding mouse left functions")
        self._canvas.unbind("<ButtonPress-1>")
        self._canvas.unbind("<Button1-Motion>")
        self._canvas.unbind("<ButtonRelease-1>")
        logger.debug("Unbound mouse left functions")

    def _bind_mouse_right(self) -> None:
        logger.debug("Binding mouse right functions")
        self._canvas.bind("<ButtonPress-3>", self._on_mouse_right_pressed)
        self._canvas.bind("<Button3-Motion>", self._on_mouse_right_pressing)
        self._canvas.bind("<ButtonRelease-3>", self._on_mouse_right_released)
        logger.debug("Bound mouse right functions")

    def _unbind_mouse_right(self) -> None:
        logger.debug("Unbinding mouse right functions")
        self._canvas.unbind("<ButtonPress-3>")
        self._canvas.unbind("<Button3-Motion>")
        self._canvas.unbind("<ButtonRelease-3>")
        logger.debug("Unbound mouse right functions")

    def _on_qingpi_mouse_pressed(self, pressed_point: tuple[int, int]) -> None:
        if isinstance((c := self._controller), switch.SwitchController):
            return

        (sx, sy), (ex, ey) = self._touchscreen_area
        if sx < pressed_point[0] < ex and sy < pressed_point[1] < ey:
            width, height = ex - sx, ey - sy
            _pos_x = int(320.0 * (pressed_point[0] - sx) / width)
            _pos_y = int(240.0 * (pressed_point[1] - sy) / height)
            c.touchscreen.touch(_pos_x, _pos_y)

    def _on_switch_mouse_pressed(self, pressed_point: tuple[int, int]) -> None:
        self._pressed_point = pressed_point
        radius = self._mouse_circle_radius
        self._draw_circle(
            pressed_point,
            radius,
            outline="cyan",
            tag="stick_circle_outer",
            ratio=(1.0, 1.0),
            delete_after_ms=None,
        )
        self._draw_circle(
            pressed_point,
            radius // 10,
            outline="cyan",
            tag="stick_circle_inner",
            ratio=(1.0, 1.0),
            delete_after_ms=None,
        )

    def _on_switch_mouse_pressing(
        self,
        pressing_point: tuple[int, int],
        stick_state: controller.StickState,
    ) -> None:
        pos = complex(
            pressing_point[0] - self._pressed_point[0],
            self._pressed_point[1] - pressing_point[1],
        )
        angle_rad = cmath.phase(pos)
        angle = math.degrees(angle_rad)
        mag = abs(pos) / self._mouse_circle_radius
        stick_state.tilt_by_polar(angle, mag)
        self._controller.send_state()

        circle_radius = self._mouse_circle_radius
        if mag >= 1.0:
            center_x = (circle_radius + circle_radius // 11) * math.cos(angle_rad)
            center_y = (circle_radius + circle_radius // 11) * math.sin(angle_rad)
            start_x = self._pressed_point[0] + center_x - circle_radius // 10
            end_x = self._pressed_point[0] + center_x + circle_radius // 10
            start_y = self._pressed_point[1] - center_y - circle_radius // 10
            end_y = self._pressed_point[1] - center_y + circle_radius // 10
        else:
            start_x = pressing_point[0] - circle_radius // 10
            start_y = pressing_point[1] - circle_radius // 10
            end_x = pressing_point[0] + circle_radius // 10
            end_y = pressing_point[1] + circle_radius // 10

        self._canvas.coords(
            "stick_circle_inner",
            start_x,
            start_y,
            end_x,
            end_y,
        )

        self._add_mouse_log(angle, mag)

    def _on_qingpi_mouse_released(self) -> None:
        if isinstance((c := self._controller), switch.SwitchController):
            return
        c.touchscreen.reset()

    def _on_switch_mouse_released(
        self,
        released_point: tuple[int, int],
        stick_state: controller.StickState,
    ) -> None:
        if not self._enabled_lstick_mouse.get():
            return

        self._canvas.config(cursor="tcross")
        stick_state.reset()
        self._controller.send_state()
        self._delete_tagged_item("stick_circle_outer")
        self._delete_tagged_item("stick_circle_inner")
        self._finish_mouse_log(released_point)

    def _init_mouse_log(self) -> None:
        if self._should_log_input:
            if self._input_logs is None:
                self._input_logs = deque()
            else:
                self._input_logs.clear()

            self._last_input_time = time.perf_counter()
            self._stick_angle = None
            self._stick_mag = None

    def _add_mouse_log(self, angle: float, mag: float) -> None:
        if self._should_log_input:
            if (logs := self._input_logs) is not None:
                current_input_time = time.perf_counter()
                if (last_input_time := self._last_input_time) is not None:
                    duration = current_input_time - last_input_time
                    logs.append((angle, mag, duration))
                    self._last_input_time = current_input_time
                    self._stick_angle = angle
                    self._stick_mag = mag

    def _finish_mouse_log(self, release_point: tuple[int, int]) -> None:
        if self._should_log_input:
            if (logs := self._input_logs) is not None:
                if (last_input_time := self._last_input_time) is not None:
                    pos = complex(
                        release_point[0] - self._pressed_point[0],
                        self._pressed_point[1] - release_point[1],
                    )
                    angle_rad = cmath.phase(pos)
                    angle = math.degrees(angle_rad)
                    mag = abs(pos) / self._mouse_circle_radius
                    logs.append((angle, mag, time.perf_counter() - last_input_time))

    def _output_mouse_log(self) -> None:
        if self._should_log_input:
            if (logs := self._input_logs) is not None:
                for log in logs:
                    logger.debug(",".join(str(v) for v in log))
                self._input_logs = None
