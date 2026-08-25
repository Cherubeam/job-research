"""Job Research - AI/ML Job Market Research Tool for German Job Boards"""

from importlib.metadata import PackageNotFoundError, version

from job_research.analyzer import JobAnalyzer
from job_research.config import Config, JobSearchParams
from job_research.scraper import ClaudeScraper

try:
    __version__ = version("job-research")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0+unknown"

__author__ = "Marco Braun"

__all__ = ["Config", "JobSearchParams", "JobAnalyzer", "ClaudeScraper", "__version__"]
