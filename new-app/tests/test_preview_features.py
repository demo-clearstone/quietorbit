from __future__ import annotations

import shutil

import fitz

from services.preview_history import (
    active_path,
    commit,
    edited_copy_path,
    editable_path,
    redo,
    snapshot_before,
    undo,
)
from services.preview_view import (
    add_annotation,
    add_secure_redaction,
    modify_pages,
    search_pdf,
    update_bookmark,
    validate_bookmarks,
)
from services.change_marks import load_marks, save_marks


def make_source(path):
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    page.insert_text((30, 60), "SSN 123-45-6789", fontsize=12)
    page.insert_text((30, 100), "Keep this paragraph", fontsize=12)
    doc.set_toc([[1, "Keep this paragraph", 1]])
    doc.save(path)
    doc.close()


def test_working_copy_undo_redo_and_separate_save(tmp_path):
    original = tmp_path / "original.pdf"
    make_source(original)
    working = editable_path(original)
    initial_marks = [{"page": 0, "x0": 1, "y0": 1, "x1": 5, "y1": 5, "label": "Cover date"}]
    save_marks(working, initial_marks)
    before = snapshot_before(working)
    modify_pages(working, "rotate", 1, [])
    save_marks(working, [])
    commit(working, before)

    assert fitz.open(original)[0].rotation == 0
    assert fitz.open(active_path(original))[0].rotation == 90
    assert undo(working)
    assert fitz.open(working)[0].rotation == 0
    assert load_marks(working) == initial_marks
    assert redo(working)
    assert fitz.open(working)[0].rotation == 90
    assert load_marks(working) == []

    saved = edited_copy_path(original)
    saved.parent.mkdir(parents=True)
    shutil.copy2(working, saved)
    assert saved.is_file()
    assert fitz.open(original)[0].rotation == 0


def test_search_bookmark_management_and_validation(tmp_path):
    path = tmp_path / "outline.pdf"
    make_source(path)
    hits = search_pdf(path, "123-45-6789")
    assert len(hits) == 1 and hits[0]["page"] == 1

    bookmarks = update_bookmark(path, "add", title="Participant Report", page=1)
    assert bookmarks[-1]["title"] == "Participant Report"
    bookmarks = update_bookmark(path, "rename", index=1, title="Keep this paragraph", page=1)
    assert bookmarks[-1]["title"] == "Keep this paragraph"
    assert validate_bookmarks(path)["valid"]
    bookmarks = update_bookmark(path, "delete", index=1)
    assert [item["title"] for item in bookmarks] == ["Keep this paragraph"]


def test_crop_resize_annotations_and_secure_redaction(tmp_path):
    path = tmp_path / "editable.pdf"
    make_source(path)
    _, _, _ = modify_pages(path, "crop", 1, [], rect=(20, 20, 280, 280))
    doc = fitz.open(path)
    assert doc[0].rect.width == 260
    doc.close()

    modify_pages(path, "resize", 1, [], page_size="letter")
    doc = fitz.open(path)
    assert round(doc[0].rect.width) == 612 and round(doc[0].rect.height) == 792
    doc.close()

    add_annotation(path, 1, "note", (30, 130, 170, 190), text="Review note")
    add_annotation(path, 1, "stamp", (180, 130, 270, 180), text="DRAFT")
    add_annotation(path, 1, "rectangle", (30, 200, 100, 250))
    add_annotation(path, 1, "signature", (30, 255, 200, 280), points=[[35, 275], [65, 260], [100, 278]])
    doc = fitz.open(path)
    target = doc[0].search_for("123-45-6789")[0]
    doc.close()
    add_annotation(path, 1, "note", tuple(target), text="Sensitive note")
    removed = add_secure_redaction(path, 1, tuple(target))

    doc = fitz.open(path)
    text = doc[0].get_text("text")
    assert "123-45-6789" not in text
    assert "Keep this paragraph" in text
    assert "Sensitive note" not in text
    assert removed > 0
    assert list(doc[0].annots())
    doc.close()
