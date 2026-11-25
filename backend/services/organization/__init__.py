"""Organization, deduplication, and spatiotemporal grouping service."""
from .bursts import detect_bursts
from .duplicates import MAX_THRESHOLD, UnionFind, choose_keeper, find_duplicates
from .grouper import group_images, name_groups, refine_events
from .live_pairs import link_live_pairs
from .similarity import (
    compute_features,
    compute_phash,
    features_from_bytes,
    hamming,
    parse_phash,
)

__all__ = [
    "detect_bursts",
    "MAX_THRESHOLD",
    "UnionFind",
    "choose_keeper",
    "find_duplicates",
    "group_images",
    "name_groups",
    "refine_events",
    "link_live_pairs",
    "compute_features",
    "compute_phash",
    "features_from_bytes",
    "hamming",
    "parse_phash",
]
