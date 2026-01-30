# TDrive-TIS Migration Toolkit

A toolkit for extracting, validating, and mapping artifacts from TIS (Test Information System) and network drives.

## Tools Overview

| Tool | Purpose |
|------|---------|
| **TIS_Artifact_Fetcher** | Extract artifacts from TIS API with validation |
| **TDrive_Artifact_Fetcher** | Extract artifacts from network LCO archives and generate migration files |
| **vVeh_LCO_Mapping** | Map software lines from Excel to TIS artifacts |

## Project Structure

```
TDrive-TIS-migration/
├── TIS_Artifact_Fetcher/       # TIS API extraction
│   └── src/
│       ├── __main__.py         # Entry point
│       ├── config.json         # Configuration
│       ├── Api/                # HTTP client with caching
│       ├── Fetchers/           # Recursive BFS extraction
│       ├── Validators/         # Path & naming validation
│       ├── Handlers/           # Artifact separation
│       ├── Models/             # Data classes
│       ├── Reports/            # Excel report generation
│       └── Filters/            # Component filtering
│
├── TDrive_Artifact_Fetcher/    # Network drive extraction
│   ├── __main__.py             # Entry point
│   ├── config.json             # Network paths & log level
│   ├── Artifacts/              # LCO 5.4.5/5.4.11 handlers
│   └── Check/                  # PVER mapping & migration
│
└── vVeh_LCO_Mapping/           # Excel mapping workflow
    └── src/
        ├── __main__.py         # Entry point
        ├── config.json         # Excel settings
        └── Handlers/           # Read, map, report modules
```

## Usage

### TIS_Artifact_Fetcher

Extracts artifacts from TIS with configurable filters and validation.

```bash
python -m TIS_Artifact_Fetcher.src
```

**Output:** `output/run_*/` containing:
- `{component}_artifacts_*.json` - All artifacts by type
- `latest_{component}_artifacts_*.json` - Latest per software line
- `*_validation_report_*.xlsx` - Validation deviations

### TDrive_Artifact_Fetcher

Extracts LCO artifact metadata from network-shared zip archives and generates migration files for TIS upload.

```bash
python -m TDrive_Artifact_Fetcher
```

**Workflow (6 steps):**

1. **Scan** network drive for LCO 5.4.5 zip archives, extract `Model_Overview.html` metadata
2. **Scan** network drive for LCO 5.4.11 zip archives, extract `Model_Overview.html` metadata
3. **Transform** `missing.xlsx` (PVER export) to CSV for processing
4. **Compare** extracted artifacts against missing PVER entries by matching PVER patterns in A2L/HEX file paths
5. **Dump** matched results to `check.json` (deduplicated, keeping latest version per artifact)
6. **Generate** `mig.json` — the migration file

**Inputs:**
- Network drive access to `LCO_Projects` directory (path in `config.json`)
- `input/missing.xlsx` — Excel export of missing PVER entries

**Output** (`output/`):
- `545list.json` — LCO 5.4.5 artifact metadata
- `5411list.json` — LCO 5.4.11 artifact metadata
- `check.json` — matched artifacts with PVER and transfer data
- `mig.json` — migration file for TIS upload

#### Migration File (`mig.json`)

The migration file is the final output used to upload artifacts into TIS. It contains a list of model entries, each specifying:

| Field | Description |
|-------|-------------|
| `model_input_filepath` | Source path to the zip archive on the network drive |
| `tis_artifact_path` | Target folder structure in TIS (e.g. `xCU Projects/{ECU}/{PVER}/Model/HiL/{CSP_SWB}/{LabcarType}`) |
| `tis_artifact_name` | Artifact display name (prefixed with `VW MDL :` if missing) |
| `customer_group` | Always `VW` |
| `tis_migration` | Migration flag (true) |
| `lco_migration` | LCO migration flag (false) |

This file serves as input for a separate TIS upload tool that creates the actual artifacts in TIS based on these transfer definitions.

### vVeh_LCO_Mapping

Maps Excel software lines to TIS artifacts.

```bash
# Auto-detect files from config
python -m vVeh_LCO_Mapping.src

# Specify files
python -m vVeh_LCO_Mapping.src artifacts.json master.xlsx
```

**Output:** `output/run_*/software_line_mapping_*.xlsx`

## Workflow

```
TIS API ──► TIS_Artifact_Fetcher ──► JSON files
                                         │
Excel Master ──► vVeh_LCO_Mapping ◄──────┘
                        │
                        ▼
              Mapping Report (Excel)

Network Drive ──► TDrive_Artifact_Fetcher ──► mig.json ──► TIS Upload
```

## Configuration

Each tool uses a `config.json` file:

- **TIS_Artifact_Fetcher**: API settings, filters, validation rules, naming conventions
- **TDrive_Artifact_Fetcher**: Network paths, LCO version configs, log level
- **vVeh_LCO_Mapping**: Input file paths, Excel formatting, output settings

## Supported Artifact Types

- `vVeh_LCO` - Vehicle models (LCO/VeMoX versions)
- `test_ECU-TEST` - Test artifacts
- `MDL` - Model artifacts
- Custom types via configuration

## Requirements

- Python 3.8+
- requests
- openpyxl
- wxPython (optional, for GUI)
