from __future__ import annotations

import fitz


def inspect_cover_stamp(page: fitz.Page) -> dict[str, object]:
    """TEST23 §A: Mutual of America stamp is on the upper right of the cover.

    Purpose:
        TEST23 §A: Mutual of America stamp is on the upper right of the cover. The company stamp is a graphic (wording is often not selectable PDF text). Pass if cover text + a graphic are present, or if an upper-right image itself has the red + navy mark from the stamp. This does **not** prove Mutual of America is the only named entity. Other TPA names on the cover remain a manual reviewer check.

    Args:
        page: One PDF page.

    Returns:
        dict[str, object].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        inspect_cover_stamp(page) returns dict[str, object].

    Side effects:
        None. This function only reads data and returns a value.
    """
    text = (page.get_text("text") or "").lower()
    has_name = "mutual of america" in text
    has_group = "financial group" in text
    image_top_right = _image_in_upper_right(page)
    colors = _brand_colors_in_upper_right(page) or _brand_colors_in_upper_right_images(page)
    has_wording = has_name or has_group

    logo = bool(image_top_right or colors)
    # Real cover letters embed the stamp as an image; require selectable text
    # only when the graphic is not the red+navy company mark.
    found = bool((has_wording and logo) or (image_top_right and colors))
    parts: list[str] = []
    if has_name:
        parts.append("cover text has Mutual of America")
    if has_group:
        parts.append("cover text has Financial Group")
    if image_top_right:
        parts.append("image in upper-right")
    if colors:
        parts.append("red and navy mark in upper-right")
    if not parts:
        detail = "No Mutual of America wording or logo on the cover (TEST23 §A)"
    elif not logo:
        detail = "Wording found, but no logo graphic in the upper-right"
    elif not found:
        detail = "Upper-right graphic found, but Mutual of America wording is missing"
    else:
        detail = "MOA stamp likely present: " + "; ".join(parts)
    return {
        "mentions_moa": has_wording or bool(image_top_right and colors),
        "moa_logo_found": found,
        "moa_stamp_detail": detail,
    }


def _image_in_upper_right(page: fitz.Page) -> bool:
    """Image in upper right.

    Purpose:
        Image in upper right.

    Args:
        page: One PDF page.

    Returns:
        bool.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _image_in_upper_right(page) returns bool.

    Side effects:
        None. This function only reads data and returns a value.
    """
    width, height = float(page.rect.width), float(page.rect.height)
    if width <= 0 or height <= 0:
        return False
    for info in page.get_images(full=True):
        xref = info[0]
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            continue
        for rect in rects:
            cx = (rect.x0 + rect.x1) / 2
            cy = (rect.y0 + rect.y1) / 2
            if cx >= width * 0.45 and cy <= height * 0.40:
                return True
    return False


def _brand_colors_in_upper_right(page: fitz.Page) -> bool:
    """MOA mark uses a red chevron and a dark navy wordmark.

    Purpose:
        MOA mark uses a red chevron and a dark navy wordmark.

    Args:
        page: One PDF page.

    Returns:
        bool.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _brand_colors_in_upper_right(page) returns bool.

    Side effects:
        None. This function only reads data and returns a value.
    """
    clip = fitz.Rect(
        page.rect.width * 0.50,
        page.rect.y0,
        page.rect.x1,
        page.rect.height * 0.38,
    )
    if clip.width < 8 or clip.height < 8:
        return False
    pix = page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2), clip=clip, alpha=False)
    try:
        return _pixmap_has_brand_colors(pix)
    finally:
        pix = None


def _brand_colors_in_upper_right_images(page: fitz.Page) -> bool:
    """Inspect embedded images so the stamp is not washed out by page whitespace.

    Purpose:
        Inspect embedded images so the stamp is not washed out by page whitespace.

    Args:
        page: One PDF page.

    Returns:
        bool.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _brand_colors_in_upper_right_images(page) returns bool.

    Side effects:
        None. This function only reads data and returns a value.
    """
    width, height = float(page.rect.width), float(page.rect.height)
    if width <= 0 or height <= 0 or page.parent is None:
        return False
    for info in page.get_images(full=True):
        xref = info[0]
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            continue
        for rect in rects:
            cx = (rect.x0 + rect.x1) / 2
            cy = (rect.y0 + rect.y1) / 2
            if cx < width * 0.45 or cy > height * 0.40:
                continue
            pix = _pixmap_from_xref(page.parent, xref)
            if pix is None:
                continue
            try:
                if _pixmap_has_brand_colors(pix):
                    return True
            finally:
                pix = None
    return False


def _pixmap_from_xref(doc: fitz.Document, xref: int) -> fitz.Pixmap | None:
    """Pixmap from xref.

    Purpose:
        Pixmap from xref.

    Args:
        doc: Open PDF. Must not be closed.
        xref: Xref. Type: int.

    Returns:
        a fitz.Pixmap | None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _pixmap_from_xref(doc, 1) returns a fitz.Pixmap | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    try:
        extracted = doc.extract_image(xref)
        pix = fitz.Pixmap(extracted["image"])
        if pix.n >= 4 or (pix.colorspace and pix.colorspace.n != 3):
            converted = fitz.Pixmap(fitz.csRGB, pix)
            pix = None
            return converted
        return pix
    except Exception:
        return None


def _pixmap_has_brand_colors(pix: fitz.Pixmap) -> bool:
    """Pixmap has brand colors.

    Purpose:
        Pixmap has brand colors.

    Args:
        pix: Pix. Type: fitz.Pixmap.

    Returns:
        True or False.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _pixmap_has_brand_colors(pix) returns True or False.

    Side effects:
        None. This function only reads data and returns a value.
    """
    raw = pix.samples
    channels = pix.n
    reds = 0
    navies = 0
    total = max(1, pix.width * pix.height)
    step = max(channels, 1)
    for index in range(0, len(raw) - 2, step):
        r, g, b = raw[index], raw[index + 1], raw[index + 2]
        if r > 145 and r > g + 35 and r > b + 20:
            reds += 1
        elif b > 45 and b >= r + 12 and g < 110 and r < 90 and (r + g + b) < 240:
            navies += 1
    return (reds / total) >= 0.004 and (navies / total) >= 0.004
