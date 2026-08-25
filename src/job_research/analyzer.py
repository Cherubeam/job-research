"""Job data analysis and reporting"""

import re
import statistics
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator


class JobListing(BaseModel):
    """Represents a single job listing"""

    title: str
    company: str = ""
    location: str = ""
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "EUR"
    job_board: str = ""
    job_url: str = ""
    work_type: str = ""
    description: str = ""
    posted_date: Optional[str] = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title must not be empty")
        return v

    @model_validator(mode="before")
    @classmethod
    def coerce_salaries(cls, data: dict) -> dict:
        if not isinstance(data, dict):
            return data
        raw_min = data.get("salary_min")
        raw_max = data.get("salary_max")
        if isinstance(raw_min, str) or isinstance(raw_max, str):
            combined = f"{raw_min or ''} {raw_max or ''}".strip()
            data["salary_min"], data["salary_max"] = _parse_salary_range(combined)
        else:
            data["salary_min"] = _coerce_salary(raw_min)
            data["salary_max"] = _coerce_salary(raw_max)
        return data

    def salary_midpoint(self) -> Optional[float]:
        """Calculate salary midpoint"""
        if self.salary_min and self.salary_max:
            return (self.salary_min + self.salary_max) / 2
        return None


def _coerce_salary(v: object) -> Optional[int]:
    """Coerce a single salary value to int or None."""
    if v is None:
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    return None


def _parse_salary_range(salary_str: str) -> tuple[Optional[int], Optional[int]]:
    """Parse a salary string into (min, max). Handles European formats, k-notation."""
    if not salary_str or not salary_str.strip():
        return None, None

    salary_str = re.sub(r"(\d+)\s*[kK]", lambda m: str(int(m.group(1)) * 1000), salary_str)

    cleaned = re.sub(r"[€$£]", "", salary_str)
    cleaned = re.sub(r"(\d)\.(\d{3})(?!\d)", r"\1\2", cleaned)
    cleaned = cleaned.replace(",", "")

    numbers = re.findall(r"\d+", cleaned)
    if not numbers:
        return None, None

    try:
        if len(numbers) >= 2:
            return int(numbers[0]), int(numbers[1])
        return int(numbers[0]), None
    except ValueError:
        return None, None


class JobAnalyzer:
    """Analyze job listings and generate reports"""

    def __init__(self) -> None:
        self.listings: list[JobListing] = []

    def add_listing(self, listing: JobListing) -> None:
        """Add a job listing to the analyzer"""
        self.listings.append(listing)

    def add_listings(self, listings: list[JobListing]) -> None:
        """Add multiple job listings"""
        self.listings.extend(listings)

    def get_total_count(self) -> int:
        """Get total number of listings"""
        return len(self.listings)

    def get_listings_by_board(self) -> dict[str, int]:
        """Count listings by job board"""
        counts: dict[str, int] = {}
        for listing in self.listings:
            board = listing.job_board or "Unknown"
            counts[board] = counts.get(board, 0) + 1
        return counts

    def get_listings_by_location(self) -> dict[str, int]:
        """Count listings by location"""
        counts: dict[str, int] = {}
        for listing in self.listings:
            location = listing.location or "Unknown"
            counts[location] = counts.get(location, 0) + 1
        return counts

    def get_salary_stats(self) -> dict:
        """Calculate salary statistics"""
        salaries = []
        for listing in self.listings:
            if listing.salary_min and listing.salary_max:
                salaries.append((listing.salary_min + listing.salary_max) / 2)

        if not salaries:
            return {
                "count": 0,
                "average": None,
                "median": None,
                "min": None,
                "max": None,
            }

        return {
            "count": len(salaries),
            "average": round(statistics.mean(salaries), 2),
            "median": round(statistics.median(salaries), 2),
            "min": min(salaries),
            "max": max(salaries),
        }

    def get_work_type_distribution(self) -> dict[str, int]:
        """Count listings by work type"""
        counts: dict[str, int] = {}
        for listing in self.listings:
            work_type = listing.work_type or "Unknown"
            counts[work_type] = counts.get(work_type, 0) + 1
        return counts

    def generate_markdown_report(self, title: str = "Job Market Research Report") -> str:
        """Generate a markdown report"""
        report = f"# {title}\n\n"
        report += f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        # Summary section
        report += "## Summary\n\n"
        report += f"- **Total Listings:** {self.get_total_count()}\n"

        salary_stats = self.get_salary_stats()
        if salary_stats["count"] > 0:
            report += f"- **Listings with Salary Info:** {salary_stats['count']}\n"
            report += f"- **Average Salary:** €{salary_stats['average']:,.0f}\n"
            report += (
                f"- **Salary Range:** €{salary_stats['min']:,.0f} - €{salary_stats['max']:,.0f}\n"
            )

        report += "\n"

        # Listings by board
        report += "## Listings by Job Board\n\n"
        board_counts = self.get_listings_by_board()
        for board, count in sorted(board_counts.items(), key=lambda x: x[1], reverse=True):
            report += f"- **{board}:** {count} listings\n"

        report += "\n"

        # Listings by location
        report += "## Top Locations\n\n"
        location_counts = self.get_listings_by_location()
        for location, count in sorted(location_counts.items(), key=lambda x: x[1], reverse=True)[
            :10
        ]:
            report += f"- **{location}:** {count} listings\n"

        report += "\n"

        # Work type distribution
        report += "## Work Type Distribution\n\n"
        work_type_counts = self.get_work_type_distribution()
        for work_type, count in sorted(work_type_counts.items(), key=lambda x: x[1], reverse=True):
            report += f"- **{work_type}:** {count} listings\n"

        report += "\n"

        # Detailed listings
        report += "## Job Listings\n\n"
        for i, listing in enumerate(self.listings, 1):
            report += f"### {i}. {listing.title}\n\n"
            report += f"**Company:** {listing.company}\n\n"
            report += f"**Location:** {listing.location}\n\n"

            if listing.salary_min and listing.salary_max:
                report += f"**Salary:** €{listing.salary_min:,} - €{listing.salary_max:,}\n\n"

            if listing.work_type:
                report += f"**Work Type:** {listing.work_type}\n\n"

            report += f"**Job Board:** {listing.job_board}\n\n"

            if listing.job_url:
                report += f"**Link:** [{listing.job_url}]({listing.job_url})\n\n"

        return report

    def generate_csv_report(self) -> str:
        """Generate a CSV report"""
        if not self.listings:
            return ""

        # Header
        lines = [
            "Title,Company,Location,Salary Min,Salary Max,Currency,Work Type,Job Board,URL,Posted Date"
        ]

        for listing in self.listings:
            salary_min = listing.salary_min or ""
            salary_max = listing.salary_max or ""
            url = listing.job_url or ""
            posted_date = listing.posted_date or ""

            line = (
                f'"{listing.title}","{listing.company}","{listing.location}",'
                f"{salary_min},{salary_max},{listing.salary_currency},"
                f'"{listing.work_type}","{listing.job_board}","{url}","{posted_date}"'
            )
            lines.append(line)

        return "\n".join(lines)
