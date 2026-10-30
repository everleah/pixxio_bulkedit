"""Erzeugung lokaler Testdateien fuer die Schreibpruefungen.

Bewusst ohne Bildbibliothek: ein kleines, gueltiges PNG wird direkt geschrieben,
damit keine zusaetzliche Abhaengigkeit noetig ist.
"""

from __future__ import annotations

import secrets
import struct
import time
import zlib
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DEFAULT_SIZE = 16


def _chunk(tag: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", checksum)


def png_bytes(size: int = DEFAULT_SIZE, seed: int = 0) -> bytes:
    """Erzeugt ein RGB-PNG mit deterministischem Muster."""
    rows = bytearray()
    for y in range(size):
        rows.append(0)  # Filtertyp "None"
        for x in range(size):
            rows.extend(
                (
                    (x * 17 + seed * 31) % 256,
                    (y * 23 + seed * 7) % 256,
                    ((x + y) * 11 + seed * 13) % 256,
                )
            )
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return b"".join(
        (
            PNG_SIGNATURE,
            _chunk(b"IHDR", header),
            _chunk(b"IDAT", zlib.compress(bytes(rows), 9)),
            _chunk(b"IEND", b""),
        )
    )


def write_test_png(path: Path, size: int = DEFAULT_SIZE, seed: int = 0) -> Path:
    path.write_bytes(png_bytes(size=size, seed=seed))
    return path


def probe_file_name(prefix: str = "bulkedit-probe") -> str:
    """Eindeutiger Dateiname, damit das Testsystem nichts als Duplikat erkennt."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}-{secrets.token_hex(4)}.png"
