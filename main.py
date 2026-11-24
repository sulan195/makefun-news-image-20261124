"""Runtime submission script for the news-image-20261124 entry.

Standard library only: validates the bundled entry.png byte by byte
(PNG magic, 1024x1024 8-bit truecolour IHDR, chunk CRC-32 walk,
decompressed IDAT length, metadata-free, exact IEND trailer, <= 1 MiB)
and atomically copies it to $MAKEFUN_OUTPUT_DIR/entry.png.

Runs offline, with no network and no third-party packages.
"""

import os
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "entry.png"
MAX_BYTES = 1_048_576
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
EXPECTED_IDAT_LEN = 3_146_752  # 1024 rows * (1 filter byte + 1024 * 3)
FORBIDDEN_CHUNKS = (b"tIME", b"tEXt", b"zTXt", b"iTXt")


class InvalidEntry(Exception):
    """The bundled entry.png fails binary validation."""


def _read_u32(data, off):
    return struct.unpack(">I", data[off:off + 4])[0]


def validate_png_bytes(data):
    """Raise InvalidEntry on the first structural problem found."""
    if len(data) > MAX_BYTES:
        raise InvalidEntry("entry.png is %d bytes, over the 1 MiB cap"
                           % len(data))
    if data[:8] != PNG_MAGIC:
        raise InvalidEntry("bad PNG magic")
    if len(data) < 8 + 25:
        raise InvalidEntry("file too short for an IHDR chunk")
    off = 8
    seen_ihdr = False
    seen_iend = False
    idat = bytearray()
    while True:
        if off + 8 > len(data):
            raise InvalidEntry("truncated chunk header at offset %d" % off)
        length = _read_u32(data, off)
        ctype = data[off + 4:off + 8]
        if ctype in FORBIDDEN_CHUNKS:
            raise InvalidEntry("forbidden metadata chunk %r" % ctype)
        if off + 12 + length > len(data):
            raise InvalidEntry("truncated %r chunk" % ctype)
        stored_crc = _read_u32(data, off + 8 + length)
        actual_crc = zlib.crc32(data[off + 4:off + 8 + length]) & 0xFFFFFFFF
        if stored_crc != actual_crc:
            raise InvalidEntry("bad CRC-32 in %r chunk" % ctype)
        if not seen_ihdr and ctype != b"IHDR":
            raise InvalidEntry("first chunk must be IHDR, got %r" % ctype)
        if ctype == b"IHDR":
            if seen_ihdr:
                raise InvalidEntry("duplicate IHDR chunk")
            seen_ihdr = True
            if length != 13:
                raise InvalidEntry("IHDR length is %d, expected 13" % length)
            width, height = struct.unpack(">II", data[off + 8:off + 16])
            depth, colour, compression, filtering, interlace = data[off + 16:off + 21]
            if (width, height) != (1024, 1024):
                raise InvalidEntry("IHDR is %dx%d, expected 1024x1024"
                                   % (width, height))
            if depth != 8 or colour != 2:
                raise InvalidEntry("IHDR must be 8-bit truecolour RGB "
                                   "(depth %d, colour type %d)"
                                   % (depth, colour))
            if compression != 0 or filtering != 0 or interlace != 0:
                raise InvalidEntry("IHDR must be non-interlaced, "
                                   "standard compression/filter")
        elif ctype == b"IDAT":
            idat.extend(data[off + 8:off + 8 + length])
        elif ctype == b"IEND":
            if length != 0:
                raise InvalidEntry("IEND chunk must be empty")
            seen_iend = True
            if off + 12 != len(data):
                raise InvalidEntry("trailing bytes after IEND")
            break
        off += 12 + length
    if not seen_ihdr:
        raise InvalidEntry("missing IHDR chunk")
    if not seen_iend:
        raise InvalidEntry("missing IEND chunk")
    if not idat:
        raise InvalidEntry("missing IDAT data")
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error as exc:
        raise InvalidEntry("IDAT stream does not decompress: %s" % exc)
    if len(raw) != EXPECTED_IDAT_LEN:
        raise InvalidEntry("decompressed IDAT is %d bytes, expected %d"
                           % (len(raw), EXPECTED_IDAT_LEN))


def copy_verified_entry(src_path, out_dir):
    """Validate src_path, then atomically write out_dir/entry.png."""
    if not out_dir:
        raise InvalidEntry("MAKEFUN_OUTPUT_DIR is not set")
    out_path = Path(out_dir)
    if not out_path.is_dir():
        out_path.mkdir(parents=True, exist_ok=True)
    data = Path(src_path).read_bytes()
    validate_png_bytes(data)
    dest = out_path / "entry.png"
    if Path(src_path).resolve() == dest.resolve():
        # Validating in place: nothing to copy, bytes already verified.
        return dest
    tmp = out_path / (".entry.png.tmp-%d" % os.getpid())
    try:
        tmp.write_bytes(data)
        validate_png_bytes(tmp.read_bytes())
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()
    return dest


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "")
    if not out_dir:
        print("MAKEFUN_OUTPUT_DIR is not set", file=sys.stderr)
        return 1
    try:
        dest = copy_verified_entry(SRC, out_dir)
    except (InvalidEntry, OSError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    print("wrote %s" % dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
