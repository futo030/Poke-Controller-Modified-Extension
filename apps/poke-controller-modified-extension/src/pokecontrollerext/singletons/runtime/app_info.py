from pathlib import Path

from pokecontrollerext.app.info import AppInfo

_app_info = AppInfo(
    name="Poke-Controller Modified Extension",
    version="0.2.0",
    latest_settings_version="0.2.0",
    latest_api_version="0.2.0",
    application_root=Path(__file__).parent.parent.parent.parent.parent,
)


def get_app_info() -> AppInfo:
    global _app_info
    return _app_info
