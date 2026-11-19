from fastapi import FastAPI

from app import __version__
from app.main import create_app


def test_create_app_returns_fastapi_instance():
    app = create_app()

    assert isinstance(app, FastAPI)
    assert app.version == __version__
