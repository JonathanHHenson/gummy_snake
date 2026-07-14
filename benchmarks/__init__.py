"""Local-first benchmark framework for Gummy Snake."""

from .framework.local_database import DEFAULT_LOCAL_HISTORY, LocalBenchmarkDatabase
from .governance import AUTHORITATIVE_DATA_REF, PERCENT_REGRESSION_LIMIT

__all__ = [
    "AUTHORITATIVE_DATA_REF",
    "DEFAULT_LOCAL_HISTORY",
    "LocalBenchmarkDatabase",
    "PERCENT_REGRESSION_LIMIT",
]
