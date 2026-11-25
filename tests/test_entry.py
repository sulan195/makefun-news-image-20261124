"""Verification suite for the news-image-20261124 entry.

Covers schema invariants, story/region counts, date/stats/exclusions,
geometry budget, typography floor + zero truncation, glyph coverage, map pin
geometry, byte-identical determinism, PNG chunk structure, the stdlib-only
runtime copier (positive + negative cases), and the 300 px legibility probe.

Run:  python3 -m pytest tests/test_entry.py -v
   or python3 tests/test_entry.py   (built-in runner, no pytest needed)
"""

import ast
import copy
import json
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import draw as D
import main as M
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def _load_data():
    return D.load_and_validate_data(ROOT / "stories.json")


def _render_bytes():
    data = _load_data()
    return D.render_newspaper(data)


# 1. Story count, tiers and ids -------------------------------------------
def test_story_count_tiers_and_ids():
    data = _load_data()
    stories = data["stories"]
    assert len(stories) == 30
    assert sorted(s["id"] for s in stories) == list(range(1, 31))
    tiers = {"hero": 0, "secondary": 0, "also": 0}
    for s in stories:
        tiers[s["tier"]] += 1
    assert tiers == {"hero": 3, "secondary": 12, "also": 15}
    assert [s["id"] for s in stories if s["tier"] == "hero"] == [1, 2, 3]
    assert [s["id"] for s in stories if s["tier"] == "secondary"] == list(
        range(4, 16))
    assert [s["id"] for s in stories if s["tier"] == "also"] == list(
        range(16, 31))


# 2. Region counts sum and match -------------------------------------------
def test_region_counts_sum_and_match():
    data = _load_data()
    counts = D.compute_region_counts(data["stories"])
    assert sum(c for _, c in counts) == 30
    expected = [("EUROPE", 7), ("EAST ASIA", 2), ("SOUTHEAST ASIA", 1),
                ("SOUTH ASIA", 2), ("MIDDLE EAST", 5), ("NORTH AMERICA", 3),
                ("LATIN AMERICA", 3), ("AFRICA", 5), ("OCEANIA", 1),
                ("WORLD", 1)]
    assert counts == expected
    top_bar = "30 STORIES · %d REGIONS · EVERY ONE DATED 24 NOVEMBER 2026" % (
        sum(1 for _, c in counts if c > 0))
    assert top_bar == ("30 STORIES · 10 REGIONS · EVERY ONE DATED "
                       "24 NOVEMBER 2026")
    for s in data["stories"]:
        assert s["region"] in dict(counts)


# 3. Date, stats, exclusions and disclaimer ---------------------------------
def test_date_stats_exclusions_and_disclaimer():
    data = _load_data()
    assert data["edition_date_display"] == "TUESDAY, 24 NOVEMBER 2026"
    assert "24 NOVEMBER 2026" in data["edition_date_display"]
    stats = {(c["label"], c["value"]) for c in data["stats"]}
    for label, value in (("NASDAQ", "+6.51%"), ("S&P 500", "+4.73%"),
                         ("NIKKEI", "+3.91%"), ("BRENT CRUDE", "$86.7"),
                         ("GOLD", "$3,620.4"), ("UK HEAT DEATHS", "5,258")):
        assert (label, value) in stats
    deltas = {c["label"]: c.get("delta") for c in data["stats"]}
    assert deltas["BRENT CRUDE"] == "−2.99%"
    assert deltas["GOLD"] == "−0.85%"
    assert deltas["UK HEAT DEATHS"] == "record"
    joined = " ".join(data["date_check_exclusions"])
    assert "Alcaraz" in joined and "22 November" in joined
    assert "Benghazi" in joined and "22–23 November" in joined
    assert "Iran sanctions" in joined and "23 November" in joined
    assert len(data["date_check_exclusions"]) == 3
    assert "Reuters" in data["sources_footer"]
    assert "Scenes are drawn illustrations, not photographs."


# 4. Vertical geometry budget ----------------------------------------------
def test_vertical_geometry_budget_1024():
    bands = D.Y_BANDS
    assert bands[0][0] == 0
    assert bands[-1][1] == 1024
    total = 0
    for (s0, e0), (s1, e1) in zip(bands, bands[1:]):
        assert e0 == s1, "bands not contiguous: %r -> %r" % ((s0, e0), (s1, e1))
        assert e0 > s0
        total += e0 - s0
    total += bands[-1][1] - bands[-1][0]
    assert total == 1024
    assert [e - s for s, e in bands] == [24, 50, 22, 42, 24, 34, 216, 276,
                                         114, 124, 64, 34]


# 5. Typography floor and zero truncation ------------------------------------
def test_typography_floor_and_zero_truncation():
    fonts = D.load_font_table()
    for (face, size) in fonts:
        assert size >= 9, "font below 9 px: %s %d" % (face, size)
        if size == 9:
            assert face == "sans-bold", "only pin numerals may be 9 px"
    # Strict render raises LayoutOverflowError on any clamped curated copy.
    png = _render_bytes()
    assert len(png) > 0


# 6. Unicode glyph audit ------------------------------------------------------
def test_unicode_glyph_audit():
    data = _load_data()
    fonts = D.load_font_table()
    D.audit_unicode_glyphs(data, fonts)  # must not raise
    for name in ("Parastoo Ahmadi", "Javokhir Sindarov"):
        assert name in json.dumps(data, ensure_ascii=False)
    poisoned = copy.deepcopy(data)
    poisoned["stories"][0]["summary"] += " \uffff"
    try:
        D.audit_unicode_glyphs(poisoned, fonts)
    except D.GlyphCoverageError:
        pass
    else:
        raise AssertionError("glyph audit did not reject U+FFFF")


# 7. Map pins in bounds and disjoint -----------------------------------------
def _pin_layout():
    data = _load_data()
    world_rect = (14, 705, 533, 796)
    zoom_rect = (542, 705, 825, 796)
    world_pins, zoom_pins = [], []
    for s in data["stories"]:
        if s["in_euro_mideast_inset"]:
            ax, ay = D.project_latlon(s["lat"], s["lon"], D.ZOOM_BOUNDS,
                                      zoom_rect)
            zoom_pins.append({"id": s["id"], "tier": s["tier"], "x": ax,
                              "y": ay})
        else:
            ax, ay = D.project_latlon(s["lat"], s["lon"], D.WORLD_BOUNDS,
                                      world_rect)
            world_pins.append({"id": s["id"], "tier": s["tier"], "x": ax,
                               "y": ay})
    return (world_pins, world_rect), (zoom_pins, zoom_rect)


def test_map_pins_in_bounds_and_disjoint():
    for pins, rect in _pin_layout():
        x0, y0, x1, y1 = rect
        pos = D.relax_pin_positions(pins, rect)
        boxes = []
        for p in pins:
            cx, cy = pos[p["id"]]
            w, h = (14, 14) if p["id"] < 10 else (15, 12)
            assert x0 <= cx - w // 2 and cx + w // 2 <= x1
            assert y0 <= cy - h // 2 and cy + h // 2 <= y1
            boxes.append((p["id"], cx - w // 2, cy - h // 2,
                          cx + w // 2, cy + h // 2))
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                overlap = (a[1] < b[3] and b[1] < a[3]
                           and a[2] < b[4] and b[2] < a[4])
                assert not overlap, "map pins %d and %d overlap" % (a[0], b[0])


# 8. Determinism: double render ----------------------------------------------
def test_determinism_double_render():
    data = _load_data()
    a = D.render_newspaper(data)
    b = D.render_newspaper(data)
    assert a == b, "two renders differ"
    entry = ROOT / "entry.png"
    if entry.is_file():
        assert a == entry.read_bytes(), "render differs from entry.png"


# 9. PNG size cap and chunk structure ------------------------------------------
def _iter_chunks(data):
    assert data[:8] == M.PNG_MAGIC
    off = 8
    while True:
        length = struct.unpack(">I", data[off:off + 4])[0]
        ctype = data[off + 4:off + 8]
        yield ctype, data[off + 8:off + 8 + length], off
        crc = struct.unpack(">I", data[off + 8 + length:off + 12 + length])[0]
        assert crc == (zlib.crc32(data[off + 4:off + 8 + length])
                       & 0xFFFFFFFF), "bad CRC in %r" % ctype
        off += 12 + length
        if ctype == b"IEND":
            assert off == len(data), "trailing bytes after IEND"
            return


def test_png_size_cap_and_chunk_structure():
    png = _render_bytes()
    assert len(png) <= 1_048_576, "entry.png is %d bytes" % len(png)
    chunks = list(_iter_chunks(png))
    types = [c for c, _, _ in chunks]
    assert types[0] == b"IHDR" and types[-1] == b"IEND"
    assert b"tIME" not in types and b"tEXt" not in types
    ihdr = chunks[0][1]
    width, height = struct.unpack(">II", ihdr[0:8])
    assert (width, height) == (1024, 1024)
    assert ihdr[8] == 8 and ihdr[9] == 2, "must be 8-bit RGB"
    idat = b"".join(payload for c, payload, _ in chunks if c == b"IDAT")
    raw = zlib.decompress(idat)
    assert len(raw) == 3_146_752


# 10. main.py: stdlib-only, copy, negative validation ---------------------------
def _rebuild_png(png, mutate_ihdr=None, bad_crc=False, trailing=b""):
    """Rebuild a PNG with an optional IHDR field mutation (CRC fixed)."""
    out = bytearray(png[:8])
    off = 8
    while off < len(png):
        length = struct.unpack(">I", png[off:off + 4])[0]
        ctype = png[off + 4:off + 8]
        payload = bytearray(png[off + 8:off + 8 + length])
        if ctype == b"IHDR" and mutate_ihdr:
            mutate_ihdr(payload)
        crc = zlib.crc32(ctype + bytes(payload)) & 0xFFFFFFFF
        if bad_crc and ctype == b"IHDR":
            crc ^= 0xFFFFFFFF
        out += struct.pack(">I", length) + ctype + bytes(payload)
        out += struct.pack(">I", crc)
        off += 12 + length
        if ctype == b"IEND":
            break
    return bytes(out) + trailing


def test_main_stdlib_only_copy_and_negative_validation():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module.split(".")[0])
    stdlib = sys.stdlib_module_names
    assert imported <= stdlib, "non-stdlib imports: %r" % (imported - stdlib)
    assert "PIL" not in imported and "requests" not in imported

    png = _render_bytes()
    M.validate_png_bytes(png)  # must not raise
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        dest = M.copy_verified_entry(ROOT / "entry.png", tmp)
        assert dest.read_bytes() == png

    def expect_invalid(data, why):
        try:
            M.validate_png_bytes(data)
        except M.InvalidEntry:
            return
        raise AssertionError("expected InvalidEntry: %s" % why)

    expect_invalid(b"not a png" + png[9:], "corrupted magic")
    expect_invalid(_rebuild_png(
        png, mutate_ihdr=lambda p: p.__setitem__(slice(4, 8),
                                                 struct.pack(">I", 1023))),
        "1024x1023 dimensions")
    expect_invalid(_rebuild_png(
        png, mutate_ihdr=lambda p: p.__setitem__(9, 3)),
        "palette colour type 3")
    expect_invalid(_rebuild_png(png, bad_crc=True), "bad CRC-32")
    expect_invalid(_rebuild_png(png, trailing=b"\x00"), "trailing byte")
    expect_invalid(png + b"\x00" * (1_048_577 - len(png)), "over 1 MiB")


# 11. 300 px downscale legibility probe ------------------------------------------
def test_300px_downscale_legibility_probe():
    png = _render_bytes()
    img = Image.open(__import__("io").BytesIO(png)).convert("RGB")
    small = img.resize((300, 300), Image.LANCZOS)
    px = small.load()

    def luma(x, y):
        r, g, b = px[x, y]
        return 0.299 * r + 0.587 * g + 0.114 * b

    # Masthead contrast (band 2 maps to y 7..21 at 300 px).
    vals = [luma(x, y) for x in range(20, 280) for y in range(7, 22)]
    assert max(vals) - min(vals) >= 140, "masthead contrast too low"

    # Clean gutter separation: hero gutters (x ~100, ~199) measured only
    # over the hero band rows, secondary gutters (x ~76, ~150, ~224) only
    # over the grid rows; mean luma must stay near paper.
    for gx, y0, y1 in ((100, 60, 118), (199, 60, 118),
                       (76, 125, 198), (150, 125, 198), (224, 125, 198)):
        gutter = [luma(x, y) for x in range(gx, gx + 2)
                  for y in range(y0, y1)]
        assert sum(gutter) / len(gutter) >= 235, "gutter at x=%d is dirty" % gx

    # Hero illustrations keep contrast and colour clusters at 300 px.
    for (hx0, hy0) in ((6, 65), (103, 65), (200, 65)):
        region = [px[x, y] for x in range(hx0, hx0 + 90)
                  for y in range(hy0, hy0 + 22)]
        lums = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b in region]
        mean = sum(lums) / len(lums)
        var = sum((v - mean) ** 2 for v in lums) / len(lums)
        assert var ** 0.5 >= 22, "hero scene at x=%d is muddy" % hx0
        clusters = {}
        for r, g, b in region:
            key = (r // 32, g // 32, b // 32)
            clusters[key] = clusters.get(key, 0) + 1
        big = [k for k, n in clusters.items() if n >= len(region) * 0.03]
        assert len(big) >= 3, "hero scene at x=%d has <3 colour clusters" % hx0

    # Overall ink-to-paper balance.
    ink = 0
    total = 300 * 300
    for y in range(300):
        for x in range(300):
            r, g, b = px[x, y]
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            chroma = max(r, g, b) - min(r, g, b)
            if lum < 220 or chroma > 20:
                ink += 1
    frac = ink / total
    assert 0.14 <= frac <= 0.34, "ink density %.3f out of range" % frac


# Built-in runner ----------------------------------------------------------------
TESTS = [v for k, v in sorted(globals().items())
         if k.startswith("test_") and callable(v)]


if __name__ == "__main__":
    failures = 0
    for fn in TESTS:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - report and continue
            failures += 1
            print("FAIL %s: %s: %s" % (fn.__name__, type(exc).__name__, exc))
        else:
            print("PASS %s" % fn.__name__)
    print("%d passed, %d failed" % (len(TESTS) - failures, failures))
    sys.exit(1 if failures else 0)
