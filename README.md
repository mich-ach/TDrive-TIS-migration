# TDrive-TIS Migration Toolkit

A toolkit for extracting, validating, and mapping artifacts from TIS (Test Information System) and network drives.

1. [How to run](#how-to-run)
2. [Tools Overview](#tools-overview)
3. [Project Structure](#project-structure)
4. [Usage](#usage)
    1. [TIS_Artifact_Fetcher](#tis_artifact_fetcher)
    2. [TDrive_Artifact_Fetcher](#tdrive_artifact_fetcher)
    3. [vVeh_LCO_Mapping](#vveh_lco_mapping)
    4. [Upload](#upload)
5. [Workflow](#workflow)
6. [Configuration](#configuration)
7. [Supported Artifact Types](#supported-artifact-types)
8. [Requirements](#requirements)

## How to run

Use available .bat files to create the Anaconda Environment to use the scripts. Run these files from cmd in the tool directory. Youll have the activated conda environment form which you can run python scripts with

    (.../TIS_Artifact_Lib)
    createEnvironment.bat
    activateEnvironment.bat

    cd TIS_Artifact_Fetcher/src
    python __main__.py
    python artifact_viewer_gui.py

The input files for each tool have to be put in a "input" dir. So create (.../TDrive_Artifact_Fetcher/input ; TIS_Artifact_Fetcher/input) and so on where the input files are located. The tools then create an output dir containing each run with metadata.

## Tools Overview

| Tool | Purpose |
|------|---------|
| **TIS_Artifact_Fetcher** | Extract artifacts from TIS API with validation |
| **TDrive_Artifact_Fetcher** | Extract artifacts from network LCO archives and generate migration files |
| **vVeh_LCO_Mapping** | Map software lines from Excel/CSV to TIS artifacts |
| **Upload** | Execute TIS/LCO migration recipes using PBClient |

## Project Structure

```
TDrive-TIS-migration/
├── TIS_Artifact_Fetcher/       # TIS API extraction
│   └── src/
│       ├── __main__.py         # Entry point
│       ├── config.json         # Configuration
│       ├── config.py           # Config loader & constants
│       ├── Api/                # HTTP client with caching & adaptive depth
│       ├── Fetchers/           # Recursive BFS extraction & component separation
│       ├── Filters/            # Component type/name/status filtering
│       ├── Validators/         # Path & naming convention validation
│       ├── Models/             # Data classes (DeviationType, ValidationReport)
│       ├── Reports/            # Excel validation report generation
│       ├── Handlers/           # Handler utilities
│       ├── Utils/              # Shared utilities
│       ├── discovery/          # Folder & test type discovery helpers
│       ├── tis_project_lister.py   # Standalone SW line lister (CSV output)
│       └── artifact_viewer_gui.py  # Optional wxPython artifact viewer
│
├── TDrive_Artifact_Fetcher/    # Network drive extraction
│   ├── __main__.py             # Entry point
│   ├── config.json             # Network paths & log level
│   ├── Artifacts/              # LCO 5.4.5/5.4.11 handlers
│   └── Check/                  # PVER mapping, CSV generation & migration
│
├── vVeh_LCO_Mapping/           # Excel/CSV mapping workflow
│   └── src/
│       ├── __main__.py         # Entry point
│       ├── config.json         # Excel settings, input paths
│       ├── config.py           # Config loader & constants
│       └── Handlers/
│           ├── directory_handler.py   # Output directory management
│           ├── excel_reader.py        # Excel file reading
│           ├── input_reader.py        # Excel/CSV input reader
│           ├── mapping_handler.py     # Software line matching logic
│           └── report_generator.py    # Excel mapping report generation
│
└── Upload/                     # TIS/LCO migration upload
    ├── __main__.py             # Entry point (PBClient recipe execution)
    ├── TIS_LCO_Migration.py    # Migration helper functions
    └── convert_to_modelsjson.py # Convert migration data to models.json
```

## Usage

### **TIS_Artifact_Fetcher**

Extracts artifacts from TIS with configurable filters and validation.

**USE CASES:**
- Get all artifacts of supported type no matter where on TIS it was uploaded
- Generate report of wrongly upload directories/wrong naming convention for supported artifacts. Get errors listed by user/project.
- GUI Tool to see and filter fetched artifacts with more options than TIS (Filter by user f.e.). Current filter view can be exported in Excel.

```bash
python -m TIS_Artifact_Fetcher.src
python -m TIS_Artifact_Fetcher.src --gui   # Open artifact viewer GUI only (no extraction)
```

**Output:** `output/run_*/` containing:
- `{component_type}_artifacts_*.json` - All artifacts by component type
- `latest_{component_type}_artifacts_*.json` - Latest artifact per software line
- `{component_type}_validation_report_*.xlsx` - Path/naming validation report (if enabled)
- `metadata.txt` - Configuration and filters used for the run

**Key features:**
- Recursive BFS search to find artifacts even in non-standard locations
- Adaptive depth with fallback for slow API responses
- Concurrent requests with caching and branch pruning
- Ensures ALL software lines appear in every component type output (even those with no artifacts of that type)
- Configurable filters: `component_type`, `component_name`, `component_grp`, `life_cycle_status`
- Naming convention validation with regex patterns per component type
- Path structure validation against expected conventions

### **TDrive_Artifact_Fetcher**

Extracts LCO artifact metadata from network-shared zip archives and generates migration files for TIS upload.

**USE CASES:**
- Parse and unzip all supported T-Drive LCO artifacts! Unzip and search for released artifacts with hex/a2l file available. These are necessary to get a mapping of Tdrive artifact to software line!

```bash
python -m TDrive_Artifact_Fetcher
```

**Workflow (7 steps):**

1. **Scan** network drive for LCO 5.4.5 zip archives, extract `Model_Overview.html` metadata
2. **Scan** network drive for LCO 5.4.11 zip archives, extract `Model_Overview.html` metadata
3. **Transform** `missing.xlsx` (PVER export) to CSV for processing - This is generated from vVeh_LCO_mapping tool: Rename the other tools software line report output to missing.xlsx as input.
4. **Compare** extracted artifacts against missing PVER entries by matching PVER patterns in A2L/HEX file paths
5. **Dump** matched results to `check.json` (deduplicated, keeping latest version per artifact)
6. **Generate CSV** of all PVER/Project pairs found on TDrive (`tdrive_pver_projects.csv`)
7. **Generate** `mig.json` - the migration file for TIS upload

**Inputs:**
- Network drive access to `LCO_Projects` directory (path in `config.json`)
- `input/missing.xlsx` - Excel export of missing PVER entries. his is generated from vVeh_LCO_mapping tool: Rename the other tools software line report output to missing.xlsx as input

**Output** (`output/`):
- `545list.json` - LCO 5.4.5 artifact metadata
- `5411list.json` - LCO 5.4.11 artifact metadata
- `check.json` - matched artifacts with PVER and transfer data
- `tdrive_pver_projects.csv` - all PVER (software line) / Project pairs found on TDrive
- `mig.json` - migration file for TIS upload

#### Migration File (`mig.json`)

The migration file is the final output used to upload artifacts into TIS. It contains a list of model entries, each specifying:

| Field | Description |
|-------|-------------|
| `model_input_filepath` | Source path to the zip archive on the network drive |
| `tis_artifact_path` | Target folder structure in TIS (e.g. `xCU Projects/{Project}/{PVER}/Model/HiL/{CSP_SWB}/{LabcarType}`) |
| `tis_artifact_name` | Artifact display name (prefixed with `VW MDL :` if missing) |
| `customer_group` | Always `VW` |
| `tis_migration` | Migration flag (true) |
| `lco_migration` | LCO migration flag (false) |

This file serves as input for the Upload tool that creates the actual artifacts in TIS based on these transfer definitions.

### **vVeh_LCO_Mapping**

Maps software lines from a master file (Excel or CSV) to TIS vVeh_LCO artifacts.

**USE CASES:**
- Get report of all TIS software lines with latest artifact. See if sottware line has a relevant artifact (CSV).
- Input the XLSX to see if the give ECU-HARDWARE / SOFTWARE LINES in the input file have an LCO artifact on TIS

```bash
# Auto-detect files from config
python -m vVeh_LCO_Mapping.src

# Specify files
python -m vVeh_LCO_Mapping.src artifacts.json master.xlsx
```

The master file can be:
- Excel (.xlsx) - original master data format
- CSV (.csv) - generated by `TIS_Artifact_Fetcher/src/tis_project_lister.py`

**Output:** `output/run_*/software_line_mapping_*.xlsx`

The generated csv has all current projects and software lines currently available on TIS under xCU Projects. Use the csv to get a mapping of artifacts to all software lines available!

The mapping report includes:
- **Master Data** columns: Software Line, Project
- **TIS Status**: Whether the software line was found in TIS
- **Artifact Data**: Latest artifact name, RID, project info, software type, LCO/VeMoX version, labcar type, life cycle status, upload path, TIS link

### **Upload**

Executes TIS and LCO migration recipes using PBClient to upload artifacts into TIS.

**USE CASES:**
- Upload the previously found artifacts back to TIS from the TDrive! The input files have to be generated from the other tools.

```bash
python -m Upload
```

**Inputs:**
- `models.json` - migration model definitions (converted from `mig.json`)
- PBClient recipe files (`.pbr`)

## Workflow

```
TIS API ──► TIS_Artifact_Fetcher ──► JSON files
                                         │
Excel Master ──► vVeh_LCO_Mapping ◄──────┘
                        │
                        ▼
              Mapping Report (Excel)

Network Drive ──► TDrive_Artifact_Fetcher ──► mig.json ──► Upload ──► TIS
```

## Configuration

Each tool uses a `config.json` file:

- **TIS_Artifact_Fetcher**: API settings, artifact filters, branch pruning, optimization (concurrency, caching, adaptive depth), naming/path convention validation rules
- **TDrive_Artifact_Fetcher**: Network paths, LCO version configs, log level
- **vVeh_LCO_Mapping**: Input file paths, Excel formatting, output settings, TIS link template

## Supported Artifact Types

- `vVeh_LCO` - Vehicle models (LCO/VeMoX versions)
- `test_ECU-TEST` - ECU test artifacts
- Custom types via `artifact_filters` in configuration

## Requirements

- Python 3.8+
- requests
- openpyxl
- wxPython (optional, for artifact viewer GUI)
