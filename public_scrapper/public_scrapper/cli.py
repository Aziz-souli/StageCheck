# cli.py
import argparse
import json
from spider_manager import SpiderManager
from dotenv import load_dotenv
import os 
load_dotenv()  # Load environment variables from .env file

MONGO_URI = os.getenv("MONGO_URI")
manager = SpiderManager(mongo_uri=MONGO_URI)


def print_json(data):
    print(json.dumps(data, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(description="Job Scraper CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # --- start-all ---
    p_all = sub.add_parser("start-all", help="Run all spiders simultaneously")
    p_all.add_argument("--query", default="", help="Search query")
    # p_all.add_argument("--country", default="FR", help="Country code")
    # p_all.add_argument("--contract", default="internship", help="Contract type")

    # --- start ---
    p_start = sub.add_parser("start", help="Run a specific spider")
    p_start.add_argument("name", choices=["welcometothejungle", "jobteaser", "spider3"])
    p_start.add_argument("--query", default="")
    # p_start.add_argument("--country", default="FR")
    # p_start.add_argument("--contract", default="internship")

    # --- stop ---
    sub.add_parser("stop", help="Stop all running spiders")

    # --- status ---
    p_status = sub.add_parser("status", help="Get spider status")
    p_status.add_argument("--name", default=None, help="Spider name (omit for all)")

    # --- stats ---
    p_stats = sub.add_parser("stats", help="Get job counts from MongoDB")
    p_stats.add_argument("--name", default=None, help="Spider name (omit for all)")

    args = parser.parse_args()

    if args.command == "start-all":
        manager.start_all(args.query)
        print("✅ All spiders started. Waiting for completion...")
        # Block CLI until done
        if manager._thread:
            manager._thread.join()
        print("✅ All spiders finished.")
        print_json(manager.get_stats())

    elif args.command == "start":
        manager.start_spider(args.name, args.query)
        print(f"✅ Spider '{args.name}' started.")

    elif args.command == "stop":
        manager.stop_all()
        print("🛑 Stop signal sent.")

    elif args.command == "status":
        print_json(manager.get_status(args.name))

    elif args.command == "stats":
        print_json(manager.get_stats(args.name))


if __name__ == "__main__":
    main()