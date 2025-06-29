import pytest
from server import app as flask_app
from server import socketio

@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    # Note: We will need to add extensive mocking here later on,
    # especially for AppleScript subprocess calls and file system access.
    yield flask_app

@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture
def socketio_client(app, client):
    """A test client for the socketio server."""
    return socketio.test_client(app, flask_test_client=client) 