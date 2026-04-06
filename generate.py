#!/usr/bin/env python3
"""
Synthetic dataset generator for storage system testing.

Creates sparse file trees that match the file count, directory count, and
apparent size of real CryoEM (Arctica, Krios01, Krios02) and SCAPE datasets.
Files are sparse by default: correct apparent size, negligible actual disk use.

Usage:
    python generate.py                           # all 4 datasets
    python generate.py --dataset arctica         # one dataset
    python generate.py --scale 0.001 --dry-run   # preview 0.1% scale
    python generate.py --output /mnt/storage     # custom output root
    python generate.py --scale 0.01              # 1% of files, full avg size
"""
from __future__ import annotations

import argparse
import math
import os
import random
import shutil
import struct
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple

from config import DATASETS, DatasetSpec, FileType, GB, MB, TB, KiB

try:
    from tqdm import tqdm as _tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


# ── File Headers ───────────────────────────────────────────────────────────────

def _tiff_header() -> bytes:
    """Little-endian TIFF magic (8 bytes). EER files also use TIFF container."""
    return struct.pack('<2sHI', b'II', 42, 8)


def _jpg_header() -> bytes:
    """Minimal JFIF SOI + APP0 marker (20 bytes)."""
    return bytes([
        0xFF, 0xD8,                          # SOI
        0xFF, 0xE0,                          # APP0
        0x00, 0x10,                          # APP0 length = 16
        0x4A, 0x46, 0x49, 0x46, 0x00,       # "JFIF\0"
        0x01, 0x01,                          # version 1.1
        0x00,                                # no aspect ratio units
        0x00, 0x01, 0x00, 0x01,             # X/Y density = 1
        0x00, 0x00,                          # no thumbnail
    ])


def _mrc_header() -> bytes:
    """MRC2014 file header (1024 bytes, little-endian)."""
    h = bytearray(1024)
    struct.pack_into('<iii', h,   0, 1, 1, 1)           # NX, NY, NZ = 1×1×1
    struct.pack_into('<i',   h,  12, 2)                  # MODE 2 = float32
    struct.pack_into('<fff', h,  28, 1.0, 1.0, 1.0)     # cell dimensions (Å)
    struct.pack_into('<fff', h,  40, 90.0, 90.0, 90.0)  # cell angles
    struct.pack_into('<iii', h,  64, 1, 2, 3)            # MAPC, MAPR, MAPS
    struct.pack_into('<i',   h,  88, 20140)              # NVERSION = MRC2014
    h[208:212] = b'MAP '
    struct.pack_into('<I',   h, 212, 0x00004144)         # machine stamp (LE)
    return bytes(h)


def _dm4_header() -> bytes:
    """DigitalMicrograph 4 file header (16 bytes, big-endian)."""
    # version=4, root tag data length=0, little_endian=1
    return struct.pack('>IQI', 4, 0, 1)


def _mat_header() -> bytes:
    """MATLAB v5 MAT-file header (128 bytes)."""
    h = bytearray(128)
    desc = b'MATLAB 5.0 MAT-file, synthetic storage test data'
    h[:len(desc)] = desc
    struct.pack_into('<H', h, 124, 0x0100)   # version
    h[126:128] = b'IM'                        # endian indicator (little-endian)
    return bytes(h)


def _xml_content(stem: str, ts: datetime, target_size: int) -> bytes:
    """EPU-style acquisition XML, padded/truncated to target_size bytes."""
    body = (
        f'<?xml version="1.0" encoding="utf-8"?>\n'
        f'<MicroscopeImage>\n'
        f'  <microscopeData>\n'
        f'    <acquisition>\n'
        f'      <acquisitionDateTime>{ts.isoformat()}Z</acquisitionDateTime>\n'
        f'      <electronBeam>\n'
        f'        <Voltage>300000</Voltage>\n'
        f'        <spotSizeIndex>3</spotSizeIndex>\n'
        f'      </electronBeam>\n'
        f'      <camera>\n'
        f'        <ExposureTime>3.0</ExposureTime>\n'
        f'        <ImageName>{stem}</ImageName>\n'
        f'      </camera>\n'
        f'    </acquisition>\n'
        f'  </microscopeData>\n'
        f'</MicroscopeImage>\n'
    ).encode()

    if len(body) >= target_size:
        return body[:target_size]

    # Pad with an XML comment to reach target_size
    pad_len = target_size - len(body) - 20
    pad = f'\n<!-- {"x" * max(0, pad_len)} -->\n'.encode()
    return (body + pad)[:target_size]


def _ini_content() -> bytes:
    """SCAPE acquisition configuration INI."""
    return b"""\
[Acquisition]
LaserPower=50.0
ExposureTime_ms=100
FrameRate=15.0
Wavelength_nm=488

[Scanner]
VolumeRate=5.0
ZSteps=200
ZStep_um=2.0
NumChannels=2

[System]
Version=2.4.1
CameraSerial=SCA-00123
"""


# ── File Writing ───────────────────────────────────────────────────────────────

_HEADERS = {
    ".tiff": _tiff_header,
    ".eer":  _tiff_header,   # EER uses TIFF container format
    ".jpg":  _jpg_header,
    ".mrc":  _mrc_header,
    ".dm":   _dm4_header,
    ".mat":  _mat_header,
}

_CHUNK = 4 * 1024 * 1024  # 4 MB write chunk for dense fallback


def _fill_dense(f, offset: int, size: int) -> None:
    """
    Allocate `size - offset` bytes of real disk space starting at `offset`.

    Uses posix_fallocate (Linux / macOS) for fast block pre-allocation without
    writing zeros. Falls back to chunked zero-writes on filesystems or platforms
    that don't support it (Windows, NFS with older servers, etc.).
    """
    remaining = size - offset
    if remaining <= 0:
        return
    try:
        os.posix_fallocate(f.fileno(), offset, remaining)
    except (AttributeError, OSError):
        # posix_fallocate unavailable or unsupported — write zeros in chunks
        f.seek(offset)
        while remaining > 0:
            chunk = min(remaining, _CHUNK)
            f.write(b'\x00' * chunk)
            remaining -= chunk


def _write_file(
    path: Path,
    size: int,
    ext: str,
    stem: str,
    ts: datetime,
    sparse: bool,
) -> None:
    """Create a single file of exactly `size` bytes, sparse or dense."""
    size = max(1, size)

    # Text-based files: write real content (always dense by nature)
    if ext == ".xml":
        path.write_bytes(_xml_content(stem, ts, size))
        return
    if ext == ".ini":
        content = _ini_content()
        path.write_bytes(content[:size])
        return

    # Binary files: write format header, then extend to target size
    header_fn = _HEADERS.get(ext)
    header = header_fn()[:size] if header_fn else b''

    with open(path, 'wb') as f:
        if header:
            f.write(header)
        if sparse:
            f.truncate(size)          # extend with a sparse hole
        else:
            _fill_dense(f, len(header), size)  # allocate real disk blocks


# ── Filename Generation ────────────────────────────────────────────────────────

_EPOCH = datetime(2023, 6, 1, 8, 0, 0)


def _cryoem_name(ext: str, idx: int, rng: random.Random) -> Tuple[str, str, datetime]:
    """EPU-style FoilHole or GridSquare filename. Returns (filename, stem, timestamp)."""
    ts  = _EPOCH + timedelta(seconds=idx * 12)
    ds  = ts.strftime('%Y%m%d')
    t   = ts.strftime('%H%M%S')

    if ext in ('.dm', '.gain'):
        # Per-grid-square calibration files
        gsq  = rng.randint(10_000_000, 99_999_999)
        stem = f"GridSquare_{gsq}_{ds}_{t}"
        return stem + ext, stem, ts

    # Per-acquisition files (tiff, eer, mrc, jpg, xml)
    gsq  = rng.randint(10_000_000, 99_999_999)
    fh   = rng.randint(10_000_000, 99_999_999)
    fh2  = fh + 1
    stem = f"FoilHole_{gsq}_Data_{fh}_{fh2}_{ds}_{t}"
    name = (stem + "_fractions" + ext) if ext == ".tiff" else (stem + ext)
    return name, stem, ts


def _scape_name(ext: str, idx: int) -> Tuple[str, str, datetime]:
    """SCAPE acquisition filename. Returns (filename, stem, timestamp)."""
    ts = _EPOCH + timedelta(seconds=idx * 6)
    if ext == ".dat":
        ch   = (idx % 3) + 1
        name = f"SCAPE_{ts.strftime('%Y%m%d')}_{idx:06d}_ch{ch}.dat"
    elif ext == ".bin":
        name = f"SCAPE_Cal_{idx:04d}.bin"
    elif ext == ".mat":
        name = f"SCAPE_Analysis_{idx:04d}.mat"
    elif ext == ".sifx":
        name = f"acquisition_{idx:04d}.sifx"
    else:  # .ini
        name = f"config_{idx:04d}.ini"
    return name, name, ts


# ── Directory Structure ────────────────────────────────────────────────────────

def _cryoem_dirs(root: Path, n_dirs: int, rng: random.Random) -> Tuple[List[Path], List[Path], List[Path]]:
    """
    Build EPU-style GridSquare tree.

        <root>/GridSquare_XXXXXXXX/
                                  Data/
                                  Thumbnails/

    Returns (all_dirs, data_dirs, thumbnail_dirs).
    Each trio counts as 3 directories toward n_dirs.
    """
    n_grid_squares = max(1, (n_dirs - 1) // 3)
    grid_dirs, data_dirs, thumb_dirs = [], [], []

    for _ in range(n_grid_squares):
        gsq_id = rng.randint(10_000_000, 99_999_999)
        gsq    = root / f"GridSquare_{gsq_id}"
        data   = gsq / "Data"
        thumb  = gsq / "Thumbnails"
        grid_dirs.append(gsq)
        data_dirs.append(data)
        thumb_dirs.append(thumb)

    return grid_dirs + data_dirs + thumb_dirs, data_dirs, thumb_dirs


def _scape_dirs(root: Path, n_dirs: int) -> Tuple[List[Path], List[Path]]:
    """
    Build SCAPE session directory tree.

        <root>/session_001/
               session_002/
               ...

    Returns (all_dirs, session_dirs).
    """
    n_sessions  = max(1, n_dirs - 1)
    session_dirs = [root / f"session_{i+1:03d}" for i in range(n_sessions)]
    return session_dirs, session_dirs


# ── Size Sampling ──────────────────────────────────────────────────────────────

def _sample_size(avg: int, rng: random.Random) -> int:
    """
    Sample a file size from a log-normal distribution centred on avg.

    sigma=0.3 gives ~30% coefficient of variation, which matches the natural
    variation in CryoEM movie file sizes (exposure time, detector gain, etc.).
    Expected value equals avg by construction.
    """
    if avg <= 0:
        return 0
    sigma = 0.3
    mu    = math.log(avg) - (sigma ** 2) / 2
    size  = int(rng.lognormvariate(mu, sigma))
    return max(64, min(size, avg * 4))


# ── Progress Reporting ─────────────────────────────────────────────────────────

def _progress(done: int, total: int, rate: float) -> None:
    pct = done / total * 100
    print(
        f"  [{pct:5.1f}%] {done:,}/{total:,}  ({rate:.0f} files/s)    ",
        end='\r', flush=True,
    )


# ── Generator ─────────────────────────────────────────────────────────────────

def _fmt_size(n: int) -> str:
    for unit, factor in [("TB", TB), ("GB", GB), ("MB", MB), ("KB", KiB)]:
        if n >= factor:
            return f"{n / factor:.2f} {unit}"
    return f"{n} B"


class DatasetGenerator:
    def __init__(
        self,
        spec: DatasetSpec,
        output: Path,
        scale: float,
        sparse: bool,
        dry_run: bool,
        seed: int,
    ):
        self.spec    = spec
        self.root    = output / spec.name
        self.scale   = scale
        self.sparse  = sparse
        self.dry_run = dry_run
        self.rng     = random.Random(seed)

    def _scaled_count(self, ft: FileType) -> int:
        return max(1, round(ft.count * self.scale))

    def _scaled_n_dirs(self) -> int:
        return max(2, round(self.spec.n_dirs * self.scale))

    def generate(self) -> None:
        scaled_files = sum(self._scaled_count(ft) for ft in self.spec.file_types)
        scaled_bytes = sum(round(ft.total_bytes * self.scale) for ft in self.spec.file_types)

        print(f"\n{'─' * 60}")
        print(f"  {self.spec.name}")
        print(f"  Files: {scaled_files:,}  |  Dirs: {self._scaled_n_dirs()}  |  Apparent: {_fmt_size(scaled_bytes)}")
        if self.dry_run:
            print("  [DRY RUN — no files written]")
        print()

        if not self.dry_run:
            self.root.mkdir(parents=True, exist_ok=True)

        # Build directory structure
        if self.spec.category == "cryoem":
            all_dirs, data_dirs, thumb_dirs = _cryoem_dirs(
                self.root, self._scaled_n_dirs(), self.rng
            )
            calib_dirs = [d.parent for d in data_dirs]   # GridSquare roots
        else:
            all_dirs, session_dirs = _scape_dirs(self.root, self._scaled_n_dirs())

        if not self.dry_run:
            for d in all_dirs:
                d.mkdir(parents=True, exist_ok=True)

        # Generate files by type
        t0 = time.monotonic()
        bar = _tqdm(total=scaled_files, unit="file", ncols=72) if HAS_TQDM else None
        files_done = 0

        for ft in self.spec.file_types:
            count = self._scaled_count(ft)
            avg   = ft.avg_bytes

            # Route each file type to the appropriate directory pool
            if self.spec.category == "cryoem":
                if ft.ext == ".jpg":
                    dirs = thumb_dirs     # thumbnails → Thumbnails/
                elif ft.ext in (".dm", ".gain"):
                    dirs = calib_dirs     # calibration → GridSquare root
                else:
                    dirs = data_dirs      # data → Data/
            else:
                dirs = session_dirs

            for i in range(count):
                size = _sample_size(avg, self.rng)

                if self.spec.category == "cryoem":
                    name, stem, ts = _cryoem_name(ft.ext, i, self.rng)
                else:
                    name, stem, ts = _scape_name(ft.ext, i)

                target = dirs[i % len(dirs)] / name

                if not self.dry_run:
                    _write_file(target, size, ft.ext, stem, ts, self.sparse)

                files_done += 1
                if bar:
                    bar.update(1)
                elif files_done % 500 == 0 or files_done == scaled_files:
                    elapsed = time.monotonic() - t0
                    rate    = files_done / elapsed if elapsed > 0 else 0
                    _progress(files_done, scaled_files, rate)

        if bar:
            bar.close()

        elapsed = time.monotonic() - t0
        rate = scaled_files / elapsed if elapsed > 0 else 0
        if not bar:
            print(f"  [100.0%] {scaled_files:,}/{scaled_files:,}  ({rate:.0f} files/s)    ")
        print(f"  → {self.root}  ({rate:.0f} files/s)")


# ── Cleanup ────────────────────────────────────────────────────────────────────

def cleanup(output: Path, keys: List[str], yes: bool) -> None:
    """Remove generated dataset directories under output."""
    targets = [output / DATASETS[k].name for k in keys]
    existing = [t for t in targets if t.exists()]

    if not existing:
        print("Nothing to clean up — no dataset directories found.")
        return

    print("The following directories will be permanently deleted:\n")
    for t in existing:
        file_count = sum(1 for _ in t.rglob("*") if _.is_file())
        print(f"  {t}  ({file_count:,} files)")

    print()
    if not yes:
        answer = input("Confirm deletion? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return

    for t in existing:
        print(f"  Removing {t.name}...", end=" ", flush=True)
        shutil.rmtree(t)
        print("done")

    print("\nCleanup complete.")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--dataset", "-d",
        choices=list(DATASETS) + ["all"],
        default="all",
        help="Dataset to generate or clean (default: all)",
    )
    ap.add_argument(
        "--output", "-o",
        type=Path, default=Path("output"),
        help="Root output directory (default: ./output)",
    )
    ap.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete generated dataset directories instead of generating",
    )
    ap.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompt when used with --cleanup",
    )
    ap.add_argument(
        "--scale", "-s",
        type=float, default=1.0, metavar="FACTOR",
        help="Fraction of files to generate; avg file size is preserved (default: 1.0)",
    )
    ap.add_argument(
        "--dense",
        action="store_true",
        help="Allocate real disk space for every file (uses posix_fallocate where available)",
    )
    ap.add_argument(
        "--no-sparse",
        action="store_true",
        help="Alias for --dense (kept for backwards compatibility)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be generated without writing any files",
    )
    ap.add_argument(
        "--seed",
        type=int, default=42,
        help="RNG seed for reproducible filenames and sizes (default: 42)",
    )
    args = ap.parse_args()

    keys = list(DATASETS) if args.dataset == "all" else [args.dataset]

    if args.cleanup:
        cleanup(args.output, keys, args.yes)
        return

    sparse = not (args.dense or args.no_sparse)
    mode   = "sparse" if sparse else "dense"

    print("Storage Test — Dataset Generator")
    print(f"Output : {args.output.resolve()}")
    print(f"Scale  : {args.scale}×  |  Mode: {mode}  |  Dry-run: {args.dry_run}")

    for key in keys:
        DatasetGenerator(
            spec    = DATASETS[key],
            output  = args.output,
            scale   = args.scale,
            sparse  = sparse,
            dry_run = args.dry_run,
            seed    = args.seed,
        ).generate()

    print("\nAll done.")


if __name__ == "__main__":
    main()
