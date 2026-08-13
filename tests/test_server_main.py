from server import main


def test_app_uses_the_memory_lifecycle_context():
    assert main.app.router.on_startup == []
    assert main.app.router.on_shutdown == []
    assert main.app.router.lifespan_context is not None


def test_generated_wiki_routes_are_read_only():
    wiki_routes = [
        route for route in main.app.routes
        if getattr(route, "path", "") == "/api/memory/wiki/{slug}"
    ]

    assert len(wiki_routes) == 1
    assert wiki_routes[0].methods == {"GET"}
