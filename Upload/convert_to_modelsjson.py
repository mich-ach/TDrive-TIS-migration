import json
import unittest

def create_mig(file: str, output: str) -> None:
    """creates migration file

    Args:
        file (str): file to create migration from
    """
    data_src = []
    with open(file, 'r') as f:
        data_src = json.load(f)
    data = {"models":[]}
    data["models"] = [e["transfer"] for e in data_src]
    with open(output, 'w') as f:
        f.write(json.dumps(data, indent=4))

class TestMigrationData(unittest.TestCase):
    """
    Tests for the migration data loaded from mig.json.
    """

        
    def setUp(self):
        """Load the JSON data before each test."""
        try:
            with open("mig4.json", 'r') as f:
                self.data = json.load(f)
        except FileNotFoundError:
            self.data = {"models": []}  # Provide a default if the file is not found
            print("mig4.json not found.  Tests will run with an empty model list.")

    def test_lco_migration_is_false(self):
        """Test that lco_migration is always False."""
        errors = []
        for model in self.data['models']:
            if model['lco_migration']:
                errors.append(f"lco_migration should be False for model: {model['tis_artifact_name']}")
        self.assertEqual(len(errors), 0, "\n".join(errors))

    def test_customer_group_is_vw(self):
        """Test that customer_group is always 'VW'."""
        errors = []
        for model in self.data['models']:
            if model['customer_group'] != 'VW':
                errors.append(f"customer_group should be 'VW' for model: {model['tis_artifact_name']}, but is {model['customer_group']}")
        self.assertEqual(len(errors), 0, "\n".join(errors))

    def test_tis_artifact_name_starts_with_vw_mdl(self):
        """Test that tis_artifact_name starts with 'VW MDL : '."""
        errors = []
        for model in self.data['models']:
            if not model['tis_artifact_name'].startswith("VW MDL :"):
                errors.append(f"tis_artifact_name should start with 'VW MDL : ' for model: {model['tis_artifact_name']}")
        self.assertEqual(len(errors), 0, "\n".join(errors))

    def test_tis_artifact_path_starts_with_xcu_projects(self):
        """Test that tis_artifact_path starts with 'xCU Projects'."""
        errors = []
        for model in self.data['models']:
            if not model['tis_artifact_path'].startswith('xCU Projects'):
                errors.append(f"tis_artifact_path should start with 'xCU Projects' for model: {model['tis_artifact_name']}, but is {model['tis_artifact_path']}")
        self.assertEqual(len(errors), 0, "\n".join(errors))

    def test_tis_artifact_path_no_minor_version(self):
        """Test that tis_artifact_path does not contain extra versioning like -3.8"""
        errors = []
        for model in self.data['models']:
            path = model['tis_artifact_path']
            parts = path.split('/')
            for part in parts:
                if '-' in part:
                    name_part = part.split('-')
                    if len(name_part) > 1:
                        try:
                            float(name_part[1])
                            errors.append(f"tis_artifact_path contains extra versioning in part: {part} for model: {model['tis_artifact_name']}")
                        except ValueError:
                            pass # not a version
        self.assertEqual(len(errors), 0, "\n".join(errors))
        
    def test_no_duplicate_tis_artifact_paths(self):
        """Test that there are no duplicate tis_artifact_paths."""
        paths = [model['tis_artifact_path'] for model in self.data['models']]
        duplicates = {path: paths.count(path) for path in set(paths) if paths.count(path) > 1}
        self.assertEqual(len(duplicates), 0, f"Found duplicate tis_artifact_paths:\n{json.dumps(duplicates, indent=4)}")

    def test_no_duplicate_model_input_filepath(self):
        """Test that there are no duplicate model_input_filepath."""
        paths = [model['model_input_filepath'] for model in self.data['models']]
        duplicates = {path: paths.count(path) for path in set(paths) if paths.count(path) > 1}
        self.assertEqual(len(duplicates), 0, f"Found duplicate model_input_filepath:\n{json.dumps(duplicates, indent=4)}")

if __name__ == "__main__":
    #create_mig(r"./check4.json", r"mig4.json")
    unittest.main()
    
    
""" #def test_path_parts_match(self, indices: list[tuple[int, int]] = [(0, 1)]):
 #    
 #    Test that parts of tis_artifact_name match parts of tis_artifact_path.

 #    Args:
 #        indices (list[tuple[int, int]]): A list of tuples, where each tuple
 #            contains (name_index, path_index) for comparison.
 #  
 #    errors = []
 #    for model in self.data['models']:
 #        name_parts = model['tis_artifact_name'].split(' / ')
 #        path_parts = model['tis_artifact_path'].split('/')
 #        #print(path_parts)
 #        #print(name_parts)
 #        if len(name_parts) <= 0:
 #            errors.append(f"tis_artifact_name has no parts for model: {model['tis_artifact_name']}")
 #            continue
 #        name_part = name_parts[0].split(': ')
 #        if len(name_part) <= 1:
 #            errors.append(f"tis_artifact_name part has no parts for model: {model['tis_artifact_name']}")
 #            continue
 #        name_part = name_part[1].split('_')[0] # Extract only the relevant part
 #        for name_index, path_index in indices:
 #            if not (len(path_parts) > path_index):
 #                errors.append(f"Not enough parts in path to compare for model: {model['tis_artifact_name']}")
 #                continue
 #            path_part = path_parts[path_index]
 #            #print(path_part)
 #            #print(name_part)
 #            if not (name_part in path_part):
 #                errors.append(f"Parts do not match for model: {model['tis_artifact_name']}. Expected '{name_part}' in '{path_part}'")
 #    self.assertEqual(len(errors), 0, "\n".join(errors))     """