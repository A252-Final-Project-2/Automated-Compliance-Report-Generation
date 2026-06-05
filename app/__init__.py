try:
    from .module3.app import app
except ImportError as exc:
    raise ImportError("Failed to import module3 app from the app package") from exc


def create_app():
    return app