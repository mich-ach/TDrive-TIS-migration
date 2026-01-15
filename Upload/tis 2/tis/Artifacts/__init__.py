import json
import os
import copy
import zipfile
from charset_normalizer import from_bytes


class Artifact:
    def __init__(self, path: str, prefix: str):
        """_summary_

        Args:
            path (str): path to search for Artifacts in
            prefix (str): LCO ver
        """
        self.__path = path
        self.__prefix = prefix
        self._dir = {}
        self._list = []

    def load_dir(self) -> None:
        """loads json into self._dir
        """
        with open(f"{self.__prefix}dir.json", 'r') as f:
            self._dir = json.load(f)

    def load_list(self) -> None:
        """loads json into self._list
        """
        with open(f"{self.__prefix}list.json", 'r') as f:
            self._list = json.load(f)

    def dump_dir(self) -> None:
        """dumps self._dir into json
        """
        with open(f"{self.__prefix}dir.json", 'w') as f:
            f.write(json.dumps(self._dir, indent=4))

    def dump_list(self) -> None:
        """dumps self._list into json
        """
        with open(f"{self.__prefix}list.json", 'w') as f:
            f.write(json.dumps(self._list, indent=4))

    def create_dir(self) -> None:
        """create the self._dir dictionary by creating a copy of the directory structure of the given directory
        """
        Artifact.__list_dir(self.__path, self._dir, 6)

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
                print(f"{e}")
                if os.path.isdir(os.path.join(path, e)):
                    data[e] = {}
                    if max_lvl != 0:
                        Artifact.__list_dir(os.path.join(path, e), data[e], max_lvl-1)
                else:
                    data[e] = os.path.join(path, e).replace("\\", "/")
        except FileNotFoundError:
            pass

    def _LCO_list(self):
        """Extract data from Model_Overview.html in Artifact
        """
        for cnt, key in enumerate(self._list):
            print(cnt)
            try:
                with zipfile.ZipFile(key["path"], 'r') as zipf:
                    if "Docs/Model_Overview.html" in zipf.namelist():
                        key["Model_Overview"] = True
                        key["Model_Overview_data"] = {}

                        with zipf.open("Docs/Model_Overview.html") as file:
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
                    else:
                        key["Model_Overview"] = False
                        key["Model_Overview_data"] = {}
            except Exception as e:
                print(e)
                key["Model_Overview"] = False
                key["Model_Overview_data"] = {}

    def cleanup_list(self):
        """Removes Artifacts where not enough data is found
        """
        data = [e for e in self._list if e.get("Model_Overview") is True and (
            "HEXFile" in e.get("Model_Overview_data") or "A2LFile" in e.get("Model_Overview_data"))]
        self._list = data


class Artifact545(Artifact):
    def __init__(self):
        super().__init__("//bosch.com/dfsrb/DfsDE/DIV/DGS/08/EC/20_CE/PJ/60_SRL_LCT/LC_TESTS/Projects/003/LCO_Projects/LCOV5.4.5", "545")

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
        Artifact._create_list_of_dicts(self._dir, self._list, "SWB26.1")
        self._LCO_list()


class Artifact5411(Artifact):
    def __init__(self):
        super().__init__("//bosch.com/dfsrb/DfsDE/DIV/DGS/08/EC/20_CE/PJ/60_SRL_LCT/LC_TESTS/Projects/003/LCO_Projects/LCOV5.4.11", "5411")

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
        Artifact._create_list_of_dicts(self._dir, self._list, "SWB26.2")
        self._LCO_list()


if __name__ == '__main__':
    art = Artifact5411()
    art.create_dir()
    art.cleanup_dir()
    art.dump_dir()
    art.create_list()
    art.cleanup_list()
    art.dump_list()
