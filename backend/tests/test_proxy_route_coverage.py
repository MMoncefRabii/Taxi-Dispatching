import re
import shlex
from pathlib import Path

import pytest

from app.config import settings
from main import create_app


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CADDYFILE = REPOSITORY_ROOT / "deploy" / "Caddyfile"


def _api_matcher_segments() -> set[str]:
    content = CADDYFILE.read_text(encoding="utf-8")
    matcher = re.search(r"(?m)^\s*@api\s+path\s+(.+)$", content)
    assert matcher is not None, "Caddyfile must define an @api path matcher."
    return {
        pattern.strip("/").split("/", maxsplit=1)[0]
        for pattern in shlex.split(matcher.group(1))
    }


def _route_paths(routes: list[object]) -> set[str]:
    paths: set[str] = set()
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.add(path)
        included_router = getattr(route, "original_router", None)
        if included_router is not None:
            paths.update(_route_paths(included_router.routes))
    return paths


@pytest.mark.parametrize("dev_tasks_enabled", [False, True])
def test_every_backend_route_is_covered_by_caddy_api_matcher(
    monkeypatch: pytest.MonkeyPatch,
    dev_tasks_enabled: bool,
) -> None:
    monkeypatch.setattr(settings, "dev_tasks_enabled", dev_tasks_enabled)
    app = create_app()
    matcher_segments = _api_matcher_segments()

    route_segments = {
        path.strip("/").split("/", maxsplit=1)[0]
        for path in _route_paths(app.routes)
        if path != "/"
    }

    assert route_segments <= matcher_segments, (
        "Caddy @api path matcher is missing top-level route segments: "
        f"{sorted(route_segments - matcher_segments)}"
    )
