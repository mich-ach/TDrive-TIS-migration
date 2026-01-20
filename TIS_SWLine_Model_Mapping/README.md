# TIS Artifact Extractor & Validator

A comprehensive tool for extracting, mapping, and validating TIS (Test Information System) artifacts. It matches software lines from an Excel master file with TIS data, extracts version information, validates paths and naming conventions, and generates detailed reports.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Artifact Viewer GUI](#artifact-viewer-gui)
- [Adding New Artifact Types](#adding-new-artifact-types)
- [Adding Component-Specific Validators](#adding-component-specific-validators)
- [Reports](#reports)
- [Troubleshooting](#troubleshooting)

## Features

- **Artifact Extraction**: Fetch artifacts from TIS API with configurable filters
- **Software Line Mapping**: Match Excel software lines with TIS data using flexible matching
- **Version Extraction**: Extract LCO and VeMoX versions from artifact metadata
- **Path Validation**: Validate artifact paths against expected conventions
- **Naming Validation**: Validate artifact names against configurable regex patterns
- **Component-Specific Validation**: Custom validation rules per artifact type
- **Interactive GUI**: Browse, filter, sort, and export artifacts
- **Excel Reports**: Detailed reports with color coding and multiple sheets

## Architecture

The project follows a modular architecture with clear separation of concerns:

```
src/
├── __main__.py              # Entry point and workflow orchestration
├── config.py                # Configuration loader (from config.json)
├── config.json              # User-configurable settings
├── artifact_viewer_gui.py   # wxPython GUI for browsing artifacts
│
├── Api/                     # TIS API client
│   └── __init__.py          # TISClient class for API interactions
│
├── Extractors/              # Data extraction from API responses
│   └── __init__.py          # ArtifactExtractor, version/type extraction
│
├── Filters/                 # Artifact filtering logic
│   └── __init__.py          # ArtifactFilter for component matching
│
├── Handlers/                # Excel file handling
│   └── __init__.py          # ExcelHandler for reading/writing Excel
│
├── Models/                  # Data models (dataclasses)
│   └── __init__.py          # ArtifactInfo, ValidationResult, enums
│
├── Reports/                 # Report generation
│   └── __init__.py          # Excel report generator with multiple sheets
│
├── Utils/                   # Utility functions
│   └── __init__.py          # VersionParser, string normalization
│
└── Validators/              # Path and naming validation
    └── __init__.py          # PathValidator class
```

### Key Components

| Module | Purpose |
|--------|---------|
| **Api** | HTTP client for TIS API with retry logic, caching, and timeout handling |
| **Extractors** | Parse API responses, extract metadata (versions, types, dates) |
| **Filters** | Filter artifacts by component type, lifecycle status, deletion state |
| **Models** | Type-safe dataclasses for all data structures |
| **Validators** | Validate paths and names against configurable conventions |
| **Reports** | Generate Excel reports with formatting and multiple analysis sheets |

## Installation

### Prerequisites

- Python 3.8+ or Anaconda/Miniconda
- Network access to TIS (Bosch network or VPN)
- Windows, Linux, or macOS

### Quick Start (Windows)

1. Extract all files maintaining the directory structure
2. Place your master Excel file in the root directory
3. Double-click `install_and_run.bat`

### Manual Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r src/requirements.txt

# Run the tool
python -m src
```

### Dependencies

Core dependencies (see `requirements.txt`):
- `requests` - HTTP client for TIS API
- `openpyxl` - Excel file handling
- `wxPython` - GUI framework (optional, for artifact viewer)

## Configuration

All settings are in `src/config.json`. The file is organized into sections:

### Workflow Settings

```json
"workflow": {
    "default_excel_file": "path/to/your/excel.xlsx",
    "auto_open_report": false,
    "generate_validation_report": false,
    "open_artifact_viewer": false
}
```

### API Settings

```json
"api": {
    "root_project_id": "790066",
    "tis_url": "http://rb-ps-tis-service.bosch.com:8081/tis-api/...",
    "timeout_connect": 15,
    "timeout_read": 60
}
```

### Artifact Filters

Filter which artifacts to extract:

```json
"artifact_filters": {
    "component_type": ["vVeh"],
    "component_name": ["vVeh_LCO"],
    "component_grp": "TIS Artifact Container",
    "life_cycle_status": ["released", "archived", "development"],
    "skip_deleted": true
}
```

- `component_type`: Filter by artifact type (e.g., "vVeh", "MDL")
- `component_name`: Filter by component name pattern
- `component_grp`: Filter by component group
- `life_cycle_status`: Include only these lifecycle states
- `skip_deleted`: Exclude artifacts with past deletion dates

### Branch Pruning

Skip unnecessary folders to improve performance:

```json
"branch_pruning": {
    "include_projects": [],
    "skip_projects": ["VC1CP013"],
    "skip_folders": ["Documentation", "Archive", "Backup"],
    "skip_patterns": ["^_.*", "^\\..*"]
}
```

### Naming Convention Patterns

Define regex patterns for artifact name validation:

```json
"naming_convention": {
    "enabled": true,
    "patterns": {
        "vveh_lco": {
            "description": "vVeh_LCO artifact pattern",
            "pattern": "^(?:(?P<timestamp>[\\dT:\\-Z]+)\\s*-\\s*)?VW\\s+vVeh_LCO\\s*:...",
            "example": "VW vVeh_LCO : DMG1211V07C1935 / M22J71 [] 110kW_OPF_DQ_CANv7"
        }
    }
}
```

### Path Convention

Define expected path structures per component type:

```json
"path_convention": {
    "enabled": true,
    "expected_structure": {
        "MDL": "{Project}/{SoftwareLine}/Model/HiL/{CSP|SWB}/.../{artifact}",
        "vVeh_LCO": "{Project}/{SoftwareLine}/Model/SiL/vVeh/.../{artifact}"
    },
    "model_subfolders": {
        "MDL": ["CSP", "SWB"],
        "vVeh": ["vVeh"]
    }
}
```

## Usage

### Command Line

```bash
# Run with default Excel file from config
python -m src

# Run with specific Excel file
python -m src --excel path/to/file.xlsx

# Run artifact viewer GUI only
python -m src.artifact_viewer_gui

# Run with a specific JSON file in viewer
python -m src.artifact_viewer_gui path/to/artifacts.json
```

### Output Files

All output is saved to `output/run_YYYYMMDD_HHMMSS/`:

- `vveh_lco_artifacts_*.json` - Extracted artifacts with full metadata
- `software_line_mapping_*.xlsx` - Excel report with mapping results
- `validation_report_*.xlsx` - Path/naming validation report (if enabled)

## Artifact Viewer GUI

The interactive GUI allows browsing and analyzing extracted artifacts.

### Features

- **Multi-level Filtering**: Filter by project, software line, component type, simulation type, software type, labcar type, test type, LCO version, VeMoX version, lifecycle status, user, and more
- **Dynamic Column Visibility**: Empty columns are automatically hidden
- **Sorting**: Click column headers to sort ascending/descending
- **Search**: Free-text search across all fields
- **Export to Excel**: Export current filter results with formatting
- **TIS Links**: Double-click to open artifact in TIS dashboard

### Running the GUI

```bash
# Open with latest artifacts
python -m src.artifact_viewer_gui

# Open specific JSON file
python -m src.artifact_viewer_gui output/run_*/vveh_lco_artifacts_*.json
```

## Adding New Artifact Types

To add support for a new artifact type (e.g., "test_ECU-TEST"):

### Step 1: Update Artifact Filters in config.json

```json
"artifact_filters": {
    "component_type": ["vVeh", "test"],
    "component_name": ["vVeh_LCO", "test_ECU-TEST"],
    ...
}
```

### Step 2: Add Naming Convention Pattern (Optional)

If the new artifact type has a specific naming convention:

```json
"naming_convention": {
    "patterns": {
        "test_ecu_test": {
            "description": "ECU-TEST artifact naming pattern",
            "pattern": "^(?P<project>.+)_(?P<testtype>BFT|SIT|UIT)_(?P<version>\\d+\\.\\d+)$",
            "example": "MyProject_BFT_1.0"
        }
    }
}
```

### Step 3: Add Path Convention (Optional)

If the artifact has an expected folder structure:

```json
"path_convention": {
    "expected_structure": {
        "test_ECU-TEST": "{Project}/{SoftwareLine}/Test/{TestType}/.../{artifact}"
    },
    "model_subfolders": {
        "test_ECU-TEST": ["BFT", "SIT", "UIT"]
    }
}
```

### Step 4: Add Extraction Logic (If Needed)

If the new artifact type has special attributes to extract, update `Extractors/__init__.py`:

```python
# In _condense_component_info method, add attribute handling:
elif name == 'customAttribute':
    condensed['custom_field'] = value
```

### Step 5: Update Models (If New Fields)

Add new fields to `ArtifactInfo` in `Models/__init__.py`:

```python
@dataclass
class ArtifactInfo:
    # ... existing fields ...
    custom_field: Optional[str] = None  # New field

    def to_dict(self) -> Dict[str, Any]:
        return {
            # ... existing fields ...
            'custom_field': self.custom_field,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtifactInfo":
        return cls(
            # ... existing fields ...
            custom_field=data.get('custom_field'),
        )
```

## Adding Component-Specific Validators

To add validation rules for a specific artifact type:

### Step 1: Add DeviationType (If Needed)

In `Models/__init__.py`, add a new deviation type:

```python
class DeviationType(Enum):
    VALID = "VALID"
    # ... existing types ...
    # Add your new deviation type
    CUSTOM_MISMATCH = "CUSTOM_MISMATCH"
```

### Step 2: Add Validation Method to PathValidator

In `Validators/__init__.py`, add a new validation method:

```python
class PathValidator:
    # ... existing methods ...

    def validate_test_type(
        self,
        component_name: str,
        test_type_attribute: Optional[str],
        upload_path: str
    ) -> Tuple[DeviationType, str, str]:
        """
        Validate that testType attribute matches the path Test/{TestType}.

        This validation is component-specific and only applies to certain
        component types (e.g., 'test_ECU-TEST').
        """
        # List of component types that require this validation
        test_type_components = ['test_ECU-TEST']

        # Only validate for specific component types
        if not component_name or component_name not in test_type_components:
            return (DeviationType.VALID, "", "")

        # Extract expected value from path
        test_type_from_path = self._extract_test_type_from_path(upload_path)

        # Check for mismatch
        if test_type_from_path and test_type_attribute:
            if test_type_from_path != test_type_attribute:
                return (
                    DeviationType.TEST_TYPE_MISMATCH,
                    f"testType attribute '{test_type_attribute}' does not match path",
                    f"Expected testType='{test_type_from_path}' based on path"
                )

        return (DeviationType.VALID, "", "")

    def _extract_test_type_from_path(self, path: str) -> Optional[str]:
        """Extract test type from path by looking for Test/{TestType} pattern."""
        if not path:
            return None
        path_parts = path.split('/')
        for i, part in enumerate(path_parts):
            if part == 'Test' and i + 1 < len(path_parts):
                return path_parts[i + 1]
        return None
```

### Step 3: Create a Custom Validator Class (For Complex Rules)

For more complex validation scenarios, create a dedicated validator:

```python
# In Validators/__init__.py or a new file

class ECUTestValidator:
    """Validator for test_ECU-TEST artifacts."""

    # Components this validator applies to
    APPLICABLE_COMPONENTS = ['test_ECU-TEST']

    def __init__(self):
        self.path_validator = PathValidator()

    def is_applicable(self, component_name: str) -> bool:
        """Check if this validator applies to the given component."""
        return component_name in self.APPLICABLE_COMPONENTS

    def validate(self, artifact: ArtifactInfo) -> List[Tuple[DeviationType, str, str]]:
        """
        Run all validations for this artifact type.

        Returns list of (DeviationType, details, hint) tuples.
        """
        results = []

        # Validate test type matches path
        result = self.path_validator.validate_test_type(
            artifact.component_type,
            artifact.test_type,
            artifact.upload_path
        )
        if result[0] != DeviationType.VALID:
            results.append(result)

        # Add more validations as needed
        # result = self._validate_custom_rule(artifact)
        # if result[0] != DeviationType.VALID:
        #     results.append(result)

        return results
```

### Step 4: Integrate Validator into Workflow

Call your validator during the extraction or report generation phase:

```python
# In __main__.py or extraction workflow

from Validators import PathValidator, ECUTestValidator

# Create validators
path_validator = PathValidator()
ecu_test_validator = ECUTestValidator()

# For each artifact
for artifact in artifacts:
    # Run component-specific validation
    if ecu_test_validator.is_applicable(artifact.component_type):
        deviations = ecu_test_validator.validate(artifact)
        for dev_type, details, hint in deviations:
            if dev_type != DeviationType.VALID:
                # Log or store the deviation
                logger.warning(f"Validation failed: {details}")
```

## Reports

### Software Line Mapping Report

Generated Excel report with sheets:

| Sheet | Content |
|-------|---------|
| **Mapping Results** | Software line to TIS mapping with versions |
| **Explanation** | Report legend and color coding |

Color coding:
- **White**: Master data from Excel
- **Blue**: TIS status column
- **Green**: Artifact found
- **Red**: No artifact found
- **Grey**: Software line not in TIS

### Validation Report

Generated when `generate_validation_report: true`:

| Sheet | Content |
|-------|---------|
| **Summary** | Overview statistics |
| **Deviations** | All path/naming violations |
| **By User** | Deviations grouped by uploader |
| **By Project** | Deviations grouped by project |
| **By Component Type** | Summary per component type |
| **Dev-{ComponentType}** | Detailed deviations per component |
| **Valid Artifacts** | All artifacts passing validation |

### GUI Export

Export current filter results to Excel with:
- Active filter summary
- All visible columns
- Formatted headers
- Auto-adjusted column widths

## Troubleshooting

### Common Issues

**Script fails to run**
- Ensure Python/Anaconda is installed and in PATH
- Verify network connectivity to TIS
- Check `config.json` syntax (valid JSON)

**No artifacts found**
- Verify `artifact_filters` in config match your target artifacts
- Check `branch_pruning` isn't skipping your projects
- Ensure `life_cycle_status` includes desired states

**GUI doesn't start**
- Install wxPython: `pip install wxPython`
- On Linux: `sudo apt-get install python3-wxgtk4.0`

**Excel export fails**
- Install openpyxl: `pip install openpyxl`

**API timeouts**
- Increase `timeout_read` in config
- Reduce `concurrent_requests`
- Check network connectivity

### Logging

Set log level in config:

```json
"debug": {
    "log_level": "DEBUG"
}
```

Levels: DEBUG, INFO, WARNING, ERROR

### Performance Tips

1. Use `branch_pruning` to skip irrelevant folders
2. Set specific `include_projects` if only checking certain projects
3. Increase `children_level` for shallow extractions (faster but less complete)
4. Use `skip_deleted: true` to reduce data volume

## License

Internal use only - Bosch proprietary.
