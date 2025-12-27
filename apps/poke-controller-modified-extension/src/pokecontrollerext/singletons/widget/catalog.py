from pokecontrollerext.widgets.catalog import (
    AppWidgetCatalog,
    CaptureWidgetCatalog,
    OutputsWidgetCatalog,
    WindowWidgetCatalog,
)

_app_widget_catalog = AppWidgetCatalog(
    outputs=OutputsWidgetCatalog(),
    capture=CaptureWidgetCatalog(),
    window=WindowWidgetCatalog(),
)


def get_app_widget_catalog() -> AppWidgetCatalog:
    global _app_widget_catalog
    return _app_widget_catalog
