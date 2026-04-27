# pipelines.py
import dataclasses
from pymongo import MongoClient, UpdateOne
from datetime import datetime
from itemadapter import ItemAdapter
import certifi

class PublicScrapperPipeline:
    def process_item(self, item, spider):
        return item


class MongoDBPipeline:
    def __init__(self, mongo_uri, mongo_db):
        self.mongo_uri = mongo_uri
        self.mongo_db = mongo_db
        self.buffer = []
        self.buffer_size = 50

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            mongo_uri=crawler.settings.get("MONGO_URI"),
            mongo_db=crawler.settings.get("MONGO_DATABASE", "jobs_db"),
        )

    def open_spider(self, spider):
        try:
            self.client = MongoClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=30000,
                connectTimeoutMS=30000,
                socketTimeoutMS=30000,
                # 
                # tlsCAFile=certifi.where(),
                # tlsAllowInvalidCertificates=True,   # ← diagnosis only
                retryWrites=True,
                w="majority",
            )
            self.client.admin.command("ping")
            spider.logger.info("✅ MongoDB connected successfully")
            self.db = self.client[self.mongo_db]
            self.collection = self.db["job_posts"]
            self.collection.create_index("job_url", unique=True)
        except Exception as e:
            spider.logger.error(f"❌ MongoDB connection failed: {e}")
            raise

    def _to_dict(self, item) -> dict:
        """Safely convert any item type to dict."""
        # dataclass (your JobPost model)
        if dataclasses.is_dataclass(item):
            doc = dataclasses.asdict(item)
        # Scrapy Item or dict-like
        else:
            doc = ItemAdapter(item).asdict()

        # Serialize non-JSON-safe types
        for key, value in doc.items():
            if hasattr(value, 'isoformat'):  # date / datetime
                doc[key] = value.isoformat()
            elif hasattr(value, '__dict__') and not isinstance(value, dict):
                doc[key] = str(value)  # nested objects like Location, Compensation

        return doc

    def process_item(self, item, spider):
        try:
            doc = self._to_dict(item)
            spider.logger.info(
                f"💾 About to save → "
                f"score: {doc.get('score')} "
                f"label: {doc.get('label')}"
        )
            spider.logger.info(f"🔵 Pipeline received: {doc.get('job_url', 'NO URL')}")

            if not doc.get("job_url"):
                spider.logger.warning(f"⚠️ Missing job_url, skipping. Keys found: {list(doc.keys())}")
                return item

            doc["scraped_at"] = datetime.utcnow()
            doc["score"] = None
            doc["label"] = None

            self.buffer.append(doc)

            if len(self.buffer) >= self.buffer_size:
                self._flush(spider)

        except Exception as e:
            spider.logger.error(f"❌ Pipeline error: {e}", exc_info=True)

        return item

    def _flush(self, spider):
        if not self.buffer:
            return
        batch = self.buffer.copy()
        self.buffer.clear()
        try:
            ops = []
            for doc in batch:
                # Split null and non-null fields
                set_fields = {k: v for k, v in doc.items() if v is not None}
                null_fields = {k: v for k, v in doc.items() if v is None}

                update = {}

                if set_fields:
                    update["$set"] = set_fields

                # $setOnInsert only applies when document is NEW (upsert insert)
                # so existing docs keep their current values for null fields
                if null_fields:
                    update["$setOnInsert"] = null_fields

                ops.append(
                    UpdateOne(
                        {"job_url": doc["job_url"]},
                        update,
                        upsert=True,
                    )
                )

            result = self.collection.bulk_write(ops, ordered=False)
            spider.logger.info(
                f"✅ Flushed {len(batch)} → "
                f"inserted: {result.upserted_count}, "
                f"updated: {result.modified_count}"
            )
        except Exception as e:
            spider.logger.error(f"❌ Flush error: {e}", exc_info=True)

    def close_spider(self, spider):
        self._flush(spider)  # flush remaining items before closing
        self.client.close()
        spider.logger.info("🔒 MongoDB connection closed")


#######  Scoring Pipeline that calls the S3 LLM scorer and attaches results to items before saving to MongoDB. #######
# # In pipelines.py

import os
import re
import sys
import certifi
import dataclasses
import requests as http_requests
from datetime import datetime
from itemadapter import ItemAdapter

os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class ScoringPipeline:
    def __init__(self, mongo_uri, db_names, ollama_url, ollama_model, sse_push_url):
        self.mongo_uri    = mongo_uri
        self.db_names     = db_names
        self.ollama_url   = ollama_url
        self.ollama_model = ollama_model
        self.sse_push_url = sse_push_url
        self.score_job    = None   # loaded in open_spider

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            mongo_uri=crawler.settings.get("MONGO_URI"),
            db_names=crawler.settings.get("SCORING_DB_NAMES", []),
            ollama_url=crawler.settings.get("OLLAMA_URL", "http://localhost:11434"),
            ollama_model=crawler.settings.get("OLLAMA_MODEL", "mistral"),
            sse_push_url=crawler.settings.get("SSE_PUSH_URL", ""),
        )

    def open_spider(self, spider):
        try:
            from .scoring.scorer import score_job
            self.score_job = score_job
            spider.logger.info("✅ Scoring module loaded")
        except ImportError as e:
            spider.logger.error(f"❌ Failed to import scoring module: {e}")
            self.score_job = None

    def _to_dict(self, item) -> dict:
        if dataclasses.is_dataclass(item):
            return dataclasses.asdict(item)
        return ItemAdapter(item).asdict()

    def _build_sse_payload(self, job: dict) -> dict:
        """Only send what the frontend needs — strip heavy HTML."""
        def strip_html(text: str) -> str:
            return re.sub(r'<[^>]+>', ' ', text or '').strip()

        return {
            "title":             job.get("title"),
            "company_name":      job.get("company_name"),
            "company_logo":      job.get("company_logo"),
            "company_url":       job.get("company_url_direct"),
            "job_url":           job.get("job_url"),
            "location":          job.get("location"),
            "salary":            job.get("salary"),
            "contract_type":     job.get("listing_type"),
            "remote_type":       job.get("work_from_home_type"),
            "date_posted":       job.get("date_posted"),
            "origine":           job.get("origine"),
            # Truncated description — no raw HTML to frontend
            "description":       strip_html(job.get("description", ""))[:500],
            # Scores
            "score":             job.get("score"),
            "label":             job.get("label"),
            "credibility_flags": job.get("credibility_flags"),
            "s1_score":          job.get("s1_score"),
            "s4_score":          job.get("s4_score"),
            "s3_score":          job.get("s3_score"),
            "s1_details":        job.get("s1_details"),
            "s4_details":        job.get("s4_details"),
            "s3_details":        job.get("s3_details"),
            "scored_at":         job.get("scored_at"),
        }

    def _push_to_sse(self, job: dict, spider):
        """Push scored job to FastAPI SSE endpoint."""
        if not self.sse_push_url:
            return
        try:
            payload = self._build_sse_payload(job)
            http_requests.post(
                self.sse_push_url,
                json=payload,
                timeout=5,
            )
            spider.logger.info(
                f"📡 Pushed to SSE: {job.get('title')} "
                f"[{job.get('score')}/100]"
            )
        except Exception as e:
            spider.logger.warning(f"⚠️ SSE push failed: {e}")

    def process_item(self, item, spider):
        DEBUG = True
        try:
            # Scoring disabled — skip but still pass item to MongoDBPipeline
            if self.score_job is None:
                spider.logger.warning("⚠️ Scoring disabled — saving without score")
                return item

            doc = self._to_dict(item)

            spider.logger.info(
                f"🔍 Scoring: {doc.get('title')} @ {doc.get('company_name')}"
            )
            if DEBUG:
                with open("scoring_debug.txt", "a") as f:
                   f.write(str(doc))                   
                   f.write("\n" + "="*50 + "\n")
            result = self.score_job(
                job=doc,
                mongo_uri=self.mongo_uri,
                db_names=self.db_names,
                ollama_url=self.ollama_url,
                ollama_model=self.ollama_model,
            )

            spider.logger.info(
                f"📊 Score: {result.total_score}/100 ({result.label}) "
                f"S1:{result.s1_score} S4:{result.s4_score} S3:{result.s3_score}"
            )

            # Attach scores to item
            item["score"] = result.total_score
            item["label"] = result.label
            item["credibility_flags"] = result.flags
            item["s1_score"]          = result.s1_score
            item["s1_details"]        = result.s1_details
            item["s4_score"]          = result.s4_score
            item["s4_details"]        = result.s4_details
            item["s3_score"]          = result.s3_score
            item["s3_details"]        = result.s3_details
            item["scored_at"]         = datetime.utcnow().isoformat()

            # Push to SSE → frontend sees it immediately
            self._push_to_sse(dict(item), spider)

        except Exception as e:
            spider.logger.error(f"❌ Scoring error: {e}", exc_info=True)
            # Neutral fallback — item still flows to MongoDBPipeline
            item["score"] = None
            item["label"] = "unscored"
            item["credibility_flags"] = [f"Scoring failed: {str(e)}"]
            item["s1_score"]          = None
            item["s1_details"]        = {}
            item["s4_score"]          = None
            item["s4_details"]        = {}
            item["s3_score"]          = None
            item["s3_details"]        = {}
            item["scored_at"]         = None

        return item  # ← always, no matter what