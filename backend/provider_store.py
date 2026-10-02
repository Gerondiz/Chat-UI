import json
import os

from models import ProviderConfig


CONFIG_FILE = os.path.join(os.path.dirname(__file__), "provider_config.json")


def load_config() -> ProviderConfig | None:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ProviderConfig(**data)
    except Exception:
        return None


def save_config(cfg: ProviderConfig) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg.model_dump(), f, ensure_ascii=False, indent=2)
