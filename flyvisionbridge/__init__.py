"""RGB sampling on published fly visual columns, not a neural-response API."""
from .bridge import Frame, map_frame, load_mapping, load_eye_mapping

__version__ = "0.1.0"
__all__ = ["Frame", "map_frame", "load_mapping", "load_eye_mapping"]
