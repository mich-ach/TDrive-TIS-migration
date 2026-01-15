import json
import os
import copy
import zipfile
from charset_normalizer import from_bytes


class Artifact:
    """
    Manages artifacts by creating, cleaning, and processing directory structures and lists of files.
    """

    def __init__(self, path: str, prefix: str):
        """
        Initializes the Artifact object.

        Args:
            path (str): The base path to search for artifacts.
            prefix (str): A prefix used for naming JSON files (e.g., LCO version).
        """
        self.__path = path
        self.__prefix = prefix
        self._dir = {}
        self._list = []

    def load_dir(self) -> None:
        """
        Loads the directory structure from a JSON file into `self._dir`.
        """
        with open(f"{self.__prefix}dir.json", 'r') as f:
            self._dir = json.load(f)

    def load_list(self) -> None:
        """
        Loads the list of artifacts from a JSON file into `self._list`.
        """
        with open(f"{self.__prefix}list.json", 'r') as f:
            self._list = json.load(f)

    def dump_dir(self) -> None:
        """
        Dumps the current `self._dir` dictionary into a JSON file.
        """
        with open(f"{self.__prefix}dir.json", 'w') as f:
            f.write(json.dumps(self._dir, indent=4))

    def dump_list(self) -> None:
        """
        Dumps the current `self._list` into a JSON file.
        """
        with open(f"{self.__prefix}list.json", 'w') as f:
            f.write(json.dumps(self._list, indent=4))

    def create_dir(self) -> None:
        """
        Creates the `self._dir` dictionary by recursively copying the directory structure
        of the specified `self.__path` up to a certain depth.
        """
        Artifact.__list_dir(self.__path, self._dir, 6)

    @staticmethod
    def _rmv_non_zip(data: dict) -> None:
        """
        Recursively removes all non-zip files from the given dictionary representing a directory structure.

        Args:
            data (dict): The dictionary to modify.
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
        """
        Recursively removes all files with the specified `name` from the dictionary.

        Args:
            data (dict): The dictionary to modify.
            name (str): The name of the file to remove.
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
        """
        Recursively removes directories from the dictionary.

        Args:
            data (dict): The dictionary to modify.
            name (str): The name of the directory to remove.
            find (bool): If True, removes all directories whose names contain `name`.
                         If False, removes only directories whose names exactly match `name`.
        """
        keys_to_del = []
        for key, value in data.items():
            if isinstance(value, dict):
                Artifact._rmv_dir(value, name, find)
                if not find:
                    if key == name:
                        keys_to_del.append(key)
                else:
                    if name in key:  # Using 'in' for partial match
                        keys_to_del.append(key)
        for key in keys_to_del:
            del data[key]

    @staticmethod
    def _rmv_everything_except_dir(data: dict, name: str) -> None:
        """
        Recursively traverses the dictionary. If a directory with the specified `name` is found
        at a given level, all other sibling entries (files or directories) at that same level
        are removed, effectively keeping only the specified directory.

        Args:
            data (dict): The dictionary to modify.
            name (str): The name of the directory to keep.
        """
        keys_to_del = []
        for key, value in data.items():
            if isinstance(value, dict):
                Artifact._rmv_everything_except_dir(value, name)
        
        # After recursive calls, check the current level for the 'name' directory
        if name in data:
            for key in list(data.keys()): # Iterate over a copy of keys to allow deletion
                if key != name:
                    keys_to_del.append(key)
        
        for key in keys_to_del:
            del data[key]


    @staticmethod
    def _rmv_unzip(data: dict) -> None:
        """
        Recursively removes directory entries that have a corresponding zip file
        (e.g., if 'folder' and 'folder.zip' exist at the same level, 'folder' is removed).

        Args:
            data (dict): The dictionary to search and modify.
        """
        for key, value in data.items():
            if isinstance(value, dict):
                Artifact._rmv_unzip(value)
        
        keys_to_del = []
        # After recursive calls, check the current level
        for key in list(data.keys()):
            if isinstance(data[key], dict) and (key + ".zip" in data):
                keys_to_del.append(key)
        for key in keys_to_del:
            del data[key]

    @staticmethod
    def _rmv_empty(data: dict) -> None:
        """
        Recursively removes empty directories (dictionaries) from the given data structure.

        Args:
            data (dict): The dictionary to modify.
        """
        keys_to_del = []
        for key, value in data.items():
            if isinstance(value, dict):
                Artifact._rmv_empty(value)
                if not value:  # If the dictionary is now empty after recursive calls
                    keys_to_del.append(key)
        for key in keys_to_del:
            del data[key]

    @staticmethod
    def _rename_released(data: dict) -> None:
        """
        Recursively renames the directory "Released" to "LatestArtifact" within the dictionary.

        Args:
            data (dict): The dictionary to modify.
        """
        for key, value in list(data.items()):  # Iterate over a copy of keys if modifying during iteration
            if isinstance(value, dict):
                Artifact._rename_released(value)
        if "Released" in data:
            data["LatestArtifact"] = data.pop("Released")

    @staticmethod
    def _sub_invalid(data: dict, invalid: dict) -> None:
        """
        Calculates the set difference between two dictionary structures.
        Removes entries from `data` that are also present in `invalid` (matching key and value).
        This is used to filter out "invalid" entries from the main data.

        Args:
            data (dict): The minuend dictionary (the one to be modified).
            invalid (dict): The subtrahend dictionary (contains entries to be removed from `data`).
        """
        for key in list(data.keys()):  # Iterate over a copy of keys to allow deletion
            if key not in invalid:
                continue
            if isinstance(data[key], dict) and isinstance(invalid[key], dict):
                Artifact._sub_invalid(data[key], invalid[key])
                if not data[key]:  # If sub-dictionary becomes empty after subtraction
                    del data[key]
            elif data[key] == invalid[key]:
                del data[key]

    @staticmethod
    def _make_valid(data: dict) -> None:
        """
        Refines the given data dictionary by identifying and removing invalid entries.
        It creates a copy, applies a set of "invalidating" rules, then subtracts these
        invalid entries from the original data.

        Args:
            data (dict): The dictionary to validate and modify.
        """
        # Create invalid
        invalid = copy.deepcopy(data)
        Artifact._rmv_dir(invalid, "LatestArtifact")  # Remove LatestArtifact from the invalid set
        Artifact._rmv_empty(invalid)  # Remove empty directories from the invalid set
        Artifact._sub_invalid(data, invalid)  # Subtract the 'invalid' set from the main data
        Artifact._rmv_empty(data)  # Remove any newly created empty directories from the main data

    @staticmethod
    def _rename_latestArtifact(data: dict) -> None:
        """
        If a "LatestArtifact" directory exists, its contents are moved one level up
        (i.e., its children become siblings of "LatestArtifact"), and "LatestArtifact" itself is removed.

        Args:
            data (dict): The dictionary to modify.
        """
        for key, value in list(data.items()):  # Iterate over a copy of keys to allow modification during iteration
            if isinstance(value, dict):
                Artifact._rename_latestArtifact(value)
        if "LatestArtifact" in data:
            latest = data.pop("LatestArtifact")
            if isinstance(latest, dict):
                for k, v in latest.items():
                    data[k] = v

    @staticmethod
    def _create_list_of_dicts(data: dict, target: list, swb: str) -> None:
        """
        Recursively traverses the directory structure represented by `data` and
        extracts all file paths, adding them as dictionaries to the `target` list.

        Args:
            data (dict): The source dictionary representing the directory structure.
            target (list): The list to append artifact dictionaries to.
            swb (str): The Software Branch (SWB) to associate with each artifact.
        """
        for key, value in list(data.items()):
            if isinstance(value, dict):
                Artifact._create_list_of_dicts(value, target, swb)
            else:
                target.append({"path": value, "swb": swb})

    @staticmethod
    def __list_dir(path: str, data: dict, max_lvl: int) -> None:
        """
        Recursive helper function that builds a dictionary representing the directory structure.

        Args:
            path (str): The current path to scan.
            data (dict): The dictionary to populate with the directory structure.
            max_lvl (int): The maximum depth to traverse.
        """
        try:
            for e in os.listdir(path):
                print(f"{e}")  # For debugging/progress tracking
                full_path = os.path.join(path, e)
                if os.path.isdir(full_path):
                    data[e] = {}
                    if max_lvl > 0:
                        Artifact.__list_dir(full_path, data[e], max_lvl - 1)
                else:
                    data[e] = full_path.replace("\\", "/")
        except FileNotFoundError:
            print(f"Path not found: {path}")
        except PermissionError:
            print(f"Permission denied for path: {path}")
        except Exception as e:
            print(f"An error occurred while listing directory {path}: {e}")

    def _LCO_list(self):
        """
        Iterates through the `self._list` of artifacts (zip files).
        For each artifact, it attempts to open the zip file and extract information
        from "Docs/Model_Overview.html" if it exists.
        Extracted data includes "name", "HEXFile", and "A2LFile".
        Updates the artifact's dictionary with "Model_Overview" boolean and "Model_Overview_data".
        """
        for cnt, key in enumerate(self._list):
            print(f"Processing artifact {cnt+1}/{len(self._list)}")
            try:
                with zipfile.ZipFile(key["path"], 'r') as zipf:
                    if "Docs/Model_Overview.html" in zipf.namelist():
                        key["Model_Overview"] = True
                        key["Model_Overview_data"] = {}

                        with zipf.open("Docs/Model_Overview.html") as file:
                            # Use charset_normalizer to robustly decode content
                            content = str(from_bytes(file.read()).best())

                            # Extract 'name'
                            start = content.find("id=\"releaseVersion\">")
                            if start != -1:
                                start = content.find(">", start) + 1
                                end = content.find("<", start)
                                if start != -1 and end != -1 and start < end:
                                    key["Model_Overview_data"]["name"] = content[start:end].strip().replace("\\", "/")

                            # Extract 'HEXFile'
                            start = content.find("HEXFile</td><td>") + len("HEXFile</td><td>")
                            if start != -1:
                                end = content.find("<", start)
                                if start != -1 and end != -1 and start < end:
                                    hex_file = content[start:end].strip().replace("\\", "/")
                                    if hex_file: # Only add if not empty
                                        key["Model_Overview_data"]["HEXFile"] = hex_file

                            # Extract 'A2LFile'
                            start = content.find("A2LFile</td><td>") + len("A2LFile</td><td>")
                            if start != -1:
                                end = content.find("<", start)
                                if start != -1 and end != -1 and start < end:
                                    a2l_file = content[start:end].strip().replace("\\", "/")
                                    if a2l_file: # Only add if not empty
                                        key["Model_Overview_data"]["A2LFile"] = a2l_file
                    else:
                        key["Model_Overview"] = False
                        key["Model_Overview_data"] = {}
            except zipfile.BadZipFile:
                print(f"Error: {key['path']} is not a valid zip file.")
                key["Model_Overview"] = False
                key["Model_Overview_data"] = {}
            except KeyError as e:
                print(f"Error accessing zip content in {key['path']}: {e}")
                key["Model_Overview"] = False
                key["Model_Overview_data"] = {}
            except Exception as e:
                print(f"An unexpected error occurred with {key['path']}: {e}")
                key["Model_Overview"] = False
                key["Model_Overview_data"] = {}

    def cleanup_list(self):
        """
        Filters the `self._list` to keep only artifacts that have:
        - "Model_Overview" set to True.
        - Either "HEXFile" or "A2LFile" present in their "Model_Overview_data".
        """
        data = [
            entry for entry in self._list
            if entry.get("Model_Overview") is True and (
                "HEXFile" in entry.get("Model_Overview_data", {}) or
                "A2LFile" in entry.get("Model_Overview_data", {})
            )
        ]
        self._list = data


class Artifact545(Artifact):
    """
    Specific implementation for artifacts related to LCOV5.4.5.
    """

    def __init__(self):
        """
        Initializes Artifact545 with its specific path and prefix.
        """
        super().__init__("//bosch.com/dfsrb/DfsDE/DIV/DGS/08/EC/20_CE/PJ/60_SRL_LCT/LC_TESTS/Projects/003/LCO_Projects/LCOV5.4.5", "545")

    def cleanup_dir(self):
        """
        Cleans up the directory structure (`self._dir`) for LCOV5.4.5 artifacts
        by applying a series of removal and renaming rules.
        """
        Artifact._rmv_non_zip(self._dir)
        Artifact._rmv_file(self._dir, "runtime.zip")
        Artifact._rmv_file(self._dir, "sources.zip")
        Artifact._rmv_dir(self._dir, "Failed")
        Artifact._rmv_dir(self._dir, "Dev")
        Artifact._rmv_dir(self._dir, "LCOV5.4.4")
        Artifact._rmv_dir(self._dir, "_old_models")
        Artifact._rmv_dir(self._dir, "Development", True)  # Remove all dirs containing "Development"
        Artifact._rmv_dir(self._dir, "Archive", True)      # Remove all dirs containing "Archive"
        Artifact._rmv_dir(self._dir, "Depreciated", True)  # Remove all dirs containing "Depreciated"
        Artifact._rmv_everything_except_dir(self._dir, "Released")
        Artifact._rmv_unzip(self._dir)
        Artifact._rmv_empty(self._dir)
        Artifact._rename_released(self._dir)
        Artifact._make_valid(self._dir)
        Artifact._rename_latestArtifact(self._dir)

    def create_list(self):
        """
        Transforms the cleaned directory structure (`self._dir`) into a flat list
        of artifact dictionaries (`self._list`) and then extracts further details
        from within the artifacts themselves.
        """
        Artifact._create_list_of_dicts(self._dir, self._list, "SWB26.1")
        self._LCO_list()


class Artifact5411(Artifact):
    """
    Specific implementation for artifacts related to LCOV5.4.11.
    """

    def __init__(self):
        """
        Initializes Artifact5411 with its specific path and prefix.
        """
        super().__init__("//bosch.com/dfsrb/DfsDE/DIV/DGS/08/EC/20_CE/PJ/60_SRL_LCT/LC_TESTS/Projects/003/LCO_Projects/LCOV5.4.11", "5411")

    def cleanup_dir(self):
        """
        Cleans up the directory structure (`self._dir`) for LCOV5.4.11 artifacts
        by applying a series of removal and renaming rules. These rules are
        identical to those for Artifact545, but applied to a different path.
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
        """
        Transforms the cleaned directory structure (`self._dir`) into a flat list
        of artifact dictionaries (`self._list`) and then extracts further details
        from within the artifacts themselves.
        """
        Artifact._create_list_of_dicts(self._dir, self._list, "SWB26.2")
        self._LCO_list()


if __name__ == '__main__':
    # Example usage for Artifact5411
    print("Processing Artifact5411...")
    art = Artifact5411()
    print("Creating directory structure...")
    art.create_dir()
    print("Cleaning up directory structure...")
    art.cleanup_dir()
    print("Dumping cleaned directory structure to file...")
    art.dump_dir()
    print("Creating artifact list and extracting data from zips...")
    art.create_list()
    print("Cleaning up artifact list...")
    art.cleanup_list()
    print("Dumping cleaned artifact list to file...")
    art.dump_list()
    print("Artifact5411 processing complete.")

    # Example usage for Artifact545 (uncomment to run)
    # print("\nProcessing Artifact545...")
    # art_545 = Artifact545()
    # print("Creating directory structure...")
    # art_545.create_dir()
    # print("Cleaning up directory structure...")
    # art_545.cleanup_dir()
    # print("Dumping cleaned directory structure to file...")
    # art_545.dump_dir()
    # print("Creating artifact list and extracting data from zips...")
    # art_545.create_list()
    # print("Cleaning up artifact list...")
    # art_545.cleanup_list()
    # print("Dumping cleaned artifact list to file...")
    # art_545.dump_list()
    # print("Artifact545 processing complete.")