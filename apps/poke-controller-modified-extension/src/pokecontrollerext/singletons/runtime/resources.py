from pokecontroller.core.camera import Camera
from pokecontroller.core.serial import Serial

from pokecontrollerext.app.exception import AppRuntimeException
from pokecontrollerext.app.resources import AppResources

_app_resources: AppResources | None = None


def get_app_resources() -> AppResources:
    global _app_resources
    if _app_resources is None:
        raise AppRuntimeException("App resources is not initialized.")
    return _app_resources


def setup_app_resources(
    camera: Camera,
    serial: Serial,
) -> AppResources:
    global _app_resources
    _app_resources = AppResources(
        camera=camera,
        serial=serial,
    )
    return _app_resources
