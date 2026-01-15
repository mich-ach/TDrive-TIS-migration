# -*- coding: utf-8 -*-
"""
Created on Tue Mar 28 19:54:40 2023

@author: FUM83WI
"""

import os, time
import TIS_LCO_Migration as mig

##########################################################################################
models = os.path.join(os.getcwd(),'models.json')

recipe_TIS_migration = os.path.join(os.getcwd(), 'MIGRATE_TDRIVE_CONTAINER_TO_TIS_WITH_METADATA.pbr')
recipe_LCO_migration = os.path.join(os.getcwd(), 'LCO_LCO_Migration.pbr')
##########################################################################################
recipe_TIS_migration_defaults = recipe_TIS_migration + '_defaults'
recipe_LCO_migration_defaults = recipe_LCO_migration + '_defaults'

data = mig.import_json(models)

for model in data['models']:
    print('Model Name:', model['tis_artifact_name'])
    model['tis_artifact_identifier'] = mig.get_tis_artifact_rId(model)

    # Check if the model should be migrated to TIS
    if (model['tis_artifact_identifier'] is None and model['tis_migration']):
        print('TIS MIGRATION:')
        mig.execute_recipe(recipe_TIS_migration_defaults, model, 'tis_migration')
    else:
        print('Artifact already exists or TIS migration not enabled')
    
    # time for artifactory to update
    time.sleep(5)

    # Check if the model should be migrated to new LCO version
    if (model['tis_artifact_identifier'] is not None and model['lco_migration']):
        print('LCO MIGRATION:')
        mig.execute_recipe(recipe_TIS_migration_defaults, model, 'lco_migration')
    else:
        print('Artifact for LCO migration does not exists or LCO migration not enabled')

print('finish')
