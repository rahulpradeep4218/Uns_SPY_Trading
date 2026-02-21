from dagster import Definitions, load_assets_from_modules, define_asset_job, AssetSelection
from resources import TrainingConfig, MLFlowResource
import yaml
import mlflow
import os
import logging
from requests.exceptions import ConnectionError as RequestsConnectionError
from mlflow.exceptions import MlflowException

import assets

all_assets = load_assets_from_modules([assets])

# Define the configuration path
config_path = os.getenv('CONFIG_CONTAINER_PATH', 'config/config.yaml')
with open(config_path, 'r') as file:
      config = yaml.safe_load(file)

logger = logging.getLogger(__name__)


run_name = f'{config["training_details"]["model_name"]}_run'
model_name = config['training_details']['model_name']

#Define a job with all assets
all_assets_job = define_asset_job(name="all_assets_job")

# Select only assets in the "ml" group
ml_assets_job = define_asset_job(
    name="ml_training_job",
    selection=AssetSelection.groups("model_training")
)

# Select only assets in the "rl" group
rl_assets_job = define_asset_job(
    name="rl_training_job",
    selection=AssetSelection.groups("rl_training")
)

defs = Definitions(
    assets=all_assets,
    resources={"training_config": TrainingConfig(config_path=config_path),
               "mlflow_resource": MLFlowResource(
                    tracking_uri=config['mlflow']['tracking_uri'],
                    experiment_name=config['mlflow']['experiment_name'],
                    model_name=model_name,
                    run_name=run_name
               )
      },
    jobs=[all_assets_job, ml_assets_job, rl_assets_job],
)
