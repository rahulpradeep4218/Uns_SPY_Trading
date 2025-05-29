from logging import config
import yaml
from dagster import ConfigurableResource, resource
import mlflow

class TrainingConfig(ConfigurableResource):
    """
    Configuration for all training pipeline
    """

    config_path: str

    def load(self) -> dict:
        """
        Load the configuration details.
        """
        with open(self.config_path, 'r') as file:
            conf = yaml.safe_load(file)
            return conf
        return {}
    

class MLFlowResource(ConfigurableResource):
    """
    MLflow as a resource for tracking experiments.
    """
    tracking_uri: str
    experiment_name: str
    def load(self):
        """
        loads mlflow from configuration
        """
        mlflow.set_tracking_uri(self.tracking_uri)
        mlflow.set_experiment(self.experiment_name)
        mlflow.set_tag("dagster", "trading_dagster")
        return mlflow
          