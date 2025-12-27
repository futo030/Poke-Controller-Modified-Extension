from pokecontrollerext.api.v0_1_8.command.commands.base import Command
from pokecontrollerext.papico.context import (
    PapicoExecContext,
    PapicoFailure,
    PapicoResult,
    PapicoSuccess,
)
from pokecontrollerext.papico.exception import (
    PapicoExecException,
)
from pokecontrollerext.papico.handlers.handler import (
    PapicoHandler,
)
from pokecontrollerext.singletons.app.settings import get_app_settings
from pokecontrollerext.singletons.runtime.app_info import get_app_info
from pokecontrollerext.singletons.runtime.runtime_info import (
    get_app_runtime_info,
)
from pokecontrollerext.singletons.widget.catalog import (
    get_app_widget_catalog,
)


class PapicoCommandInitializeHandler(PapicoHandler):
    _registered_trace = False

    def handle(self, ctx: PapicoExecContext) -> PapicoResult[None]:
        try:
            self._initialize_base_command()
            if not PapicoCommandInitializeHandler._registered_trace:
                self._register_traces()
                PapicoCommandInitializeHandler._registered_trace = True
            return PapicoSuccess(ctx=ctx, data=None)
        except Exception as e:
            return PapicoFailure(
                ctx=ctx,
                error=PapicoExecException(f"{e}"),
            )

    def _initialize_base_command(self) -> None:
        app_info = get_app_info()
        app_widget_catalog = get_app_widget_catalog()
        app_settings = get_app_settings()
        app_runtime_info = get_app_runtime_info()

        Command.text_area_1 = app_widget_catalog.outputs.textarea1
        Command.text_area_2 = app_widget_catalog.outputs.textarea2
        Command.stdout_destination = str(app_settings.widget.output.stdout.get())
        dialog_confirm_buttons_position = (
            app_settings.widget.dialog.confirm_buttons_position.get()
        )
        if dialog_confirm_buttons_position == "top":
            Command.pos_dialogue_buttons = "1"
        elif dialog_confirm_buttons_position == "bottom":
            Command.pos_dialogue_buttons = "2"
        else:
            Command.pos_dialogue_buttons = "3"
        Command.canvas = app_widget_catalog.capture.canvas
        Command.isGuide = app_settings.capture.show_guide.get()
        Command.isSimilarity = app_settings.capture.show_matched.get()
        Command.isImage = False
        Command.isWinNotStart = app_settings.notification.windows.enabled_started.get()
        Command.isWinNotEnd = app_settings.notification.windows.enabled_ended.get()
        Command.isLineNotStart = app_settings.notification.line.enabled_started.get()
        Command.isLineNotEnd = app_settings.notification.line.enabled_ended.get()
        Command.isDiscordNotStart = (
            app_settings.notification.discord.enabled_started.get()
        )
        Command.isDiscordNotEnd = app_settings.notification.discord.enabled_ended.get()
        Command.app_name = app_info.name
        Command.profilename = app_runtime_info.profile

    def _register_traces(self) -> None:
        app_settings = get_app_settings()

        def _on_stdout_changed(*_: str) -> None:
            Command.stdout_destination = str(app_settings.widget.output.stdout.get())

        def _on_pos_dialogue_buttons_changed(*_: str) -> None:
            dialog_confirm_buttons_position = (
                app_settings.widget.dialog.confirm_buttons_position.get()
            )
            if dialog_confirm_buttons_position == "top":
                Command.pos_dialogue_buttons = "1"
            elif dialog_confirm_buttons_position == "bottom":
                Command.pos_dialogue_buttons = "2"
            else:
                Command.pos_dialogue_buttons = "3"

        def _on_is_guide_changed(*_: str) -> None:
            Command.isGuide = app_settings.capture.show_guide.get()

        def _on_is_similarity_changed(*_: str) -> None:
            Command.isSimilarity = app_settings.capture.show_matched.get()

        def _on_is_win_not_start(*_: str) -> None:
            Command.isWinNotStart = (
                app_settings.notification.windows.enabled_started.get()
            )

        def _on_is_win_not_end(*_: str) -> None:
            Command.isWinNotEnd = app_settings.notification.windows.enabled_ended.get()

        def _on_is_line_not_start(*_: str) -> None:
            Command.isLineNotStart = (
                app_settings.notification.line.enabled_started.get()
            )

        def _on_is_line_not_end(*_: str) -> None:
            Command.isLineNotEnd = app_settings.notification.line.enabled_ended.get()

        def _on_is_discord_not_start(*_: str) -> None:
            Command.isDiscordNotStart = (
                app_settings.notification.discord.enabled_started.get()
            )

        def _on_is_discord_not_end(*_: str) -> None:
            Command.isDiscordNotEnd = (
                app_settings.notification.discord.enabled_ended.get()
            )

        app_settings.widget.output.stdout.trace_add("write", _on_stdout_changed)
        app_settings.widget.dialog.confirm_buttons_position.trace_add(
            "write", _on_pos_dialogue_buttons_changed
        )
        app_settings.capture.show_guide.trace_add("write", _on_is_guide_changed)
        app_settings.capture.show_matched.trace_add("write", _on_is_similarity_changed)
        app_settings.notification.windows.enabled_started.trace_add(
            "write", _on_is_win_not_start
        )
        app_settings.notification.windows.enabled_ended.trace_add(
            "write", _on_is_win_not_end
        )
        app_settings.notification.line.enabled_started.trace_add(
            "write", _on_is_line_not_start
        )
        app_settings.notification.line.enabled_ended.trace_add(
            "write", _on_is_line_not_end
        )
        app_settings.notification.discord.enabled_started.trace_add(
            "write", _on_is_discord_not_start
        )
        app_settings.notification.discord.enabled_ended.trace_add(
            "write", _on_is_discord_not_end
        )
