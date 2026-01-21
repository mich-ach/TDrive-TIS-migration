"""
Artifact extraction module for TDrive LCO Projects.

This module provides classes to scan the network drive for LCO artifact zip files,
extract metadata from Model_Overview.html inside each zip, and export the results
to JSON files for further processing.

Classes:
    Artifact: Base class for artifact extraction with common functionality.
    Artifact545: Extracts artifacts from LCO version 5.4.5.
    Artifact5411: Extracts artifacts from LCO version 5.4.11.

Configuration is loaded from config.json in the parent directory.
"""

import json
import logging
import os
import copy
import zipfile
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from charset_normalizer import from_bytes

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

MAX_WORKERS = CONFIG.get("max_workers", 8)
LOG_LEVEL = CONFIG.get("log_level", "INFO")
BASE_PATH = CONFIG.get("base_path", "")
LCO_VERSIONS = CONFIG.get("lco_versions", {})

# Create logger for this module
logger = logging.getLogger(__name__)
_console_level = getattr(logging, LOG_LEVEL, logging.INFO)

# Set logger to DEBUG to allow all messages through to handlers
# Each handler will filter based on its own level
logger.setLevel(logging.DEBUG)

# Configure console handler with level from config
_console_handler = logging.StreamHandler()
_console_handler.setLevel(_console_level)
_console_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
))
logger.addHandler(_console_handler)


def _setup_file_logging(prefix: str) -> logging.FileHandler:
    """Setup file logging to output directory.

    Args:
        prefix: Prefix for the log file name

    Returns:
        The file handler that was added
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(OUTPUT_DIR, f"{prefix}_{timestamp}.log")

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(file_handler)
    logger.info(f"Log file: {log_file}")
    return file_handler


class Artifact:
    """Base class for extracting artifact metadata from LCO project zip files.

    This class provides common functionality for scanning network directories,
    extracting metadata from zip files, and caching results to JSON.

    Attributes:
        _dir (dict): Directory structure of artifacts on the network drive.
        _list (list): List of artifact metadata dictionaries.
    """

    def __init__(self, path: str, prefix: str):
        """Initialize an Artifact extractor.

        Args:
            path (str): Network path to the LCO project directory to scan.
            prefix (str): LCO version identifier used for output file naming (e.g., '545', '5411').
        """
        self.__path = path
        self.__prefix = prefix
        self._dir = {}
        self._list = []
        self._file_handler = None

    def start_logging(self) -> None:
        """Start file logging to output directory."""
        if self._file_handler is None:
            self._file_handler = _setup_file_logging(self.__prefix)
            logger.info(f"[Step: Initialize] Started artifact extraction session for LCO version: {self.__prefix}")
            logger.info(f"[Step: Initialize] Network path: {self._Artifact__path}")

    def stop_logging(self) -> None:
        """Stop file logging and close the file handler."""
        if self._file_handler is not None:
            logger.info(f"[Step: Finalize] Completed artifact extraction session for LCO version: {self.__prefix}")
            logger.removeHandler(self._file_handler)
            self._file_handler.close()
            self._file_handler = None

    def load_dir(self) -> None:
        """loads json into self._dir from output directory
        """
        filepath = os.path.join(OUTPUT_DIR, f"{self.__prefix}dir.json")
        logger.info(f"[Step: Load Cache] Loading cached directory structure from: {filepath}")
        with open(filepath, 'r') as f:
            self._dir = json.load(f)
        logger.debug(f"[Step: Load Cache] Loaded directory structure with {len(self._dir)} top-level entries")

    def load_list(self) -> None:
        """loads json into self._list from output directory
        """
        filepath = os.path.join(OUTPUT_DIR, f"{self.__prefix}list.json")
        logger.info(f"[Step: Load Cache] Loading cached artifact list from: {filepath}")
        with open(filepath, 'r') as f:
            self._list = json.load(f)
        logger.info(f"[Step: Load Cache] Loaded {len(self._list)} artifacts from cache")

    def dump_dir(self) -> None:
        """dumps self._dir into json in output directory
        """
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        filepath = os.path.join(OUTPUT_DIR, f"{self.__prefix}dir.json")
        logger.info(f"[Step: Save Cache] Saving directory structure to: {filepath}")
        with open(filepath, 'w') as f:
            f.write(json.dumps(self._dir, indent=4))
        logger.debug(f"[Step: Save Cache] Directory structure saved successfully")

    def dump_list(self) -> None:
        """dumps self._list into json in output directory
        """
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        filepath = os.path.join(OUTPUT_DIR, f"{self.__prefix}list.json")
        logger.info(f"[Step: Save Cache] Saving artifact list ({len(self._list)} artifacts) to: {filepath}")
        with open(filepath, 'w') as f:
            f.write(json.dumps(self._list, indent=4))
        logger.info(f"[Step: Save Cache] Artifact list saved successfully")

    def create_dir(self) -> None:
        """create the self._dir dictionary by creating a copy of the directory structure of the given directory
        """
        logger.info(f"[Step: Scan Network] Scanning network drive for artifact directories (max depth: 6)...")
        logger.debug(f"[Step: Scan Network] Base path: {self._Artifact__path}")
        Artifact.__list_dir(self._Artifact__path, self._dir, 6)
        logger.info(f"[Step: Scan Network] Network scan complete, found {len(self._dir)} top-level directories")

    @staticmethod
    def _rmv_non_zip(data: dict) -> None:
        """removes non zip files in dict

        Args:
            data (dict): dict to remove from
        """
        keys_to_del = []
        for key, value in data.items():
            if isinstance(value, dict):
                Artifact._rmv_non_zip(value)
            elif key.find(".zip") == -1:
                keys_to_del.append(key)
        for key in keys_to_del:
            del data[key]

    @staticmethod
    def _rmv_file(data: dict, name: str) -> None:
        """remove all files with name <name> from dict

        Args:
            data (dict): dict to remove from
            name (str): file to remove
        """
        keys_to_del = []
        for key, value in data.items():
            if isinstance(value, dict):
                Artifact._rmv_file(value, name)
            elif key == name:
                keys_to_del.append(key)
        for key in keys_to_del:
            del data[key]

    @staticmethod
    def _rmv_dir(data: dict, name: str, find: bool = False) -> None:
        """removes dir specified by name

        Args:
            data (dict): dict to remove from
            name (str): dir to remove
            find (bool): if true it removes all dirs which have *name* in there name
        """
        keys_to_del = []
        for key, value in data.items():
            if isinstance(value, dict):
                Artifact._rmv_dir(value, name, find)
                if find == False:
                    if key == name:
                        keys_to_del.append(key)
                else:
                    if key.find(name) != -1:
                        keys_to_del.append(key)
        for key in keys_to_del:
            del data[key]

    @staticmethod
    def _rmv_everything_except_dir(data: dict, name: str) -> None:
        """if directory with name <name> is found everything else expect the directory is removed from this level

        Args:
            data (dict): dict to remove from
            name (str): dir to keep
        """
        keys_to_del = []
        for key, value in data.items():
            if isinstance(value, dict):
                Artifact._rmv_everything_except_dir(value, name)
                if name in data.keys() and key != name:
                    keys_to_del.append(key)
        for key in keys_to_del:
            del data[key]

    @staticmethod
    def _rmv_unzip(data: dict) -> None:
        """checks if a dir with the same name as a zip exists on a lvl -> removes it

        Args:
            data (dict): dict to search in
        """
        for key, value in data.items():
            if isinstance(value, dict):
                Artifact._rmv_unzip(value)
        keys_to_del = []
        for key, value in data.items():
            if key+".zip" in data.keys():
                keys_to_del.append(key)
        for key in keys_to_del:
            del data[key]

    @staticmethod
    def _rmv_empty(data: dict) -> None:
        """remove empty dir

        Args:
            data (dict): dict to remove from
        """
        keys_to_del = []
        for key, value in data.items():
            if isinstance(value, dict):
                Artifact._rmv_empty(value)
                if not value:
                    keys_to_del.append(key)
        for key in keys_to_del:
            del data[key]

    @staticmethod
    def _rename_released(data: dict) -> None:
        """rename dir Released to LatestArtifact

        Args:
            data (dict): working dict
        """
        for key, value in list(data.items()):
            if isinstance(value, dict):
                Artifact._rename_released(value)
        if "Released" in data:
            data["LatestArtifact"] = data.pop("Released")

    @staticmethod
    def _sub_invalid(data: dict, invalid: dict) -> None:
        """creates the delta a two dicts

        Args:
            data (dict): minuend
            invalid (dict): subtrahend
        """
        for key in list(data.keys()):
            if key not in invalid:
                continue
            if isinstance(data[key], dict) and isinstance(invalid[key], dict):
                Artifact._sub_invalid(data[key], invalid[key])
            elif data[key] == invalid[key]:
                del data[key]

    @staticmethod
    def _make_valid(data: dict) -> None:
        """remove all invalid from dict

        Args:
            data (dict): working dict
        """
        # create invalid
        invalid = copy.deepcopy(data)
        Artifact._rmv_dir(invalid, "LatestArtifact")
        Artifact._rmv_empty(invalid)
        Artifact._sub_invalid(data, invalid)
        Artifact._rmv_empty(data)

    @staticmethod
    def _rename_latestArtifact(data: dict) -> None:
        """Drop name latestArtifact and drop all elements in it one lvl down

        Args:
            data (dict): working dict
        """
        for key, value in list(data.items()):
            if isinstance(value, dict):
                Artifact._rename_latestArtifact(value)
        if "LatestArtifact" in data:
            latest = data.pop("LatestArtifact")
            if isinstance(latest, dict):
                for k, v in latest.items():
                    data[k] = v

    @staticmethod
    def _create_list_of_dicts(data: dict, target: list, swb: str) -> None:
        """Retructures the directory structure into an list with only artifacts

        Args:
            data (dict): source directory structure
            target (list): target list structure
            swb (str): SWB
        """
        for key, value in list(data.items()):
            if isinstance(value, dict):
                Artifact._create_list_of_dicts(value, target, swb)
            else:
                target.append({"path": value, "swb": swb})

    @staticmethod
    def __list_dir(path: str, data: dict, max_lvl: int) -> None:
        """Recursive function which creates dictionary of LCO_Projects directory structure layout.

        Args:
            path (str): 1st level to search in
            data (dict): Dictionary to create.
            max_lvl (int): Maximum steps to make into the directory structure
        """
        try:
            for e in os.listdir(path):
                logger.debug(f"[Step: Scan Network] Found: {e}")
                if os.path.isdir(os.path.join(path, e)):
                    data[e] = {}
                    if max_lvl != 0:
                        Artifact.__list_dir(os.path.join(path, e), data[e], max_lvl-1)
                else:
                    data[e] = os.path.join(path, e).replace("\\", "/")
        except FileNotFoundError:
            pass

    def _LCO_list(self, max_workers=None):
        """Extract data from Model_Overview.html in Artifact using parallel processing

        Args:
            max_workers: Number of parallel threads (default: from config.json)
        """
        if max_workers is None:
            max_workers = MAX_WORKERS
        total_artifacts = len(self._list)
        logger.info(f"[Step: Extract Metadata] Starting extraction of Model_Overview.html from {total_artifacts} artifact zip files using {max_workers} parallel workers")

        def process_artifact(args):
            cnt, key = args
            artifact_path = key.get('path', 'unknown')
            artifact_name = os.path.basename(artifact_path)
            logger.debug(f"[Step: Open Zip] ({cnt + 1}/{total_artifacts}) Opening artifact zip: {artifact_name}")
            try:
                with zipfile.ZipFile(key["path"], 'r') as zipf:
                    try:
                        with zipf.open("Docs/Model_Overview.html") as file:
                            key["Model_Overview"] = True
                            key["Model_Overview_data"] = {}
                            logger.debug(f"[Step: Parse HTML] ({cnt + 1}/{total_artifacts}) Found Model_Overview.html, parsing metadata...")
                            content = str(from_bytes(file.read()).best())
                            start = content.find("id=\"releaseVersion\">")
                            start = content.find(">", start) + 1
                            end = content.find("<", start)
                            key["Model_Overview_data"]["name"] = content[start:end].replace("\\", "/")
                            start = content.find("HEXFile</td><td>") + 16
                            if start != 15:
                                end = content.find("<", start)
                                if start != end:
                                    key["Model_Overview_data"]["HEXFile"] = content[start:end].replace("\\", "/")
                            start = content.find("A2LFile</td><td>") + 16
                            if start != 15:
                                end = content.find("<", start)
                                if start != end:
                                    key["Model_Overview_data"]["A2LFile"] = content[start:end].replace("\\", "/")
                            logger.debug(f"[Step: Extract Complete] ({cnt + 1}/{total_artifacts}) Extracted - Name: {key['Model_Overview_data'].get('name')}, HEX: {key['Model_Overview_data'].get('HEXFile', 'N/A')}, A2L: {key['Model_Overview_data'].get('A2LFile', 'N/A')}")
                    except KeyError:
                        logger.debug(f"[Step: Skip] ({cnt + 1}/{total_artifacts}) No Model_Overview.html in zip: {artifact_name}")
                        key["Model_Overview"] = False
                        key["Model_Overview_data"] = {}
            except Exception as e:
                logger.error(f"[Step: Error] ({cnt + 1}/{total_artifacts}) Failed to process {artifact_name}: {e}")
                key["Model_Overview"] = False
                key["Model_Overview_data"] = {}
            return key

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            list(executor.map(process_artifact, enumerate(self._list)))

        successful = sum(1 for k in self._list if k.get("Model_Overview"))
        failed = total_artifacts - successful
        logger.info(f"[Step: Extract Metadata Complete] Processed {total_artifacts} artifacts: {successful} with valid Model_Overview, {failed} skipped/failed")

    def cleanup_list(self):
        """Removes Artifacts where not enough data is found
        """
        before_count = len(self._list)
        logger.info(f"[Step: Filter Artifacts] Filtering artifacts - keeping only those with HEXFile or A2LFile...")
        data = [e for e in self._list if e.get("Model_Overview") is True and (
            "HEXFile" in e.get("Model_Overview_data") or "A2LFile" in e.get("Model_Overview_data"))]
        self._list = data
        removed_count = before_count - len(self._list)
        logger.info(f"[Step: Filter Artifacts] Kept {len(self._list)} valid artifacts, removed {removed_count} without HEXFile/A2LFile")


def _get_lco_path(version: str) -> str:
    """Get full path for LCO version from config."""
    lco_config = LCO_VERSIONS.get(version, {})
    return os.path.join(BASE_PATH, lco_config.get("path", "")).replace("\\", "/")


def _get_sw_line(version: str) -> str:
    """Get SW line for LCO version from config."""
    lco_config = LCO_VERSIONS.get(version, {})
    return lco_config.get("sw_line", "")


class Artifact545(Artifact):
    """Artifact extractor for LCO version 5.4.5.

    Scans the LCOV5.4.5 directory on the network drive and extracts
    artifact metadata using SW line SWB26.1.
    """

    def __init__(self):
        """Initialize Artifact545 with paths from config.json."""
        super().__init__(_get_lco_path("545"), "545")
        self._sw_line = _get_sw_line("545")

    def cleanup_dir(self):
        """cleanup the dir structure so that only valid entries are in it
        """
        Artifact._rmv_non_zip(self._dir)
        Artifact._rmv_file(self._dir, "runtime.zip")
        Artifact._rmv_file(self._dir, "sources.zip")
        Artifact._rmv_dir(self._dir, "Failed")
        Artifact._rmv_dir(self._dir, "Dev")
        Artifact._rmv_dir(self._dir, "LCOV5.4.4")
        Artifact._rmv_dir(self._dir, "_old_models")
        Artifact._rmv_dir(self._dir, "Development", True)
        Artifact._rmv_dir(self._dir, "Archive", True)
        Artifact._rmv_dir(self._dir, "Depreciated", True)
        Artifact._rmv_everything_except_dir(self._dir, "Released")
        Artifact._rmv_unzip(self._dir)
        Artifact._rmv_empty(self._dir)
        Artifact._rename_released(self._dir)
        Artifact._make_valid(self._dir)
        Artifact._rename_latestArtifact(self._dir)

    def create_list(self):
        """transform the dir structure to an list with only artifacts also extracts info from inside Artifacts
        """
        Artifact._create_list_of_dicts(self._dir, self._list, self._sw_line)
        self._LCO_list()


class Artifact5411(Artifact):
    """Artifact extractor for LCO version 5.4.11.

    Scans the LCOV5.4.11 directory on the network drive and extracts
    artifact metadata using SW line SWB26.2.
    """

    def __init__(self):
        """Initialize Artifact5411 with paths from config.json."""
        super().__init__(_get_lco_path("5411"), "5411")
        self._sw_line = _get_sw_line("5411")

    def cleanup_dir(self):
        """cleanup the dir structure so that only valid entries are in it
        """
        Artifact._rmv_non_zip(self._dir)
        Artifact._rmv_file(self._dir, "runtime.zip")
        Artifact._rmv_file(self._dir, "sources.zip")
        Artifact._rmv_dir(self._dir, "Failed")
        Artifact._rmv_dir(self._dir, "Dev")
        Artifact._rmv_dir(self._dir, "LCOV5.4.4")
        Artifact._rmv_dir(self._dir, "_old_models")
        Artifact._rmv_dir(self._dir, "Development", True)
        Artifact._rmv_dir(self._dir, "Archive", True)
        Artifact._rmv_dir(self._dir, "Depreciated", True)
        Artifact._rmv_everything_except_dir(self._dir, "Released")
        Artifact._rmv_unzip(self._dir)
        Artifact._rmv_empty(self._dir)
        Artifact._rename_released(self._dir)
        Artifact._make_valid(self._dir)
        Artifact._rename_latestArtifact(self._dir)

    def create_list(self):
        """transform the dir structure to an list with only artifacts also extracts info from inside Artifacts
        """
        Artifact._create_list_of_dicts(self._dir, self._list, self._sw_line)
        self._LCO_list()


if __name__ == '__main__':
    art = Artifact5411()
    art.create_dir()
    art.cleanup_dir()
    art.dump_dir()
    art.create_list()
    art.cleanup_list()
    art.dump_list()