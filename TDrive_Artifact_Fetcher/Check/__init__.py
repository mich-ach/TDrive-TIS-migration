"""
Check module for mapping artifacts to PVER entries.

This module provides functionality to compare available artifacts (from Artifact extraction)
with missing PVER entries (from Excel export) and create migration files for TIS upload.

Classes:
    Check: Maps artifacts to PVER entries and generates migration JSON.

Functions:
    normalize_artifact_name: Extracts artifact name up to first semicolon.
    numeric_key_from_path: Extracts numeric key from file path for sorting.
    dedupe_by_artifact_and_pick_latest: Removes duplicate entries keeping the latest.
"""

import csv
import json
import logging
import os
import re

import openpyxl

# Load configuration
_config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
with open(_config_path, 'r') as f:
    CONFIG = json.load(f)

# Make paths absolute relative to the project root (where config.json is)
_project_root = os.path.dirname(os.path.abspath(_config_path))

_input_dir_from_config = CONFIG.get("input_dir", "input")
INPUT_DIR = os.path.join(_project_root, _input_dir_from_config) if not os.path.isabs(_input_dir_from_config) else _input_dir_from_config

_output_dir_from_config = CONFIG.get("output_dir", "output")
OUTPUT_DIR = os.path.join(_project_root, _output_dir_from_config) if not os.path.isabs(_output_dir_from_config) else _output_dir_from_config

LOG_LEVEL = CONFIG.get("log_level", "INFO")

# Setup logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Console handler with level from config
_console_handler = logging.StreamHandler()
_console_level = getattr(logging, LOG_LEVEL, logging.INFO)
_console_handler.setLevel(_console_level)
_console_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
))
logger.addHandler(_console_handler)


def normalize_artifact_name(name: str) -> str:
    """
    Return tis_artifact_name up to the first ';' (trimmed).
    If no ';' is present, return the whole trimmed string.
    """
    if not isinstance(name, str):
        return ""
    return name.split(';', 1)[0].strip()


def numeric_key_from_path(path: str) -> int:
    """
    Extract a numeric key from the last segment of `path`:
    - Take basename after the last '/'
    - Concatenate all digits in that basename
    - Interpret as integer (fallback 0 if none)
    Examples:
      '.../190627_132113_vme.zip' -> 190627132113
      '.../v7.zip' -> 7
    """
    base = os.path.basename(str(path))
    digits = re.findall(r"\d+", base)
    if not digits:
        return 0
    return int("".join(digits))


def dedupe_by_artifact_and_pick_latest(items: list) -> list:
    """
    Deduplicate entries where:
      - transfer.tis_artifact_path matches
      - transfer.tis_artifact_name (up to ';') matches
    For duplicates, keep the entry with the largest numeric key extracted
    from the last component of `path`.
    """
    best_per_key = {}
    best_score = {}

    for entry in items:
        transfer = entry.get("transfer", {}) or {}
        tis_path = transfer.get("tis_artifact_path", "") or ""
        tis_name_raw = transfer.get("tis_artifact_name", "") or ""
        tis_name = normalize_artifact_name(tis_name_raw)

        # Skip entries that don't have enough info to form the key
        if not tis_path or not tis_name:
            key = (tis_path, tis_name)
        else:
            key = (tis_path, tis_name)

        score = numeric_key_from_path(entry.get("path", ""))

        if key not in best_per_key or score > best_score[key]:
            best_per_key[key] = entry
            best_score[key] = score
        # Optional tie-breaker: if equal score, keep lexicographically larger path
        elif score == best_score[key]:
            existing_path = best_per_key[key].get("path", "")
            candidate_path = entry.get("path", "")
            if str(candidate_path) > str(existing_path):
                best_per_key[key] = entry
                best_score[key] = score

    return list(best_per_key.values())


class Check:
    """Maps available artifacts to missing PVER entries for TIS migration.

    This class loads artifact data from JSON files (created by Artifact classes)
    and missing PVER data from CSV (converted from Excel), then matches them
    based on PVER patterns found in A2L/HEX file paths.

    Attributes:
        __av (list): List of available artifacts with metadata.
        __miss (list): List of missing PVER entries from CSV.
    """

    def __init__(self, available: list[str] | str, missing: str):
        """Initialize Check with artifact and missing PVER data.

        Args:
            available (list[str] | str): Path(s) to JSON file(s) containing
                artifact data created by Artifact classes (e.g., '545list.json').
            missing (str): Path to CSV file containing missing PVER entries
                (converted from Excel using transform_excel()).
        """
        self.__av = []
        self.__miss = []

        logger.info("[Step: Load Artifacts] Loading artifact data...")
        if type(available) is list:
            for e in available:
                logger.debug(f"[Step: Load Artifacts] Loading from: {e}")
                with open(e, 'r') as f:
                    data = json.load(f)
                    self.__av.extend(data)
                    logger.debug(f"[Step: Load Artifacts] Loaded {len(data)} artifacts")
        else:
            logger.debug(f"[Step: Load Artifacts] Loading from: {available}")
            with open(available, 'r') as f:
                self.__av.extend(json.load(f))

        logger.info(f"[Step: Load Artifacts] Total artifacts loaded: {len(self.__av)}")

        logger.info(f"[Step: Load Missing] Loading missing PVER entries from: {missing}")
        with open(missing, 'r') as f:
            reader = csv.reader(f, delimiter=';')
            self.__miss = [{"PVER": row[0], "ECU": row[1], "Project": row[2]} for row in reader if row[4] == "No"]
        logger.info(f"[Step: Load Missing] Loaded {len(self.__miss)} missing PVER entries")

    @staticmethod
    def __cut_string(input_string: str) -> str:
        """cuts string by the first char which is not [A-Z0-9]

        Args:
            input_string (str): string to cut

        Returns:
            str: cut string
        """
        for i, char in enumerate(input_string):
            if not ('a' <= char <= 'z' or 'A' <= char <= 'Z' or '0' <= char <= '9'):
                return input_string[:i]
        return input_string

    def compare(self) -> None:
        """compares available data with missing data

        it checks if the PVER is in the paths of the A2L or HEXFile -> connects them and creates transfer entry for upload
        """
        logger.info("[Step: Compare] Matching artifacts to missing PVER entries...")
        logger.info(f"[Step: Compare] Artifacts to check: {len(self.__av)}, Missing PVER entries: {len(self.__miss)}")

        matched_count = 0
        debug_examples_logged = 0
        max_debug_examples = 2

        for e in self.__av:
            e["PVER"] = []
            is_debug_example = debug_examples_logged < max_debug_examples

            if is_debug_example:
                debug_examples_logged += 1
                logger.debug(f"[Step: Compare] === Example {debug_examples_logged} ===")
                logger.debug(f"[Step: Compare]   Artifact path: {e.get('path', 'N/A')}")
                logger.debug(f"[Step: Compare]   Model name: {e.get('Model_Overview_data', {}).get('name', 'N/A')}")
                a2l = e.get("Model_Overview_data", {}).get("A2LFile", None)
                hex_f = e.get("Model_Overview_data", {}).get("HEXFile", None)
                logger.debug(f"[Step: Compare]   A2LFile: {a2l}")
                logger.debug(f"[Step: Compare]   HEXFile: {hex_f}")

            if "A2LFile" in e["Model_Overview_data"]:
                a2l_value = e["Model_Overview_data"]["A2LFile"]
                if is_debug_example:
                    logger.debug(f"[Step: Compare]   Checking against A2LFile: '{a2l_value}'")
                for m in self.__miss:
                    cut_pver = Check.__cut_string(m["PVER"])
                    match = cut_pver in a2l_value
                    if is_debug_example:
                        logger.debug(
                            f"[Step: Compare]     '{cut_pver}' (from '{m['PVER']}') "
                            f"in '{a2l_value}' -> {'MATCH' if match else 'no match'}"
                        )
                    if match:
                        e["PVER"].append(m)

            if "HEXFile" in e["Model_Overview_data"]:
                hex_value = e["Model_Overview_data"]["HEXFile"]
                if is_debug_example:
                    logger.debug(f"[Step: Compare]   Checking against HEXFile: '{hex_value}'")
                for m in self.__miss:
                    cut_pver = Check.__cut_string(m["PVER"])
                    match = cut_pver in hex_value
                    if is_debug_example:
                        logger.debug(
                            f"[Step: Compare]     '{cut_pver}' (from '{m['PVER']}') "
                            f"in '{hex_value}' -> {'MATCH' if match else 'no match'}"
                        )
                    if match:
                        e["PVER"].append(m)

            if e["PVER"]:
                matched_count += 1
                if is_debug_example:
                    logger.debug(f"[Step: Compare]   Result: MATCHED with {len(e['PVER'])} PVER entries")
                    for pver in e["PVER"]:
                        logger.debug(f"[Step: Compare]     -> PVER={pver['PVER']}, ECU={pver['ECU']}, Project={pver['Project']}")
            elif is_debug_example:
                logger.debug(f"[Step: Compare]   Result: NO MATCH")

        data = [e for e in self.__av if len(e["PVER"]) != 0]
        self.__av = data
        logger.info(f"[Step: Compare] Found {matched_count} artifacts with PVER matches")

        transfer_count = 0
        for e in self.__av:
            path_tail = e["path"][e["path"].rfind("/"):]
            LC_Type = ""
            if "pcie" in path_tail:
                LC_Type = "PCIE"
            elif "vme" in path_tail:
                LC_Type = "VME"
            else:
                logger.debug(f"[Step: Transfer] Skipped (no pcie/vme in tail '{path_tail}'): {e['path']}")
                continue

            ecu = e["PVER"][0]["ECU"]
            i = ecu.find("-")
            if i != -1:
                ecu = ecu[:i]

            name = e["Model_Overview_data"]["name"].strip()
            if name.find("VW MDL :") == -1:
                name = "VW MDL : " + name

            e["transfer"] = {}
            e["transfer"]["model_input_filepath"] = e["path"]
            e["transfer"]["customer_group"] = "VW"
            e["transfer"]["tis_artifact_name"] = e["Model_Overview_data"]["name"].strip()
            e["transfer"]["tis_artifact_path"] = f"xCU Projects/{ecu.replace('.', '')}/{e['PVER'][0]['PVER']}/Model/HiL/{e['swb']}/{LC_Type}"
            e["transfer"]["tis_migration"] = True
            e["transfer"]["lco_migration"] = False
            transfer_count += 1

            if transfer_count <= max_debug_examples:
                logger.debug(f"[Step: Transfer] === Transfer Example {transfer_count} ===")
                logger.debug(f"[Step: Transfer]   ECU raw='{e['PVER'][0]['ECU']}' -> cleaned='{ecu}'")
                logger.debug(f"[Step: Transfer]   LC_Type='{LC_Type}' (from path tail: '{path_tail}')")
                logger.debug(f"[Step: Transfer]   tis_artifact_name='{e['transfer']['tis_artifact_name']}'")
                logger.debug(f"[Step: Transfer]   tis_artifact_path='{e['transfer']['tis_artifact_path']}'")

        logger.info(f"[Step: Compare] Created {transfer_count} transfer entries")

        before_dedupe = len(self.__av)
        self.__av = dedupe_by_artifact_and_pick_latest(self.__av)
        logger.info(f"[Step: Compare] Deduplicated: {before_dedupe} -> {len(self.__av)} entries")

    def dump(self, output_dir: str = None) -> None:
        """dumps compare json to output directory

        Args:
            output_dir (str): Directory to write check.json to (default: from config.json)
        """
        if output_dir is None:
            output_dir = OUTPUT_DIR

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, "check.json")
        logger.info(f"[Step: Save] Saving comparison results to: {output_path}")
        with open(output_path, 'w') as f:
            f.write(json.dumps(self.__av, indent=4))
        logger.debug(f"[Step: Save] Saved {len(self.__av)} entries to check.json")

    @staticmethod
    def create_mig(file: str, output_dir: str = None) -> None:
        """creates migration file

        Args:
            file (str): file to create migration from
            output_dir (str): Directory to write mig.json to (default: from config.json)
        """
        if output_dir is None:
            output_dir = OUTPUT_DIR

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        logger.info(f"[Step: Migration] Loading check data from: {file}")
        data_src = []
        with open(file, 'r') as f:
            data_src = json.load(f)

        data = {"models": []}
        data["models"] = [e["transfer"] for e in data_src]

        output_path = os.path.join(output_dir, "mig.json")
        logger.info(f"[Step: Migration] Saving migration file ({len(data['models'])} models) to: {output_path}")
        with open(output_path, 'w') as f:
            f.write(json.dumps(data, indent=4))

    def create_csv(self, output_dir: str = None) -> str:
        """Generate a CSV listing all unique PVER and Project pairs found on TDrive.

        Extracts PVER/ECU/Project information from successfully matched artifacts
        and writes a semicolon-delimited CSV with unique entries.

        Args:
            output_dir: Directory to write the CSV (default: from config.json)

        Returns:
            Path to the generated CSV file
        """
        if output_dir is None:
            output_dir = OUTPUT_DIR

        os.makedirs(output_dir, exist_ok=True)

        # Collect unique PVER/Project pairs from matched artifacts
        seen = set()
        entries = []

        for artifact in self.__av:
            for pver_entry in artifact.get("PVER", []):
                pver = pver_entry.get("PVER", "")
                project = pver_entry.get("Project", "")
                key = (pver, project)
                if key not in seen and pver:
                    seen.add(key)
                    entries.append({"PVER": pver, "Project": project})

        # Sort by project then PVER
        entries.sort(key=lambda e: (e["Project"], e["PVER"]))

        output_path = os.path.join(output_dir, "tdrive_pver_projects.csv")
        headers = ["PVER", "Project"]

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(';'.join(headers) + '\n')
            for entry in entries:
                f.write(f"{entry['PVER']};{entry['Project']}\n")

        logger.info(f"[Step: CSV] Saved {len(entries)} unique PVER/Project pairs to: {output_path}")
        return output_path

    @staticmethod
    def transform_excel(file_in: str, file_out: str) -> None:
        """transform missing.xlsx to csv which Check() can work with

        Args:
            file_in (str): xlsx file
            file_out (str): target csv file
        """
        logger.info(f"[Step: Transform] Converting Excel to CSV: {file_in}")

        # Create directory for output file if it doesn't exist
        output_dir = os.path.dirname(file_out)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        wb = openpyxl.load_workbook(file_in)
        sh = wb.active
        row_count = 0
        with open(file_out, 'w', newline="", encoding='utf-8') as f:
            c = csv.writer(f, delimiter=";")
            for i, r in enumerate(sh.iter_rows(), start=1):
                if i < 25:  # skip until row 25
                    continue
                cleaned_row = []
                for cell in r:
                    val = cell.value
                    if isinstance(val, str):
                        val = val.replace('"', '')  # remove all double quotes
                    if val is None:
                        val = ""  # write empty instead of None
                    cleaned_row.append(val)
                c.writerow(cleaned_row)
                row_count += 1

        logger.info(f"[Step: Transform] Wrote {row_count} rows to: {file_out}")


if __name__ == '__main__':
    # Check.transform_excel("missing.xlsx", "missing.csv")
    check = Check(["545list.json", "5411list.json"], "missing.csv")
    check.compare()
    check.dump()
    Check.create_mig("output/check.json")
