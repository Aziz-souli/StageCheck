# scoring/s3_llm.py
import json
import re
import requests
from dataclasses import dataclass, field


@dataclass
class S3Result:
    score: int          # 0-34
    flags: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

DEBUG = False

SYSTEM_PROMPT = """You are an expert at detecting fake, ghost, or low-quality cybersecurity internship postings.

Analyze the internship posting and return ONLY a valid JSON object — no markdown, no explanation.

Focus on the fact that this is a cybersecurity internship. Evaluate these criteria:
1. Description quality: specific cybersecurity mission, clear technical tasks, realistic expectations for an intern.
2. Company credibility: known company or legitimate cybersecurity organization, real sector, consistent and coherent information.
3. Compensation coherence: salary/stipend aligns with cybersecurity role, location, and internship duration.
4. Red flags: exaggerated claims, vague responsibilities, missing contact info, generic copy-paste language, or unrealistic perks for a cybersecurity intern.
5. Overall posting quality: professionalism, technical relevance, and clarity for cybersecurity candidates.

Return exactly this JSON:
{
  "score": <integer 0-50>,
  "verdict": "<legit|suspicious|fake>",
  "confidence": "<high|medium|low>",
  "reasons": ["reason1", "reason2"],
  "red_flags": ["flag1", "flag2"],
  "positive_signals": ["signal1", "signal2"]
}"""


def strip_html(text: str) -> str:
    return re.sub(r'<[^>]+>', ' ', text or '').strip()


def build_prompt(job: dict) -> str:
    return f"""
Title: {job.get('title', 'N/A')}
Company: {job.get('company_name', 'N/A')}
Origin site: {job.get('origine', 'N/A')}
Location: {job.get('location', 'N/A')}
Contract: {job.get('listing_type', 'N/A')} — {job.get('contract_duration', 'N/A')}
Salary: {job.get('salary') or 'Not specified'}
Remote: {job.get('work_from_home_type') or 'Not specified'}
Starting date: {job.get('starting_date') or 'Not specified'}
Apply URL: {job.get('job_url_direct') or 'None'}
Company website: {job.get('company_url_direct') or 'None'}
Company industry: {job.get('company_industry') or 'Unknown'}
Company description: {strip_html(job.get('company_description', ''))[:300]}

Job description:
{strip_html(job.get('description', ''))[:1500]}

Profile required:
{strip_html(job.get('profile', ''))[:500]}
""".strip()


def score_s3(
    job: dict,
    ollama_url: str ,
    model: str = "mistral",
) -> S3Result:
    """Score using a local Ollama model."""
    try:
        prompt = build_prompt(job)

        response = requests.post(
            f"http://ollama:11434/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "format": "json",   # Ollama JSON mode
            },
            timeout=60,
        )
        response.raise_for_status()

        raw = response.json()
        content = raw["message"]["content"]

        # Clean and parse JSON
        content = re.sub(r'```json|```', '', content).strip()
        result = json.loads(content)

        score = max(0, min(50, int(result.get("score", 0))))
        verdict = result.get("verdict", "suspicious")
        flags = result.get("red_flags", [])
        positive = result.get("positive_signals", [])
        reasons = result.get("reasons", [])
        if DEBUG:
            with open("s3_debug.txt", "a") as f:
                f.write(f"Job: {job['title']} @ {job['company_name']}\n")
                f.write(f"Prompt:\n{prompt}\n")
                f.write(f"LLM Response:\n{content}\n")
                f.write("-"*40 + "\n")

        return S3Result(
            score=score,
            flags=flags,
            details={
                "verdict": verdict,
                "confidence": result.get("confidence", "low"),
                "reasons": reasons,
                "red_flags": flags,
                "positive_signals": positive,
                "model": model,
            },
        )

    except json.JSONDecodeError as e:
        return S3Result(
            score=10,   # neutral score on parse failure
            flags=[f"LLM response parse failed: {e}"],
            details={"error": "json_parse_failed"},
        )
    except Exception as e:
        return S3Result(
            score=0,
            flags=[f"LLM scoring failed: {e}"],
            details={"error": str(e)},
        )