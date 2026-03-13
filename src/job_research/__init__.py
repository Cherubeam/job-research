"""Job Research - AI/ML Job Market Research Tool for German Job Boards"""

__version__ = "0.1.0"
__author__ = "Marco Braun"

from job_research.config import Config, JobSearchParams
from job_research.analyzer import JobAnalyzer
from job_research.scraper import ClaudeScraper

__all__ = ["Config", "JobSearchParams", "JobAnalyzer", "ClaudeScraper"]
