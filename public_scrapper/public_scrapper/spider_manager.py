# spider_manager.py
import os
import sys
import certifi


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import multiprocessing
import threading
import socket
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pymongo import MongoClient
# ------------------------------------------------------------------ #
#  Spider Registry                                                     #
# ------------------------------------------------------------------ #

SPIDER_REGISTRY = {
    "welcometothejungle": {
        "module": "spiders.welcometothejungle",
        "cls_name": "WelcomeToTheJungleSpider",
        "db": "jobs_welcometothejungle",
    },
    "jobteaser": {
        "module": "spiders.jobteaser",
        "cls_name": "JobteaserSpider",
        "db": "jobs_jobteaser",
    },
    "stagefr": {
        "module": "spiders.stagefr",
        "cls_name": "StagefrSpider",
        "db": "jobs_stagefr",
    },
}


# ------------------------------------------------------------------ #
#  Status Enum                                                         #
# ------------------------------------------------------------------ #

class SpiderStatus(str, Enum):
    IDLE      = "idle"
    RUNNING   = "running"
    FINISHED  = "finished"
    ERROR     = "error"
    STOPPED   = "stopped"


# ------------------------------------------------------------------ #
#  Process target — runs in a separate process                        #
# ------------------------------------------------------------------ #

def _run_spider_process(module_name: str, cls_name: str, settings_dict: dict, params: dict):
    """
    Runs inside a separate process.
    Each process gets its own Twisted reactor, DNS resolver, SSL context.
    """
    import os
    import sys
    import certifi

    # Fix SSL inside the subprocess
    os.environ['SSL_CERT_FILE'] = certifi.where()
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

    # Fix import paths inside subprocess
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    # Dynamically import the spider class
    import importlib
    module = importlib.import_module(module_name)
    spider_cls = getattr(module, cls_name)

    from scrapy.crawler import CrawlerProcess
    from scrapy.utils.project import get_project_settings

    settings = get_project_settings()
    for key, value in settings_dict.items():
        settings.set(key, value)

    process = CrawlerProcess(settings)
    process.crawl(
        spider_cls,
        query=params.get("query", ""),
        country=params.get("country", "FR"),
        contract_type=params.get("contract_type", "internship"),
    )
    process.start()  # blocks until spider finishes


# ------------------------------------------------------------------ #
#  SpiderManager                                                       #
# ------------------------------------------------------------------ #

class SpiderManager:
    def __init__(self, mongo_uri: str):
        self.mongo_uri = mongo_uri
        self._lock = threading.Lock()

        # Per-spider state
        self._state: Dict[str, Dict[str, Any]] = {
            name: {
                "status": SpiderStatus.IDLE,
                "started_at": None,
                "finished_at": None,
                "error": None,
                "params": {},
                "pid": None,
            }
            for name in SPIDER_REGISTRY
        }

        # Track running processes
        self._processes: Dict[str, multiprocessing.Process] = {}

        # Background watcher thread
        self._watcher: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def start_all(
        self,
        query:         str = "",
        # country:       str = "FR",
        # contract_type: str = "internship",
        search_id:     Optional[str] = None,
        sse_push_url:  Optional[str] = None,
        sse_done_url:  Optional[str] = None,
    ):
        """Start all spiders simultaneously, each in its own process."""
        params = {
            "query":         query,
            # "country":       country,
            # "contract_type": contract_type,
        }

        with self._lock:
            running = [
                name for name, state in self._state.items()
                if state["status"] == SpiderStatus.RUNNING
            ]
            if running:
                raise RuntimeError(f"Spiders already running: {running}")

        self._debug_dns()

        for name, registry in SPIDER_REGISTRY.items():
            settings_dict = {
                "MONGO_URI":         self.mongo_uri,
                "MONGO_DATABASE":    registry["db"],
                "SSE_PUSH_URL":      sse_push_url or "",
                "SEARCH_ID":         search_id or "",
            }
            self._launch_process(name, registry, params, settings_dict)

        # Watch all processes in background
        self._watcher = threading.Thread(
            target=self._watch_all,
            args=(list(SPIDER_REGISTRY.keys()), sse_done_url),
            daemon=True,
        )
        self._watcher.start()

    def start_spider(
        self,
        name:          str,
        query:         str = "",
        # country:       str = "FR",
        # contract_type: str = "internship",
        search_id:     Optional[str] = None,
        sse_push_url:  Optional[str] = None,
        sse_done_url:  Optional[str] = None,
    ):
        """Start a single spider by name."""
        if name not in SPIDER_REGISTRY:
            raise ValueError(
                f"Unknown spider '{name}'. Available: {list(SPIDER_REGISTRY)}"
            )

        with self._lock:
            if self._state[name]["status"] == SpiderStatus.RUNNING:
                raise RuntimeError(f"Spider '{name}' is already running.")

        params = {
            "query":         query,
            # "country":       country,
            # "contract_type": contract_type,
        }

        settings_dict = {
            "MONGO_URI":      self.mongo_uri,
            "MONGO_DATABASE": SPIDER_REGISTRY[name]["db"],
            "SSE_PUSH_URL":   sse_push_url or "",
            "SEARCH_ID":      search_id or "",
        }

        self._debug_dns()
        self._launch_process(name, SPIDER_REGISTRY[name], params, settings_dict)

        # Watch this single spider
        t = threading.Thread(
            target=self._watch_single,
            args=(name, sse_done_url),
            daemon=True,
        )
        t.start()

    def stop_all(self):
        """Send SIGTERM to all running spiders."""
        with self._lock:
            for name, process in self._processes.items():
                if process.is_alive():
                    process.terminate()
                    self._state[name]["status"]      = SpiderStatus.STOPPED
                    self._state[name]["finished_at"] = datetime.utcnow().isoformat()
                    print(f"🛑 Stopped '{name}' (pid {process.pid})")

    def stop_spider(self, name: str):
        """Stop a specific spider by name."""
        if name not in SPIDER_REGISTRY:
            raise ValueError(f"Unknown spider '{name}'")

        with self._lock:
            process = self._processes.get(name)
            if process and process.is_alive():
                process.terminate()
                self._state[name]["status"]      = SpiderStatus.STOPPED
                self._state[name]["finished_at"] = datetime.utcnow().isoformat()
                print(f"🛑 Stopped '{name}' (pid {process.pid})")
            else:
                print(f"⚠️ Spider '{name}' is not running")

    def get_status(self, name: Optional[str] = None) -> Dict:
        """Return status of one or all spiders."""
        with self._lock:
            if name:
                if name not in SPIDER_REGISTRY:
                    raise ValueError(f"Unknown spider '{name}'")
                return {name: dict(self._state[name])}
            return {n: dict(s) for n, s in self._state.items()}

    def get_stats(self, name: Optional[str] = None) -> Dict:
        """Return MongoDB job counts and score distribution per spider."""
        try:
            client = MongoClient(
                self.mongo_uri,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=10000,
            )

            result = {}
            targets = [name] if name else list(SPIDER_REGISTRY)

            for spider_name in targets:
                if spider_name not in SPIDER_REGISTRY:
                    result[spider_name] = {"error": f"Unknown spider '{spider_name}'"}
                    continue

                db_name = SPIDER_REGISTRY[spider_name]["db"]
                try:
                    col    = client[db_name]["job_posts"]
                    total  = col.count_documents({})
                    scored = col.count_documents({"credibility_score": {"$ne": None}})
                    legit  = col.count_documents({"credibility_label": "legit"})
                    suspicious = col.count_documents({"credibility_label": "suspicious"})
                    fake   = col.count_documents({"credibility_label": "fake"})

                    avg_pipeline = [
                        {"$match":  {"credibility_score": {"$ne": None}}},
                        {"$group":  {"_id": None, "avg": {"$avg": "$credibility_score"}}},
                    ]
                    avg_result = list(col.aggregate(avg_pipeline))
                    avg_score  = round(avg_result[0]["avg"], 1) if avg_result else None

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
                except Exception as e:
                    result[spider_name] = {"error": str(e)}

            client.close()
            return result

        except Exception as e:
            return {"error": f"MongoDB connection failed: {e}"}

    def wait_all(self):
        """Block until all spiders finish. Used by CLI."""
        if self._watcher and self._watcher.is_alive():
            self._watcher.join()

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _launch_process(
        self,
        name:          str,
        registry:      dict,
        params:        dict,
        settings_dict: dict,
    ):
        """Create and start a subprocess for one spider."""
        process = multiprocessing.Process(
            target=_run_spider_process,
            args=(
                registry["module"],
                registry["cls_name"],
                settings_dict,
                params,
            ),
            name=f"spider-{name}",
        )
        process.start()

        with self._lock:
            self._processes[name] = process
            self._state[name].update({
                "status":      SpiderStatus.RUNNING,
                "started_at":  datetime.utcnow().isoformat(),
                "finished_at": None,
                "error":       None,
                "params":      params,
                "pid":         process.pid,
            })

        print(
            f"🚀 Started '{name}' "
            f"(pid {process.pid}) → db: {registry['db']}"
        )

    def _watch_all(self, names: List[str], sse_done_url: Optional[str] = None):
        """
        Watch all spider processes.
        When ALL finish → call sse_done_url to close frontend stream.
        """
        remaining = list(names)

        while remaining:
            for name in list(remaining):
                process = self._processes.get(name)
                if process and not process.is_alive():
                    self._update_finished(name, process.exitcode)
                    remaining.remove(name)

            if remaining:
                threading.Event().wait(2)  # poll every 2s

        print("🏁 All spiders finished.")

        # Signal frontend stream is done
        # if sse_done_url:
        #     self._notify_done(sse_done_url)

    def _watch_single(self, name: str, sse_done_url: Optional[str] = None):
        """Watch a single spider process."""
        process = self._processes.get(name)
        if not process:
            return

        process.join()
        self._update_finished(name, process.exitcode)

        print(f"🏁 Spider '{name}' finished.")

        # if sse_done_url:
        #     self._notify_done(sse_done_url)

    def _update_finished(self, name: str, exitcode: int):
        """Update state when a spider process exits."""
        with self._lock:
            if self._state[name]["status"] == SpiderStatus.RUNNING:
                if exitcode == 0:
                    self._state[name]["status"] = SpiderStatus.FINISHED
                    print(f"✅ Spider '{name}' finished successfully")
                else:
                    self._state[name]["status"] = SpiderStatus.ERROR
                    self._state[name]["error"]  = f"Exit code {exitcode}"
                    print(f"❌ Spider '{name}' failed (exit code {exitcode})")
                self._state[name]["finished_at"] = datetime.utcnow().isoformat()

    # def _notify_done(self, sse_done_url: str):
    #     """Notify FastAPI that all spiders finished → closes SSE stream."""
    #     try:
    #         requests.post(sse_done_url, timeout=5)
    #         print(f"📡 Notified SSE done: {sse_done_url}")
    #     except Exception as e:
    #         print(f"⚠️ Failed to notify SSE done: {e}")

    def _debug_dns(self):
        """Quick DNS check before launching spiders."""
        try:
            socket.getaddrinfo("mongodb.com", 443)
            print("✅ DNS resolution working")
        except Exception as e:
            print(f"⚠️ DNS warning: {e}")