import json
from pathlib import Path
from tkinter import BooleanVar, DoubleVar, IntVar, StringVar
from typing import Any

from pokecontrollerext.app.settings import (
    DEFAULT,
    AppSettings,
)
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


class PapicoSettingsLoadHandler(PapicoHandler):
    _path: Path | None
    _settings: dict[str, Any]
    _tk_variables: dict[str, Any]

    def handle(self, ctx: PapicoExecContext) -> PapicoResult[AppSettings]:
        try:
            if (params := ctx.params) is None or "path" not in params:
                self._path = None
            else:
                self._path = params["path"]
            self._settings = self._load_settings()
            self._fill_by_default()
            self._tk_variables = self._value_to_tk_variables()
            return PapicoSuccess(
                ctx=ctx,
                data=AppSettings.from_dict(self._tk_variables),
            )
        except Exception as e:
            return PapicoFailure(
                ctx=ctx,
                error=PapicoExecException(f"{e}"),
            )

    def _load_settings(self) -> dict[str, Any]:
        if (p := self._path) is None or not p.exists():
            return {}
        default_settings: dict[str, Any] = json.loads(
            p.read_text(encoding="utf-8-sig"),
        )
        return default_settings

    def _fill_by_default(self) -> None:
        def assign_default(data: dict[str, Any], default: dict[str, Any]) -> None:
            for k, v in default.items():
                if isinstance(v, dict):
                    data.setdefault(k, {})
                    assign_default(data[k], v)
                else:
                    data.setdefault(k, v)

        assign_default(self._settings, DEFAULT)

    def _value_to_tk_variables(self) -> dict[str, Any]:
        def to_tk_variables(data: dict[str, Any], res: dict[str, Any]) -> None:
            for k, v in data.items():
                if isinstance(v, dict):
                    d = res.setdefault(k, {})
                    to_tk_variables(v, d)
                elif v is True or v is False:
                    res[k] = BooleanVar(value=v)
                elif isinstance(v, int):
                    res[k] = IntVar(value=v)
                elif isinstance(v, float):
                    res[k] = DoubleVar(value=v)
                elif isinstance(v, str):
                    res[k] = StringVar(value=v)
                else:
                    raise PapicoExecException(f"unsupported type: {v}({type(v)})")

        result: dict[str, Any] = {}
        to_tk_variables(self._settings, result)
        return result
