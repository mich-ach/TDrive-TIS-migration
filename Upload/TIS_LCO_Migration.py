import re
import os
import shutil
import json
import unicodedata
import requests


def import_json(path):
    f = open(path)
    data = json.load(f)
    f.close()

    return data


def run_recipe(recipe, name, recipe_type):
    # Create the target directory if it doesn't exist
    target_dir = os.path.join(os.path.dirname(recipe), name, recipe_type)
    os.makedirs(target_dir, exist_ok=True)

    # Copy the recipe and its defaults file to the target directory
    shutil.copy(recipe, os.path.join(target_dir, os.path.basename(recipe)))
    shutil.copy(recipe + '_defaults', os.path.join(target_dir, os.path.basename(recipe) + '_defaults'))

    # Execute PBClient.exe with the recipe in the target directory
    os.system(f'PBClient.exe -r {os.path.join(target_dir, os.path.basename(recipe))}')


def slugify(value, allow_unicode=False):
    """
    Taken from https://github.com/django/django/blob/master/django/utils/text.py
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
    else:
        value = unicodedata.normalize('NFKD', value).encode(
            'ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('-_')


def execute_recipe(recipe_defaults, model, recipe_type):
    # Read the template file
    with open(recipe_defaults, 'r') as file:
        defaults = file.read()

    # Replace parameters in the template
    for key, value in model.items():
        if key not in ['tis_migration', 'lco_migration']:
            if isinstance(value, str):
                value = value.replace('\\', '\\\\')
            try:
                defaults = re.sub(
                    rf'<param name="{key}">.*?</param>',
                    f'<param name="{key}">{value}</param>',
                    defaults,
                )
            except:
                print(f"Parameter {key} not found in {os.path.basename(recipe_defaults).split('/')[-1]}")

    # Update a specific part of the template
    if recipe_type == 'lco_migration':
        arr = defaults.split('/')
        arr[arr.index('HiL') + 1] = 'CSP LC 2022.1'
        defaults = "/".join(arr)

    # Write the modified template back to the file
    with open(recipe_defaults, 'w') as file:
        file.write(defaults)

    # Execute the recipe
    run_recipe(recipe_defaults.replace('_defaults', ''), slugify(model['tis_artifact_name']), recipe_type)


def get_tis_artifact_rId(model):
    request = 'http://rb-ps-tis-service.bosch.com:8081/tis-api/manage/componentInstance?$filter=componentGrp.name eq \'TIS Artifact Container\' and component.name eq \'vVeh_LCO\' and name eq \'tis_artifact_name\'&Stop=0'
    headers = {'X-ToolName': 'Migration Tool ECV', 'X-ToolVersion' : '1.0'}

    try:
        data = json.loads(requests.get(request.replace('tis_artifact_name', model['tis_artifact_name']), headers = headers, timeout=4).text)
        if len(data) == 1:
            data = data[0]
            rId = data['rId']
        elif len(data) == 2:
            data = data[1]
            rId = data['rId']
        else:
            rId = None

        return rId
    except requests.exceptions.Timeout as e:
        # Maybe set up for a retry
        print(e)
        rId = None
    
    
    