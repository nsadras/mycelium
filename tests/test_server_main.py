from server import main


def test_app_has_no_automatic_memory_lifecycle_handlers():
    assert main.app.router.on_startup == []
    assert main.app.router.on_shutdown == []


def test_generated_wiki_routes_are_read_only():
    wiki_routes = [
        route for route in main.app.routes
        if getattr(route, "path", "") == "/api/memory/wiki/{slug}"
    ]

    assert len(wiki_routes) == 1
    assert wiki_routes[0].methods == {"GET"}
