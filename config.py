"""
Dataset specifications for storage system testing.

Sizes are in bytes. Counts match the PDF specification exactly.
Source: CryoEM_and_Imaging_Dataset_Characteristics_v3.pdf
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

# ── Units ──────────────────────────────────────────────────────────────────────
KB  = 1_024
MB  = 1_024 * KB
GB  = 1_024 * MB
TB  = 1_024 * GB
GiB = 1_024 ** 3
MiB = 1_024 ** 2
KiB = 1_024


# ── Data Model ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FileType:
    ext: str          # e.g. ".tiff"
    count: int        # number of files in the full dataset
    total_bytes: int  # combined size of all files of this type

    @property
    def avg_bytes(self) -> int:
        return self.total_bytes // self.count if self.count else 0


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    category: str        # "cryoem" or "imaging"
    n_dirs: int          # total directory count including root
    file_types: List[FileType]

    @property
    def total_files(self) -> int:
        return sum(ft.count for ft in self.file_types)

    @property
    def total_bytes(self) -> int:
        return sum(ft.total_bytes for ft in self.file_types)


# ── Dataset Registry ───────────────────────────────────────────────────────────

DATASETS: dict[str, DatasetSpec] = {

    # Thermo Fisher Arctica (200 kV)
    # Total: 1.41 TB, 28,356 files, 64 dirs
    "arctica": DatasetSpec("Arctica", "cryoem", 64, [
        FileType(".tiff", 13_734, int(1.41  * TB)),    # raw movie frames
        FileType(".jpg",   7_126, int(564.4 * MB)),    # thumbnail previews
        FileType(".xml",   7_124, int(75.8  * MB)),    # EPU acquisition metadata
        FileType(".dm",      371, int(59.4  * MB)),    # DigitalMicrograph calibration
        FileType(".mrc",       1, int(89.9  * MB)),    # processed volume
    ]),

    # Thermo Fisher Krios #2 (300 kV, EER detector)
    # Total: 5.70 TB, 47,428 files, 35 dirs
    "krios02": DatasetSpec("Krios02", "cryoem", 35, [
        FileType(".eer",  11_544, int(5.34   * TB)),   # Electron Event Representation
        FileType(".mrc",  11_787, int(372.90 * GB)),   # gain-corrected frames
        FileType(".jpg",  11_788, int(1.42   * GB)),   # thumbnail previews
        FileType(".xml",  11_787, int(168.6  * MB)),   # EPU acquisition metadata
        FileType(".dm",      521, int(47.7   * MB)),   # DigitalMicrograph calibration
        FileType(".gain",      1, int(33.6   * MB)),   # detector gain reference
    ]),

    # Thermo Fisher Krios #1 (300 kV, TIFF detector)
    # Total: 8.65 TB, 162,527 files, 148 dirs
    "krios01": DatasetSpec("Krios01", "cryoem", 148, [
        FileType(".tiff", 39_900, int(8.17   * TB)),   # raw movie frames
        FileType(".mrc",  40_741, int(483.42 * GB)),   # gain-corrected frames
        FileType(".jpg",  40_740, int(3.11   * GB)),   # thumbnail previews
        FileType(".xml",  40_740, int(446.3  * MB)),   # EPU acquisition metadata
        FileType(".dm",      406, int(17.1   * MB)),   # DigitalMicrograph calibration
    ]),

    # Hillman SCAPE (light-sheet microscopy)
    # Total: 77.5 GiB, 9,099 files, 8 dirs
    # Note: file composition scales proportionally with dataset size
    "scape": DatasetSpec("SCAPE", "imaging", 8, [
        FileType(".dat",  9_036, int(64.9 * GiB)),    # raw volumetric data
        FileType(".bin",     14, int(12.6 * GiB)),    # binary calibration/reference
        FileType(".mat",     35, int(2.9  * MiB)),    # MATLAB analysis data
        FileType(".sifx",     7, int(1.4  * MiB)),    # Andor camera acquisition
        FileType(".ini",      7, int(3.5  * KiB)),    # acquisition configuration
    ]),
}
