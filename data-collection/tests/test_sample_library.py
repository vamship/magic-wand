import time
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from wand_collect.clip_writer import ClipWriter
from wand_collect.server import create_app
from wand_collect.services.library import SampleLibrary
from wand_collect.state import (
    ApplicationState,
    Label,
    Owner,
    SessionInfo,
    SessionRole,
)
from wand_core.dataset import (
    DatasetStore,
    Handedness,
    PositionColumns,
    SampleRecord,
    SampleStatus,
    VideoRecord,
)

TZ = timezone(timedelta(hours=-4))
LABELS = [Label("circle", "Circle"), Label("zigzag", "Zigzag")]


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 1, 16, 0, 0, tzinfo=TZ)

    def __call__(self):
        self.now += timedelta(seconds=1)
        return self.now


class Rig:
    def __init__(self, tmp_path):
        self.clock = Clock()
        self.state = ApplicationState()
        self.state.update(Owner.LABEL_SERVICE, labels=LABELS)
        self.store = DatasetStore.open(
            tmp_path / "data", create=True, clock=self.clock
        )
        self.cache = tmp_path / "cache"
        self.library = SampleLibrary(self.state, self.store, self.cache)
        self.client = TestClient(
            create_app(
                self.state, routers=[self.library.router], static_dir=None
            )
        )

    def session(self, author="ada", name=None):
        return self.store.create_session(author, Handedness.RIGHT, name=name)

    def sample(self, session, label="circle", status="accepted", clip=False):
        sample_id = self.store.new_sample_id(session.session_id)
        video = None
        if clip:
            video = VideoRecord(
                file=self.store.clip_reference(sample_id), gesture_start_s=0.1
            )
            self.make_clip(sample_id)
        record = SampleRecord(
            sample_id=sample_id,
            session_id=session.session_id,
            captured_at=self.clock(),
            updated_at=self.clock(),
            label=label,
            status=SampleStatus(status),
            handedness=Handedness.RIGHT,
            frame_size=(160, 120),
            positions=PositionColumns(
                time_s=[0.0, 0.1, 0.2],
                horizontal=[0.2, 0.5, 0.8],
                vertical=[0.5, 0.2, 0.5],
            ),
            video=video,
        )
        return self.store.add_sample(record)

    def make_clip(self, sample_id):
        class F:
            def __init__(self, t, jpeg):
                self.timestamp_s, self.jpeg = t, jpeg

        frames = []
        for i in range(12):
            image = np.full((120, 160, 3), 200, np.uint8)
            ok, jpeg = cv2.imencode(".jpg", image)
            frames.append(F(i / 30, jpeg.tobytes()))
        writer = ClipWriter()
        path = self.store.clip_path(sample_id)
        assert writer.submit(frames, 30.0, path).result(10).ok
        writer.close()


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def ids(response):
    return [item["id"] for item in response.json()["items"]]


# --- Index, counts and revision ----------------------------------------------


def test_the_index_is_built_from_the_data_folder(tmp_path):
    first = Rig(tmp_path)
    session = first.session()
    first.sample(session)
    first.sample(session, status="rejected")
    first.sample(session, label="zigzag")
    second = SampleLibrary(ApplicationState(), first.store, tmp_path / "c2")
    assert second.query()[1] == 3


def test_new_samples_appear_in_queries_counts_and_revision(rig):
    session = rig.session()
    assert rig.state.snapshot.counts == {}
    revision = rig.state.snapshot.samples_revision
    rig.sample(session)
    rig.sample(session, status="rejected")
    assert rig.client.get("/api/samples").json()["total"] == 2
    snapshot = rig.state.snapshot
    assert dict(snapshot.counts) == {"circle": 1}  # accepted only
    assert snapshot.samples_revision > revision


def test_edits_and_deletes_update_counts_and_revision(rig):
    session = rig.session()
    sample = rig.sample(session)
    rig.sample(session)
    assert rig.state.snapshot.counts["circle"] == 2
    revision = rig.state.snapshot.samples_revision

    response = rig.client.patch(
        f"/api/samples/{sample.sample_id}", json={"label": "zigzag"}
    )
    assert response.status_code == 200
    assert response.json()["label"] == "zigzag"
    assert dict(rig.state.snapshot.counts) == {"circle": 1, "zigzag": 1}
    rig.client.patch(
        f"/api/samples/{sample.sample_id}", json={"status": "rejected"}
    )
    assert dict(rig.state.snapshot.counts) == {"circle": 1}
    assert rig.state.snapshot.samples_revision > revision

    revision = rig.state.snapshot.samples_revision
    gone = rig.client.delete(f"/api/samples/{sample.sample_id}")
    assert gone.status_code == 204
    assert rig.client.get("/api/samples").json()["total"] == 1
    assert rig.state.snapshot.samples_revision > revision


def test_changes_are_on_disk_before_the_request_returns(rig):
    session = rig.session()
    sample = rig.sample(session)
    rig.client.patch(
        f"/api/samples/{sample.sample_id}", json={"status": "rejected"}
    )
    assert rig.store.get_sample(sample.sample_id).status is (
        SampleStatus.REJECTED
    )
    rig.client.delete(f"/api/samples/{sample.sample_id}")
    assert rig.store.read_samples(session.session_id) == []


def test_edits_work_in_ended_sessions(rig):
    session = rig.session()
    sample = rig.sample(session)
    rig.store.end_session(session.session_id)
    ok = rig.client.patch(
        f"/api/samples/{sample.sample_id}", json={"label": "zigzag"}
    )
    assert ok.status_code == 200
    assert rig.client.delete(
        f"/api/samples/{sample.sample_id}"
    ).status_code == (204)


def test_an_unknown_label_is_rejected(rig):
    sample = rig.sample(rig.session())
    response = rig.client.patch(
        f"/api/samples/{sample.sample_id}", json={"label": "fireball"}
    )
    assert response.status_code == 400
    assert rig.store.get_sample(sample.sample_id).label == "circle"


def test_bad_patches_are_rejected(rig):
    sample = rig.sample(rig.session())
    url = f"/api/samples/{sample.sample_id}"
    assert rig.client.patch(url, json={}).status_code == 400
    assert rig.client.patch(url, json={"status": "maybe"}).status_code == 400


def test_unknown_samples_are_not_found(rig):
    session = rig.session()
    missing = f"{session.session_id}-0009"
    for call in (
        rig.client.get(f"/api/samples/{missing}"),
        rig.client.patch(f"/api/samples/{missing}", json={"label": "circle"}),
        rig.client.delete(f"/api/samples/{missing}"),
        rig.client.get(f"/api/samples/{missing}/thumbnail"),
        rig.client.get("/api/samples/nonsense"),
    ):
        assert call.status_code == 404


def test_label_use_counts_all_statuses(rig):
    session = rig.session()
    rig.sample(session)
    rig.sample(session, status="rejected")
    rig.sample(session, label="zigzag")
    assert rig.library.label_use_count("circle") == 2
    assert rig.library.label_use_count("fireball") == 0


def test_session_changes_reach_the_summaries(rig):
    session = rig.session(name="old")
    rig.sample(session)
    rig.store.update_session(session.session_id, name="new")
    item = rig.client.get("/api/samples").json()["items"][0]
    assert item["sessionName"] == "new" and item["author"] == "ada"


# --- Queries -----------------------------------------------------------------


def test_filters_combine(rig):
    ada, bob = rig.session("ada"), rig.session("bob")
    a1 = rig.sample(ada, "circle")
    rig.sample(ada, "zigzag")
    a3 = rig.sample(ada, "circle", "rejected")
    b1 = rig.sample(bob, "circle")
    get = rig.client.get
    assert ids(get("/api/samples?label=circle")) == [
        a1.sample_id,
        a3.sample_id,
        b1.sample_id,
    ]
    assert ids(get("/api/samples?label=circle&author=bob")) == [b1.sample_id]
    assert ids(
        get(
            f"/api/samples?session={ada.session_id}&status=accepted&label=circle"
        )
    ) == [a1.sample_id]
    assert get("/api/samples?status=rejected").json()["total"] == 1
    assert get("/api/samples?status=maybe").status_code == 400


def test_date_filters(rig):
    session = rig.session()
    first = rig.sample(session)
    for _ in range(3):
        rig.sample(session)
    stamp = first.captured_at.isoformat()
    day = first.captured_at.date().isoformat()
    total = rig.client.get(f"/api/samples?from={day}&to={day}").json()["total"]
    assert total == 4
    only = rig.client.get("/api/samples", params={"to": stamp}).json()
    assert [i["id"] for i in only["items"]] == [first.sample_id]
    none = rig.client.get("/api/samples?from=2030-01-01").json()
    assert none["total"] == 0
    assert rig.client.get("/api/samples?from=yesterday").status_code == 400


def test_order_and_stable_pages(rig):
    session = rig.session()
    made = [rig.sample(session).sample_id for _ in range(7)]
    got = []
    for page in (1, 2, 3, 4):
        response = rig.client.get(f"/api/samples?page={page}&pageSize=3")
        got += ids(response)
        assert response.json()["total"] == 7
    assert got == made
    newest = rig.client.get("/api/samples?order=newest&pageSize=2")
    assert ids(newest) == [made[6], made[5]]
    assert rig.client.get("/api/samples?page=0").status_code == 400
    assert rig.client.get("/api/samples?pageSize=100000").status_code == 400


def test_the_current_session_can_be_the_default_for_review(rig):
    one, two = rig.session(), rig.session()
    rig.sample(one)
    mine = rig.sample(two)
    assert rig.client.get("/api/samples?session=current").status_code == 400
    rig.state.update(
        Owner.SESSION_SERVICE,
        session=SessionInfo(two.session_id, "n", SessionRole.REVIEW),
    )
    assert ids(rig.client.get("/api/samples?session=current")) == [
        mine.sample_id
    ]
    assert rig.client.get("/api/samples").json()["total"] == 2


def test_queries_over_10000_samples_are_fast(rig):
    session = rig.session()
    base = datetime(2026, 11, 1, tzinfo=TZ)
    from wand_collect.services.library import SampleSummary

    for i in range(10000):
        sample_id = f"{session.session_id}-{i + 1:05d}"
        rig.library._samples[sample_id] = SampleSummary(
            sample_id,
            session.session_id,
            None,
            "ada" if i % 2 else "bob",
            "circle" if i % 3 else "zigzag",
            SampleStatus.ACCEPTED,
            base + timedelta(seconds=i),
            False,
        )
    start = time.perf_counter()
    for _ in range(5):
        items, total = rig.library.query(
            label="circle", author="ada", order="newest", page=3
        )
    assert (time.perf_counter() - start) / 5 < 0.1
    assert total > 1000 and len(items) == 50


# --- Details and images -------------------------------------------------------


def test_details_have_the_record_and_a_clip_flag(rig):
    session = rig.session()
    plain = rig.sample(session)
    clipped = rig.sample(session, clip=True)
    one = rig.client.get(f"/api/samples/{plain.sample_id}").json()
    two = rig.client.get(f"/api/samples/{clipped.sample_id}").json()
    assert one["id"] == plain.sample_id and one["hasClip"] is False
    assert one["positions"]["horizontal"] == [0.2, 0.5, 0.8]
    assert two["hasClip"] is True and two["video"]["gestureStartS"] == 0.1


def decode(response):
    assert response.headers["content-type"] == "image/png"
    return cv2.imdecode(
        np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR
    )


def test_path_images_have_the_frame_size_or_the_requested_width(rig):
    sample = rig.sample(rig.session())
    url = f"/api/samples/{sample.sample_id}/image"
    assert decode(rig.client.get(url)).shape == (120, 160, 3)
    assert decode(rig.client.get(url + "?mode=path&width=320")).shape == (
        240,
        320,
        3,
    )
    assert rig.client.get(url + "?mode=other").status_code == 400


def test_overlay_uses_the_clip_frame(rig):
    sample = rig.sample(rig.session(), clip=True)
    image = decode(
        rig.client.get(f"/api/samples/{sample.sample_id}/image?mode=overlay")
    )
    assert image.shape == (120, 160, 3)
    assert abs(int(image[2, 158].mean()) - 200) < 12  # the clip's grey


def test_overlay_without_a_clip_is_not_found_but_paths_work(rig):
    session = rig.session()
    plain = rig.sample(session)
    lost = rig.sample(session, clip=True)
    rig.store.clip_path(lost.sample_id).unlink()
    for sample in (plain, lost):
        base = f"/api/samples/{sample.sample_id}"
        assert rig.client.get(base + "/image?mode=overlay").status_code == 404
        assert rig.client.get(base + "/image").status_code == 200
        assert rig.client.get(base + "/thumbnail").status_code == 200
        assert rig.client.get(base).json()["hasClip"] is False


def test_thumbnails_are_small_and_cached_outside_the_data_folder(rig, tmp_path):
    sample = rig.sample(rig.session())
    url = f"/api/samples/{sample.sample_id}/thumbnail"
    assert decode(rig.client.get(url)).shape == (72, 96, 3)
    cached = list(rig.cache.glob(f"{sample.sample_id}-*.png"))
    assert len(cached) == 1
    assert rig.store.path not in cached[0].parents
    cached[0].write_bytes(b"cached")  # a hit is served as stored
    assert rig.client.get(url).content == b"cached"
    cached[0].unlink()  # deleting the cache does no harm
    assert decode(rig.client.get(url)).shape == (72, 96, 3)


def test_thumbnails_are_keyed_by_the_positions(rig):
    sample = rig.sample(rig.session())
    url = f"/api/samples/{sample.sample_id}/thumbnail"
    rig.client.get(url)
    before = {p.name for p in rig.cache.iterdir()}
    session_id, _ = sample.session_id, 0
    # change the positions on disk, as an edit of the file would
    records = rig.store.read_samples(session_id)
    records[0] = records[0].model_copy(
        update={
            "positions": PositionColumns(
                time_s=[0.0, 0.1], horizontal=[0.1, 0.9], vertical=[0.1, 0.9]
            )
        }
    )
    from wand_core.dataset import write_samples

    write_samples(rig.store.session_dir(session_id) / "samples.jsonl", records)
    rig.client.get(url)
    assert {p.name for p in rig.cache.iterdir()} != before


def test_deleting_a_sample_removes_its_clip_and_thumbnails(rig):
    sample = rig.sample(rig.session(), clip=True)
    rig.client.get(f"/api/samples/{sample.sample_id}/thumbnail")
    rig.client.delete(f"/api/samples/{sample.sample_id}")
    assert not rig.store.clip_path(sample.sample_id).exists()
    assert list(rig.cache.glob("*.png")) == []
