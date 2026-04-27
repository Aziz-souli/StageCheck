# scoring/batch_scorer.py
import os
import sys
import time
import certifi
import argparse
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv()
mongo_uri = os.getenv("MONGO_URI")
ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scoring.scorer import score_job

# All databases to score + use for cross-site S2 check
SPIDER_DBS = {
    "welcometothejungle": "jobs_welcometothejungle",
    "jobteaser":          "jobs_jobteaser",
    "stagefr":          "jobs_stagefr",
}

ALL_DB_NAMES = list(SPIDER_DBS.values())


def run_batch(
    mongo_uri: str = mongo_uri,
    target_db: str = None,          # None = score all DBs
    ollama_url: str = ollama_url,
    ollama_model: str = "mistral",
    limit: int = None,
    dry_run: bool = False,
):
    client = MongoClient(
        mongo_uri,
        tlsCAFile=certifi.where(),
        serverSelectionTimeoutMS=10000,
    )

    dbs_to_score = {target_db: target_db} if target_db else SPIDER_DBS

    for spider_name, db_name in dbs_to_score.items():
        db = client[db_name]
        collection = db["job_posts"]

        query = {"credibility_score": None}
        total = collection.count_documents(query)
        cursor = collection.find(query).limit(limit) if limit else collection.find(query)

        print(f"\n{'='*60}")
        print(f"Scoring '{spider_name}' → {db_name} ({total} unscored jobs)")
        print(f"{'='*60}")

        for i, job in enumerate(cursor):
            try:
                print(f"[{i+1}/{total}] {job.get('title')} @ {job.get('company_name')}")

                result = score_job(
                    job=job,
                    mongo_uri=mongo_uri,
                    db_names=ALL_DB_NAMES,
                    ollama_url=ollama_url,
                    ollama_model=ollama_model,
                )

                print(
                    f"  → Score: {result.total_score}/100 "
                    f"| Label: {result.label} "
                    f"| S1:{result.s1_score} S2:{result.s2_score} S3:{result.s3_score}"
                )
                if result.flags:
                    print(f"  → Flags: {result.flags[:3]}")

                if not dry_run:
                    newcollection = client[db_name]["jobs_credibility"]
                    # newcollection.create_index("_id", unique=True)
                    newcollection.insert_one(
                            {
                            "title": job["title"],
                            "company_name": job["company_name"],
                            "job_url": job["job_url"],
                            "credibility_score":  result.total_score,
                            "credibility_label":  result.label,
                            "credibility_flags":  result.flags,
                            "s1_score":           result.s1_score,
                            "s1_details":         result.s1_details,
                            "s2_score":           result.s2_score,
                            "s2_details":         result.s2_details,
                            "s3_score":           result.s3_score,
                            "s3_details":         result.s3_details,
                            "scored_at":          datetime.utcnow(),
                            }                          
                    )
                    # collection.update_one(
               
                    # )

                time.sleep(0.5)  # be polite to Ollama

            except Exception as e:
                print(f"  ❌ Error scoring job {job.get('_id')}: {e}")

    client.close()
    print("\n✅ Batch scoring complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch job scorer")
    parser.add_argument("--mongo-uri",     required=False, default=mongo_uri, help="MongoDB connection URI")
    parser.add_argument("--db",            default=None,    help="Score specific DB only")
    parser.add_argument("--ollama-url",    default="http://localhost:11434" )
    parser.add_argument("--model",         default="mistral")
    parser.add_argument("--limit",         type=int, default=None)
    parser.add_argument("--dry-run",       action="store_true")
    args = parser.parse_args()

    run_batch(
        mongo_uri=args.mongo_uri,
        target_db=args.db,
        ollama_url=args.ollama_url,
        ollama_model=args.model,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    