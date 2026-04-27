# api.py
import os
import sys
import json
import uuid
import certifi
import asyncio
from datetime import datetime
from typing import Optional, AsyncGenerator

import certifi
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pymongo import MongoClient

os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from public_scrapper.spider_manager import SpiderManager
from sse_manager import SSEManager
from dotenv import load_dotenv  
load_dotenv()  # Load environment variables from .env file
MONGO_URI = os.getenv("MONGO_URI")
# ------------------------------------------------------------------ #
#  Config                                                              #
# ------------------------------------------------------------------ #

# MONGO_URI = "mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority"

SPIDER_DBS = {
    "welcometothejungle": "jobs_welcometothejungle",
    "jobteaser":          "jobs_jobteaser",
}

# ------------------------------------------------------------------ #
#  App setup                                                           #
# ------------------------------------------------------------------ #

app = FastAPI(title="Job Scraper API", version="1.0.0")
manager = SpiderManager(mongo_uri=MONGO_URI)
sse_manager = SSEManager()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------ #
#  Models                                                              #
# ------------------------------------------------------------------ #

class SearchParams(BaseModel):
    query: str
    # country: str = "FR"
    # contract_type: str = "internship"


# ------------------------------------------------------------------ #
#  Search — POST /api/search                                           #
# ------------------------------------------------------------------ #

@app.post("/api/search")
async def start_search(params: SearchParams):
    """Start all spiders for a query. Returns search_id for SSE stream."""
    search_id = str(uuid.uuid4())

    # Create SSE queue for this search
    sse_manager.create_stream(search_id)

    sse_push_url = f"http://localhost:8000/internal/push/{search_id}"
    sse_done_url = f"http://localhost:8000/internal/done/{search_id}"

    try:
        print(params)
        # manager.start_spider(
        #     name="welcometothejungle",
        #     query=params.query,
        #     search_id=search_id,
        #     sse_push_url=sse_push_url,
        #     sse_done_url=sse_done_url,
        # )
        manager.start_all(
            query=params.query,
            # country=params.country,
            # contract_type=params.contract_type,
            search_id=search_id,
            sse_push_url=sse_push_url,
            sse_done_url=sse_done_url,
        )
    except RuntimeError as e:
        sse_manager.close_stream(search_id)
        raise HTTPException(status_code=409, detail=str(e))

    return {
        "search_id": search_id,
        "stream_url": f"/api/stream/{search_id}",
        "message": "Search started",
    }


# ------------------------------------------------------------------ #
#  SSE Stream — GET /api/stream/{search_id}                           #
# ------------------------------------------------------------------ #

@app.get("/api/stream/{search_id}")
async def stream_jobs(search_id: str):
    """SSE endpoint — streams scored jobs to frontend in real time."""
    queue = sse_manager.get_queue(search_id)
    if not queue:
        raise HTTPException(status_code=404, detail="Search not found or expired")

    async def event_generator() -> AsyncGenerator[str, None]:
        # Initial connection event
        yield f"data: {json.dumps({'type': 'connected', 'search_id': search_id})}\n\n"

        while True:
            try:
                job = await asyncio.wait_for(queue.get(), timeout=30.0)

                if job.get("__done__"):
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    break

                if job.get("__error__"):
                    yield f"data: {json.dumps({'type': 'error', 'message': job['__error__']})}\n\n"
                    break

                yield f"data: {json.dumps({'type': 'job', 'job': job}, default=str)}\n\n"

            except asyncio.TimeoutError:
                # Keep-alive ping every 30s
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )


# ------------------------------------------------------------------ #
#  Internal — spider pushes jobs here                                  #
# ------------------------------------------------------------------ #

@app.post("/internal/push/{search_id}")
async def internal_push(search_id: str, request: Request):
    """Called by ScoringPipeline to push a scored job to the SSE queue."""
    try:
        job = await request.json()
        sse_manager.push(search_id, job)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/internal/done/{search_id}")
async def internal_done(search_id: str):
    """Called by SpiderManager when all spiders finish."""
    sse_manager.close_stream(search_id)
    return {"ok": True}


# ------------------------------------------------------------------ #
#  Jobs — GET /api/jobs                                                #
# ------------------------------------------------------------------ #

@app.get("/api/jobs")
async def get_jobs(
    query:     Optional[str] = None,
    label:     Optional[str] = None,
    min_score: Optional[int] = None,
    origine:   Optional[str] = None,
    limit:     int = 50,
    skip:      int = 0,
):
    """Query saved jobs from MongoDB across all spider databases."""
    try:
        client = MongoClient(
            MONGO_URI,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=10000,
        )

        results = []
        total = 0

        for spider_name, db_name in SPIDER_DBS.items():
            # Skip if filtering by origine and this isn't it
            if origine and origine.lower() not in spider_name.lower():
                continue

            col = client[db_name]["job_posts"]

            # Build filters
            filters = {}
            if query:
                filters["$or"] = [
                    {"title":        {"$regex": query, "$options": "i"}},
                    {"company_name": {"$regex": query, "$options": "i"}},
                    {"description":  {"$regex": query, "$options": "i"}},
                ]
            if label:
                filters["credibility_label"] = label
            if min_score is not None:
                filters["credibility_score"] = {"$gte": min_score}

            # Count + fetch
            count = col.count_documents(filters)
            total += count

            jobs = list(
                col.find(filters, {"_id": 0})
                   .sort("credibility_score", -1)
                   .skip(skip)
                   .limit(limit)
            )
            results.extend(jobs)

        client.close()

        # Sort combined results by score desc
        results.sort(key=lambda x: x.get("credibility_score") or 0, reverse=True)

        return {
            "jobs":  results[:limit],
            "total": total,
            "skip":  skip,
            "limit": limit,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


# ------------------------------------------------------------------ #
#  Job detail — GET /api/jobs/{job_url:path}                          #
# ------------------------------------------------------------------ #

@app.get("/api/job")
async def get_job(job_url: str):
    """Get a single job by its URL."""
    try:
        client = MongoClient(
            MONGO_URI,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=10000,
        )

        for db_name in SPIDER_DBS.values():
            job = client[db_name]["job_posts"].find_one(
                {"job_url": job_url},
                {"_id": 0},
            )
            if job:
                client.close()
                return job

        client.close()
        raise HTTPException(status_code=404, detail="Job not found")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------ #
#  Stats — GET /api/stats                                              #
# ------------------------------------------------------------------ #

@app.get("/api/stats")
async def get_stats():
    """Job counts and score distribution per database."""
    try:
        client = MongoClient(
            MONGO_URI,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=10000,
        )

        result = {}
        for spider_name, db_name in SPIDER_DBS.items():
            col = client[db_name]["job_posts"]
            total   = col.count_documents({})
            scored  = col.count_documents({"credibility_score": {"$ne": None}})
            legit   = col.count_documents({"credibility_label": "legit"})
            suspicious = col.count_documents({"credibility_label": "suspicious"})
            fake    = col.count_documents({"credibility_label": "fake"})

            # Average score
            pipeline = [
                {"$match": {"credibility_score": {"$ne": None}}},
                {"$group": {"_id": None, "avg": {"$avg": "$credibility_score"}}},
            ]
            avg_result = list(col.aggregate(pipeline))
            avg_score = round(avg_result[0]["avg"], 1) if avg_result else None

            result[spider_name] = {
                "database":   db_name,
                "total":      total,
                "scored":     scored,
                "unscored":   total - scored,
                "legit":      legit,
                "suspicious": suspicious,
                "fake":       fake,
                "avg_score":  avg_score,
            }

        client.close()
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------ #
#  Status — GET /api/status                                            #
# ------------------------------------------------------------------ #

@app.get("/api/status")
async def get_status():
    """Current spider run status."""
    return manager.get_status()


# ------------------------------------------------------------------ #
#  Stop — POST /api/stop                                               #
# ------------------------------------------------------------------ #

@app.post("/api/stop")
async def stop_all():
    """Stop all running spiders."""
    manager.stop_all()
    return {"message": "Stop signal sent to all spiders"}


@app.post("/api/stop/{name}")
async def stop_spider(name: str):
    """Stop a specific spider."""
    try:
        manager.stop_spider(name)
        return {"message": f"Spider '{name}' stopped"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ------------------------------------------------------------------ #
#  Health check                                                        #
# ------------------------------------------------------------------ #

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ------------------------------------------------------------------ #
#  Entry point                                                         #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)