from dagster import Definitions, load_assets_from_modules
from resources import TrainingConfig, MLFlowResource
import yaml
import mlflow
import os

import assets

all_assets = load_assets_from_modules([assets])

# Define the configuration path
config_path = os.getenv('CONFIG_CONTAINER_PATH', 'config/config.yaml')
with open(config_path, 'r') as file:
      config = yaml.safe_load(file)

# Set ML Flow config
mlflow.set_tracking_uri(config['mlflow']['tracking_uri'])
experiment_name = config['mlflow']['experiment_name']
exp = mlflow.get_experiment_by_name(experiment_name)
if exp is None:
    exp_id = mlflow.create_experiment(experiment_name)
else:
    exp_id = exp.experiment_id

run_name = f'{config["training_details"]["model_name"]}_run'
model_name = config['training_details']['model_name']

defs = Definitions(
    assets=all_assets,
    resources={"training_config": TrainingConfig(config_path=config_path),
               "mlflow_resource": MLFlowResource(
                    experiment_name=experiment_name,
                    model_name=model_name,
                    experiment_id=exp_id,
                    run_name=run_name
               )
      }
)
