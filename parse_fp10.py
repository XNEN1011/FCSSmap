"""
Parse FCSS .fp10 map files without OCR.

The map file stores one variable-length record per hex.  For Coburg the
header says 81 x 40, and the file contains 3240 validated hex records.

Observed height convention:
    stored_height: 300, 350, 400, ...
    map label:     275, 325, 375, ...

So the displayed per-hex elevation is stored_height - 25.
"""

from __future__ import annotations

import argparse
import json
import struct
from collections import Counter
from pathlib import Path


DEFAULT_FP10 = Path(
    r"N:\SteamLibrary\steamapps\common\Flashpoint Campaigns Southern Storm"
    r"\Modules\FCSS\Maps\Coburg.fp10"
)
DEFAULT_OUT = Path(r"N:\claude\fcss\hex_data_fp10.json")
DEFAULT_MAPS_DIR = DEFAULT_FP10.parent
DEFAULT_OUT_DIR = Path(r"N:\claude\fcss\maps_json")
DEFAULT_INDEX = Path(r"N:\claude\fcss\maps_index.json")

CELL_MARKER = 666
HEIGHT_LABEL_OFFSET = 25


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def read_header(data: bytes) -> dict:
    name_len = u32(data, 4)
    name = data[8 : 8 + name_len * 2].decode("utf-16-le", errors="replace")
    base = 8 + name_len * 2
    return {
        "version": u32(data, 0),
        "name": name,
        "cols": u32(data, base + 8),
        "rows": u32(data, base + 12),
    }


def is_printable_ascii_utf16(data: bytes, offset: int, chars: int) -> bool:
    end = offset + chars * 2
    if end > len(data):
        return False
    try:
        text = data[offset:end].decode("utf-16-le")
    except UnicodeDecodeError:
        return False
    return all(32 <= ord(ch) < 127 for ch in text)


def strings_between(data: bytes, start: int, end: int) -> list[str]:
    """Return plausible UTF-16LE strings inside one variable-length cell record."""
    strings: list[str] = []
    pos = start
    while pos + 4 <= end:
        n = u32(data, pos)
        if 3 <= n < 300 and pos + 4 + n * 2 <= end:
            text_offset = pos + 4
            if is_printable_ascii_utf16(data, text_offset, n):
                text = data[text_offset : text_offset + n * 2].decode("utf-16-le")
                strings.append(text)
                pos = text_offset + n * 2
                continue
        pos += 2
    return strings


def find_first_cell_start(data: bytes, first_marker: int) -> int:
    for offset in range(max(0, first_marker - 3000), first_marker, 2):
        if offset + 32 > len(data):
            continue
        values = [u32(data, offset + i * 4) for i in range(8)]
        if 1 <= values[0] <= 30 and 0 <= values[6] <= 2000 and values[7] == 0xFFFFFFFF:
            return offset
    raise RuntimeError("Could not find first cell before first 666 marker")


def find_cell_starts(data: bytes, expected_cells: int | None = None) -> list[int]:
    """Find FCSS variable-length cell records.

    The first cell directly follows two map-scale integers and lacks the 666
    marker.  Every later cell begins with the little-endian u32 marker 666.
    Records are only 2-byte aligned because UTF-16 strings have variable
    lengths, so byte-pattern search is intentional here.
    """
    marker_starts = []
    marker = struct.pack("<I", CELL_MARKER)
    pos = data.find(marker, 0)
    while pos != -1:
        if pos + 36 <= len(data):
            values = [u32(data, pos + i * 4) for i in range(9)]
            if (
                values[0] == CELL_MARKER
                and 1 <= values[1] <= 30
                and 0 <= values[7] <= 2000
                and values[8] == 0xFFFFFFFF
            ):
                marker_starts.append(pos)
        pos = data.find(marker, pos + 1)

    if not marker_starts:
        raise RuntimeError("No cell markers found")

    starts = [find_first_cell_start(data, marker_starts[0]), *marker_starts]
    starts = sorted(set(starts))
    if expected_cells is not None and len(starts) != expected_cells:
        raise RuntimeError(f"Expected {expected_cells} cells, found {len(starts)}")
    return starts


def index_to_coord(index: int, cols: int, rows: int, order: str) -> tuple[int, int]:
    if order.startswith("row-major"):
        col = index % cols
        row = index // cols
    elif order.startswith("col-major"):
        col = index // rows
        row = index % rows
    else:
        raise ValueError(f"Unknown order: {order}")

    if "flip-x" in order:
        col = cols - 1 - col
    if "flip-y" in order:
        row = rows - 1 - row
    return col, row


def parse_cells(data: bytes, cols: int, rows: int, order: str) -> list[dict]:
    expected = cols * rows
    starts = find_cell_starts(data, expected)

    record_ends = starts[1:] + [len(data)]
    cells = []
    for index, (start, end) in enumerate(zip(starts, record_ends)):
        if u32(data, start) != CELL_MARKER:
            level = u32(data, start)
            terrain_primary = u32(data, start + 4)
            terrain_secondary = u32(data, start + 8)
            terrain_detail = u32(data, start + 12)
            stored_height = u32(data, start + 24)
            strings_start = start + 32
        else:
            level = u32(data, start + 4)
            terrain_primary = u32(data, start + 8)
            terrain_secondary = u32(data, start + 12)
            terrain_detail = u32(data, start + 16)
            stored_height = u32(data, start + 28)
            strings_start = start + 36

        col, row = index_to_coord(index, cols, rows, order)
        labels = strings_between(data, strings_start, end)
        terrain_text = labels[-1] if labels else ""
        cells.append(
            {
                "col": col,
                "row": row,
                "elevation": stored_height - HEIGHT_LABEL_OFFSET,
                "stored_height": stored_height,
                "elevation_level": level,
                "terrain": terrain_primary,
                "terrain_primary": terrain_primary,
                "terrain_secondary": terrain_secondary,
                "terrain_detail": terrain_detail,
                "terrain_text": terrain_text,
                "labels": labels,
            }
        )
    return cells


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse FCSS .fp10 map data.")
    parser.add_argument("--fp10", type=Path, default=DEFAULT_FP10)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--all", action="store_true", help="Parse every .fp10 in --maps-dir.")
    parser.add_argument("--maps-dir", type=Path, default=DEFAULT_MAPS_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument(
        "--order",
        default="row-major",
        choices=[
            "row-major",
            "row-major-flip-x",
            "row-major-flip-y",
            "row-major-flip-x-flip-y",
            "col-major",
            "col-major-flip-x",
            "col-major-flip-y",
            "col-major-flip-x-flip-y",
        ],
        help="Coordinate transform for record order. Use visual checks to calibrate.",
    )
    args = parser.parse_args()

    if args.all:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        maps = []
        for fp10_path in sorted(args.maps_dir.glob("*.fp10")):
            data = fp10_path.read_bytes()
            header = read_header(data)
            cols = header["cols"]
            rows = header["rows"]
            cells = parse_cells(data, cols, rows, args.order)
            elevations = [c["elevation"] for c in cells]
            stored = [c["stored_height"] for c in cells]
            out_name = f"{fp10_path.stem}.json"
            out_path = args.out_dir / out_name
            output = {
                "cols": cols,
                "rows": rows,
                "source": str(fp10_path),
                "source_format": "fp10",
                "record_order": args.order,
                "height_rule": "elevation = stored_height - 25",
                "cells": cells,
                "stats": {
                    "cell_count": len(cells),
                    "elevation_min": min(elevations),
                    "elevation_max": max(elevations),
                    "stored_height_counts": dict(sorted(Counter(stored).items())),
                    "elevation_counts": dict(sorted(Counter(elevations).items())),
                },
            }
            out_path.write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
            maps.append(
                {
                    "name": header["name"],
                    "cols": cols,
                    "rows": rows,
                    "cells": len(cells),
                    "elevation_min": min(elevations),
                    "elevation_max": max(elevations),
                    "url": f"{args.out_dir.name}/{out_name}",
                    "source": str(fp10_path),
                }
            )
            print(f"{header['name']}: {cols} x {rows}, {len(cells)} cells -> {out_path}")

        index = {"maps": maps}
        args.index.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote index: {args.index}")
        return

    data = args.fp10.read_bytes()
    header = read_header(data)
    cols = header["cols"]
    rows = header["rows"]
    cells = parse_cells(data, cols, rows, args.order)

    elevations = [c["elevation"] for c in cells]
    stored = [c["stored_height"] for c in cells]
    output = {
        "cols": cols,
        "rows": rows,
        "source": str(args.fp10),
        "source_format": "fp10",
        "record_order": args.order,
        "height_rule": "elevation = stored_height - 25",
        "cells": cells,
        "stats": {
            "cell_count": len(cells),
            "elevation_min": min(elevations),
            "elevation_max": max(elevations),
            "stored_height_counts": dict(sorted(Counter(stored).items())),
            "elevation_counts": dict(sorted(Counter(elevations).items())),
        },
    }

    args.out.write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
    print(f"Map: {header['name']} ({cols} x {rows})")
    print(f"Cells: {len(cells)}")
    print(f"Elevation range: {min(elevations)} - {max(elevations)}")
    print(f"Wrote: {args.out}")
    print("First row sample:", [c["elevation"] for c in cells[:12]])


if __name__ == "__main__":
    main()
