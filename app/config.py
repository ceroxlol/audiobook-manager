import os
import yaml
from typing import Dict, Any

class Config:
    def __init__(self):
        self.config_path = "/opt/audiobook-manager/config/settings.yaml"
        self.load_config()
    
    def load_config(self):
        with open(self.config_path, 'r') as file:
            self._config = yaml.safe_load(file)
    
    def get(self, key: str, default=None) -> Any:
        keys = key.split('.')
        value = self._config
        for k in keys:
            value = value.get(k, {})
        return value if value != {} else default
    
    def update(self, updates: Dict[str, Any]):
        # Helper method to update nested config values
        def update_nested(config_dict, update_dict):
            for key, value in update_dict.items():
                if isinstance(value, dict) and key in config_dict:
                    update_nested(config_dict[key], value)
                else:
                    config_dict[key] = value
        
        update_nested(self._config, updates)
        with open(self.config_path, 'w') as file:
            yaml.safe_dump(self._config, file, default_flow_style=False)

config = Config()
