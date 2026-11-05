"""Capture Controller: the capture cycle.

A state machine that counts down, arms the Capture Engine, turns each
gesture into a saved sample, and handles pause and resume
(``data-collection/docs/design.md`` sections 3.4 and 4.7). It owns the
``capture``, ``active_label``, ``latest_sample`` and ``last_discard`` fields
of the Application State.

One loop reads messages from one queue (user commands, the engine's results,
and the completion of save jobs) and handles them one at a time, so the state
machine needs no locks. The countdown is a deadline the loop waits for, not a
tick. ``handle`` and ``tick`` are public so tests can drive the machine
without a thread.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from fastapi import APIRouter
from pydantic import BaseModel

from wand_collect.clip_writer import ClipWriter
from wand_collect.engine import (
    GestureDiscarded,
    GestureFound,
    MotionStarted,
)
from wand_collect.server import ConflictError, InvalidRequestError
from wand_collect.state import (
    ApplicationState,
    CaptureState,
    CaptureStatus,
    LatestSample,
    Owner,
    SessionRole,
)
from wand_core.dataset import (
    DatasetStore,
    PositionColumns,
    SampleRecord,
    SampleStatus,
    VideoRecord,
    make_sample_id,
)
from wand_core.types import Gesture

logger = logging.getLogger(__name__)

FRAME_WAIT_EXTRA_S = 5.0  # how long past the window to wait for frames
CLIP_TIMEOUT_S = 120.0
STOP_TIMEOUT_S = 150.0


class Clock:
    """The time sources of the controller (replaced in tests)."""

    def monotonic(self) -> float:
        return time.monotonic()

    def wall(self) -> float:
        """Seconds since the Unix epoch, which the Web UI shares."""
        return time.time()

    def now(self) -> datetime:
        return datetime.now().astimezone()


class EnginePort(Protocol):
    def arm(self) -> Any: ...

    def disarm(self) -> Any: ...

    def frames_between(self, start_s: float, end_s: float) -> list: ...

    def newest_frame_s(self) -> float | None: ...


class SessionPort(Protocol):
    def next_sample_number(self) -> int: ...


# --- Messages ---------------------------------------------------------------


@dataclass(frozen=True)
class Start:
    pass


@dataclass(frozen=True)
class Pause:
    pass


@dataclass(frozen=True)
class Resume:
    pass


@dataclass(frozen=True)
class SetLabel:
    label: str | None


@dataclass(frozen=True)
class Stop:
    done: Future


@dataclass(frozen=True)
class SaveDone:
    sample_id: str
    label: str
    ok: bool
    clip: bool


class LabelBody(BaseModel):
    label: str


class CaptureController:
    def __init__(
        self,
        state: ApplicationState,
        engine: EnginePort,
        sessions: SessionPort,
        store: DatasetStore,
        clip_writer: ClipWriter,
        countdown_s: float = 3.0,
        clip_padding: tuple[float, float] = (2.0, 2.0),
        clock: Clock | None = None,
        run_job: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        self._state = state
        self._engine = engine
        self._sessions = sessions
        self._store = store
        self._clips = clip_writer
        self._countdown_s = countdown_s
        self._pre_s, self._post_s = clip_padding
        self._clock = clock or Clock()
        self._run_job = run_job or _run_in_thread

        self._queue: queue.Queue[Any] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()

        # Loop state.
        self._status = CaptureStatus.STOPPED
        self._deadline: float | None = None  # monotonic, in COUNTDOWN
        self._countdown_over = False
        self._remaining: float | None = None  # while PAUSED
        self._pause_pending = False  # pause asked for during RECORDING
        self._saving = 0
        self._stop_waiters: list[Future] = []
        self._issued: dict[str, int] = {}  # session id -> highest number given

        self.router = APIRouter()
        add = self.router.add_api_route
        add(
            "/recording/label", self.put_label, methods=["PUT"], status_code=204
        )
        add(
            "/recording/start",
            self.post_start,
            methods=["POST"],
            status_code=204,
        )
        add(
            "/recording/pause",
            self.post_pause,
            methods=["POST"],
            status_code=204,
        )
        add(
            "/recording/resume",
            self.post_resume,
            methods=["POST"],
            status_code=204,
        )

    # --- The loop --------------------------------------------------------

    def start_loop(self) -> None:
        if self._thread is None:
            self._stopping.clear()
            self._thread = threading.Thread(
                target=self._run, name="capture-controller", daemon=True
            )
            self._thread.start()

    def shutdown(self) -> None:
        """Stop the loop (the application is closing)."""
        if self._thread is not None:
            self._stopping.set()
            self._queue.put(None)
            self._thread.join()
            self._thread = None

    def post(self, message: Any) -> None:
        """Hand a message to the loop (any thread)."""
        self._queue.put(message)

    def on_engine_message(self, message: Any) -> None:
        """The engine's receiver: results arrive on the engine thread."""
        self.post(message)

    def _run(self) -> None:
        while not self._stopping.is_set():
            wait = None
            if self._deadline is not None and not self._countdown_over:
                wait = max(0.0, self._deadline - self._clock.monotonic())
            try:
                message = self._queue.get(timeout=wait)
            except queue.Empty:
                self.tick()
                continue
            if message is None:
                break
            try:
                self.handle(message)
            except Exception:  # noqa: BLE001 - the loop must keep running
                logger.exception("capture controller failed on %r", message)

    def tick(self) -> None:
        """Act on the countdown deadline if it has been reached."""
        if (
            self._status is CaptureStatus.COUNTDOWN
            and not self._countdown_over
            and self._deadline is not None
            and self._clock.monotonic() >= self._deadline
        ):
            self._countdown_over = True
            self._maybe_ready()

    def handle(self, message: Any) -> None:
        """Process one message. The only place the machine changes."""
        match message:
            case Start():
                self._start()
            case Pause():
                self._pause()
            case Resume():
                self._resume()
            case SetLabel(label=label):
                self._state.update(Owner.CAPTURE_CONTROLLER, active_label=label)
            case Stop(done=done):
                self._end(done)
            case MotionStarted():
                if self._status is CaptureStatus.READY:
                    self._set_status(CaptureStatus.RECORDING)
            case GestureDiscarded(discard=discard):
                if self._status in (
                    CaptureStatus.READY,
                    CaptureStatus.RECORDING,
                ):
                    self._state.update(
                        Owner.CAPTURE_CONTROLLER, last_discard=discard
                    )
                    self._after_result()
            case GestureFound(gesture=gesture):
                if self._status in (
                    CaptureStatus.READY,
                    CaptureStatus.RECORDING,
                ):
                    self._gesture(gesture)
            case SaveDone():
                self._save_done(message)
        self.tick()

    # --- Transitions -----------------------------------------------------

    def _set_status(
        self,
        status: CaptureStatus,
        ends_at: float | None = None,
        remaining: float | None = None,
    ) -> None:
        self._status = status
        self._state.update(
            Owner.CAPTURE_CONTROLLER,
            capture=CaptureState(status, ends_at, remaining),
        )

    def _enter_countdown(self, seconds: float) -> None:
        self._engine.disarm()
        self._deadline = self._clock.monotonic() + seconds
        self._countdown_over = False
        self._remaining = None
        self._set_status(
            CaptureStatus.COUNTDOWN, ends_at=self._clock.wall() + seconds
        )

    def _maybe_ready(self) -> None:
        """READY needs the countdown over and no sample being saved."""
        if (
            self._status is CaptureStatus.COUNTDOWN
            and self._countdown_over
            and self._saving == 0
        ):
            self._deadline = None
            self._engine.arm()
            self._set_status(CaptureStatus.READY)

    def _start(self) -> None:
        if self._status is CaptureStatus.STOPPED:
            self._pause_pending = False
            self._enter_countdown(self._countdown_s)

    def _after_result(self) -> None:
        """A gesture or a discard was processed: count down, or pause."""
        self._enter_countdown(self._countdown_s)
        if self._pause_pending:
            self._pause_pending = False
            self._pause()

    def _pause(self) -> None:
        status = self._status
        if status is CaptureStatus.COUNTDOWN:
            left = max(0.0, (self._deadline or 0.0) - self._clock.monotonic())
            self._freeze(left)
        elif status is CaptureStatus.READY:
            self._freeze(None)  # resume starts a fresh countdown
        elif status is CaptureStatus.RECORDING:
            self._pause_pending = True  # after the result is processed

    def _freeze(self, remaining: float | None) -> None:
        self._engine.disarm()
        self._deadline = None
        self._remaining = remaining
        self._set_status(CaptureStatus.PAUSED, remaining=remaining)

    def _resume(self) -> None:
        if self._status is CaptureStatus.PAUSED:
            seconds = (
                self._countdown_s
                if self._remaining is None
                else self._remaining
            )
            self._enter_countdown(seconds)

    def _end(self, done: Future) -> None:
        """The session ends: STOPPED from any state, losing no saved data."""
        self._engine.disarm()
        self._deadline = None
        self._pause_pending = False
        self._remaining = None
        self._set_status(CaptureStatus.STOPPED)
        if self._saving == 0:
            done.set_result(None)
        else:  # let the sample being saved finish first
            self._stop_waiters.append(done)

    # --- Samples ---------------------------------------------------------

    def _gesture(self, gesture: Gesture) -> None:
        snapshot = self._state.snapshot
        label = snapshot.active_label
        session = snapshot.session
        if label is None or session is None:
            logger.warning("a gesture arrived with no label or session")
            self._after_result()
            return
        number = self._reserve_number(session.id)
        sample_id = make_sample_id(session.id, number)
        self._saving += 1
        self._state.update(
            Owner.CAPTURE_CONTROLLER,
            latest_sample=LatestSample(
                sample_id, label, SampleStatus.ACCEPTED.value, False, True
            ),
        )
        job = _SaveJob(self, session.id, sample_id, label, gesture)
        self._run_job(job.run)
        self._after_result()

    def _reserve_number(self, session_id: str) -> int:
        """The next number, never given twice (the store hands out the next
        one on request, so a second request before the sample is saved would
        repeat it)."""
        number = max(
            self._sessions.next_sample_number(),
            self._issued.get(session_id, 0) + 1,
        )
        self._issued[session_id] = number
        return number

    def _save_done(self, done: SaveDone) -> None:
        self._saving = max(0, self._saving - 1)
        if done.ok:
            self._state.update(
                Owner.CAPTURE_CONTROLLER,
                latest_sample=LatestSample(
                    done.sample_id,
                    done.label,
                    SampleStatus.ACCEPTED.value,
                    done.clip,
                    False,
                ),
            )
        else:
            self._state.update(Owner.CAPTURE_CONTROLLER, latest_sample=None)
        if self._saving == 0:
            for waiter in self._stop_waiters:
                waiter.set_result(None)
            self._stop_waiters.clear()
        self._maybe_ready()

    # --- Requests --------------------------------------------------------

    def put_label(self, body: LabelBody) -> None:
        if not any(
            label.id == body.label for label in self._state.snapshot.labels
        ):
            raise InvalidRequestError(f"no such label: {body.label!r}")
        self.post(SetLabel(body.label))

    def post_start(self) -> None:
        snapshot = self._state.snapshot
        if (
            snapshot.session is None
            or snapshot.session.role is not SessionRole.CAPTURE
        ):
            raise ConflictError(
                "no_session", "start a session before capturing"
            )
        if snapshot.active_label is None:
            raise InvalidRequestError("choose a label first")
        if snapshot.capture.state is not CaptureStatus.STOPPED:
            raise ConflictError("already_capturing", "capture is running")
        self.post(Start())

    def post_pause(self) -> None:
        if self._state.snapshot.capture.state in (
            CaptureStatus.STOPPED,
            CaptureStatus.PAUSED,
        ):
            raise ConflictError("not_capturing", "capture is not running")
        self.post(Pause())

    def post_resume(self) -> None:
        if self._state.snapshot.capture.state is not CaptureStatus.PAUSED:
            raise ConflictError("not_paused", "capture is not paused")
        self.post(Resume())

    # --- The Session Service's view --------------------------------------

    def stop(self) -> None:
        """Stop capturing and wait for a sample being saved (session end)."""
        done: Future = Future()
        if self._thread is None:
            self.handle(Stop(done))
        else:
            self.post(Stop(done))
        done.result(STOP_TIMEOUT_S)


def _run_in_thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="save-sample", daemon=True).start()


class _SaveJob:
    """Collects a gesture's frames, writes its clip and saves the sample."""

    def __init__(
        self,
        controller: CaptureController,
        session_id: str,
        sample_id: str,
        label: str,
        gesture: Gesture,
    ) -> None:
        self._c = controller
        self._session_id = session_id
        self._sample_id = sample_id
        self._label = label
        self._gesture = gesture

    def run(self) -> None:
        c = self._c
        clip_ok = False
        try:
            clip_ok = self._save()
            ok = True
        except Exception:  # noqa: BLE001 - reported to the loop
            logger.exception("sample %s was not saved", self._sample_id)
            ok = False
        c.post(SaveDone(self._sample_id, self._label, ok, clip_ok))

    def _save(self) -> bool:
        c, gesture = self._c, self._gesture
        start = gesture.start_timestamp_s - c._pre_s
        end = gesture.end_timestamp_s + c._post_s
        self._wait_for_frames(end)
        frames = c._engine.frames_between(start, end)
        fps = self._fps()

        video = None
        if frames:
            path = c._store.clip_path(self._sample_id)
            result = c._clips.submit(frames, fps, path).result(CLIP_TIMEOUT_S)
            if result.ok:
                video = VideoRecord(
                    file=c._store.clip_reference(self._sample_id),
                    gesture_start_s=max(
                        0.0, gesture.start_timestamp_s - frames[0].timestamp_s
                    ),
                )
            else:
                logger.warning(
                    "sample %s saved without a clip: %s",
                    self._sample_id,
                    result.error,
                )
        session = c._store.get_session(self._session_id)
        size = self._frame_size()
        now = c._clock.now()
        c._store.add_sample(
            SampleRecord(
                sample_id=self._sample_id,
                session_id=self._session_id,
                captured_at=now,
                updated_at=now,
                label=self._label,
                status=SampleStatus.ACCEPTED,
                handedness=session.handedness,
                frame_size=size,
                positions=PositionColumns(
                    time_s=[p.time_s for p in gesture.positions],
                    horizontal=[p.horizontal for p in gesture.positions],
                    vertical=[p.vertical for p in gesture.positions],
                ),
                video=video,
            )
        )
        return video is not None

    def _wait_for_frames(self, end_s: float) -> None:
        """Wait until the engine's frames reach the end of the window."""
        c = self._c
        give_up = time.monotonic() + c._post_s + FRAME_WAIT_EXTRA_S
        while time.monotonic() < give_up:
            newest = c._engine.newest_frame_s()
            if newest is not None and newest >= end_s:
                return
            time.sleep(0.02)

    def _fps(self) -> float:
        camera = self._c._state.snapshot.camera
        return (
            camera.actual.fps if camera.actual and camera.actual.fps else 30.0
        )

    def _frame_size(self) -> tuple[int, int]:
        gesture = self._gesture
        if gesture.frame_width and gesture.frame_height:
            return gesture.frame_width, gesture.frame_height
        actual = self._c._state.snapshot.camera.actual
        return (actual.width, actual.height) if actual else (640, 480)
