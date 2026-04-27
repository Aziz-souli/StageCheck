from typing import Optional
from pymisp import PyMISP
from dotenv import load_dotenv
import os

load_dotenv()
MISP_URL = os.getenv("MISP_URL")
MISP_API_KEY = os.getenv("MISP_API_KEY")

def check_misp(domain: str, ip: Optional[str] = None) -> dict:
    result = {"hits": [], "score": 0, "flags": []}

    if not MISP_URL or not MISP_API_KEY:
        result["flags"].append("MISP not configured")
        result["score"] = 5
        return result

    try:
        misp = PyMISP(MISP_URL, MISP_API_KEY, ssl=False, timeout=10)

        # First, search for existing attributes
        hits = []
        domain_results = misp.search(controller='attributes', value=domain, type='domain', limit=10)
        hits.extend(domain_results.get("Attribute", []))

        if ip:
            ip_results = misp.search(controller='attributes', value=ip, type='ip-dst', limit=10)
            hits.extend(ip_results.get("Attribute", []))

        # If no hits exist, create a test event
        if not hits:
            event = misp.add_event({
                "info": f"TEST: {domain} and {ip} for scoring test",
                "distribution": 0,       # only me
                "threat_level_id": 4,    # undefined
                "analysis": 0            # initial
            })
            event_id = event["Event"]["id"]

            # Add domain attribute
            misp.add_attribute(event_id, {
                "type": "domain",
                "value": domain,
                "category": "Network activity",
                "to_ids": True,
                "comment": "Domain for scoring"
            })

            # Add IP attribute if provided
            if ip:
                misp.add_attribute(event_id, {
                    "type": "ip-dst",
                    "value": ip,
                    "category": "Network activity",
                    "to_ids": True,
                    "comment": "IP for scoring"
                })

            # Search again to populate hits
            domain_results = misp.search(controller='attributes', value=domain, type='domain', limit=10)
            hits.extend(domain_results.get("Attribute", []))
            if ip:
                ip_results = misp.search(controller='attributes', value=ip, type='ip-dst', limit=10)
                hits.extend(ip_results.get("Attribute", []))

        # Normalize results
        result["hits"] = [{"value": h.get("value"), "category": h.get("category"), "comment": h.get("comment")} for h in hits]

        # Scoring logic
        hit_count = len(result["hits"])
        if hit_count >= 3:
            result["score"] = 0
            result["flags"].append(f"MISP: {hit_count} threat intelligence hits for this domain/IP")
        elif hit_count >= 1:
            result["score"] = 1
            result["flags"].append(f"MISP: {hit_count} threat intelligence hit(s)")
        else:
            result["score"] = 5  # clean

    except Exception as e:
        result["flags"].append(f"MISP check failed: {e}")
        result["score"] = 3

    return result

# Example usage
r = check_misp("erstin.com")
print(r)