from pokecontrollerext.app.exception import AppRuntimeException
from pokecontrollerext.papico import Papico

_papico: Papico | None = None


def setup_papico() -> Papico:
    global _papico
    _papico = Papico()
    return _papico


def get_papico() -> Papico:
    global _papico
    if _papico is None:
        raise AppRuntimeException("Papico is not initialized.")
    return _papico
