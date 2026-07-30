from brandscan.config.loader import ConfigError, load_config, validate_config
from brandscan.config.model import (
    DEFAULT_SIMILARITY_THRESHOLD,
    Config,
    ReferenceImage,
    ScanScope,
    SearchGroup,
    Severity,
    Target,
)

__all__ = [
    "Config",
    "ConfigError",
    "DEFAULT_SIMILARITY_THRESHOLD",
    "ReferenceImage",
    "ScanScope",
    "SearchGroup",
    "Severity",
    "Target",
    "load_config",
    "validate_config",
]
