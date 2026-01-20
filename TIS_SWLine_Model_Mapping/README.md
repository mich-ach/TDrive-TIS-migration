# TIS Artifact Extractor

A general-purpose tool for extracting artifacts from TIS (Test Information System). It uses recursive BFS search to find and extract artifacts based on configurable filters, supporting multiple artifact types with type-specific data extraction.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Artifact Viewer GUI](#artifact-viewer-gui)
- [Adding New Artifact Types](#adding-new-artifact-types)
- [Adding Component-Specific Validators](#adding-component-specific-validators)
- [Output Format](#output-format)
- [Troubleshooting](#troubleshooting)

## Features

- **Multi-Type Extraction**: Extract different artifact types (vVeh_LCO, test_ECU-TEST, etc.) in a single run
- **Separate Output**: Artifacts are automatically separated by component type into individual JSON files
- **Type-Specific Data**: Each artifact type extracts its relevant metadata:
  - **vVeh_LCO**: LCO version, VeMoX version, simulation type, SW type, labcar type
  - **test_ECU-TEST**: Test type, test version, ECU-TEST version
- **Path & Naming Validation**: Validate artifacts against expected path and naming conventions
- **Interactive GUI**: Browse, filter, sort, and export artifacts with type-specific columns
- **Performance Optimized**: Concurrent requests, caching, and branch pruning

## Architecture

```
TIS_SWLine_Model_Mapping/
├── src/
│   ├── __main__.py              # Entry point - extraction workflow
│   ├── config.py                # Configuration loader
│   ├── config.json              # User settings
│   ├── artifact_viewer_gui.py   # wxPython GUI
│   │
│   ├── Api/                     # TIS API client
│   │   └── __init__.py          # HTTP client with retry logic
│   │
│   ├── Extractors/              # Data extraction
│   │   └── __init__.py          # BFS extraction, version parsing
│   │
│   ├── Filters/                 # Artifact filtering
│   │   └── __init__.py          # Component type/name filtering
│   │
│   ├── Models/                  # Data models
│   │   └── __init__.py          # ArtifactInfo, DeviationType, enums
│   │
│   ├── Utils/                   # Utilities
│   │   └── __init__.py          # Version parsing, string normalization
│   │
│   └── Validators/              # Validation logic
│       └── __init__.py          # Path and naming validators
│
└── output/                      # Generated output files
    └── run_YYYYMMDD_HHMMSS/     # Timestamped run directories
```

### Key Components

| Module | Purpose |
|--------|---------|
| **Api** | HTTP client for TIS API with retry logic, caching, and timeout handling |
| **Extractors** | BFS traversal, parse API responses, extract type-specific metadata |
| **Filters** | Filter artifacts by component type, lifecycle status, deletion state |
| **Models** | Type-safe dataclasses for artifacts, validation results, enums |
| **Validators** | Validate paths and names against configurable conventions |

## Installation

### Prerequisites

- Python 3.8+ or Anaconda/Miniconda
- Network access to TIS (Bosch network or VPN)
- Windows, Linux, or macOS

### Quick Start

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r src/requirements.txt

# Run extraction
python -m src
```

### Dependencies

- `requests` - HTTP client for TIS API
- `openpyxl` - Excel file handling (for GUI export)
- `wxPython` - GUI framework (optional)

## Configuration

All settings are in `src/config.json`:

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

Control which artifacts to extract:

```json
"artifact_filters": {
    "component_type": ["vVeh", "test"],
    "component_name": ["vVeh_LCO", "test_ECU-TEST"],
    "component_grp": "TIS Artifact Container",
    "life_cycle_status": ["released", "archived", "development"],
    "skip_deleted": true
}
```

### Branch Pruning

Skip folders to improve performance:

```json
"branch_pruning": {
    "include_projects": [],
    "skip_projects": ["VC1CP013"],
    "skip_folders": ["Documentation", "Archive"],
    "skip_patterns": ["^_.*", "^\\..*"]
}
```

### Naming Convention Patterns

Define regex patterns for artifact name validation using **component_name** as key:

```json
"naming_convention": {
    "enabled": true,
    "patterns": {
        "vVeh_LCO": {
            "description": "vVeh_LCO artifact: [timestamp -] VW vVeh_LCO : <SW> / <PVER> [<dataset>] <variant>",
            "pattern": "^(?:(?P<timestamp>[\\dT:\\-Z]+)\\s*-\\s*)?VW\\s+vVeh_LCO\\s*:...",
            "example": "VW vVeh_LCO : DMG1211V07C1935 / M22J71 [] 110kW_OPF_DQ_CANv7"
        },
        "test_ECU-TEST": {
            "description": "ECU-TEST test artifact: <Project>_<TestType>_<Description>",
            "pattern": "^(?P<project>[A-Za-z0-9_]+)_(?P<test_type>BFT|SIT|UIT|SWT|HIT)_(?P<description>.+)$",
            "example": "MG1CS211_BFT_DiagnosticTests"
        }
    }
}
```

### Path Convention

Define expected path structures using **component_name** as key:

```json
"path_convention": {
    "enabled": true,
    "expected_structure": {
        "vVeh_LCO": "{Project}/{SoftwareLine}/Model/SiL/vVeh/.../{artifact}",
        "test_ECU-TEST": "{Project}/{SoftwareLine}/Test/{TestType}/.../{artifact}"
    },
    "model_subfolders": {
        "vVeh_LCO": ["vVeh"],
        "test_ECU-TEST": ["BFT", "SIT", "UIT", "SWT", "HIT"]
    }
}
```

## Usage

### Command Line

```bash
# Run extraction
python -m src

# Run extraction then open GUI
python -m src --gui

# Open GUI with existing JSON file
python -m src.artifact_viewer_gui path/to/artifacts.json
```

### Output

Output is saved to `output/run_YYYYMMDD_HHMMSS/`:

- `vveh_lco_artifacts_*.json` - vVeh_LCO artifacts
- `test_ecu_test_artifacts_*.json` - ECU-TEST artifacts
- `{component_type}_artifacts_*.json` - Other artifact types

## Artifact Viewer GUI

Interactive GUI for browsing extracted artifacts with type-specific columns.

### Features

- **Artifact Type First**: Component type selector determines which columns are shown
- **Dynamic Columns**: Columns adapt to selected artifact type:
  - **vVeh_LCO**: simulation_type, sw_type, labcar_type, lco_version, vemox_version
  - **test_ECU-TEST**: test_type, test_version, ecu_test_version
  - **All**: Shows all available columns
- **Filtering**: Multi-level filters (project, software line, type-specific)
- **Dynamic Column Visibility**: Empty columns are automatically hidden
- **Sorting**: Click column headers to sort
- **Search**: Free-text search across all fields
- **Export**: Export filtered results to Excel
- **TIS Links**: Double-click to open artifact in TIS dashboard

### Running the GUI

```bash
# Open GUI and select JSON file
python -m src.artifact_viewer_gui

# Open specific artifact file
python -m src.artifact_viewer_gui output/run_*/vveh_lco_artifacts_*.json
```

## Adding New Artifact Types

### Step 1: Update Artifact Filters

In `config.json`:

```json
"artifact_filters": {
    "component_type": ["vVeh", "test", "myNewType"],
    "component_name": ["vVeh_LCO", "test_ECU-TEST", "myNewType_Name"],
    ...
}
```

### Step 2: Add Extraction Logic

In `Extractors/__init__.py`, add attribute handling in `_condense_component_info`:

```python
elif name == 'myCustomAttribute':
    condensed['my_custom_field'] = value
```

### Step 3: Update Models

In `Models/__init__.py`, add new fields to `ArtifactInfo`:

```python
@dataclass
class ArtifactInfo:
    # ... existing fields ...
    my_custom_field: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            # ... existing fields ...
            'my_custom_field': self.my_custom_field,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtifactInfo":
        return cls(
            # ... existing fields ...
            my_custom_field=data.get('my_custom_field'),
        )
```

### Step 4: Configure GUI Columns

In `artifact_viewer_gui.py`, add column definition:

```python
MY_NEW_TYPE_COLUMNS = [
    ("project", "Project", 120, 1, "_project"),
    ("sw_line", "Software Line", 120, 1, "_sw_line"),
    ("name", "Name", 180, 3, "name"),
    ("artifact_rid", "Artifact RID", 55, 0, "artifact_rid"),
    ("my_custom_field", "Custom Field", 80, 0, "my_custom_field"),
    ("created_date", "Created Date", 90, 0, "created_date"),
    ("user", "User", 70, 0, "user"),
    ("upload_path", "Upload Path", 200, 3, "upload_path"),
]

# Register in COMPONENT_COLUMNS:
COMPONENT_COLUMNS = {
    "vVeh_LCO": VVEH_LCO_COLUMNS,
    "test_ECU-TEST": TEST_ECU_TEST_COLUMNS,
    "myNewType_Name": MY_NEW_TYPE_COLUMNS,
}
```

Column tuple: `(key, header, min_width, weight, data_key)`

### Step 5: Add Naming Convention

Add a naming pattern in `config.json` using **component_name** as the key:

```json
"naming_convention": {
    "patterns": {
        "myNewType_Name": {
            "description": "Description of the naming pattern",
            "pattern": "^regex_pattern_here$",
            "example": "Example artifact name"
        }
    }
}
```

### Step 6: Add Path Convention

Add expected path structure using **component_name** as the key:

```json
"path_convention": {
    "expected_structure": {
        "myNewType_Name": "{Project}/{SoftwareLine}/CustomFolder/.../{artifact}"
    },
    "model_subfolders": {
        "myNewType_Name": ["Subfolder1", "Subfolder2"]
    }
}
```

### Reference: Additional Convention Patterns

Below are example patterns for other artifact types that can be added:

**Naming Conventions:**

```json
"naming_convention": {
    "patterns": {
        "MDL": {
            "description": "MDL Model (HiL/SiL optional): [timestamp -] VW MDL[_HiL|_SiL] : <ECU> / <variant>",
            "pattern": "^(?:(?P<timestamp>[\\dT:\\-Z]+)\\s*-\\s*)?VW\\s+MDL(?:_(?P<type>HiL|SiL))?\\s*:\\s*(?P<ecu>[^/]+)\\s*/\\s*(?P<variant>.+?)(?:;[a-zA-Z0-9]+)?$",
            "example": "VW MDL : MG1CS038_C3 / V8T_Stereo_DCT_FX_v8"
        },
        "MDL_HiL_PCIe": {
            "description": "HiL Model with platform: [timestamp -] VW MDL[_HiL]_<platform> : <ECU> / <variant>",
            "pattern": "^(?:(?P<timestamp>[\\dT:\\-Z]+)\\s*-\\s*)?VW\\s+MDL(?:_HiL)?_(?P<platform>PCIe|VME)\\s*:\\s*(?P<ecu>[^/]+)\\s*/\\s*(?P<variant>.+?)(?:;[a-zA-Z0-9]+)?$",
            "example": "VW MDL_HiL_PCIe : MG1CS211_C_EA211Evo / 110kW_OPF_DQ_CANv7"
        },
        "MDL_SiL": {
            "description": "SiL Reference Model: [timestamp -] VW MDL[_HiL|_SiL] : <ECU> / <variant>_Ref_SiL",
            "pattern": "^(?:(?P<timestamp>[\\dT:\\-Z]+)\\s*-\\s*)?VW\\s+MDL(?:_(?:HiL|SiL))?\\s*:\\s*(?P<ecu>[^/]+)\\s*/\\s*(?P<variant>.+)_Ref_SiL$",
            "example": "VW MDL : MG1CS211_C_EA211Evo / 110kW_OPF_DQ_CANv7_Ref_SiL"
        },
        "vVehFrame_Silver": {
            "description": "vVehFrame: [timestamp -] VW vVehFrame_<env> : <SW> / <PVER> [<dataset>] <variant>",
            "pattern": "^(?:(?P<timestamp>[\\dT:\\-Z]+)\\s*-\\s*)?VW\\s+vVehFrame_(?P<env>Silver|FMU)\\s*:\\s*(?P<sw>[^/]+)\\s*/\\s*(?P<pver>\\S+)\\s*\\[(?P<dataset>[^\\]]*)\\]\\s*(?P<variant>.+?)(?:;[a-zA-Z0-9]+)?$",
            "example": "VW vVehFrame_Silver : DMG1211V07C1935 / M22J71 [] 110kW_OPF_DQ_CANv7"
        },
        "SetupSkeleton_Silver": {
            "description": "SetupSkeleton: [timestamp -] VW SetupSkeleton_<env> : <SW> / <PVER> [<dataset>] <variant>",
            "pattern": "^(?:(?P<timestamp>[\\dT:\\-Z]+)\\s*-\\s*)?VW\\s+SetupSkeleton_(?P<env>Silver|FMU)\\s*:\\s*(?P<sw>[^/]+)\\s*/\\s*(?P<pver>\\S+)\\s*\\[(?P<dataset>[^\\]]*)\\]\\s*(?P<variant>.+?)(?:;[a-zA-Z0-9]+)?$",
            "example": "VW SetupSkeleton_Silver : DMG1211V07C1935 / M22J71 [] 110kW_OPF_DQ_CANv7"
        },
        "vVeh_Silver": {
            "description": "vVeh complete workspace: [timestamp -] VW vVeh_<env> : <SW> / <PVER> [<dataset>] <variant>",
            "pattern": "^(?:(?P<timestamp>[\\dT:\\-Z]+)\\s*-\\s*)?VW\\s+vVeh_(?P<env>Silver|FMU)\\s*:\\s*(?P<sw>[^/]+)\\s*/\\s*(?P<pver>\\S+)\\s*\\[(?P<dataset>[^\\]]*)\\]\\s*(?P<variant>.+?)(?:;[a-zA-Z0-9]+)?$",
            "example": "VW vVeh_Silver : DMG1211V07C1935 / M22J71 [] 110kW_OPF_DQ_CANv7"
        }
    }
}
```

**Path Conventions:**

```json
"path_convention": {
    "expected_structure": {
        "MDL": "{Project}/{SoftwareLine}/Model/HiL/{CSP|SWB}/.../{artifact}",
        "MDL_HiL_PCIe": "{Project}/{SoftwareLine}/Model/HiL/{CSP|SWB}/.../{artifact}",
        "MDL_HiL_VME": "{Project}/{SoftwareLine}/Model/HiL/{CSP|SWB}/.../{artifact}",
        "MDL_SiL": "{Project}/{SoftwareLine}/Model/SiL/{Flexray|Plant|SubCAN|vEL}/.../{artifact}",
        "SetupSkeleton_Silver": "{Project}/{SoftwareLine}/Model/SiL/SetupSkeleton_Silver/.../{artifact}",
        "SetupSkeleton_FMU": "{Project}/{SoftwareLine}/Model/SiL/SetupSkeleton/.../{artifact}",
        "vVehFrame_Silver": "{Project}/{SoftwareLine}/Model/SiL/vVehFrame_Silver/.../{artifact}",
        "vVehFrame_FMU": "{Project}/{SoftwareLine}/Model/SiL/vVehFrame/.../{artifact}",
        "vVeh_Silver": "{Project}/{SoftwareLine}/Model/SiL/vVeh/.../{artifact}",
        "vVeh_FMU": "{Project}/{SoftwareLine}/Model/SiL/vVeh/.../{artifact}",
        "vXCU_Silver": "{Project}/{SoftwareLine}/Model/SiL/vXCU/.../{artifact}",
        "XCUSW_Hex": "{Project}/{SoftwareLine}/Model/SiL/XCUSW/.../{artifact}"
    },
    "model_subfolders": {
        "MDL": ["CSP", "SWB"],
        "MDL_HiL": ["CSP", "SWB"],
        "MDL_SiL": ["Flexray", "Plant", "SubCAN", "vEL"],
        "SetupSkeleton": ["SetupSkeleton", "SetupSkeleton_Silver"],
        "vVehFrame": ["vVehFrame", "vVehFrame_Silver"],
        "vVeh": ["vVeh"],
        "vXCU": ["vXCU"],
        "XCUSW": ["XCUSW"]
    }
}
```

## Adding Component-Specific Validators

### Step 1: Add DeviationType

In `Models/__init__.py`:

```python
class DeviationType(Enum):
    VALID = "VALID"
    # ... existing types ...
    MY_CUSTOM_MISMATCH = "MY_CUSTOM_MISMATCH"
```

### Step 2: Add Validation Method

In `Validators/__init__.py`:

```python
class PathValidator:
    def validate_my_custom_rule(
        self,
        component_name: str,
        attribute_value: Optional[str],
        upload_path: str
    ) -> Tuple[DeviationType, str, str]:
        """Validate custom rule for specific component type."""
        applicable_components = ['myNewType_Name']

        if component_name not in applicable_components:
            return (DeviationType.VALID, "", "")

        # Your validation logic here
        if some_condition_fails:
            return (
                DeviationType.MY_CUSTOM_MISMATCH,
                f"Validation failed: {details}",
                f"Expected: {hint}"
            )

        return (DeviationType.VALID, "", "")
```

### Step 3: Integrate into Extraction

In `Extractors/__init__.py`, call your validator during extraction:

```python
# After extracting artifact info
deviation, details, hint = path_validator.validate_my_custom_rule(
    component_name,
    artifact.my_custom_field,
    artifact.upload_path
)
if deviation != DeviationType.VALID:
    artifact.deviation_type = deviation.value
    artifact.deviation_details = details
```

## Output Format

### JSON Structure

```json
{
    "ProjectName": {
        "project_rid": "123456",
        "software_lines": {
            "SWLineName": {
                "software_line_rid": "789012",
                "latest_artifact": {
                    "artifact_rid": "345678",
                    "name": "Artifact Name",
                    "component_type": "vVeh_LCO",
                    "created_date": "2024-01-15",
                    "user": "username",
                    "upload_path": "/Project/SWLine/Model/...",
                    "lco_version": "DMG1211V07C1935",
                    "vemox_version": "M22J71"
                },
                "artifacts": [...]
            }
        }
    }
}
```

## Troubleshooting

### Common Issues

**No artifacts found**
- Check `artifact_filters` match your targets
- Verify `branch_pruning` isn't skipping your projects
- Ensure `life_cycle_status` includes desired states

**GUI doesn't start**
- Install wxPython: `pip install wxPython`
- Linux: `sudo apt-get install python3-wxgtk4.0`

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

### Performance Tips

1. Use `branch_pruning` to skip irrelevant folders
2. Set specific `include_projects` for focused extraction
3. Use `skip_deleted: true` to reduce data volume
4. Adjust `concurrent_requests` based on network conditions

## Related Tools

- **vVeh_LCO_Mapping**: Workflow for mapping vVeh_LCO artifacts to Excel software lines (see `../vVeh_LCO_Mapping/`)
- **Upload**: Tool for uploading artifacts to TIS (see `../Upload/`)

## License

Internal use only - Bosch proprietary.
