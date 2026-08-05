from server import main


def test_app_has_no_automatic_memory_lifecycle_handlers():
    assert main.app.router.on_startup == []
    assert main.app.router.on_shutdown == []
