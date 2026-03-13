"""Configuration management for job research tool"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from enum import Enum
import json
from dotenv import load_dotenv
import os


class SeniorityLevel(str, Enum):
    """Job seniority levels"""
    JUNIOR = "Junior"
    MID_LEVEL = "Mid-level"
    SENIOR = "Senior"
    ALL = "All levels"


class WorkType(str, Enum):
    """Work arrangement types"""
    REMOTE = "Remote only"
    HYBRID = "Remote/Hybrid"
    ONSITE = "Onsite only"
    ANY = "Any"


class OutputFormat(str, Enum):
    """Output file formats"""
    MARKDOWN = "markdown"
    CSV = "csv"
    JSON = "json"


@dataclass
class JobSearchParams:
    """Parameters for job search"""
    keywords: str = "AI Engineer"
    job_title_alternatives: list[str] = field(default_factory=lambda: [
        "Machine Learning Engineer",
        "ML Engineer",
        "Artificial Intelligence Engineer",
        "Deep Learning Engineer"
    ])
    location: str = "All of Germany"
    specific_cities: list[str] = field(default_factory=list)
    country_code: str = "DE"
    work_type: WorkType = WorkType.HYBRID
    seniority_level: SeniorityLevel = SeniorityLevel.ALL
    years_experience_min: int = 0
    years_experience_max: int = 50
    salary_minimum: int = 50000
    salary_maximum: int = 200000
    currency: str = "EUR"
    industries: list[str] = field(default_factory=lambda: ["All"])


@dataclass
class JobBoardConfig:
    """Configuration for job board searches"""
    search_stepstone: bool = True
    search_linkedin: bool = True
    search_indeed: bool = True
    search_xing: bool = True
    search_honeypot: bool = True
    search_jobborse: bool = True
    search_startups: bool = True
    search_wellfound: bool = True
    search_remote_rocketship: bool = True


@dataclass
class OutputConfig:
    """Output configuration"""
    output_directory: Path = field(default_factory=lambda: Path.cwd() / "data" / "results")
    output_format: OutputFormat = OutputFormat.MARKDOWN
    generate_summary: bool = True
    generate_salary_analysis: bool = True
    cache_directory: Path = field(default_factory=lambda: Path.cwd() / "data" / "cache")
    cache_results: bool = True
    cache_duration_hours: int = 24
    send_email_notification: bool = False
    email_recipient: Optional[str] = None


@dataclass
class Config:
    """Main configuration class"""
    search_params: JobSearchParams = field(default_factory=JobSearchParams)
    job_boards: JobBoardConfig = field(default_factory=JobBoardConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    verbose: bool = False
    claude_api_key: Optional[str] = None
    claude_model: str = "claude-opus-4-6"
    max_jobs_per_search: int = 20

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        load_dotenv()

        search_params = JobSearchParams(
            keywords=os.getenv("JOB_KEYWORDS", "AI Engineer"),
            location=os.getenv("LOCATION", "All of Germany"),
            work_type=WorkType(os.getenv("WORK_TYPE", "Remote/Hybrid")),
            seniority_level=SeniorityLevel(os.getenv("SENIORITY_LEVELS", "All levels")),
            salary_minimum=int(os.getenv("SALARY_MINIMUM", "50000")),
            salary_maximum=int(os.getenv("SALARY_MAXIMUM", "200000")),
        )

        job_boards = JobBoardConfig(
            search_stepstone=os.getenv("SEARCH_STEPSTONE", "true").lower() == "true",
            search_linkedin=os.getenv("SEARCH_LINKEDIN", "true").lower() == "true",
            search_indeed=os.getenv("SEARCH_INDEED", "true").lower() == "true",
            search_xing=os.getenv("SEARCH_XING", "true").lower() == "true",
            search_honeypot=os.getenv("SEARCH_HONEYPOT", "true").lower() == "true",
            search_jobborse=os.getenv("SEARCH_JOBBORSE", "true").lower() == "true",
            search_startups=os.getenv("SEARCH_STARTUPS", "true").lower() == "true",
            search_wellfound=os.getenv("SEARCH_WELLFOUND", "true").lower() == "true",
            search_remote_rocketship=os.getenv("SEARCH_REMOTE_ROCKETSHIP", "true").lower() == "true",
        )

        output = OutputConfig(
            output_directory=Path(os.getenv("OUTPUT_DIRECTORY", "data/results")),
            output_format=OutputFormat(os.getenv("OUTPUT_FORMAT", "markdown")),
            cache_duration_hours=int(os.getenv("CACHE_DURATION_HOURS", "24")),
        )

        return cls(
            search_params=search_params,
            job_boards=job_boards,
            output=output,
            verbose=os.getenv("VERBOSE", "false").lower() == "true",
            claude_api_key=os.getenv("CLAUDE_API_KEY"),
            claude_model=os.getenv("CLAUDE_MODEL", "claude-opus-4-6"),
            max_jobs_per_search=int(os.getenv("MAX_JOBS_PER_SEARCH", "20")),
        )

    @classmethod
    def from_json(cls, filepath: Path) -> "Config":
        """Load configuration from JSON file"""
        with open(filepath, 'r') as f:
            data = json.load(f)

        search_params = JobSearchParams(**data.get("search_params", {}))
        job_boards = JobBoardConfig(**data.get("job_boards", {}))
        output = OutputConfig(**data.get("output", {}))

        return cls(
            search_params=search_params,
            job_boards=job_boards,
            output=output,
            verbose=data.get("verbose", False),
        )

    def to_dict(self) -> dict:
        """Convert configuration to dictionary"""
        return {
            "search_params": {
                "keywords": self.search_params.keywords,
                "location": self.search_params.location,
                "work_type": self.search_params.work_type.value,
                "seniority_level": self.search_params.seniority_level.value,
                "salary_minimum": self.search_params.salary_minimum,
                "salary_maximum": self.search_params.salary_maximum,
                "industries": self.search_params.industries,
            },
            "job_boards": {
                "search_stepstone": self.job_boards.search_stepstone,
                "search_linkedin": self.job_boards.search_linkedin,
                "search_indeed": self.job_boards.search_indeed,
                "search_xing": self.job_boards.search_xing,
                "search_honeypot": self.job_boards.search_honeypot,
            },
            "output": {
                "output_format": self.output.output_format.value,
                "generate_summary": self.output.generate_summary,
                "generate_salary_analysis": self.output.generate_salary_analysis,
            },
        }
