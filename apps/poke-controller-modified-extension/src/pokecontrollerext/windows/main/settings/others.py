import tkinter as tk
from typing import Any

from pokecontrollerext.app.translation import t
from pokecontrollerext.singletons.app.model import get_app_model
from pokecontrollerext.singletons.app.settings import get_app_settings
from pokecontrollerext.singletons.widget.catalog import (
    get_app_widget_catalog,
)
from pokecontrollerext.widgets.button import Button
from pokecontrollerext.widgets.checkbutton import Checkbutton
from pokecontrollerext.widgets.frame import Frame
from pokecontrollerext.widgets.labelframe import Labelframe
from pokecontrollerext.widgets.radiobutton import Radiobutton
from pokecontrollerext.widgets.scale import Scale


class OthersSettings(Frame):
    def __init__(self, master: tk.Misc, *args: Any, **kwargs: Any) -> None:
        super().__init__(master, *args, **kwargs)

        self._app_settings = get_app_settings()
        self._app_model = get_app_model()
        self._widget_catalog = get_app_widget_catalog()

        self._output_size = self._app_settings.widget.output.size_balance
        self._output_stdout = self._app_settings.widget.output.stdout
        self._output1_visibility = self._app_settings.widget.output.visible_output1
        self._output2_visibility = self._app_settings.widget.output.visible_output2
        self._software_controller_visibility = (
            self._app_settings.widget.software_controller.visible
        )
        self._software_controller_position = (
            self._app_settings.widget.software_controller.position
        )
        self._confirm_dialogue_buttons_position = (
            self._app_settings.widget.dialog.confirm_buttons_position
        )

        self.build_ui()

    def build_ui(self) -> None:
        upper_frame = Labelframe(self, text="Output Settings")
        size_adjuster = self._build_size_adjuster(upper_frame)
        standard_output_destination_settings = self._build_stdout_settings(upper_frame)
        clear_outputs = self._build_clear_outputs(upper_frame)

        lower_frame = Labelframe(self, text="Widget Settings")
        widget_mode = self._build_widget_mode(lower_frame)
        software_controller_position_settings = (
            self._build_software_controller_position_settings(lower_frame)
        )
        dialogue_confirm_buttons_position_settings = (
            self._build_dialogue_confirm_buttons_position_settings(lower_frame)
        )

        # Layout
        size_adjuster.pack(expand=True, fill=tk.X, side=tk.LEFT, padx=4, pady=4)
        standard_output_destination_settings.pack(
            expand=False,
            fill=tk.BOTH,
            side=tk.LEFT,
            padx=7,
            pady=4,
        )
        clear_outputs.pack(expand=False, fill=tk.X, side=tk.LEFT, padx=4, pady=4)
        upper_frame.pack(expand=False, fill=tk.X, side=tk.TOP, padx=4, pady=4)

        widget_mode.pack(
            expand=False,
            fill=tk.X,
            side=tk.LEFT,
            anchor=tk.CENTER,
            padx=4,
            pady=4,
        )
        software_controller_position_settings.pack(
            expand=False,
            fill=tk.NONE,
            side=tk.LEFT,
            anchor=tk.CENTER,
            padx=7,
            pady=4,
        )
        dialogue_confirm_buttons_position_settings.pack(
            expand=False,
            fill=tk.X,
            side=tk.LEFT,
            padx=4,
            pady=4,
        )
        lower_frame.pack(expand=False, fill=tk.X, side=tk.TOP, padx=4, pady=4)

    def _build_size_adjuster(self, master: tk.Misc) -> Labelframe:
        tid_prefix = "main.settings.others.output.size_adjuster"
        labelframe = Labelframe(
            master,
            text=t(f"{tid_prefix}"),
        )

        # Size
        size_scale = Scale(
            labelframe,
            tooltip=t(f"{tid_prefix}.tooltip"),
            length=200,
            orient=tk.HORIZONTAL,
            from_=1,
            to=99,
            variable=self._output_size,
        )

        # Layout
        size_scale.pack(
            expand=True,
            fill=tk.X,
            side=tk.LEFT,
            anchor=tk.CENTER,
            padx=4,
            pady=(5, 12),
        )

        return labelframe

    def _build_stdout_settings(self, master: tk.Misc) -> Labelframe:
        labelframe = Labelframe(master, text="Standard Output")

        # Destinations
        tid_prefix = "main.settings.others.output.stdout"
        stdout_radiobuttons = [
            Radiobutton(
                labelframe,
                text=t(f"{tid_prefix}.{i}"),
                tooltip=t(f"{tid_prefix}.{i}.tooltip"),
                value=i,
                variable=self._output_stdout,
            )
            for i in range(1, 3)
        ]

        # Layout
        for radiobutton in stdout_radiobuttons:
            radiobutton.pack(expand=False, fill=tk.X, side=tk.LEFT, padx=4)

        return labelframe

    def _build_clear_outputs(self, master: tk.Misc) -> Labelframe:
        labelframe = Labelframe(master, text="Clear")

        # Outputs Clear Buttons
        tid_prefix = "main.settings.others.output.clear"
        buttons = [
            Button(
                labelframe,
                text=t(f"{tid_prefix}.{i}"),
                tooltip=t(f"{tid_prefix}.{i}"),
                command=lambda i=i: self._on_clear_pressed(textarea_id=i),
            )
            for i in [1, 2]
        ]

        # Layout
        for button in buttons:
            button.pack(expand=False, fill=tk.X, side=tk.LEFT, padx=4, pady=(3, 5))

        return labelframe

    def _build_widget_mode(self, master: tk.Misc) -> Labelframe:
        labelframe = Labelframe(master, text="Display")

        # Widget Mode Checkbuttons
        tid_prefix = "main.settings.others.widget.display"
        checkbuttons = [
            Checkbutton(
                labelframe,
                text=text,
                tooltip=tooltip,
                variable=var,
            )
            for text, tooltip, var in [
                (
                    t(f"{tid_prefix}.output1"),
                    t(f"{tid_prefix}.output1.tooltip"),
                    self._output1_visibility,
                ),
                (
                    t(f"{tid_prefix}.output2"),
                    t(f"{tid_prefix}.output2.tooltip"),
                    self._output2_visibility,
                ),
                (
                    t(f"{tid_prefix}.software_controller"),
                    t(f"{tid_prefix}.software_controller.tooltip"),
                    self._software_controller_visibility,
                ),
            ]
        ]

        # Layout
        for checkbutton in checkbuttons:
            checkbutton.pack(expand=False, fill=tk.X, side=tk.LEFT, padx=4, pady=4)

        return labelframe

    def _build_software_controller_position_settings(
        self,
        master: tk.Misc,
    ) -> Labelframe:
        labelframe = Labelframe(master, text="Software-Controller Position")

        # Positions
        tid_prefix = "main.settings.others.widget.software_controller"
        position_radiobuttons = [
            Radiobutton(
                labelframe,
                text=t(f"{tid_prefix}.{value}"),
                tooltip=t(f"{tid_prefix}.{value}.tooltip"),
                value=value,
                variable=self._software_controller_position,
            )
            for value in ["top", "bottom"]
        ]

        # Layout
        for radiobutton in position_radiobuttons:
            radiobutton.pack(expand=False, fill=tk.X, side=tk.LEFT, padx=4, pady=4)

        return labelframe

    def _build_dialogue_confirm_buttons_position_settings(
        self,
        master: tk.Misc,
    ) -> Labelframe:
        labelframe = Labelframe(master, text="Dialogue OK/Cancel Position")

        # Positions
        tid_prefix = "main.settings.others.widget.dialog.confirm_buttons_position"
        position_radiobuttons = [
            Radiobutton(
                labelframe,
                text=t(f"{tid_prefix}.{value}"),
                tooltip=t(f"{tid_prefix}.{value}.tooltip"),
                value=value,
                variable=self._confirm_dialogue_buttons_position,
            )
            for value in ["top", "bottom", "both"]
        ]

        # Layout
        for radiobutton in position_radiobuttons:
            radiobutton.pack(expand=False, fill=tk.X, side=tk.LEFT, padx=4, pady=4)

        return labelframe

    def _on_clear_pressed(self, textarea_id: int) -> None:
        self._widget_catalog.outputs.clear(textarea_id=textarea_id)
