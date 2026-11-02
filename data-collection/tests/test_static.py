import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wand_collect import server
from wand_collect.server import create_app
from wand_collect.settings import DataCollectionSettings
from wand_collect.state import ApplicationState

STATIC = Path(server.__file__).parent / "static"
VENDOR = STATIC / "vendor"
MAX_COLUMNS = 80


@pytest.fixture
def client():
    app = create_app(ApplicationState(), app_settings=DataCollectionSettings())
    with TestClient(app) as client:
        yield client


def test_no_line_outside_vendor_is_over_80_columns_except_html():
    too_long = []
    for path in sorted(STATIC.rglob("*")):
        if not path.is_file() or VENDOR in path.parents:
            continue
        if path.suffix == ".html":
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if len(line) > MAX_COLUMNS:
                too_long.append(f"{path.relative_to(STATIC)}:{number}")
    assert not too_long, f"lines over {MAX_COLUMNS} columns: {too_long}"


def test_root_serves_index_html_that_loads_modules_without_a_build_step(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    page = response.text
    assert '<script type="module" src="/app/main.js">' in page
    assert 'rel="stylesheet" href="/style.css"' in page
    assert not re.search(r"<script[^>]+src=\"[^\"]*(bundle|dist)", page)


def test_every_file_the_page_references_is_served(client):
    page = client.get("/").text
    imports = re.search(r'"imports":\s*({[^}]*})', page).group(1)
    paths = re.findall(r'"(/[^"]+)"', imports)
    assert sorted(paths) == [
        "/vendor/hooks.module.js",
        "/vendor/htm.module.js",
        "/vendor/preact.module.js",
    ]
    for path in [*paths, "/app/main.js", "/style.css"]:
        response = client.get(path)
        assert response.status_code == 200, path
    assert "javascript" in client.get("/app/main.js").headers["content-type"]


def test_relative_imports_in_app_modules_all_exist():
    app = STATIC / "app"
    for module in app.rglob("*.js"):
        for target in re.findall(r'from "(\.[^"]+)"', module.read_text()):
            assert (module.parent / target).resolve().is_file(), (
                f"{module.relative_to(STATIC)} imports missing {target}"
            )


def test_bare_imports_are_all_in_the_import_map():
    page = (STATIC / "index.html").read_text()
    mapped = set(re.findall(r'"([a-z/]+)":\s*"/vendor/', page))
    for module in (STATIC / "app").rglob("*.js"):
        for name in re.findall(r'from "([^."/][^"]*)"', module.read_text()):
            assert name in mapped, f"{module.name} imports unmapped {name}"
    hooks = (VENDOR / "hooks.module.js").read_text()
    assert 'from"preact"' in hooks and "preact" in mapped


def test_vendor_versions_list_every_vendored_file_with_a_checksum():
    import hashlib

    versions = (VENDOR / "VERSIONS.md").read_text()
    files = sorted(p.name for p in VENDOR.glob("*.js"))
    assert files == ["hooks.module.js", "htm.module.js", "preact.module.js"]
    for name in files:
        row = next(
            line for line in versions.splitlines() if f"`{name}`" in line
        )
        assert re.search(r"\| \d+\.\d+\.\d+ \|", row), f"no version for {name}"
        assert "https://" in row, f"no source for {name}"
        digest = hashlib.sha256((VENDOR / name).read_bytes()).hexdigest()
        assert digest in row, f"{name} differs from the recorded checksum"


def test_config_endpoint_gives_the_page_its_shortcuts(client):
    body = client.get("/api/config").json()
    assert body["shortcuts"] == {
        "pause": "Escape",
        "previous": "ArrowLeft",
        "next": "ArrowRight",
        "reject": "r",
        "delete": "Backspace",
        "toggleView": "p",
    }
    assert body["countdownS"] == 3.0
    assert body["clipPadding"] == {"preS": 2.0, "postS": 2.0}
