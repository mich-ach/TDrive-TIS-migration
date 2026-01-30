# TDrive Artifact Fetcher

Extracts LCO artifact metadata from network-shared zip archives, maps them to missing PVER entries, and generates migration files for TIS upload.

## Requirements

- **Network Drive Access**: Read access to `LCO_Projects` directory (path configured in `config.json`)
- **Python 3.8+**
- **Dependencies**: `charset_normalizer`, `openpyxl`

## Usage

```bash
python -m TDrive_Artifact_Fetcher
```

## Workflow

The tool runs a 6-step pipeline:

1. **Scan LCO 5.4.5** — Traverse network drive, extract `Model_Overview.html` metadata from zip archives
2. **Scan LCO 5.4.11** — Same for the newer LCO version
3. **Transform Excel** — Convert `missing.xlsx` (PVER export) to CSV
4. **Compare** — Match artifacts to missing PVER entries via A2L/HEX file path patterns
5. **Dump** — Save matched results to `check.json` (deduplicated, keeping latest per artifact)
6. **Generate migration** — Create `mig.json` for TIS upload

## Input

- `input/missing.xlsx` — Excel export listing PVER entries and their availability status

## Output

All files are saved to the `output/` directory:

| File | Description |
|------|-------------|
| `545dir.json` | Directory structure cache (LCO 5.4.5) |
| `5411dir.json` | Directory structure cache (LCO 5.4.11) |
| `545list.json` | Extracted artifact metadata (LCO 5.4.5) |
| `5411list.json` | Extracted artifact metadata (LCO 5.4.11) |
| `545_*.log` | Processing log with DEBUG level (LCO 5.4.5) |
| `5411_*.log` | Processing log with DEBUG level (LCO 5.4.11) |
| `check.json` | Matched artifacts with PVER data and transfer entries |
| `mig.json` | Migration file for TIS upload |

## Migration File (`mig.json`)

The final output used to upload artifacts into TIS. Contains a list of model entries:

| Field | Description |
|-------|-------------|
| `model_input_filepath` | Source path to the zip archive on the network drive |
| `tis_artifact_path` | Target folder in TIS (e.g. `xCU Projects/{ECU}/{PVER}/Model/HiL/{CSP_SWB}/{LabcarType}`) |
| `tis_artifact_name` | Artifact display name (prefixed with `VW MDL :` if missing) |
| `customer_group` | Always `VW` |
| `tis_migration` | Migration flag (`true`) |
| `lco_migration` | LCO migration flag (`false`) |

This file serves as input for a separate TIS upload tool that creates the actual artifacts in TIS.

## Modules

### Artifacts

Extracts metadata from LCO zip files. Subclasses for each LCO version: `Artifact545`, `Artifact5411`.

```python
from Artifacts import Artifact545

art545 = Artifact545()
art545.start_logging()   # Enable file logging to output/
art545.create_dir()      # Scan network drive for artifacts
art545.cleanup_dir()     # Remove invalid entries (Failed, Dev, Archive, etc.)
art545.dump_dir()        # Save to output/545dir.json
art545.create_list()     # Extract metadata from zip files (parallel, 8 threads)
art545.cleanup_list()    # Keep only artifacts with HEXFile or A2LFile
art545.dump_list()       # Save to output/545list.json
art545.stop_logging()    # Close log file
```

**Extracted metadata per artifact:**
- Path to zip archive
- Model name, HEXFile, A2LFile from `Docs/Model_Overview.html`

### Check

Maps extracted artifacts to missing PVER entries and generates migration files.

```python
from Check import Check

Check.transform_excel("input/missing.xlsx", "input/missing.csv")
check = Check(["output/545list.json", "output/5411list.json"], "input/missing.csv")
check.compare()    # Match artifacts to PVER entries
check.dump()       # Save to output/check.json
Check.create_mig("output/check.json")  # Generate output/mig.json
```

## Configuration (`config.json`)

| Key | Description |
|-----|-------------|
| `base_path` | Network drive root path |
| `input_dir` | Input directory (default: `input`) |
| `output_dir` | Output directory (default: `output`) |
| `log_level` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
