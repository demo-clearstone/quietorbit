from __future__ import annotations

import fitz

from services.preview_view import add_highlight, add_text, modify_pages, page_lines, replace_line, shift_line_down


def make_pdf(path):
    doc = fitz.open()
    for label in ("First page", "Second page", "Third page"):
        page = doc.new_page(width=300, height=300)
        page.insert_text((30, 60), label, fontsize=12)
    doc.set_toc([[1, "First", 1], [1, "Second", 2], [1, "Third", 3]])
    doc.save(path)
    doc.close()


def test_rotate_reorder_delete_and_insert_pages(tmp_path):
    path = tmp_path / "pages.pdf"
    inserted = tmp_path / "inserted.pdf"
    make_pdf(path)
    insert_doc = fitz.open()
    page = insert_doc.new_page(width=300, height=300)
    page.insert_text((30, 60), "Inserted page", fontsize=12)
    insert_doc.save(inserted)
    insert_doc.close()
    marks = [{"page": 0, "x0": 10, "y0": 10, "x1": 30, "y1": 20, "label": "one"},
             {"page": 2, "x0": 10, "y0": 10, "x1": 30, "y1": 20, "label": "three"}]

    modify_pages(path, "rotate", 1, marks)
    doc = fitz.open(path)
    assert doc[0].rotation == 90
    doc.close()

    _, _, marks = modify_pages(path, "reorder", 1, marks, target_page=3)
    doc = fitz.open(path)
    assert "Second page" in doc[0].get_text()
    assert "Third page" in doc[1].get_text()
    assert "First page" in doc[2].get_text()
    doc.close()

    page, count, updated = modify_pages(path, "insert", 2, marks, inserted_pdf=inserted.read_bytes())
    assert (page, count) == (2, 4)
    assert [mark["page"] for mark in updated] == [3, 2]
    doc = fitz.open(path)
    assert "Inserted page" in doc[1].get_text()
    doc.close()

    page, count, updated = modify_pages(path, "delete", 3, updated)
    assert (page, count) == (3, 3)
    assert [mark["page"] for mark in updated] == [2]
    doc = fitz.open(path)
    assert "Third page" not in "\n".join(item.get_text() for item in doc)
    doc.close()


def test_add_text_and_highlight_annotations(tmp_path):
    path = tmp_path / "annotations.pdf"
    make_pdf(path)
    add_text(path, 1, 40, 100, "Added note")
    add_highlight(path, 1, (25, 40, 120, 65))

    doc = fitz.open(path)
    page = doc[0]
    assert "Added note" in page.get_text()
    assert list(page.annots())
    doc.close()


def test_long_replacement_fits_original_line(tmp_path):
    path = tmp_path / "replace.pdf"
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    page.insert_text((30, 60), "Short", fontsize=12)
    page.insert_text((150, 60), "NEIGHBOR", fontsize=12)
    doc.save(path)
    doc.close()
    line = page_lines(path, 1)["lines"][0]

    replace_line(path, 1, (line["x0"], line["y0"], line["x1"], line["y1"]), "A much longer replacement", [])

    doc = fitz.open(path)
    spans = [span for block in doc[0].get_text("dict")["blocks"] if block.get("type") == 0 for row in block["lines"] for span in row["spans"]]
    replacement = next(span for span in spans if span["text"] == "A much longer replacement")
    neighbor = next(span for span in spans if span["text"] == "NEIGHBOR")
    assert replacement["size"] < 12
    assert replacement["bbox"][2] <= neighbor["bbox"][0]
    doc.close()


def test_enter_moves_text_onto_the_next_line(tmp_path):
    path = tmp_path / "shift.pdf"
    doc = fitz.open()
    page = doc.new_page(width=400, height=400)
    page.insert_text((30, 60), "Hello world", fontsize=12)
    page.insert_text((30, 84), "Next line", fontsize=12)
    page.insert_text((30, 108), "Last line", fontsize=12)
    doc.save(path)
    doc.close()
    lines = page_lines(path, 1)["lines"]
    assert [line["text"] for line in lines] == ["Hello world", "Next line", "Last line"]
    first = lines[0]
    shift_line_down(path, 1, (first["x0"], first["y0"], first["x1"], first["y1"]), "Hello world", len("Hello world"), [])

    updated = page_lines(path, 1)["lines"]
    assert [line["text"] for line in updated] == ["Hello world", "Next line", "Last line"]
    assert updated[0]["y0"] > first["y0"] + 8
    assert updated[1]["y0"] > lines[1]["y0"] + 8


def test_rotated_page_preview_coordinates_work_for_edits_and_annotations(tmp_path):
    path = tmp_path / "rotated.pdf"
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((30, 60), "Rotate target", fontsize=12)
    page.set_rotation(90)
    doc.save(path)
    doc.close()

    meta = page_lines(path, 1)
    line = meta["lines"][0]
    assert (meta["width"], meta["height"], meta["rotation"]) == (200, 300, 90)
    assert line["x0"] > 100 and line["y0"] < 50
    replace_line(path, 1, (line["x0"], line["y0"], line["x1"], line["y1"]), "Rotated edit", [])
    add_text(path, 1, 100, 100, "Rotated note")
    add_highlight(path, 1, (line["x0"], line["y0"], line["x1"], line["y1"]))

    doc = fitz.open(path)
    assert "Rotated edit" in doc[0].get_text()
    assert "Rotated note" in doc[0].get_text()
    assert list(doc[0].annots())
    doc.close()
