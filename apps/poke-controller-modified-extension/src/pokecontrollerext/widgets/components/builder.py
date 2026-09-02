import tkinter as tk
import tkinter.ttk as ttk
from typing import Any, Callable, Literal, Protocol, Self, overload

from pokecontrollerext.widgets.button import Button
from pokecontrollerext.widgets.checkbutton import Checkbutton
from pokecontrollerext.widgets.combobox import Combobox
from pokecontrollerext.widgets.entry import Entry
from pokecontrollerext.widgets.frame import Frame
from pokecontrollerext.widgets.label import Label
from pokecontrollerext.widgets.labelframe import Labelframe
from pokecontrollerext.widgets.radiobutton import Radiobutton
from pokecontrollerext.widgets.scale import Scale
from pokecontrollerext.widgets.scrollable_frame import ScrollableFrame
from pokecontrollerext.widgets.spinbox import Spinbox


class Refreshable(Protocol):
    def refresh(self) -> None: ...


class TraceRegisterable(Protocol):
    def register_trace(
        self,
        mode: Literal["write"],
        variable: tk.Variable,
        callback: Callable[[str, str, str], None],
    ) -> None: ...

    def register_refreshable(self, refreshable: Refreshable) -> None: ...


class ComponentRowBuilder[T: TraceRegisterable]:
    def __init__(
        self,
        caller: T,
        container: Frame | Labelframe | ScrollableFrame,
    ) -> None:
        self._caller = caller
        self._container = container
        if isinstance(container, ScrollableFrame):
            self._master: ttk.Widget = container.scrollable_frame
        else:
            self._master = container

    def add_button(
        self,
        text: str,
        command: Callable[[], Any],
        disabled: tk.BooleanVar | None = None,
        tooltip: str | None = None,
    ) -> Self:
        button = Button(self._master, text=text, command=command, tooltip=tooltip)
        button.pack(side=tk.LEFT)
        if disabled is not None:
            button.configure(state=tk.DISABLED if disabled.get() else tk.NORMAL)
            self._register_disable_trace(button, disabled)
        return self

    def add_checkbutton(
        self,
        variable: tk.BooleanVar,
        text: str,
        disabled: tk.BooleanVar | None = None,
        tooltip: str | None = None,
    ) -> Self:
        checkbutton = Checkbutton(
            self._master, variable=variable, text=text, tooltip=tooltip
        )
        checkbutton.pack(side=tk.LEFT)
        if disabled is not None:
            checkbutton.configure(state=tk.DISABLED if disabled.get() else tk.NORMAL)
            self._register_disable_trace(checkbutton, disabled)
        return self

    def add_combobox(
        self,
        variable: tk.IntVar | tk.StringVar,
        values: list[str],
        disabled: tk.BooleanVar | None = None,
        tooltip: str | None = None,
    ) -> Self:
        combobox = Combobox(
            self._master, textvariable=variable, values=values, tooltip=tooltip
        )
        combobox.pack(side=tk.LEFT)
        if disabled is not None:
            combobox.configure(state=tk.DISABLED if disabled.get() else tk.NORMAL)
            self._register_disable_trace(combobox, disabled)
        return self

    def add_entry(
        self,
        variable: tk.StringVar,
        disabled: tk.BooleanVar | None = None,
        tooltip: str | None = None,
    ) -> Self:
        entry = Entry(self._master, textvariable=variable, tooltip=tooltip)
        entry.pack(side=tk.LEFT)
        if disabled is not None:
            entry.configure(state=tk.DISABLED if disabled.get() else tk.NORMAL)
            self._register_disable_trace(entry, disabled)
        return self

    @overload
    def add_label(
        self,
        *,
        variable: tk.StringVar,
        width: int | None = None,
        tooltip: str | None = None,
    ) -> Self: ...

    @overload
    def add_label(
        self, *, text: str, width: int | None = None, tooltip: str | None = None
    ) -> Self: ...

    def add_label(
        self,
        *,
        variable: tk.StringVar | None = None,
        text: str | None = None,
        width: int | None = None,
        tooltip: str | None = None,
    ) -> Self:
        if variable is not None:
            label = Label(self._master, textvariable=variable, tooltip=tooltip)
        elif text is not None:
            label = Label(self._master, text=text, tooltip=tooltip)
        else:
            raise ValueError("Either variable or text must be specified.")
        if width is not None:
            label.configure(width=width)
        label.pack(side=tk.LEFT)
        return self

    def add_radiobutton(
        self,
        variable: tk.StringVar,
        values: list[str],
        tooltips: list[str] | None = None,
    ) -> Self:
        if tooltips is not None and len(tooltips) == len(values):
            for value, tooltip in zip(values, tooltips):
                Radiobutton(
                    self._master, variable=variable, value=value, tooltip=tooltip
                ).pack(side=tk.LEFT)
        else:
            for value in values:
                Radiobutton(self._master, variable=variable, value=value).pack(
                    side=tk.LEFT
                )
        return self

    @overload
    def add_scale(
        self,
        variable: tk.IntVar,
        from_: int,
        to: int,
        expand: bool = False,
        disabled: tk.BooleanVar | None = None,
        tooltip: str | None = None,
    ) -> Self: ...

    @overload
    def add_scale(
        self,
        variable: tk.DoubleVar,
        from_: float,
        to: float,
        expand: bool = False,
        disabled: tk.BooleanVar | None = None,
        tooltip: str | None = None,
    ) -> Self: ...

    def add_scale(
        self,
        variable: tk.IntVar | tk.DoubleVar,
        from_: int | float,
        to: int | float,
        expand: bool = False,
        disabled: tk.BooleanVar | None = None,
        tooltip: str | None = None,
    ) -> Self:
        scale = Scale(
            self._master,
            variable=variable,
            from_=from_,
            to=to,
            tooltip=tooltip,
        )
        if disabled is not None:
            scale.configure(state=tk.DISABLED if disabled.get() else tk.NORMAL)
            self._register_disable_trace(scale, disabled)
        if expand:
            scale.pack(side=tk.LEFT, expand=expand, fill=tk.X)
        else:
            scale.pack(side=tk.LEFT)
        return self

    def add_spinbox(
        self,
        variable: tk.IntVar,
        to: int,
        from_: int,
        increment: int = 1,
        disabled: tk.BooleanVar | None = None,
        tooltip: str | None = None,
    ) -> Self:
        spinbox = Spinbox(
            self._master,
            textvariable=variable,
            to=to,
            from_=from_,
            increment=increment,
            tooltip=tooltip,
        )
        if disabled is not None:
            spinbox.configure(state=tk.DISABLED if disabled.get() else tk.NORMAL)
            self._register_disable_trace(spinbox, disabled)
        spinbox.pack(side=tk.LEFT)
        return self

    def add_frame_row(self) -> "ComponentRowBuilder[Self]":
        return ComponentRowBuilder(self, Frame(self._master))

    def add_labelframe_row(self, label: str) -> "ComponentRowBuilder[Self]":
        return ComponentRowBuilder(self, Labelframe(self._master, text=label))

    def add_scrollable_frame_row(self) -> "ComponentRowBuilder[Self]":
        container = ScrollableFrame(self._master)
        self._caller.register_refreshable(container)
        return ComponentRowBuilder(self, container)

    def end(self) -> T:
        self._container.pack(expand=False, side=tk.TOP, fill=tk.BOTH)
        return self._caller

    def register_trace(
        self,
        mode: Literal["write"],
        variable: tk.Variable,
        callback: Callable[[str, str, str], None],
    ) -> None:
        self._caller.register_trace(mode, variable, callback)

    def _register_disable_trace(
        self,
        widget: ttk.Widget,
        disabled: tk.BooleanVar,
    ) -> None:
        self._caller.register_trace(
            "write",
            disabled,
            lambda *_: widget.configure(  # type: ignore[call-arg]
                state=tk.DISABLED if disabled.get() else tk.NORMAL,
            ),
        )

    def register_refreshable(self, refreshable: Refreshable) -> None:
        self._caller.register_refreshable(refreshable)


class ComponentBuilder:
    _container: Frame | Labelframe | ScrollableFrame | None

    def __init__(self, master: Frame | Labelframe | ScrollableFrame) -> None:
        self._master = master
        self._container = None
        self._refreshables: list[Refreshable] = []

    def refresh(self) -> None:
        for refreshable in self._refreshables:
            refreshable.refresh()

    def add_frame_row(self) -> ComponentRowBuilder[Self]:
        self._container = Frame(self._master)
        return ComponentRowBuilder(self, self._container)

    def add_labelframe_row(self, label: str) -> ComponentRowBuilder[Self]:
        self._container = Labelframe(self._master, text=label)
        return ComponentRowBuilder(self, self._container)

    def add_scrollable_frame_row(self) -> ComponentRowBuilder[Self]:
        self._container = ScrollableFrame(self._master)
        self._refreshables.append(self._container)
        return ComponentRowBuilder(self, self._container)

    def build(self) -> Frame | Labelframe | ScrollableFrame:
        if self._container is None:
            return self._master
        self._container.update_idletasks()
        return self._container

    def register_trace(
        self,
        mode: Literal["write"],
        variable: tk.Variable,
        callback: Callable[[str, str, str], None],
    ) -> None:
        self._master.register_trace(mode, variable, callback)

    def register_refreshable(self, refreshable: Refreshable) -> None:
        self._refreshables.append(refreshable)
