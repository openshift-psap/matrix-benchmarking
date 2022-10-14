import enum

class DownloadModes(enum.Enum):
    CACHE_ONLY = "cache_only"
    PREFER_CACHE = "prefer_cache"
    IMPORTANT = "important"
    ALL = "all"
