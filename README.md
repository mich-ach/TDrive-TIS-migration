# TDrive-TIS Migration Toolkit

A toolkit for extracting, validating, and mapping artifacts from TIS (Test Information System) and network drives.

## Tools Overview

| Tool | Purpose |
|------|---------|
| **TIS_Artifact_Fetcher** | Extract artifacts from TIS API with validation |
| **TDrive_Artifact_Fetcher** | Extract artifacts from network LCO archives |
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
│   ├── config.json             # Network paths
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

Extracts artifacts from network-shared LCO zip archives.

```bash
python -m TDrive_Artifact_Fetcher
```

**Output:** Migration JSON files for TIS upload.

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
```

## Configuration

Each tool uses a `config.json` file for settings:

- **TIS_Artifact_Fetcher**: API settings, filters, validation rules, naming conventions
- **TDrive_Artifact_Fetcher**: Network paths, LCO version configs
- **vVeh_LCO_Mapping**: Input paths, Excel formatting, output settings

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
