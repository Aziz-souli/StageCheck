# api.py
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from spider_manager import SpiderManager

MONGO_URI = "mongodb+srv://user:pass@cluster.mongodb.net/"
manager = SpiderManager(mongo_uri=MONGO_URI)
app = FastAPI(title="Job Scraper API", version="1.0.0")


class RunParams(BaseModel):
    query: str = ""
    country: str = "FR"
    contract_type: str = "internship"


# --- Start all spiders ---
@app.post("/spiders/api/search")
def start_all(params: RunParams):
    try:
        manager.start_all(
            query=params.query,
            # country=params.country,
            # contract_type=params.contract_type,
        )
        return {"message": "All spiders started", "params": params}
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


# --- Start a specific spider ---
@app.post("/spiders/{name}/start")
def start_spider(name: str, params: RunParams):
    try:
        manager.start_spider(
            name=name,
            query=params.query,
            country=params.country,
            contract_type=params.contract_type,
        )
        return {"message": f"Spider '{name}' started", "params": params}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


# --- Stop all spiders ---
@app.post("/spiders/stop")
def stop_all():
    manager.stop_all()
    return {"message": "Stop signal sent to all spiders"}


# --- Get status ---
@app.get("/spiders/status")
def get_all_status():
    return manager.get_status()


@app.get("/spiders/{name}/status")
def get_spider_status(name: str):
    try:
        return manager.get_status(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# --- Get stats ---
@app.get("/spiders/stats")
def get_all_stats():
    return manager.get_stats()


@app.get("/spiders/{name}/stats")
def get_spider_stats(name: str):
    try:
        return manager.get_stats(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))