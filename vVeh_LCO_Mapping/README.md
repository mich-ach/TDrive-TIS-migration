# vVeh_LCO Software Line Mapping

A workflow tool for mapping software lines from an Excel master file to vVeh_LCO artifacts extracted from TIS. It creates detailed Excel mapping reports showing which software lines have corresponding TIS artifacts and validates artifact paths/naming conventions.

## Overview

This tool is designed specifically for vVeh_LCO artifacts. It takes:
1. **Input**: vVeh_LCO artifact JSON (from TIS_SWLine_Model_Mapping) + Excel master file
2. **Output**: Excel mapping report + optional validation report

## Prerequisites

- Extracted vVeh_LCO artifacts (JSON file from TIS_SWLine_Model_Mapping)
- Master Excel file with software lines to map
- Python 3.8+

## Installation

```bash
cd vVeh_LCO_Mapping

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# Install dependencies
pip install openpyxl
```

## Usage

### Two-Step Workflow

**Step 1: Extract artifacts from TIS**

```bash
# Run the TIS extractor (from parent directory)
cd ../TIS_SWLine_Model_Mapping
python -m src
```

This generates `vveh_lco_artifacts_*.json` in `TIS_SWLine_Model_Mapping/output/run_*/`.

**Step 2: Run the mapping workflow**

```bash
# From vVeh_LCO_Mapping directory
cd ../vVeh_LCO_Mapping

# With auto-detection (finds latest JSON, uses default Excel)
python -m src

# With specific files
python -m src path/to/vveh_lco_artifacts.json path/to/master.xlsx

# With just JSON file (uses default Excel)
python -m src path/to/vveh_lco_artifacts.json
```

## Configuration

Settings are in `src/config.json`:

```json
{
    "workflow": {
        "default_excel_file": "../Masterdata-XCU.xlsx",
        "auto_open_report": false,
        "generate_validation_report": false,
        "tis_extractor_path": "../TIS_SWLine_Model_Mapping"
    },
    "output": {
        "excel_prefix": "software_line_mapping"
    },
    "excel": {
        "colors": {
            "found_green": "E8F5E8",
            "not_found_red": "FFE6E6",
            "not_in_tis_grey": "D9D9D9"
        }
    }
}
```

### Key Settings

| Setting | Description |
|---------|-------------|
| `default_excel_file` | Path to master Excel file (relative to src/) |
| `auto_open_report` | Automatically open generated Excel reports |
| `generate_validation_report` | Generate path/naming validation report |
| `tis_extractor_path` | Path to TIS_SWLine_Model_Mapping (for imports) |

## Output

Output is saved to `output/run_YYYYMMDD_HHMMSS/`:

- `software_line_mapping_*.xlsx` - Main mapping report
- `validation_report_*.xlsx` - Path/naming validation (if enabled)

### Mapping Report

The Excel report shows:

| Column | Description |
|--------|-------------|
| Software Line | Name from master Excel |
| Project | Project name |
| TIS Status | Found / Not Found / Not in TIS |
| Artifact Name | TIS artifact name |
| LCO Version | Extracted LCO version |
| VeMoX Version | Extracted VeMoX version |
| TIS Link | Direct link to artifact in TIS |

**Color Coding:**
- **Green**: Artifact found in TIS
- **Red**: No artifact found for software line
- **Grey**: Software line not present in TIS structure

### Validation Report

When `generate_validation_report: true`, creates report with:

- **Summary**: Statistics overview
- **Deviations**: All path/naming violations
- **By User**: Grouped by uploader
- **By Project**: Grouped by project
- **Valid Artifacts**: All passing validation

## Architecture

```
vVeh_LCO_Mapping/
├── src/
│   ├── __main__.py      # Workflow entry point
│   ├── config.py        # Configuration loader
│   ├── config.json      # Settings
│   │
│   ├── Handlers/        # Excel file handling
│   │   └── __init__.py  # ExcelHandler, DirectoryHandler
│   │
│   └── Reports/         # Report generation
│       └── __init__.py  # Validation report generator
│
├── output/              # Generated reports
└── README.md
```

### Module Dependencies

This workflow imports from TIS_SWLine_Model_Mapping:
- `Models` - Data models (ArtifactInfo, ValidationReport, DeviationType)
- `Validators` - PathValidator for validation reports

## Troubleshooting

**"No vVeh_LCO artifact JSON file found"**
- Run TIS extraction first: `python -m src` in TIS_SWLine_Model_Mapping
- Ensure artifact filter is set for vVeh_LCO

**"Excel file not found"**
- Check `default_excel_file` path in config.json
- Provide explicit path: `python -m src artifacts.json master.xlsx`

**Import errors for Models/Validators**
- Verify `tis_extractor_path` in config.json points to TIS_SWLine_Model_Mapping

## Related Tools

- **TIS_SWLine_Model_Mapping**: General TIS artifact extractor (required for JSON input)
- **Upload**: Tool for uploading artifacts to TIS

## License

Internal use only - Bosch proprietary.
