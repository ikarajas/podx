from functools import lru_cache
from podx.services.config import Config, load_config

@lru_cache(maxsize=1)
def get_config() -> Config:
    """Load and cache the application :class:`Config`."""
    return load_config()

__all__ = ["get_config", "Config"]
