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

import json
import csv
import openpyxl
import os
import re

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
            # treat as its own unique group using empty components to avoid accidental collisions
            # you can also choose to always keep such entries
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
        if type(available) is list:
            for e in available:
                with open(e, 'r') as f:
                    self.__av.extend(json.load(f))
        else:
            with open(available, 'r') as f:
                self.__av.extend(json.load(f))
        with open(missing, 'r') as f:
            reader = csv.reader(f, delimiter=';')
            self.__miss = [{"PVER": row[0], "ECU": row[1], "Project": row[2]} for row in reader if row[4] == "No"]

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
        for e in self.__av:
            e["PVER"] = []
            if "A2LFile" in e["Model_Overview_data"]:
                for m in self.__miss:
                    if Check.__cut_string(m["PVER"]) in e["Model_Overview_data"]["A2LFile"]:
                        e["PVER"].append(m)
            if "HEXFile" in e["Model_Overview_data"]:
                for m in self.__miss:
                    if Check.__cut_string(m["PVER"]) in e["Model_Overview_data"]["HEXFile"]:
                        e["PVER"].append(m)

        data = [e for e in self.__av if len(e["PVER"]) != 0]
        self.__av = data

        for e in self.__av:
            LC_Type = ""
            if "pcie" in e["path"][e["path"].rfind("/"):]:
                LC_Type = "PCIE"
            elif "vme" in e["path"][e["path"].rfind("/"):]:
                LC_Type = "VME"
            else:
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

        self.__av = dedupe_by_artifact_and_pick_latest(self.__av)


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
        with open(output_path, 'w') as f:
            f.write(json.dumps(self.__av, indent=4))

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
        
        data_src = []
        with open(file, 'r') as f:
            data_src = json.load(f)
        data = {"models":[]}
        data["models"] = [e["transfer"] for e in data_src]
        
        output_path = os.path.join(output_dir, "mig.json")
        with open(output_path, 'w') as f:
            f.write(json.dumps(data, indent=4))

    @staticmethod
    def transform_excel(file_in: str, file_out: str) -> None:
        """transform missing.xlsx to csv which Check() can work with

        Args:
            file_in (str): xlsx file
            file_out (str): target csv file
        """
        # Create directory for output file if it doesn't exist
        output_dir = os.path.dirname(file_out)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        wb = openpyxl.load_workbook(file_in)
        sh = wb.active
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

if __name__ == '__main__':
    # Check.transform_excel("missing.xlsx", "missing.csv")
    check = Check(["545list.json", "5411list.json"], "missing.csv")
    check.compare()
    check.dump()
    Check.create_mig("output/check.json")