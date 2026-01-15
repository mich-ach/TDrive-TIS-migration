# T-Drive artifact parser

Extracts artifact metadata from LCO project zip files on the network drive to check available backups for TIS reupload.

## Requirements

- **Network Drive Access**: Read access to `//bosch.com/dfsrb/DfsDE/DIV/DGS/08/EC/20_CE/PJ/60_SRL_LCT/LC_TESTS/Projects/003/LCO_Projects/`
- **Python 3.8+**
- **Dependencies**: `charset_normalizer`

## Output

All exports are saved to the `output/` directory:
- `{prefix}dir.json` - Directory structure cache
- `{prefix}list.json` - Artifact metadata list
- `{prefix}_{timestamp}.log` - Processing log (DEBUG level)

## Classes

### Artifact

Extracts artifact metadata from LCO project zip files. Subclasses exist for LCO versions (`Artifact545`, `Artifact5411`).

**Workflow:**

```python
from Artifacts import Artifact545

art545 = Artifact545()
art545.start_logging()   # Enable file logging to output/
art545.create_dir()      # Scan network drive for artifacts
art545.cleanup_dir()     # Remove invalid entries (Failed, Dev, Archive, etc.)
art545.dump_dir()        # Save to output/545dir.json
art545.create_list()     # Extract metadata from zip files (parallel processing)
art545.cleanup_list()    # Keep only artifacts with HEXFile or A2LFile
art545.dump_list()       # Save to output/545list.json
art545.stop_logging()    # Close log file
```

**Extracted metadata:**
- Path to artifact zip
- Model name, HEXFile, A2LFile from `Docs/Model_Overview.html`

**Performance:** Uses parallel processing (8 threads) for zip file extraction.

### Check

Maps artifacts to PVER entries from an Excel export.

```python
from Check import Check

Check.transform_excel("missing.xlsx", "missing.csv")
check = Check(["output/545list.json"], "missing.csv")
check.compare()
check.dump()
# Manual review required for ambiguous mappings
Check.create_mig("check.json")  # Generate upload-ready JSON
```