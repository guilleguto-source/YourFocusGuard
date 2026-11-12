import json
import os


class Config:
    def __init__(self, config_path: str = "config.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    def get_api_for_task(self, task_type: str) -> str:
        for api_name, cfg in self.data.get("apis", {}).items():
            if task_type in cfg.get("usar_para", []):
                return api_name
        return "groq"

    def get_model(self, api_name: str) -> str:
        return self.data["apis"][api_name]["modelo"]

    def get_env(self, key: str) -> str:
        return os.getenv(key, "")