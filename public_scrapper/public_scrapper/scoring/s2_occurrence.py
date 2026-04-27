# scoring/s2_occurrence.py
from dataclasses import dataclass, field
from typing import Any
from pymongo import MongoClient
import certifi
import re

@dataclass
class S2Result:
    score: int          # 0-33
    flags: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


def normalize(text: str) -> str:
    """Lowercase, remove punctuation and extra spaces."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text


def score_s2(job: dict, mongo_uri: str, db_names: list[str]) -> S2Result:
    """
    Check how many times the same internship appears
    across all scraped databases (cross-site duplicates).
    More occurrences on different sites = more legit.
    Zero occurrences on other sites = suspicious.
    """
    flags = []
    details = {}

    title = normalize(job.get("title", ""))
    company = normalize(job.get("company_name", ""))
    current_origin = job.get("origine", "")

    if not title or not company:
        return S2Result(
            score=0,
            flags=["Missing title or company name for occurrence check"],
            details={},
        )

    try:
        client = MongoClient(mongo_uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=10000)
        sites_found = []
        total_occurrences = 0

        for db_name in db_names:
            try:
                collection = client[db_name]["job_posts"]

                # Fuzzy match using regex on normalized fields
                count = collection.count_documents({
                    "title": {"$regex": re.escape(title[:30]), "$options": "i"},
                    "company_name": {"$regex": re.escape(company[:30]), "$options": "i"},
                })

                if count > 0:
                    # Find which origins posted it
                    origins = collection.distinct(
                        "origine",
                        {
                            "title": {"$regex": re.escape(title[:30]), "$options": "i"},
                            "company_name": {"$regex": re.escape(company[:30]), "$options": "i"},
                        }
                    )
                    sites_found.extend(origins)
                    total_occurrences += count

            except Exception as e:
                flags.append(f"DB check failed for {db_name}: {e}")

        client.close()

        # Remove current site from found sites
        other_sites = list(set(s for s in sites_found if s != current_origin))
        cross_site_count = len(other_sites)

        details = {
            "title_searched": title[:30],
            "company_searched": company[:30],
            "total_occurrences": total_occurrences,
            "found_on_sites": list(set(sites_found)),
            "cross_site_count": cross_site_count,
        }

        # Scoring logic:
        # Found on 3+ other sites → very legit → 33
        # Found on 2 other sites  → likely legit → 25
        # Found on 1 other site   → possible → 15
        # Only on current site    → suspicious → 5
        # Nowhere else at all     → very suspicious → 0
        if cross_site_count >= 3:
            score = 33
        elif cross_site_count == 2:
            score = 25
            flags.append(f"Found on {cross_site_count} other sites")
        elif cross_site_count == 1:
            score = 15
            flags.append(f"Only found on 1 other site")
        elif total_occurrences > 1:
            score = 5
            flags.append("Only duplicated within same site — not cross-validated")
        else:
            score = 0
            flags.append("Internship not found on any other scraped site")

        return S2Result(score=score, flags=flags, details=details)

    except Exception as e:
        return S2Result(
            score=0,
            flags=[f"S2 occurrence check failed: {e}"],
            details={"error": str(e)},
        )