"""Label Service: the shared list of spell labels (``config/labels.yaml``).

It owns the ``labels`` field of the Application State. Changes are written
back to the file with the replace routine, keeping its comments, and the file
is polled so labels pulled from git appear without a restart
(``data-collection/docs/design.md`` section 4.10).
"""

from __future__ import annotations

import io
import logging
import threading
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel
from ruamel.yaml import YAML

from wand_collect.labels import LabelsError, load_labels
from wand_collect.server import (
    ConflictError,
    InvalidRequestError,
    NotFoundError,
)
from wand_collect.state import ApplicationState, Label, Owner
from wand_core.dataset import replace_file
from wand_core.dataset.models import LABEL_PATTERN

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 2.0


class NewLabel(BaseModel):
    id: str
    name: str


class Rename(BaseModel):
    name: str


class LabelService:
    def __init__(
        self,
        state: ApplicationState,
        path: Path,
        use_count: Callable[[str], int],
        poll_s: float = POLL_INTERVAL_S,
    ) -> None:
        self._state = state
        self._path = Path(path)
        self._use_count = use_count
        self._poll_s = poll_s
        self._lock = threading.Lock()
        self._stamp = self._file_stamp()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self.router = APIRouter()
        add = self.router.add_api_route
        add("/labels", self.post_label, methods=["POST"], status_code=201)
        add("/labels/{label_id}", self.patch_label, methods=["PATCH"])
        add(
            "/labels/{label_id}",
            self.delete_label,
            methods=["DELETE"],
            status_code=204,
        )

    # --- The state and the file ------------------------------------------

    def load(self) -> None:
        """Read the file and write the labels to the state (at startup).

        Raises ``LabelsError`` if the file is malformed.
        """
        with self._lock:
            labels = load_labels(self._path)
            self._stamp = self._file_stamp()
            self._state.update(Owner.LABEL_SERVICE, labels=labels)

    def start(self) -> None:
        """Start polling the file for changes."""
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._poll, name="labels-poll", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _poll(self) -> None:
        while not self._stop.wait(self._poll_s):
            self.check_file()

    def check_file(self) -> bool:
        """Re-read the file if it changed. True if the labels were updated.

        A malformed file is logged and ignored; the running labels stay.
        """
        with self._lock:
            stamp = self._file_stamp()
            if stamp == self._stamp:
                return False
            self._stamp = stamp
            try:
                labels = load_labels(self._path)
            except LabelsError as error:
                logger.warning("labels file not reloaded: %s", error)
                return False
            if tuple(labels) == self._state.snapshot.labels:
                return False
            self._state.update(Owner.LABEL_SERVICE, labels=labels)
            return True

    def _file_stamp(self) -> tuple[int, int] | None:
        try:
            info = self._path.stat()
        except OSError:
            return None
        return (info.st_mtime_ns, info.st_size)

    def _edit(self, change: Callable[[list], None]) -> None:
        """Apply ``change`` to the file's label list, keeping its comments."""
        yaml = YAML()  # round trip: comments and order are kept
        yaml.indent(mapping=2, sequence=4, offset=2)
        yaml.preserve_quotes = True
        try:
            document = yaml.load(self._path.read_text(encoding="utf-8"))
        except OSError as error:
            raise ConflictError(
                "labels_unavailable", f"cannot read the labels file: {error}"
            ) from error
        change(document["labels"])
        out = io.StringIO()
        yaml.dump(document, out)
        replace_file(self._path, out.getvalue().encode("utf-8"))
        self._stamp = self._file_stamp()
        labels = load_labels(self._path)
        self._state.update(Owner.LABEL_SERVICE, labels=labels)

    # --- Requests --------------------------------------------------------

    def post_label(self, body: NewLabel) -> dict[str, str]:
        label_id, name = body.id.strip(), body.name.strip()
        if not LABEL_PATTERN.match(label_id):
            raise InvalidRequestError(
                "a label id must be a lowercase slug (letters, digits, "
                "underscore)"
            )
        if not name:
            raise InvalidRequestError("a label needs a name")
        with self._lock:
            if any(label.id == label_id for label in self._labels()):
                raise InvalidRequestError(f"the label {label_id!r} exists")
            self._edit(
                lambda entries: entries.append({"id": label_id, "name": name})
            )
        return {"id": label_id, "name": name}

    def patch_label(self, label_id: str, body: Rename) -> dict[str, str]:
        name = body.name.strip()
        if not name:
            raise InvalidRequestError("a label needs a name")
        with self._lock:
            self._require(label_id)

            def rename(entries: list) -> None:
                for entry in entries:
                    if str(entry["id"]) == label_id:
                        entry["name"] = name

            self._edit(rename)
        return {"id": label_id, "name": name}

    def delete_label(self, label_id: str) -> None:
        with self._lock:
            self._require(label_id)
            count = self._use_count(label_id)
            if count:
                raise ConflictError(
                    "label_in_use",
                    f"{count} sample(s) use the label {label_id!r}; "
                    "relabel or delete them first",
                )

            def remove(entries: list) -> None:
                for index, entry in enumerate(entries):
                    if str(entry["id"]) == label_id:
                        del entries[index]
                        return

            self._edit(remove)

    def _labels(self) -> tuple[Label, ...]:
        return self._state.snapshot.labels

    def _require(self, label_id: str) -> None:
        if not any(label.id == label_id for label in self._labels()):
            raise NotFoundError(f"no label {label_id!r}")
