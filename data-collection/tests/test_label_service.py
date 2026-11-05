import pytest
from fastapi.testclient import TestClient

from wand_collect.server import create_app
from wand_collect.services.labels import LabelService
from wand_collect.state import ApplicationState

TEXT = """\
# Header comment that must stay.
labels:
  # the first one
  - id: spell_one
    name: Spell One
  - id: spell_two   # trailing note
    name: Spell Two
"""


class Rig:
    def __init__(self, tmp_path, used=()):
        self.path = tmp_path / "labels.yaml"
        self.path.write_text(TEXT)
        self.state = ApplicationState()
        self.used = dict(used)
        self.service = LabelService(
            self.state, self.path, lambda label: self.used.get(label, 0)
        )
        self.service.load()
        self.client = TestClient(
            create_app(
                self.state, routers=[self.service.router], static_dir=None
            )
        )

    def ids(self):
        return [label.id for label in self.state.snapshot.labels]


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def test_labels_are_read_into_the_state_at_startup(rig):
    assert rig.ids() == ["spell_one", "spell_two"]
    assert rig.state.snapshot.labels[0].name == "Spell One"


def test_adding_a_label_updates_the_file_and_the_state(rig):
    response = rig.client.post(
        "/api/labels", json={"id": "fireball", "name": "Fireball"}
    )
    assert response.status_code == 201
    assert rig.ids() == ["spell_one", "spell_two", "fireball"]
    text = rig.path.read_text()
    assert "fireball" in text
    assert "# Header comment that must stay." in text
    assert "# the first one" in text and "# trailing note" in text
    assert text.index("spell_one") < text.index("spell_two")


@pytest.mark.parametrize(
    "body",
    [
        {"id": "Fire Ball", "name": "x"},
        {"id": "", "name": "x"},
        {"id": "ok", "name": "  "},
        {"id": "spell_one", "name": "again"},
    ],
)
def test_bad_labels_are_refused_with_400(rig, body):
    before = rig.path.read_text()
    assert rig.client.post("/api/labels", json=body).status_code == 400
    assert rig.path.read_text() == before
    assert rig.ids() == ["spell_one", "spell_two"]


def test_renaming_changes_only_the_name(rig):
    response = rig.client.patch(
        "/api/labels/spell_two", json={"name": "Second"}
    )
    assert response.status_code == 200
    assert rig.state.snapshot.labels[1].name == "Second"
    assert rig.ids() == ["spell_one", "spell_two"]
    assert "# trailing note" in rig.path.read_text()
    assert (
        rig.client.patch("/api/labels/spell_two", json={"name": ""}).status_code
        == 400
    )
    assert (
        rig.client.patch("/api/labels/nope", json={"name": "x"}).status_code
        == 404
    )


def test_removing_an_unused_label(rig):
    assert rig.client.delete("/api/labels/spell_one").status_code == 204
    assert rig.ids() == ["spell_two"]
    assert "spell_one" not in rig.path.read_text()
    assert rig.client.delete("/api/labels/spell_one").status_code == 404


def test_removing_a_used_label_is_refused(tmp_path):
    rig = Rig(tmp_path, used={"spell_one": 3})
    response = rig.client.delete("/api/labels/spell_one")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "label_in_use"
    assert rig.ids() == ["spell_one", "spell_two"]


def test_a_changed_file_is_reloaded(rig):
    assert rig.service.check_file() is False  # nothing changed
    rig.path.write_text(
        "labels:\n  - id: other\n    name: Other\n  - id: more\n    name: M\n"
    )
    assert rig.service.check_file() is True
    assert rig.ids() == ["other", "more"]
    assert rig.service.check_file() is False


def test_our_own_writes_are_not_reloaded_again(rig):
    rig.client.post("/api/labels", json={"id": "x", "name": "X"})
    assert rig.service.check_file() is False


def test_a_malformed_file_later_keeps_the_running_labels(rig):
    rig.path.write_text("labels: [unclosed\n")
    assert rig.service.check_file() is False
    assert rig.ids() == ["spell_one", "spell_two"]
    rig.path.write_text("labels:\n  - id: Bad Id\n    name: x\n")
    assert rig.service.check_file() is False
    assert rig.ids() == ["spell_one", "spell_two"]


def test_a_malformed_file_at_startup_is_a_clear_error(tmp_path):
    from wand_collect.labels import LabelsError

    path = tmp_path / "labels.yaml"
    path.write_text("nothing: here\n")
    service = LabelService(ApplicationState(), path, lambda label: 0)
    with pytest.raises(LabelsError, match="labels"):
        service.load()


def test_the_poller_picks_up_changes(tmp_path):
    import time

    rig = Rig(tmp_path)
    rig.service._poll_s = 0.05
    rig.service.start()
    try:
        rig.path.write_text("labels:\n  - id: late\n    name: Late\n")
        deadline = time.time() + 3
        while rig.ids() != ["late"] and time.time() < deadline:
            time.sleep(0.02)
        assert rig.ids() == ["late"]
    finally:
        rig.service.stop()
