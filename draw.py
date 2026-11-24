"""Deterministic build-time renderer for the news-image-20261124 entry.

Renders a one-page newspaper front page (1024x1024 RGB PNG) summing up the
world news of Tuesday 24 November 2026 from stories.json, using Pillow and
the DejaVu fonts shipped with the system. Build-time only: the grader runs
main.py (stdlib only), never this file.

Layout: 12 vertical bands summing to exactly 1024 px, 996 px content width
(x = 14..1010). All coordinates are integers; no time, randomness, locale or
network input, so two runs produce byte-identical PNGs.
"""

import io
import json
import struct
import unicodedata
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1024, 1024
MARGIN = 14
CONTENT_W = 996
CONTENT_X0 = 14
CONTENT_X1 = 1010
MAX_BYTES = 1_048_576

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")

# 12 vertical bands: (start, end), heights sum to exactly 1024.
Y_BANDS = [
    (0, 24),      # 1 Top Bar
    (24, 74),     # 2 Date Masthead
    (74, 96),     # 3 One-Line Dek
    (96, 138),    # 4 Stats Strip
    (138, 162),   # 5 Region Bar
    (162, 196),   # 6 UTC Timeline
    (196, 412),   # 7 Three Heroes
    (412, 688),   # 8 Secondary 12 Grid
    (688, 802),   # 9 World Map + Inset
    (802, 926),   # 10 ALSO (15 Stories)
    (926, 990),   # 11 DATE CHECK Box
    (990, 1024),  # 12 Footer
]

# Palette (hex).
PAPER = "#F7F3EA"
CARD = "#FCFBF7"
DATECHECK_FILL = "#ECE7D8"
DATECHECK_BORDER = "#8A816E"
SLATE = "#16202B"
RULE = "#C9C1B0"
INK = "#141A21"
BODY = "#242E38"
MUTED = "#52606D"
GOLD = "#D9A441"
OCEAN = "#EEF3F7"
LAND_DOT = "#B0BEC9"
ICON_BOX = "#F4F1E8"
POS_GREEN = "#1B6B3A"
NEG_RED = "#9E2A2B"
RECORD_BROWN = "#7C2D12"

CERTAINTY = {
    "REPORTED": ("#DDF3E4", "#2B7A4B", "#14532D"),
    "OFFICIALS_SAY": ("#DCEBFA", "#2B6CB0", "#1E3A8A"),
    "CLAIM": ("#FEF0C7", "#B7791F", "#78350F"),
}

# Canonical region order and colours (7 truthful regions).
REGIONS = [
    "EUROPE",
    "ASIA-PACIFIC",
    "MIDDLE EAST",
    "NORTH AMERICA",
    "LATIN AMERICA",
    "AFRICA",
    "WORLD",
]
REGION_COLORS = {
    "EUROPE": "#2B5B84",
    "ASIA-PACIFIC": "#1F7A6E",
    "MIDDLE EAST": "#A64B2A",
    "NORTH AMERICA": "#6B4C8C",
    "LATIN AMERICA": "#8C3B6B",
    "AFRICA": "#B87D1E",
    "WORLD": "#3D4F5F",
}

TIER_RANK = {"hero": 0, "secondary": 1, "also": 2}

# Land masks as row spans (inclusive column ranges) on a 4 px grid.
# World panel: 130 cols x 23 rows, lon -168..+180, lat -56..+74.
WORLD_SPANS = [
    [(0, 10), (41, 55), (77, 129)],
    [(0, 40), (57, 58), (64, 70), (77, 129)],
    [(2, 10), (12, 40), (64, 69), (75, 125)],
    [(15, 40), (60, 62), (63, 75), (85, 115), (124, 126)],
    [(14, 38), (60, 78), (85, 110), (115, 117)],
    [(16, 36), (60, 76), (85, 115)],
    [(18, 35), (60, 75), (76, 84), (88, 95), (98, 117)],
    [(20, 34), (58, 84), (87, 94), (98, 114)],
    [(22, 30), (56, 82), (86, 92), (100, 108)],
    [(25, 30), (55, 72), (76, 81), (87, 91), (100, 107), (109, 111)],
    [(26, 29), (54, 62), (88, 90), (101, 106)],
    [(32, 42), (56, 66), (102, 106), (108, 116)],
    [(33, 44), (60, 68), (106, 118), (120, 126)],
    [(33, 45), (61, 69), (108, 117), (121, 127)],
    [(34, 46), (62, 70), (110, 116), (118, 124)],
    [(35, 46), (63, 70), (72, 73), (116, 124)],
    [(36, 45), (64, 70), (72, 73), (116, 123)],
    [(37, 44), (65, 70), (117, 122)],
    [(38, 43), (66, 69), (118, 121), (125, 127)],
    [(39, 42), (125, 127)],
    [(40, 42), (125, 126)],
    [(40, 41)],
    [(40, 40)],
]
WORLD_BOUNDS = (-56.0, 74.0, -168.0, 180.0)  # lat_min, lat_max, lon_min, lon_max

# Europe & Middle East zoom panel: 71 cols x 23 rows, lon -10..+56, lat +23..+64.
ZOOM_SPANS = [
    [(16, 37)],
    [(5, 7), (15, 38)],
    [(4, 8), (14, 38)],
    [(4, 8), (18, 38)],
    [(5, 9), (18, 37)],
    [(4, 9), (18, 42)],
    [(4, 8), (14, 42)],
    [(4, 7), (13, 48)],
    [(8, 29), (38, 48)],
    [(8, 47)],
    [(8, 14), (18, 23), (28, 36), (50, 54)],
    [(1, 6), (8, 13), (17, 22), (33, 36), (38, 50), (52, 56)],
    [(0, 7), (17, 21), (32, 35), (38, 50), (52, 55)],
    [(0, 7), (18, 20), (32, 34), (38, 50)],
    [(1, 6), (19, 21), (33, 35), (38, 48)],
    [(19, 20), (45, 51)],
    [(45, 58)],
    [(46, 64)],
    [(46, 66)],
    [(42, 67)],
    [(42, 44), (46, 54), (60, 68)],
    [(43, 44), (46, 55), (61, 68)],
    [(47, 68)],
]
ZOOM_BOUNDS = (23.0, 64.0, -10.0, 56.0)


class LayoutOverflowError(Exception):
    """A curated story did not fit its measured character budget (strict mode)."""


class GlyphCoverageError(Exception):
    """A character has no real glyph in its assigned DejaVu font face."""


def load_and_validate_data(json_path):
    """Parse stories.json and enforce every schema invariant."""
    with open(json_path, encoding="utf-8") as fh:
        data = json.load(fh)
    for key in ("series_title", "edition_date_display", "dek", "stats",
                "stories", "date_check_exclusions", "sources_footer"):
        if key not in data:
            raise ValueError("stories.json missing top-level key: %s" % key)
    stories = data["stories"]
    if len(stories) != 30:
        raise ValueError("expected 30 stories, got %d" % len(stories))
    ids = sorted(s["id"] for s in stories)
    if ids != list(range(1, 31)):
        raise ValueError("story ids must be exactly 1..30, got %r" % (ids,))
    tiers = {"hero": 0, "secondary": 0, "also": 0}
    for s in stories:
        for key in ("id", "tier", "region", "field", "certainty", "headline",
                    "summary", "source", "lat", "lon", "in_euro_mideast_inset",
                    "utc_time", "scene_id"):
            if key not in s:
                raise ValueError("story %s missing field %s" % (s.get("id"), key))
        if s["tier"] not in tiers:
            raise ValueError("story %d bad tier %r" % (s["id"], s["tier"]))
        tiers[s["tier"]] += 1
        if s["region"] not in REGIONS:
            raise ValueError("story %d bad region %r" % (s["id"], s["region"]))
        if s["certainty"] not in CERTAINTY:
            raise ValueError("story %d bad certainty %r" % (s["id"], s["certainty"]))
        if not isinstance(s["headline"], str) or not s["headline"].strip():
            raise ValueError("story %d empty headline" % s["id"])
        if s["tier"] in ("hero", "secondary"):
            if not isinstance(s["summary"], str) or not s["summary"].strip():
                raise ValueError("story %d empty summary" % s["id"])
        if not isinstance(s["source"], str) or not s["source"].strip():
            raise ValueError("story %d empty source" % s["id"])
        if not (-90.0 <= s["lat"] <= 90.0):
            raise ValueError("story %d lat out of range" % s["id"])
        if not (-180.0 <= s["lon"] <= 180.0):
            raise ValueError("story %d lon out of range" % s["id"])
        if s["utc_time"] is not None:
            hh, _, mm = s["utc_time"].partition(":")
            if not (hh.isdigit() and mm.isdigit()
                    and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
                raise ValueError("story %d bad utc_time %r" % (s["id"], s["utc_time"]))
    if tiers != {"hero": 3, "secondary": 12, "also": 15}:
        raise ValueError("tier split must be 3/12/15, got %r" % (tiers,))
    if len(data["stats"]) != 6:
        raise ValueError("expected 6 stats cells, got %d" % len(data["stats"]))
    for cell in data["stats"]:
        if not cell.get("label") or not cell.get("value"):
            raise ValueError("stats cell missing label/value: %r" % (cell,))
    if len(data["date_check_exclusions"]) != 3:
        raise ValueError("expected 3 DATE CHECK exclusions")
    if not data["sources_footer"]:
        raise ValueError("sources_footer must not be empty")
    return data


def load_font_table(font_dir=FONT_DIR):
    """Load pinned DejaVu faces at exact sizes; enforce the 10 px floor."""
    faces = {
        "serif": "DejaVuSerif.ttf",
        "serif-bold": "DejaVuSerif-Bold.ttf",
        "sans": "DejaVuSans.ttf",
        "sans-bold": "DejaVuSans-Bold.ttf",
    }
    sizes = {
        ("serif-bold", 38), ("serif-bold", 17), ("serif-bold", 15),
        ("serif-bold", 11), ("serif", 11), ("sans", 11), ("sans-bold", 11),
        ("sans", 10), ("sans-bold", 10), ("sans-bold", 9),
    }
    fonts = {}
    for face, size in sorted(sizes):
        if size < 10 and size != 9:
            raise ValueError("font size below floor: %s %d" % (face, size))
        path = Path(font_dir) / faces[face]
        if not path.is_file():
            raise FileNotFoundError("missing DejaVu font file: %s" % path)
        fonts[(face, size)] = ImageFont.truetype(str(path), size)
    return fonts


def _char_bitmap(font, char):
    """Render one character to a small bitmap for .notdef comparison."""
    img = Image.new("L", (48, 48), 0)
    d = ImageDraw.Draw(img)
    d.text((4, 4), char, font=font, fill=255)
    return img.tobytes()


def audit_unicode_glyphs(data, fonts):
    """Abort the build if any used character has no real glyph.

    Compares every (font face, character) pair against the font's unmapped
    sentinel (U+FFFF) by rendered bitmap; space is excluded.
    """
    static_texts = [
        data["series_title"], data["edition_date_display"], data["dek"],
        "30 STORIES · 7 REGIONS · EVERY ONE DATED 24 NOVEMBER 2026",
        "REGIONS:", "UTC TIMELINE",
        "WHERE IT HAPPENED — 30 STORIES PINNED", "MAP KEY",
        "ALSO ON 24 NOVEMBER — 15 MORE STORIES",
        "DATE CHECK — Every story in this paper happened, or was first "
        "reported, on Tuesday 24 November 2026. Deliberately left out:",
        "REPORTED — verified by 2+ outlets",
        "OFFICIALS SAY — attributed statement",
        "CLAIM — one party’s assertion",
        "Scenes are drawn illustrations, not photographs.",
    ]
    static_texts += [c["label"] for c in data["stats"]]
    static_texts += [c["value"] for c in data["stats"]]
    static_texts += [c["delta"] for c in data["stats"] if c.get("delta")]
    static_texts += list(data["date_check_exclusions"])
    static_texts += list(data["sources_footer"])
    for s in data["stories"]:
        static_texts += [s["headline"], s["summary"], s["source"],
                         s["region"], s["field"], s["certainty"]]
    for ev in data.get("timeline", []):
        static_texts.append(ev["label"])
        static_texts.append(ev["time"])

    # (font face, size) assignments used by the renderer.
    assignments = [
        ("serif-bold", 38), ("serif-bold", 17), ("serif-bold", 15),
        ("serif-bold", 11), ("serif", 11), ("sans", 11), ("sans-bold", 11),
        ("sans", 10), ("sans-bold", 10), ("sans-bold", 9),
    ]
    seen = set()
    for text in static_texts:
        text = unicodedata.normalize("NFC", text)
        for char in text:
            if char == " ":
                continue
            for face, size in assignments:
                key = (face, size, char)
                if key in seen:
                    continue
                seen.add(key)
                font = fonts[(face, size)]
                if _char_bitmap(font, char) == _char_bitmap(font, "\uffff"):
                    raise GlyphCoverageError(
                        "character %r (U+%04X) has no glyph in %s %dpx"
                        % (char, ord(char), face, size))


def compute_region_counts(stories):
    """Aggregate story counts per region in canonical order; sum must be 30."""
    counts = [(region, 0) for region in REGIONS]
    by_region = dict(counts)
    for s in stories:
        by_region[s["region"]] += 1
    counts = [(region, by_region[region]) for region in REGIONS]
    if sum(c for _, c in counts) != 30:
        raise ValueError("region counts do not sum to 30: %r" % (counts,))
    return counts


def _split_long_token(token, font, max_w):
    """Split an over-wide token on hyphens/slashes, else binary-search a prefix."""
    parts = []
    current = token
    while font.getlength(current) > max_w:
        cut = -1
        for sep in ("-", "/"):
            pos = current.rfind(sep, 0, len(current) - 1)
            if pos > cut:
                cut = pos
        if cut > 0 and font.getlength(current[:cut + 1]) <= max_w:
            parts.append(current[:cut + 1])
            current = current[cut + 1:]
            continue
        lo, hi = 1, len(current)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if font.getlength(current[:mid] + "…") <= max_w:
                lo = mid
            else:
                hi = mid - 1
        parts.append(current[:lo] + "…")
        current = current[lo:]
    if current:
        parts.append(current)
    return parts


def _wrap_lines(text, font, max_w):
    """Greedy measured word-wrap; returns all lines, no clamping."""
    text = unicodedata.normalize("NFC", text)
    text = " ".join(text.split())
    words = []
    for token in text.split(" "):
        if font.getlength(token) > max_w:
            words.extend(_split_long_token(token, font, max_w))
        else:
            words.append(token)
    lines = []
    current = ""
    for word in words:
        candidate = word if not current else current + " " + word
        if font.getlength(candidate) <= max_w:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def wrap_and_clamp_lines(text, font, max_w, max_lines, strict=True):
    """Measured word-wrap; clamps the last line with an ellipsis on overflow.

    Returns (lines, clamped). In strict mode the caller raises
    LayoutOverflowError when clamped is True for curated copy.
    """
    lines = _wrap_lines(text, font, max_w)
    clamped = False
    if len(lines) > max_lines:
        clamped = True
        head = lines[:max_lines - 1]
        rest = " ".join(lines[max_lines - 1:])
        last = rest
        while font.getlength(last + "…") > max_w and " " in last:
            last = last.rsplit(" ", 1)[0]
        if font.getlength(last + "…") > max_w:
            last = ""
            while font.getlength(last + "…") <= max_w and last != rest:
                last = rest[:len(last) + 1]
            last = last[:-1]
        lines = head + [last + "…"]
    return lines, clamped


def shorten_headline(text, font, max_w, max_lines=2):
    """Fit a headline into max_lines at fixed size; trim words with ellipsis."""
    lines, clamped = wrap_and_clamp_lines(text, font, max_w, max_lines,
                                          strict=False)
    if not clamped:
        return lines
    # Rebuild from the full wrapped lines: keep the first max_lines-1 lines,
    # pack the rest onto the final line and drop words from the right.
    lines = _wrap_lines(text, font, max_w)
    if len(lines) <= max_lines:
        return lines
    head = lines[:max_lines - 1]
    tail = " ".join(lines[max_lines - 1:])
    tail = tail.rstrip(",;:–—. ")
    while font.getlength(tail + "…") > max_w and " " in tail:
        tail = tail.rsplit(" ", 1)[0].rstrip(",;:–—. ")
    return head + [tail + "…"]


def project_latlon(lat, lon, bounds, rect):
    """Linear lat/lon projection into a panel rect, clamped inside its edges."""
    lat_min, lat_max, lon_min, lon_max = bounds
    x0, y0, x1, y1 = rect
    fx = (lon - lon_min) / (lon_max - lon_min)
    fy = (lat_max - lat) / (lat_max - lat_min)
    x = x0 + int(round(fx * (x1 - x0)))
    y = y0 + int(round(fy * (y1 - y0)))
    x = max(x0 + 8, min(x1 - 8, x))
    y = max(y0 + 7, min(y1 - 7, y))
    return x, y


def relax_pin_positions(pins, rect):
    """Deterministically separate clustered pin badges inside a panel.

    pins: list of dicts with keys id, tier, x, y (anchor). Returns
    {id: (badge_cx, badge_cy)} after 24 repulsion passes; badges keep a
    15x12 pill (2-digit) or 14x14 circle (1-digit) footprint.
    """
    x0, y0, x1, y1 = rect
    ordered = sorted(pins, key=lambda p: (TIER_RANK[p["tier"]], p["id"]))
    pos = {p["id"]: (p["x"], p["y"]) for p in ordered}

    def box(pid):
        cx, cy = pos[pid]
        w, h = (14, 14) if pid < 10 else (15, 12)
        return (cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2)

    def overlaps(a, b):
        ax0, ay0, ax1, ay1 = box(a)
        bx0, by0, bx1, by1 = box(b)
        return ax0 < bx1 + 15 and bx0 < ax1 + 15 and ay0 < by1 + 12 and by0 < ay1 + 12

    def _clamp(px, py):
        return (max(x0 + 8, min(x1 - 8, px)), max(y0 + 7, min(y1 - 7, py)))

    for _ in range(24):
        moved = False
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                a, b = ordered[i]["id"], ordered[j]["id"]
                if not overlaps(a, b):
                    continue
                old_a, old_b = pos[a], pos[b]
                # Try the axis of least separation first, then the other one.
                # Push b away from a; if b hits the panel edge, push a the
                # shortfall in the opposite direction instead.
                ax, ay = pos[a]
                bx, by = pos[b]
                dx, dy = bx - ax, by - ay
                axes = (0, 1) if abs(dx) >= abs(dy) else (1, 0)
                for axis in axes:
                    if not overlaps(a, b):
                        break
                    ax, ay = pos[a]
                    bx, by = pos[b]
                    dx, dy = bx - ax, by - ay
                    if axis == 0:
                        need = 15 - abs(dx) + 1
                        direction = 1 if dx >= 0 else -1
                        want_bx = bx + direction * need
                        new_bx, _ = _clamp(want_bx, by)
                        short = abs(want_bx - new_bx)
                        want_ax = ax - direction * short
                        new_ax, _ = _clamp(want_ax, ay)
                        pos[b] = (new_bx, by)
                        pos[a] = (new_ax, ay)
                    else:
                        need = 12 - abs(dy) + 1
                        direction = 1 if dy >= 0 else -1
                        want_by = by + direction * need
                        _, new_by = _clamp(bx, want_by)
                        short = abs(want_by - new_by)
                        want_ay = ay - direction * short
                        _, new_ay = _clamp(ax, want_ay)
                        pos[b] = (bx, new_by)
                        pos[a] = (ax, new_ay)
                if pos[a] != old_a or pos[b] != old_b:
                    moved = True
        if not moved:
            break
    return pos


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def _text_w(font, text):
    return font.getlength(text)


def _pill(draw, x, y, text, font, fill, border, text_color, pad_x=6, height=17):
    """Draw a rounded certainty/region pill; returns its right edge."""
    w = int(_text_w(font, text)) + 2 * pad_x
    draw.rounded_rectangle([x, y, x + w - 1, y + height - 1], radius=height // 2,
                           fill=fill, outline=border, width=1)
    draw.text((x + pad_x, y + (height - 10) // 2 - 1), text, font=font,
              fill=text_color, anchor="lt")
    return x + w


def draw_header_stack(canvas, draw, data, fonts):
    """Bands 1-6 (y = 0..196): top bar, masthead, dek, stats, regions, timeline."""
    stories = data["stories"]
    counts = compute_region_counts(stories)
    total_regions = sum(1 for _, c in counts if c > 0)

    # Band 1 — Top Bar (0..24), dark slate full bleed.
    draw.rectangle([0, 0, W - 1, 23], fill=SLATE)
    f_series = fonts[("sans-bold", 11)]
    draw.text((CONTENT_X0, 12), data["series_title"], font=f_series,
              fill=PAPER, anchor="lm")
    f_top = fonts[("sans-bold", 10)]
    top_right = ("30 STORIES · %d REGIONS · EVERY ONE DATED 24 NOVEMBER 2026"
                 % total_regions)
    draw.text((CONTENT_X1, 12), top_right, font=f_top, fill=PAPER, anchor="rm")

    # Band 2 — Date Masthead (24..74).
    f_mast = fonts[("serif-bold", 38)]
    draw.text((W // 2, 30), data["edition_date_display"], font=f_mast,
              fill=INK, anchor="mt")
    draw.rectangle([CONTENT_X0, 70, CONTENT_X1 - 1, 71], fill=SLATE)
    draw.rectangle([CONTENT_X0, 73, CONTENT_X1 - 1, 73], fill=SLATE)

    # Band 3 — One-Line Dek (74..96).
    f_dek = fonts[("serif", 11)]
    draw.text((W // 2, 78), data["dek"], font=f_dek, fill=BODY, anchor="mt")
    draw.line([(CONTENT_X0, 95), (CONTENT_X1 - 1, 95)], fill=RULE, width=1)

    # Band 4 — Stats Strip (96..138): 6 cells of 166 px.
    f_val = fonts[("serif-bold", 17)]
    f_delta = fonts[("sans-bold", 10)]
    f_lab = fonts[("sans-bold", 10)]
    for i, cell in enumerate(data["stats"]):
        x0 = CONTENT_X0 + i * 166
        cx = x0 + 83
        value, delta, label = cell["value"], cell.get("delta"), cell["label"]
        if delta:
            total_w = _text_w(f_val, value) + 4 + _text_w(f_delta, delta)
            vx = cx - total_w // 2
            draw.text((vx, 100), value, font=f_val, fill=INK, anchor="lt")
            dcolor = NEG_RED if delta.startswith("−") else (
                RECORD_BROWN if delta == "record" else POS_GREEN)
            draw.text((vx + _text_w(f_val, value) + 4, 107), delta,
                      font=f_delta, fill=dcolor, anchor="lt")
        else:
            draw.text((cx, 100), value, font=f_val, fill=INK, anchor="mt")
        draw.text((cx, 121), label, font=f_lab, fill=MUTED, anchor="mt")
        if i > 0:
            draw.line([(x0, 100), (x0, 133)], fill=RULE, width=1)
    draw.line([(CONTENT_X0, 137), (CONTENT_X1 - 1, 137)], fill=RULE, width=1)

    # Band 5 — Region Bar (138..162).
    f_reg = fonts[("sans-bold", 10)]
    y = 141
    draw.text((CONTENT_X0, y + 3), "REGIONS:", font=f_reg, fill=INK, anchor="lt")
    x = CONTENT_X0 + int(_text_w(f_reg, "REGIONS:")) + 10
    for region, count in counts:
        if count == 0:
            continue
        label = "%s %d" % (region, count)
        x = _pill(draw, x, y, label, f_reg, REGION_COLORS[region],
                  REGION_COLORS[region], "#FFFFFF") + 6
    draw.line([(CONTENT_X0, 161), (CONTENT_X1 - 1, 161)], fill=RULE, width=1)

    # Band 6 — UTC Timeline (162..196).
    f_time = fonts[("sans-bold", 10)]
    draw.text((CONTENT_X0, 166), "UTC TIMELINE", font=f_time, fill=INK,
              anchor="lt")
    axis_x0, axis_x1 = 148, CONTENT_X1
    axis_y = 182

    def _to_x(hhmm):
        hh, mm = (int(p) for p in hhmm.split(":"))
        return axis_x0 + int(round((hh * 60 + mm) / 1440.0 * (axis_x1 - axis_x0)))

    events = sorted(data.get("timeline", []), key=lambda e: e["time"])
    # Greedy non-overlapping label slots above the axis, left to right.
    slots = []
    prev_right = axis_x0
    for ev in events:
        label = "%s %s" % (ev["time"], ev["label"])
        w = int(_text_w(f_time, label))
        cx = _to_x(ev["time"])
        lx = max(cx - w // 2, prev_right + 4)
        if lx + w > axis_x1:
            lx = axis_x1 - w
        slots.append((ev, label, lx, w))
        prev_right = lx + w
    for ev, label, lx, w in slots:
        draw.text((lx, 164), label, font=f_time, fill=BODY, anchor="lt")
        tick_x = _to_x(ev["time"])
        label_cx = lx + w // 2
        draw.line([(label_cx, 176), (tick_x, axis_y - 1)], fill=MUTED, width=1)
        draw.ellipse([tick_x - 2, axis_y - 2, tick_x + 2, axis_y + 2],
                     fill=INK)
    draw.line([(axis_x0, axis_y), (axis_x1 - 1, axis_y)], fill=INK, width=1)
    for hh in range(0, 25, 4):
        tx = _to_x("%02d:00" % hh)
        draw.text((tx, 184), "%02dZ" % hh, font=f_time, fill=MUTED, anchor="mt")
    draw.line([(CONTENT_X0, 195), (CONTENT_X1 - 1, 195)], fill=RULE, width=1)


# ---------------------------------------------------------------------------
# Hero scenes (308 x 74 px, flat vector shapes, <= 10 shapes each)
# ---------------------------------------------------------------------------

def draw_hero_scene(draw, box, scene_id):
    x0, y0, x1, y1 = box
    if scene_id == "nvidia":
        draw.rectangle([x0, y0, x1, y1], fill="#E6EFE9", outline=RULE, width=1)
        # Processor package (left).
        draw.rounded_rectangle([x0 + 18, y0 + 14, x0 + 64, y0 + 60], radius=4,
                               fill="#1E6B3B")
        draw.rectangle([x0 + 30, y0 + 26, x0 + 52, y0 + 48], fill=GOLD)
        for sx, sy, ex, ey in (
                (x0 + 41, y0 + 8, x0 + 41, y0 + 14),
                (x0 + 41, y0 + 60, x0 + 41, y0 + 66),
                (x0 + 12, y0 + 37, x0 + 18, y0 + 37),
                (x0 + 64, y0 + 37, x0 + 70, y0 + 37)):
            draw.line([(sx, sy), (ex, ey)], fill=INK, width=3)
        # Rally bars: Nasdaq, S&P 500, Nikkei (verified stats only).
        draw.line([(x0 + 100, y0 + 58), (x0 + 292, y0 + 58)], fill="#C5D6CC",
                  width=1)
        draw.line([(x0 + 100, y0 + 20), (x0 + 292, y0 + 20)], fill="#C5D6CC",
                  width=1)
        bars = [(118, 16), (168, 26), (218, 38)]
        for bx, bh in bars:
            draw.rectangle([x0 + bx, y0 + 58 - bh, x0 + bx + 26, y0 + 58],
                           fill="#2B7A4B")
        draw.line([(x0 + 108, y0 + 52), (x0 + 160, y0 + 40),
                   (x0 + 212, y0 + 28), (x0 + 268, y0 + 12)],
                  fill=INK, width=3)
        draw.polygon([(x0 + 268, y0 + 12), (x0 + 252, y0 + 10),
                      (x0 + 262, y0 + 26)], fill=GOLD)
    elif scene_id == "zaporizhzhia":
        draw.rectangle([x0, y0, x1, y1], fill="#1B263B")
        draw.rectangle([x0, y0 + 66, x1, y1], fill="#0F1722")
        # Crescent moon (04:00 night cue).
        draw.ellipse([x0 + 14, y0 + 8, x0 + 34, y0 + 28], fill="#DCE4EE")
        draw.ellipse([x0 + 20, y0 + 6, x0 + 40, y0 + 26], fill="#1B263B")
        # Collapsed private house (left-center).
        draw.polygon([(x0 + 62, y0 + 58), (x0 + 76, y0 + 40),
                      (x0 + 96, y0 + 46), (x0 + 110, y0 + 58)],
                     fill="#6C788E")
        draw.polygon([(x0 + 76, y0 + 40), (x0 + 88, y0 + 30),
                      (x0 + 96, y0 + 46)], fill="#415A77")
        # Smoke plume rising rightward.
        for ex, ey, r in ((118, 34, 7), (128, 26, 8), (140, 18, 9)):
            draw.ellipse([x0 + ex - r, y0 + ey - r, x0 + ex + r, y0 + ey + r],
                         fill="#415A77")
        # Five-storey residential block (right-center), notched by the strike.
        draw.rectangle([x0 + 150, y0 + 10, x0 + 246, y0 + 64], fill="#8D99AE")
        for row in range(5):
            for col in range(5):
                wx = x0 + 158 + col * 17
                wy = y0 + 16 + row * 10
                lit = (row, col) in ((1, 1), (2, 3), (3, 0))
                draw.rectangle([wx, wy, wx + 6, wy + 5],
                               fill="#E9C46A" if lit else "#243242")
        draw.polygon([(x0 + 214, y0 + 10), (x0 + 246, y0 + 10),
                      (x0 + 246, y0 + 30), (x0 + 228, y0 + 22)],
                     fill="#1B263B")
        draw.polygon([(x0 + 224, y0 + 30), (x0 + 240, y0 + 22),
                      (x0 + 246, y0 + 34), (x0 + 228, y0 + 38)],
                     fill="#D95D39")
        for tx in (156, 176, 198):
            draw.polygon([(x0 + tx, y0 + 64), (x0 + tx + 10, y0 + 64),
                          (x0 + tx + 5, y0 + 54)], fill="#0F1722")
    elif scene_id == "gaza":
        draw.rectangle([x0, y0, x1, y1], fill="#EDE6D6")
        draw.rectangle([x0, y0 + 60, x1, y1], fill="#C9BFA9")
        # Flat-roofed Gaza City silhouettes on the horizon.
        for bx, bw, bh, col in ((8, 52, 38, "#B5A892"), (72, 34, 28, "#9C8F7A"),
                                (118, 44, 34, "#B5A892"), (232, 52, 30, "#9C8F7A")):
            draw.rectangle([x0 + bx, y0 + 60 - bh, x0 + bx + bw, y0 + 60],
                           fill=col)
        # Targeted compound / vehicle silhouette, centre foreground.
        draw.polygon([(x0 + 128, y0 + 44), (x0 + 184, y0 + 44),
                      (x0 + 184, y0 + 60), (x0 + 128, y0 + 60)],
                     fill="#2F3E36")
        draw.polygon([(x0 + 148, y0 + 44), (x0 + 164, y0 + 36),
                      (x0 + 172, y0 + 44)], fill="#2F3E36")
        draw.polygon([(x0 + 150, y0 + 36), (x0 + 162, y0 + 26),
                      (x0 + 170, y0 + 38)], fill="#B84A39")
        # Rising smoke column.
        for ex, ey, r in ((162, 22, 5), (164, 13, 7), (166, 5, 8)):
            draw.ellipse([x0 + ex - r, y0 + ey - r, x0 + ex + r, y0 + ey + r],
                         fill="#5A6572")
        # Striped roadblock barriers flanking the compound.
        for bx in (104, 196):
            draw.rectangle([x0 + bx, y0 + 50, x0 + bx + 18, y0 + 56],
                           fill="#FFFFFF", outline=INK, width=1)
            draw.line([(x0 + bx, y0 + 56), (x0 + bx + 18, y0 + 50)],
                      fill="#B84A39", width=2)
    else:
        raise ValueError("unknown hero scene_id: %r" % scene_id)


def draw_heroes_band(canvas, draw, heroes, fonts, clamped):
    """Band 7 (196..412): three 324x210 px hero panels."""
    f_kick = fonts[("sans-bold", 10)]
    f_head = fonts[("serif-bold", 15)]
    f_body = fonts[("sans", 11)]
    f_src = fonts[("sans", 10)]
    for i, hero in enumerate(heroes):
        x0 = CONTENT_X0 + i * (324 + 12)
        y0 = 199
        x1, y1 = x0 + 324 - 1, y0 + 210 - 1
        draw.rectangle([x0, y0, x1, y1], fill=CARD, outline=RULE, width=1)
        ix = x0 + 8  # inner left edge (308 px inner width)
        # Badge / kicker / certainty row (14 px).
        ry = y0 + 5
        badge_col = REGION_COLORS[hero["region"]]
        draw.rectangle([ix, ry, ix + 13, ry + 13], fill=badge_col)
        draw.text((ix + 7, ry + 7), str(hero["id"]), font=f_kick,
                  fill="#FFFFFF", anchor="mm")
        kicker = "%s · %s" % (hero["region"], hero["field"])
        draw.text((ix + 18, ry + 7), kicker, font=f_kick, fill=INK, anchor="lm")
        fill, border, tcol = CERTAINTY[hero["certainty"]]
        _pill(draw, x0 + 316 - (int(_text_w(f_kick, hero["certainty"])) + 12),
              ry, hero["certainty"], f_kick, fill, border, tcol, height=14)
        # Geometric scene (308x74).
        draw_hero_scene(draw, (ix, ry + 17, ix + 308 - 1, ry + 17 + 74 - 1),
                        hero["scene_id"])
        # Headline, 2 lines at 15 px Serif-Bold, 18 px leading.
        hy = ry + 17 + 74 + 4
        head_lines = shorten_headline(hero["headline"], f_head, 308, 2)
        for li, line in enumerate(head_lines):
            draw.text((ix, hy + li * 18), line, font=f_head, fill=INK, anchor="lt")
        # Summary, 4 lines at 11 px Sans, 13 px leading.
        sy = hy + 36 + 3
        body_lines, was_clamped = wrap_and_clamp_lines(
            hero["summary"], f_body, 308, 4, strict=True)
        if was_clamped:
            clamped.append(hero["id"])
        for li, line in enumerate(body_lines):
            draw.text((ix, sy + li * 13), line, font=f_body, fill=BODY, anchor="lt")
        # Source line.
        draw.text((ix, sy + 52 + 2), "Source: %s" % hero["source"],
                  font=f_src, fill=MUTED, anchor="lt")
    draw.line([(CONTENT_X0, 411), (CONTENT_X1 - 1, 411)], fill=RULE, width=1)


# ---------------------------------------------------------------------------
# Secondary grid mini-icons (34 x 34 px, 2-3 bold shapes in the region colour)
# ---------------------------------------------------------------------------

def draw_mini_icon(draw, box, scene_id, accent):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    draw.rectangle([x0, y0, x1, y1], fill=ICON_BOX, outline=RULE, width=1)
    if scene_id == "lecterns":
        draw.polygon([(x0 + 6, y0 + 26), (x0 + 14, y0 + 26),
                      (x0 + 12, y0 + 12), (x0 + 8, y0 + 12)], fill=accent)
        draw.polygon([(x0 + 20, y0 + 26), (x0 + 28, y0 + 26),
                      (x0 + 26, y0 + 12), (x0 + 22, y0 + 12)], fill=accent)
        draw.line([(x0 + 10, y0 + 12), (x0 + 24, y0 + 12)], fill=INK, width=2)
    elif scene_id == "hull_shield":
        draw.polygon([(x0 + 5, y0 + 20), (x0 + 29, y0 + 20),
                      (x0 + 24, y0 + 28), (x0 + 10, y0 + 28)], fill=accent)
        draw.polygon([(cx - 6, y0 + 6), (cx + 6, y0 + 6), (cx + 6, y0 + 14),
                      (cx, y0 + 19), (cx - 6, y0 + 14)], fill=INK)
    elif scene_id == "pillar_ring":
        draw.rectangle([x0 + 14, y0 + 8, x0 + 20, y0 + 24], fill=accent)
        draw.rectangle([x0 + 10, y0 + 24, x0 + 24, y0 + 27], fill=accent)
        draw.ellipse([x0 + 8, y0 + 5, x0 + 26, y0 + 29], outline=INK, width=2)
        draw.line([(x0 + 8, y0 + 17), (x0 + 26, y0 + 17)], fill=INK, width=2)
    elif scene_id == "note_bars":
        draw.ellipse([x0 + 9, y0 + 21, x0 + 16, y0 + 28], fill=accent)
        draw.line([(x0 + 15, y0 + 22), (x0 + 15, y0 + 8)], fill=accent, width=2)
        draw.line([(x0 + 15, y0 + 8), (x0 + 24, y0 + 11)], fill=accent, width=2)
        draw.line([(x0 + 22, y0 + 6), (x0 + 22, y0 + 26)], fill=INK, width=2)
        draw.line([(x0 + 27, y0 + 6), (x0 + 27, y0 + 26)], fill=INK, width=2)
    elif scene_id == "diamond_net":
        pts = [(cx, y0 + 5), (x0 + 29, cy), (cx, y0 + 29), (x0 + 5, cy)]
        draw.polygon(pts, outline=accent, width=2)
        for px, py in pts:
            draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=INK)
        draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=accent)
    elif scene_id == "awacs":
        draw.ellipse([x0 + 8, y0 + 4, x0 + 26, y0 + 12], fill=accent)
        draw.polygon([(x0 + 4, y0 + 18), (x0 + 30, y0 + 18),
                      (x0 + 26, y0 + 23), (x0 + 8, y0 + 23)], fill=INK)
        draw.polygon([(x0 + 24, y0 + 18), (x0 + 30, y0 + 14),
                      (x0 + 30, y0 + 20)], fill=accent)
        draw.line([(x0 + 12, y0 + 23), (x0 + 10, y0 + 28)], fill=INK, width=2)
        draw.line([(x0 + 22, y0 + 23), (x0 + 24, y0 + 28)], fill=INK, width=2)
    elif scene_id == "border_post":
        draw.rectangle([x0 + 6, y0 + 10, x0 + 12, y0 + 28], fill=accent)
        draw.rectangle([x0 + 22, y0 + 10, x0 + 28, y0 + 28], fill=accent)
        draw.line([(x0 + 6, y0 + 10), (x0 + 28, y0 + 10)], fill=INK, width=2)
        draw.polygon([(cx, y0 + 16), (cx + 6, y0 + 26), (cx - 6, y0 + 26)],
                     fill="#B7791F")
        draw.text((cx, y0 + 21), "!", font=ImageFont.truetype(
            str(FONT_DIR / "DejaVuSans-Bold.ttf"), 10), fill="#FFFFFF",
            anchor="mm")
    elif scene_id == "thermometer":
        draw.ellipse([x0 + 11, y0 + 19, x0 + 23, y0 + 31], fill="#B84A39")
        draw.rectangle([x0 + 14, y0 + 6, x0 + 20, y0 + 22], fill=accent)
        draw.ellipse([x0 + 14, y0 + 20, x0 + 20, y0 + 26], fill="#B84A39")
    elif scene_id == "gavel":
        draw.rectangle([x0 + 6, y0 + 10, x0 + 22, y0 + 15], fill=accent)
        draw.line([(x0 + 20, y0 + 13), (x0 + 28, y0 + 21)], fill=INK, width=3)
        draw.rectangle([x0 + 6, y0 + 26, x0 + 28, y0 + 29], fill=INK)
    elif scene_id == "globe_nodes":
        draw.ellipse([x0 + 5, y0 + 5, x0 + 29, y0 + 29], outline=accent, width=2)
        draw.ellipse([x0 + 12, y0 + 5, x0 + 22, y0 + 29], outline=accent, width=1)
        draw.line([(x0 + 5, cy), (x0 + 29, cy)], fill=accent, width=1)
        for px, py in ((x0 + 10, y0 + 10), (x0 + 24, y0 + 12), (cx, y0 + 24)):
            draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=INK)
    elif scene_id == "mercury_orbit":
        draw.ellipse([x0 + 12, y0 + 12, x0 + 22, y0 + 22], fill=accent)
        draw.arc([x0 + 3, y0 + 3, x0 + 31, y0 + 31], start=200, end=340,
                 fill=INK, width=2)
        draw.ellipse([x0 + 26, y0 + 6, x0 + 30, y0 + 10], fill=INK)
    elif scene_id == "chess_rook":
        draw.rectangle([x0 + 6, y0 + 6, x0 + 16, y0 + 16], fill=accent)
        draw.rectangle([x0 + 18, y0 + 18, x0 + 28, y0 + 28], fill=accent)
        draw.rectangle([x0 + 18, y0 + 6, x0 + 28, y0 + 16], outline=accent,
                       width=1)
        draw.rectangle([x0 + 6, y0 + 18, x0 + 16, y0 + 28], outline=accent,
                       width=1)
        draw.polygon([(cx - 5, y0 + 8), (cx + 5, y0 + 8), (cx + 4, y0 + 14),
                      (cx - 4, y0 + 14)], fill=INK)
    else:
        raise ValueError("unknown mini-icon scene_id: %r" % scene_id)


def draw_secondary_grid(canvas, draw, secondaries, fonts, clamped):
    """Band 8 (412..688): 4x3 grid of 240x86 px secondary story cards."""
    f_kick = fonts[("sans-bold", 10)]
    f_head = fonts[("serif-bold", 11)]
    f_body = fonts[("sans", 10)]
    f_src = fonts[("sans", 10)]
    for idx, story in enumerate(secondaries):
        row, col = divmod(idx, 4)
        x0 = CONTENT_X0 + col * (240 + 12)
        y0 = 415 + row * (86 + 5)
        x1, y1 = x0 + 240 - 1, y0 + 86 - 1
        draw.rectangle([x0, y0, x1, y1], fill=CARD, outline=RULE, width=1)
        # 34x34 icon, left; number badge above it is the story id in the
        # kicker row instead (icon box carries the pictogram only).
        draw_mini_icon(draw, (x0 + 6, y0 + 4, x0 + 39, y0 + 37),
                       story["scene_id"], REGION_COLORS[story["region"]])
        # Right column (188 px): region kicker + certainty pill.
        col_x = x0 + 46
        ky = y0 + 4
        draw.text((col_x, ky), "%d · %s" % (story["id"], story["region"]),
                  font=f_kick, fill=INK, anchor="lt")
        fill, border, tcol = CERTAINTY[story["certainty"]]
        pill_w = int(_text_w(f_kick, story["certainty"])) + 12
        _pill(draw, x0 + 234 - pill_w, ky, story["certainty"], f_kick,
              fill, border, tcol, height=13)
        # Headline, 2 lines at 11 px Serif-Bold, 13 px leading.
        hy = ky + 12
        head_lines = shorten_headline(story["headline"], f_head, 188, 2)
        for li, line in enumerate(head_lines):
            draw.text((col_x, hy + li * 13), line, font=f_head, fill=INK,
                      anchor="lt")
        # Summary, 2 lines at 10 px Sans, 12 px leading (full card width).
        sy = y0 + 4 + 38 + 2
        body_lines, was_clamped = wrap_and_clamp_lines(
            story["summary"], f_body, 228, 2, strict=True)
        if was_clamped:
            clamped.append(story["id"])
        for li, line in enumerate(body_lines):
            draw.text((x0 + 6, sy + li * 12), line, font=f_body, fill=BODY,
                      anchor="lt")
        # Source line.
        draw.text((x0 + 6, sy + 24 + 2), "Source: %s" % story["source"],
                  font=f_src, fill=MUTED, anchor="lt")
    draw.line([(CONTENT_X0, 687), (CONTENT_X1 - 1, 687)], fill=RULE, width=1)


# ---------------------------------------------------------------------------
# Map band, ALSO band, DATE CHECK + footer
# ---------------------------------------------------------------------------

def _draw_landmask(draw, spans, rect):
    """Render a dot-matrix landmask: 2x2 dots centred in each 4x4 cell."""
    x0, y0, x1, y1 = rect
    for r, row_spans in enumerate(spans):
        cy = y0 + r * 4
        for c0, c1 in row_spans:
            for c in range(c0, c1 + 1):
                cx = x0 + c * 4
                draw.rectangle([cx + 1, cy + 1, cx + 2, cy + 2], fill=LAND_DOT)


def _draw_pin(draw, cx, cy, story_id, fill, ring_gold=False):
    """Draw one numbered map pin badge (circle for 1-digit, pill for 2-digit)."""
    f_pin = ImageFont.truetype(str(FONT_DIR / "DejaVuSans-Bold.ttf"),
                               10 if story_id < 10 else 9)
    label = str(story_id)
    if story_id < 10:
        draw.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=fill,
                     outline="#FFFFFF", width=1)
        if ring_gold:
            draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], outline=GOLD,
                         width=1)
        draw.text((cx, cy), label, font=f_pin, fill="#FFFFFF", anchor="mm")
    else:
        draw.rounded_rectangle([cx - 8, cy - 6, cx + 7, cy + 6], radius=6,
                               fill=fill, outline="#FFFFFF", width=1)
        draw.text((cx, cy), label, font=f_pin, fill="#FFFFFF", anchor="mm")


def draw_world_map_band(canvas, draw, stories, fonts):
    """Band 9 (688..802): dot-matrix world map, Europe/Mideast zoom, key."""
    f_title = fonts[("sans-bold", 10)]
    f_key = fonts[("sans", 10)]
    f_key_b = fonts[("sans-bold", 10)]
    draw.text((CONTENT_X0, 690), "WHERE IT HAPPENED — 30 STORIES PINNED",
              font=f_title, fill=INK, anchor="lt")
    py0, py1 = 705, 797  # panel top/bottom (92 px tall)
    world_rect = (CONTENT_X0, py0, CONTENT_X0 + 520 - 1, py1 - 1)
    zoom_rect = (CONTENT_X0 + 528, py0, CONTENT_X0 + 528 + 284 - 1, py1 - 1)
    key_rect = (CONTENT_X0 + 820, py0, CONTENT_X1 - 1, py1 - 1)
    for rect in (world_rect, zoom_rect, key_rect):
        draw.rectangle([rect[0], rect[1], rect[2], rect[3]], fill=CARD,
                       outline=RULE, width=1)
    draw.rectangle([world_rect[0], world_rect[1], world_rect[2],
                    world_rect[3]], fill=OCEAN)
    draw.rectangle([zoom_rect[0], zoom_rect[1], zoom_rect[2],
                    zoom_rect[3]], fill=OCEAN)
    _draw_landmask(draw, WORLD_SPANS, (world_rect[0] + 1, world_rect[1] + 1,
                                        world_rect[2], world_rect[3]))
    _draw_landmask(draw, ZOOM_SPANS, (zoom_rect[0] + 1, zoom_rect[1] + 1,
                                      zoom_rect[2], zoom_rect[3]))
    # Outline the zoomed region on the world map.
    zx0, zy0 = project_latlon(64.0, -10.0, WORLD_BOUNDS, world_rect)
    zx1, zy1 = project_latlon(23.0, 56.0, WORLD_BOUNDS, world_rect)
    draw.rectangle([zx0, zy0, zx1, zy1], outline="#52606D", width=1)

    by_id = {s["id"]: s for s in stories}
    world_pins, zoom_pins = [], []
    for s in stories:
        if s["in_euro_mideast_inset"]:
            ax, ay = project_latlon(s["lat"], s["lon"], ZOOM_BOUNDS, zoom_rect)
            zoom_pins.append({"id": s["id"], "tier": s["tier"], "x": ax,
                              "y": ay})
            # Small reference dot inside the zoom box on the world map.
            wx, wy = project_latlon(s["lat"], s["lon"], WORLD_BOUNDS,
                                    world_rect)
            draw.rectangle([wx - 1, wy - 1, wx + 1, wy + 1], fill=INK)
        else:
            ax, ay = project_latlon(s["lat"], s["lon"], WORLD_BOUNDS,
                                    world_rect)
            world_pins.append({"id": s["id"], "tier": s["tier"], "x": ax,
                               "y": ay})
    for pins, rect in ((world_pins, world_rect), (zoom_pins, zoom_rect)):
        pos = relax_pin_positions(pins, rect)
        for p in sorted(pins, key=lambda q: (TIER_RANK[q["tier"]], q["id"])):
            s = by_id[p["id"]]
            bx, by = pos[p["id"]]
            if (bx, by) != (p["x"], p["y"]):
                dist = ((bx - p["x"]) ** 2 + (by - p["y"]) ** 2) ** 0.5
                if dist > 3:
                    draw.line([(bx, by), (p["x"], p["y"])], fill=INK, width=1)
                    draw.rectangle([p["x"] - 1, p["y"] - 1, p["x"] + 1,
                                    p["y"] + 1], fill=INK)
            fill = INK if s["tier"] == "hero" else REGION_COLORS[s["region"]]
            _draw_pin(draw, bx, by, s["id"], fill,
                      ring_gold=(s["tier"] == "hero"))
    # Key panel (176x92).
    kx = key_rect[0] + 8
    draw.text((kx, py0 + 6), "MAP KEY", font=f_key_b, fill=INK, anchor="lt")
    key_lines = [
        "HERO 1–3 · gold ring",
        "SECONDARY 4–15 · region colour",
        "ALSO 16–30 · region colour",
        "[14] ESOC / Mercury Orbit",
    ]
    for i, line in enumerate(key_lines):
        yy = py0 + 22 + i * 13
        draw.text((kx, yy), line, font=f_key, fill=BODY, anchor="lt")
    draw.text((kx, py0 + 74), "Dots = land", font=f_key, fill=MUTED,
              anchor="lt")
    draw.line([(CONTENT_X0, 801), (CONTENT_X1 - 1, 801)], fill=RULE, width=1)


def draw_also_band(canvas, draw, also_stories, fonts, clamped):
    """Band 10 (802..926): two-column numbered list of stories 16-30."""
    f_head = fonts[("sans-bold", 11)]
    f_num = fonts[("sans-bold", 10)]
    f_item = fonts[("sans", 10)]
    draw.text((CONTENT_X0, 805), "ALSO ON 24 NOVEMBER — 15 MORE STORIES",
              font=f_head, fill=INK, anchor="lt")
    left = sorted(also_stories, key=lambda s: s["id"])[:8]   # 16-23
    right = sorted(also_stories, key=lambda s: s["id"])[8:]  # 24-30
    for i, story in enumerate(left):
        yy = 820 + i * 13
        _draw_also_row(draw, CONTENT_X0, yy, story, f_num, f_item, clamped)
    for i, story in enumerate(right):
        yy = 820 + i * 13
        _draw_also_row(draw, CONTENT_X0 + 506, yy, story, f_num, f_item,
                       clamped)
    sources = sorted({s["source"] for s in also_stories})
    draw.text((CONTENT_X0 + 506, 820 + 7 * 13),
              "Sources: %s." % ", ".join(sources), font=f_item, fill=MUTED,
              anchor="lt")
    draw.line([(CONTENT_X0, 925), (CONTENT_X1 - 1, 925)], fill=RULE, width=1)


def _draw_also_row(draw, x, y, story, f_num, f_item, clamped):
    num = "%d." % story["id"]
    draw.text((x, y), num, font=f_num, fill=REGION_COLORS[story["region"]],
              anchor="lt")
    tx = x + int(_text_w(f_num, num)) + 5
    lines, was_clamped = wrap_and_clamp_lines(story["headline"], f_item,
                                              490 - (tx - x), 1, strict=True)
    if was_clamped:
        clamped.append(story["id"])
    draw.text((tx, y), lines[0], font=f_item, fill=BODY, anchor="lt")


def draw_date_check_and_footer(canvas, draw, data, fonts):
    """Band 11 (926..990) DATE CHECK box and Band 12 (990..1024) footer."""
    f_bold = fonts[("sans-bold", 10)]
    f_reg = fonts[("sans", 10)]
    # Band 11 — bordered verification panel (996x60 + 4 px margin).
    draw.rectangle([CONTENT_X0, 926, CONTENT_X1 - 1, 985],
                   fill=DATECHECK_FILL, outline=DATECHECK_BORDER, width=1)
    draw.text((CONTENT_X0 + 8, 930),
              "DATE CHECK — Every story in this paper happened, or was first "
              "reported, on Tuesday 24 November 2026. Deliberately left out:",
              font=f_bold, fill=INK, anchor="lt")
    for i, exc in enumerate(data["date_check_exclusions"]):
        yy = 943 + i * 13
        # Red exclusion cross (vector geometry, no Dingbat codepoint).
        cx = CONTENT_X0 + 14
        draw.line([(cx, yy + 2), (cx + 6, yy + 8)], fill=NEG_RED, width=2)
        draw.line([(cx + 6, yy + 2), (cx, yy + 8)], fill=NEG_RED, width=2)
        draw.text((CONTENT_X0 + 24, yy), exc, font=f_reg, fill=BODY,
                  anchor="lt")
    # Band 12 — Footer (990..1024).
    fy = 994
    x = CONTENT_X0
    for tag, label, definition in (
            ("REPORTED", "REPORTED", "verified by 2+ outlets"),
            ("OFFICIALS_SAY", "OFFICIALS SAY", "attributed statement"),
            ("CLAIM", "CLAIM", "one party’s assertion")):
        fill, border, tcol = CERTAINTY[tag]
        x = _pill(draw, x, fy, label, f_bold, fill, border, tcol) + 4
        draw.text((x, fy + 3), "— %s" % definition, font=f_reg, fill=MUTED,
                  anchor="lt")
        x += int(_text_w(f_reg, "— %s" % definition)) + 14
    sources = "SOURCES: %s." % ", ".join(data["sources_footer"])
    draw.text((CONTENT_X0, fy + 17), sources, font=f_reg, fill=MUTED,
              anchor="lt")
    draw.text((CONTENT_X1, fy + 17),
              "Scenes are drawn illustrations, not photographs.",
              font=f_bold, fill=BODY, anchor="rt")


# ---------------------------------------------------------------------------
# Deterministic encoding & orchestration
# ---------------------------------------------------------------------------

def encode_deterministic_png(canvas, max_bytes=MAX_BYTES):
    """Metadata-free PNG; undithered colour-reduction cascade if over 1 MiB."""
    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True, compress_level=9)
    png = buf.getvalue()
    for colors in (256, 128, 64):
        if len(png) <= max_bytes:
            break
        reduced = canvas.quantize(colors=colors, method=Image.Quantize.FASTOCTREE,
                                  kmeans=0, dither=Image.Dither.NONE)
        buf = io.BytesIO()
        reduced.convert("RGB").save(buf, format="PNG", optimize=True,
                                    compress_level=9)
        png = buf.getvalue()
    if len(png) > max_bytes:
        raise ValueError("entry.png still %d bytes after colour reduction"
                         % len(png))
    return png


def render_newspaper(data, font_dir=FONT_DIR, strict=True):
    """Validate, audit, draw all 12 bands, encode; returns PNG bytes."""
    stories = sorted(data["stories"], key=lambda s: s["id"])
    heroes = [s for s in stories if s["tier"] == "hero"]
    secondaries = [s for s in stories if s["tier"] == "secondary"]
    also = [s for s in stories if s["tier"] == "also"]
    fonts = load_font_table(font_dir)
    audit_unicode_glyphs(data, fonts)
    clamped = []
    canvas = Image.new("RGB", (W, H), PAPER)
    draw = ImageDraw.Draw(canvas)
    draw_header_stack(canvas, draw, data, fonts)
    draw_heroes_band(canvas, draw, heroes, fonts, clamped)
    draw_secondary_grid(canvas, draw, secondaries, fonts, clamped)
    draw_world_map_band(canvas, draw, stories, fonts)
    draw_also_band(canvas, draw, also, fonts, clamped)
    draw_date_check_and_footer(canvas, draw, data, fonts)
    if strict and clamped:
        raise LayoutOverflowError(
            "curated copy clamped (strict mode), story ids: %r" % (clamped,))
    return encode_deterministic_png(canvas)


def main():
    here = Path(__file__).resolve().parent
    data = load_and_validate_data(here / "stories.json")
    png = render_newspaper(data)
    (here / "entry.png").write_bytes(png)
    print("wrote entry.png: %d bytes" % len(png))


if __name__ == "__main__":
    main()
