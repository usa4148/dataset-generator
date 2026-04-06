# Storage Test — Dataset Generator

Generates synthetic file trees that match the characteristics of real CryoEM and imaging datasets used at some research centers. Designed for validating storage systems without moving actual research data.

Two file modes are supported:
- **Sparse** (default) — correct apparent size, negligible actual disk use
- **Dense** — allocates real disk blocks, consumes actual storage space

## Datasets

| Dataset | Instrument | Files | Apparent Size | Dirs |
|---------|------------|------:|-------------:|-----:|
| `arctica` | Thermo Fisher Arctica (200 kV) | 28,356 | 1.41 TB | 64 |
| `krios02` | Thermo Fisher Krios #2 — EER detector | 47,428 | 5.70 TB | 35 |
| `krios01` | Thermo Fisher Krios #1 — TIFF detector | 162,527 | 8.65 TB | 148 |
| `scape` | Hillman SCAPE light-sheet microscope | 9,099 | 77.5 GiB | 8 |

Source specification: `CryoEM_and_Imaging_Dataset_Characteristics_v3 1.pdf`

## Requirements

Python 3.9+. Install dependencies with the provided installer.

## Installation

**macOS / Linux / Windows (Git Bash or WSL):**
```bash
bash install.sh
source .venv/bin/activate      # path shown at end of install output
```

**Windows (Command Prompt):**
```bat
install.bat
.venv\Scripts\activate
```

> **Note:** If the project path contains a colon (e.g. `SM:R`), the installer automatically creates the virtual environment under `~/Library/Application Support/stjude-generator/` (macOS) or `~/.local/share/stjude-generator/` (Linux). The exact path is printed at the end of installation.

## Usage

All commands are run from the `dataset-generator/` directory.

### Generate all datasets

```bash
python3 generate.py --output /path/to/storage
```

### Generate a single dataset

```bash
python3 generate.py --dataset arctica --output /path/to/storage
python3 generate.py --dataset krios01 --output /path/to/storage
python3 generate.py --dataset krios02 --output /path/to/storage
python3 generate.py --dataset scape   --output /path/to/storage
```

### Scale down for quick testing

`--scale` reduces file counts proportionally while preserving average file size.

```bash
# 1% of files (~2,500 files total across all datasets)
python3 generate.py --scale 0.01 --output /path/to/storage

# 0.1% of files (~260 files total)
python3 generate.py --scale 0.001 --output /path/to/storage
```

### Dense mode — consume real disk space

By default files are sparse (correct apparent size, negligible actual disk use). Use `--dense` to allocate real disk blocks, which exercises the storage system's actual write path.

```bash
python3 generate.py --dense --output /path/to/storage

# Dense + scaled for a realistic but smaller write test
python3 generate.py --dense --scale 0.01 --output /path/to/storage
```

`--dense` uses `posix_fallocate(2)` on Linux and macOS for fast block pre-allocation. On Windows or filesystems that don't support it (some NFS servers), it falls back to writing zeros in 4 MB chunks.

### Clean up generated data

```bash
# Delete all dataset directories (prompts for confirmation)
python3 generate.py --cleanup --output /path/to/storage

# Delete a single dataset
python3 generate.py --cleanup --dataset krios01 --output /path/to/storage

# Skip confirmation prompt (for scripted use)
python3 generate.py --cleanup --yes --output /path/to/storage
```

### Preview without writing files

```bash
python3 generate.py --dry-run
python3 generate.py --dry-run --scale 0.01 --dataset krios01
```

### All options

```
--dataset {arctica,krios01,krios02,scape,all}
                      Dataset to generate or clean (default: all)
--output, -o DIR      Root output directory (default: ./output)
--scale, -s FACTOR    Fraction of files to generate; avg file size is
                      preserved (default: 1.0)
--dense               Allocate real disk space (uses posix_fallocate
                      where available, falls back to zero-writes)
--no-sparse           Alias for --dense (backwards compatibility)
--cleanup             Delete generated dataset directories
--yes, -y             Skip confirmation prompt with --cleanup
--dry-run             Show what would be generated without writing files
--seed INT            RNG seed for reproducible output (default: 42)
```

## Output Structure

Each dataset is written to its own subdirectory under `--output`.

**CryoEM datasets** mirror the EPU (Electron Pickups) software directory layout:

```
output/
└── Arctica/
    └── GridSquare_XXXXXXXX/
        ├── Data/
        │   ├── FoilHole_XXXXXXXX_Data_XXXXXXXX_XXXXXXXX_20230601_080000_fractions.tiff
        │   ├── FoilHole_XXXXXXXX_Data_XXXXXXXX_XXXXXXXX_20230601_080000.mrc
        │   ├── FoilHole_XXXXXXXX_Data_XXXXXXXX_XXXXXXXX_20230601_080000.xml
        │   └── GridSquare_XXXXXXXX_20230601_080000.dm
        └── Thumbnails/
            └── FoilHole_XXXXXXXX_Data_XXXXXXXX_XXXXXXXX_20230601_080000.jpg
```

**SCAPE datasets** use flat session directories:

```
output/
└── SCAPE/
    ├── session_001/
    │   ├── SCAPE_20230601_000000_ch1.dat
    │   ├── SCAPE_Cal_0000.bin
    │   ├── SCAPE_Analysis_0000.mat
    │   ├── acquisition_0000.sifx
    │   └── config_0000.ini
    └── session_002/
        └── ...
```

## File Authenticity

Generated files are recognized correctly by format-aware tools:

| Extension | Header | Recognized as |
|-----------|--------|---------------|
| `.tiff` | TIFF little-endian magic | `TIFF image data, little-endian` |
| `.eer` | TIFF container | `TIFF image data, little-endian` |
| `.mrc` | MRC2014 1024-byte header | `CCP4 Electron Density Map` |
| `.jpg` | JFIF SOI + APP0 | `JPEG image data, JFIF standard 1.01` |
| `.dm` | DM4 big-endian header | DigitalMicrograph 4 |
| `.mat` | MATLAB v5 128-byte header | MATLAB MAT-file |
| `.xml` | Valid EPU acquisition XML | Parseable by any XML library |
| `.ini` | Valid INI config | Parseable by `configparser` |

File sizes follow a log-normal distribution (σ=0.3) around the per-type average, matching the natural variation in real acquisition data.

## Project Files

```
dataset-generator/
├── config.py         # Dataset specs — edit here when requirements change
├── generate.py       # Generator logic and CLI
├── requirements.txt  # Python dependencies (tqdm)
├── install.sh        # Installer for macOS, Linux, Windows Git Bash/WSL
└── install.bat       # Installer for Windows Command Prompt
```
