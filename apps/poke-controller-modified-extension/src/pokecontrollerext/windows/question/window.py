import tkinter as tk
import tkinter.messagebox as mb
import tkinter.scrolledtext as st
from typing import Any

from pokecontrollerext.app.translation import t
from pokecontrollerext.singletons.app.command import get_app_command_state
from pokecontrollerext.singletons.app.model import get_app_model
from pokecontrollerext.singletons.app.settings import get_app_settings
from pokecontrollerext.singletons.runtime.runtime_info import get_app_runtime_info
from pokecontrollerext.singletons.widget.catalog import get_app_widget_catalog
from pokecontrollerext.widgets.button import Button
from pokecontrollerext.widgets.frame import Frame
from pokecontrollerext.widgets.label import Label
from pokecontrollerext.widgets.separator import Separator
from pokecontrollerext.widgets.window import Window


class QuestionWindow(Window):
    _content_text: st.ScrolledText
    _attempt_text: st.ScrolledText

    def __init__(
        self,
        master: tk.Misc,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, *args, **kwargs)
        self.title(t("question.title"))

        self._runtime_info = get_app_runtime_info()
        self._settings = get_app_settings()
        self._model = get_app_model()
        self._widget_catalog = get_app_widget_catalog()

        self._command_state = get_app_command_state()
        self._selected_command_info = self._command_state.selected_command_info

        self._stdout = self._settings.widget.output.stdout

        if (info := self._selected_command_info) is not None:
            self._program = tk.StringVar(value=info.display_name)
        else:
            self._program = tk.StringVar()
        self._author = tk.StringVar()

        self.build_ui()

    def build_ui(self) -> None:
        frame = Frame(self)

        # title
        description_label = Label(frame, text=t("question.description"))
        description_label.pack(expand=True, anchor=tk.CENTER, padx=5, pady=5)

        # program
        label_width = 18
        program_frame = Frame(frame)
        program_label = Label(
            program_frame,
            width=label_width,
            text=t("question.program"),
        )
        program_entry = tk.Entry(program_frame, textvariable=self._program)
        program_label.pack(side=tk.LEFT)
        program_entry.pack(side=tk.LEFT, expand=True, fill=tk.X)
        program_frame.pack(expand=True, fill=tk.X, padx=2, pady=2)

        # author
        author_frame = Frame(frame)
        author_label = Label(
            author_frame,
            width=label_width,
            text=t("question.author"),
        )
        author_entry = tk.Entry(author_frame, textvariable=self._author)
        author_label.pack(side=tk.LEFT)
        author_entry.pack(side=tk.LEFT, expand=True, fill=tk.X)
        author_frame.pack(expand=True, fill=tk.X, padx=2, pady=2)

        # content
        content_frame = Frame(frame)
        content_label = Label(
            content_frame,
            width=label_width,
            text=t("question.content"),
        )
        self._content_text = st.ScrolledText(content_frame)
        content_label.pack(side=tk.LEFT)
        self._content_text.pack(side=tk.LEFT, expand=True, fill=tk.X)
        content_frame.pack(expand=True, fill=tk.X, padx=2, pady=2)

        # attempt
        attempt_frame = Frame(frame)
        attempt_label = Label(
            attempt_frame,
            width=label_width,
            text=t("question.attempt"),
        )
        self._attempt_text = st.ScrolledText(attempt_frame)
        attempt_label.pack(side=tk.LEFT)
        self._attempt_text.pack(side=tk.LEFT, expand=True, fill=tk.X)
        attempt_frame.pack(expand=True, fill=tk.X, padx=2, pady=2)

        Separator(frame, orient=tk.HORIZONTAL).pack(
            expand=True, fill=tk.X, padx=5, pady=5
        )

        # ok/cancel buttons
        buttons_row = Frame(frame)
        ok_button = Button(buttons_row, text="OK", command=self._on_ok_pressed)
        cancel_button = Button(
            buttons_row, text="Cancel", command=self._on_cancel_pressed
        )
        ok_button.pack(side=tk.RIGHT, padx=4)
        cancel_button.pack(side=tk.RIGHT, padx=4)
        buttons_row.pack(expand=True, padx=5, pady=(10, 4))

        frame.pack(expand=True, fill=tk.BOTH)

    def _on_ok_pressed(self) -> None:
        if not self._validate_inputs():
            return

        outputs = (
            t("question.separator.start"),
            f"■{t('question.program')}",
            self._program.get(),
            f"■{t('question.author')}",
            self._author.get(),
            f"■{t('question.content')}",
            self._content_text.get("1.0", tk.END),
            f"■{t('question.attempt')}",
            self._attempt_text.get("1.0", tk.END),
            t("question.separator.end"),
        )
        self._widget_catalog.outputs.append_line(
            textarea_id=self._stdout.get(),
            text="\n".join(outputs),
        )

        mb.showinfo(title=t("question.title"), message=t("question.message.finish"))

        self.destroy()

    def _on_cancel_pressed(self) -> None:
        self.destroy()

    def _validate_inputs(self) -> bool:
        program = self._program.get()
        if not program:
            mb.showerror(
                title=t("question.title"), message=t("question.message.empty_program")
            )
            return False

        author = self._author.get()
        if not author:
            mb.showerror(
                title=t("question.title"), message=t("question.message.empty_author")
            )
            return False

        content = self._content_text.get("1.0", tk.END)
        if not content:
            mb.showerror(
                title=t("question.title"), message=t("question.message.empty_content")
            )
            return False

        attempt = self._attempt_text.get("1.0", tk.END)
        if not attempt:
            mb.showerror(
                title=t("question.title"), message=t("question.message.empty_attempt")
            )
            return False

        return True
