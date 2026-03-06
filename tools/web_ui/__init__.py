"""Web UI package — gallery mode + live real-time demo dashboard."""
from tools.web_ui.app import make_app
from tools.web_ui.helpers import generate_static
from tools.web_ui.cli import main

__all__ = ["make_app", "generate_static", "main"]
