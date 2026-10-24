"""Working-copy and bounded undo/redo support for preview edits."""

from __future__ import annotations

import shutil
import threading
import uuid
from pathlib import Path

_HISTORY_LIMIT = 20
_LOCK = threading.Lock()
_UNDO: dict[str, list[Path]] = {}
_REDO: dict[str, list[Path]] = {}


def working_path(original: Path) -> Path:
    """Working path.

    Purpose:
        Working path.

    Args:
        original: Original. Type: Path.

    Returns:
        a Path.

    Raises:
        None.

    Example:
        working_path(original) returns a Path.

    Side effects:
        None. This function only reads data and returns a value.
    """
    return original.parent / ".preview-edits" / f"{original.stem}-working.pdf"


def edited_copy_path(original: Path) -> Path:
    """Edited copy path.

    Purpose:
        Edited copy path.

    Args:
        original: Original. Type: Path.

    Returns:
        a Path.

    Raises:
        None.

    Example:
        edited_copy_path(original) returns a Path.

    Side effects:
        None. This function only reads data and returns a value.
    """
    return original.parent / "edited" / f"{original.stem}-edited.pdf"


def active_path(original: Path) -> Path:
    """Active path.

    Purpose:
        Active path.

    Args:
        original: Original. Type: Path.

    Returns:
        a Path.

    Raises:
        None.

    Example:
        active_path(original) returns a Path.

    Side effects:
        None. This function only reads data and returns a value.
    """
    working = working_path(original)
    return working if working.is_file() else original


def editable_path(original: Path) -> Path:
    """Create a separate working PDF on first mutation; never edit the original.

    Purpose:
        Create a separate working PDF on first mutation; never edit the original.

    Args:
        original: Original. Type: Path.

    Returns:
        a Path.

    Raises:
        None.

    Example:
        editable_path(original) returns a Path.

    Side effects:
        None. This function only reads data and returns a value.
    """
    working = working_path(original)
    if not working.is_file():
        working.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, working)
        original_marks = original.parent / "highlights.json"
        if original_marks.is_file():
            shutil.copy2(original_marks, working.parent / "highlights.json")
    return working


def snapshot_before(path: Path) -> Path:
    """Create a pre-edit snapshot. Call commit() after success, abort() on failure.

    Purpose:
        Create a pre-edit snapshot. Call commit() after success, abort() on failure.

    Args:
        path: Path to a file on disk.

    Returns:
        Path.

    Raises:
        None.

    Example:
        snapshot_before(path) returns Path.

    Side effects:
        Writes or changes a file on disk.
    """
    snapshot_dir = path.parent / "history"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot = snapshot_dir / f"before-{uuid.uuid4().hex}.pdf"
    shutil.copy2(path, snapshot)
    marks = path.parent / "highlights.json"
    if marks.is_file():
        shutil.copy2(marks, snapshot.with_suffix(".marks.json"))
    return snapshot


def commit(path: Path, snapshot: Path) -> None:
    """Commit.

    Purpose:
        Commit.

    Args:
        path: Path to a file on disk.
        snapshot: Snapshot. Type: Path.

    Returns:
        None.

    Raises:
        None.

    Example:
        commit(path, snapshot) returns None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    key = str(path.resolve())
    with _LOCK:
        undo = _UNDO.setdefault(key, [])
        undo.append(snapshot)
        for old in undo[:-_HISTORY_LIMIT]:
            _discard(old)
        del undo[:-_HISTORY_LIMIT]
        for old in _REDO.pop(key, []):
            _discard(old)


def abort(snapshot: Path) -> None:
    """Abort.

    Purpose:
        Abort.

    Args:
        snapshot: Snapshot. Type: Path.

    Returns:
        None.

    Raises:
        None.

    Example:
        abort(snapshot) returns None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    _discard(snapshot)


def undo(path: Path) -> bool:
    """Undo.

    Purpose:
        Undo.

    Args:
        path: Path to a file on disk.

    Returns:
        bool.

    Raises:
        None.

    Example:
        undo(path) returns bool.

    Side effects:
        Writes or changes a file on disk.
    """
    key = str(path.resolve())
    with _LOCK:
        stack = _UNDO.get(key, [])
        if not stack:
            return False
        redo_snapshot = path.parent / "history" / f"redo-{uuid.uuid4().hex}.pdf"
        shutil.copy2(path, redo_snapshot)
        snapshot = stack.pop()
        _restore(snapshot, path)
        _discard(snapshot)
        _REDO.setdefault(key, []).append(redo_snapshot)
    return True


def redo(path: Path) -> bool:
    """Redo.

    Purpose:
        Redo.

    Args:
        path: Path to a file on disk.

    Returns:
        bool.

    Raises:
        None.

    Example:
        redo(path) returns bool.

    Side effects:
        Writes or changes a file on disk.
    """
    key = str(path.resolve())
    with _LOCK:
        stack = _REDO.get(key, [])
        if not stack:
            return False
        undo_snapshot = path.parent / "history" / f"undo-{uuid.uuid4().hex}.pdf"
        shutil.copy2(path, undo_snapshot)
        snapshot = stack.pop()
        _restore(snapshot, path)
        _discard(snapshot)
        _UNDO.setdefault(key, []).append(undo_snapshot)
    return True


def history_state(path: Path) -> dict[str, bool]:
    """History state.

    Purpose:
        History state.

    Args:
        path: Path to a file on disk.

    Returns:
        dict[str, bool].

    Raises:
        None.

    Example:
        history_state(path) returns dict[str, bool].

    Side effects:
        None. This function only reads data and returns a value.
    """
    key = str(path.resolve())
    return {"can_undo": bool(_UNDO.get(key)), "can_redo": bool(_REDO.get(key))}


def _restore(snapshot: Path, path: Path) -> None:
    """Restore.

    Purpose:
        Restore.

    Args:
        snapshot: Snapshot. Type: Path.
        path: Path to a file on disk.

    Returns:
        None.

    Raises:
        None.

    Example:
        _restore(snapshot, path) returns None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    shutil.copy2(snapshot, path)
    saved_marks = snapshot.with_suffix(".marks.json")
    current_marks = path.parent / "highlights.json"
    if saved_marks.is_file():
        shutil.copy2(saved_marks, current_marks)
    else:
        current_marks.unlink(missing_ok=True)


def _discard(snapshot: Path) -> None:
    """Discard.

    Purpose:
        Discard.

    Args:
        snapshot: Snapshot. Type: Path.

    Returns:
        None.

    Raises:
        None.

    Example:
        _discard(snapshot) returns None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    snapshot.unlink(missing_ok=True)
    snapshot.with_suffix(".marks.json").unlink(missing_ok=True)
