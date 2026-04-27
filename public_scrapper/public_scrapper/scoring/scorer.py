# scoring/scorer.py
from dataclasses import dataclass, field
from typing import Optional
from .s1_osint import score_s1, S1Result
from .s2_occurrence import score_s2, S2Result
from .s3_llm import score_s3, S3Result
from  .s4_cti import score_s4, S4Result
@dataclass
class CredibilityResult:
    # Final
    total_score: int        # 0-100
    label: str              # legit / suspicious / fake
    flags: list[str] = field(default_factory=list)

    # Per module
    s1_score: int = 0
    s1_details: dict = field(default_factory=dict)
    s4_score: int = 0
    s4_details: dict = field(default_factory=dict)
    s3_score: int = 0
    s3_details: dict = field(default_factory=dict)


def get_label(score: int) -> str:
    if score >= 70:
        return "legit"
    elif score >= 40:
        return "suspicious"
    else:
        return "fake"


def score_job(
    job: dict,
    mongo_uri: str,
    db_names: list[str],
    ollama_url: str,
    ollama_model: str = "mistral",
) -> CredibilityResult:
    """
    Run all 3 scoring modules and combine results.
    S1 (OSINT)      : 0-33
    S2 (Occurrence) : 0-33
    S3 (LLM)        : 0-34
    Total           : 0-100
    """

    # Run modules
    s1: S1Result = score_s1(job)
    s3: S3Result = score_s3(job, ollama_url, ollama_model)
    s4: S4Result = score_s4(job)

    total = s1.score + s3.score +  s4.score
    total = max(0, min(100, total))  # clamp to 0-100

    all_flags = s1.flags + s3.flags
    label = get_label(total)

    return CredibilityResult(
        total_score=total,
        label=label,
        flags=all_flags,
        s1_score=s1.score,
        s1_details=s1.details,
        s4_score = s4.score,
        s4_details = s4.details,
        s3_score=s3.score,
        s3_details=s3.details,
    )