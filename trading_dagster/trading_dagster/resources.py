from logging import config
import yaml
from dagster import ConfigurableResource

class IndicatorConfig(ConfigurableResource):
    """
    Configuration for loading and processing indicator data.
    """

    config_path: str = "../Config/training.yaml"

    def load(self) -> dict:
        """
        Load the configuration details.
        """
        with open(self.config_path, 'r') as file:
            conf = yaml.safe_load(file)
            return conf
        return {}