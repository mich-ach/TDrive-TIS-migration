import json
import csv
import openpyxl

class Check:
    def __init__(self, available: list[str] | str, missing: str):
        """_summary_

        Args:
            available (list[str] | str): available artifacts created with Artifact class (json file)
            missing (str): missing artifacts (csv file)
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
            e["transfer"]["tis_artifact_path"] = f"xCU Projects/{ecu.replace(".", "")}/{e["PVER"][0]["PVER"]}/Model/HiL/{e["swb"]}/{LC_Type}"
            e["transfer"]["tis_migration"] = True
            e["transfer"]["lco_migration"] = False

    def dump(self) -> None:
        """dumps compare json
        """
        with open("check.json", 'w') as f:
            f.write(json.dumps(self.__av, indent=4))

    @staticmethod
    def create_mig(file: str) -> None:
        """creates migration file

        Args:
            file (str): file to create migration from
        """
        data_src = []
        with open(file, 'r') as f:
            data_src = json.load(f)
        data = {"models":[]}
        data["models"] = [e["transfer"] for e in data_src]
        with open("mig.json", 'w') as f:
            f.write(json.dumps(data, indent=4))

    @staticmethod
    def transform_excel(file_in: str, file_out: str) -> None:
        """transform missing.xlsx to csv which Check() can work with

        Args:
            file_in (str): xlsx file
            file_out (str): target csv file
        """
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
    Check.create_mig("check.json")