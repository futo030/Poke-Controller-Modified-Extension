from dataclasses import dataclass

from pokecontroller.core.camera import Camera
from pokecontroller.core.serial import Serial


@dataclass(kw_only=True, frozen=True)
class AppResources:
    camera: Camera
    serial: Serial
