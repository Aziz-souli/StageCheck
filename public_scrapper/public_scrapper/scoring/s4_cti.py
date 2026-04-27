# scoring/s4_cti.py
import os
import socket
import requests
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse
import re
from typing import Optional
from pymisp import PyMISP

@dataclass
class S4Result:
    score: int                          # 0-25
    flags: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


# ------------------------------------------------------------------ #
#  API Keys — set in environment variables                            #
# ------------------------------------------------------------------ #

VT_API_KEY       = os.getenv("VIRUSTOTAL_API_KEY", "")
ABUSEIPDB_KEY    = os.getenv("ABUSEIPDB_API_KEY", "")
SHODAN_KEY       = os.getenv("SHODAN_API_KEY", "")
MISP_URL         = os.getenv("MISP_URL", "")
MISP_API_KEY     = os.getenv("MISP_API_KEY", "")


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def extract_domain(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        return re.sub(r'^www\.', '', domain).strip()
    except Exception:
        return None


def resolve_ip(domain: str) -> Optional[str]:
    try:
        return socket.gethostbyname(domain)
    except Exception:
        return None


# ------------------------------------------------------------------ #
#  VirusTotal — domain reputation                                     #
# ------------------------------------------------------------------ #

def check_virustotal(domain: str) -> dict:
    result = {
        "malicious":  0,
        "suspicious": 0,
        "harmless":   0,
        "score":      0,
        "flags":      [],
    }

    if not VT_API_KEY:
        result["flags"].append("VirusTotal API key not set")
        return result

    try:
        url = f"https://www.virustotal.com/api/v3/domains/{domain}"
        resp = requests.get(
            url,
            headers={"x-apikey": VT_API_KEY},
            timeout=10,
        )

        if resp.status_code == 404:
            result["flags"].append("Domain not found in VirusTotal")
            result["score"] = 3   # neutral — unknown domain
            return result

        resp.raise_for_status()
        data = resp.json()

        stats = (
            data.get("data", {})
                .get("attributes", {})
                .get("last_analysis_stats", {})
        )

        malicious  = stats.get("malicious", 0)
        suspicious = stats.get("suspicious", 0)
        harmless   = stats.get("harmless", 0)

        result["malicious"]  = malicious
        result["suspicious"] = suspicious
        result["harmless"]   = harmless

        if malicious >= 5:
            result["score"] = 0
            result["flags"].append(
                f"VirusTotal: {malicious} engines flagged as MALICIOUS"
            )
        elif malicious >= 1 or suspicious >= 3:
            result["score"] = 1
            result["flags"].append(
                f"VirusTotal: {malicious} malicious, {suspicious} suspicious detections"
            )
        elif suspicious >= 1:
            result["score"] = 2
            result["flags"].append(
                f"VirusTotal: {suspicious} suspicious detections"
            )
        else:
            result["score"] = 5   # clean

    except Exception as e:
        result["flags"].append(f"VirusTotal check failed: {e}")
        result["score"] = 3   # neutral on error

    return result


# ------------------------------------------------------------------ #
#  AbuseIPDB — malicious IP check                                     #
# ------------------------------------------------------------------ #

def check_abuseipdb(ip: str) -> dict:
    result = {
        "abuse_score":    0,
        "total_reports":  0,
        "country":        None,
        "score":          0,
        "flags":          [],
    }

    if not ABUSEIPDB_KEY:
        result["flags"].append("AbuseIPDB API key not set")
        return result

    if not ip:
        result["flags"].append("No IP to check")
        return result

    try:
        resp = requests.get(
            "https://api.abuseipdb.com/api/v2/check",
            headers={
                "Key":    ABUSEIPDB_KEY,
                "Accept": "application/json",
            },
            params={
                "ipAddress":    ip,
                "maxAgeInDays": 90,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})

        abuse_score   = data.get("abuseConfidenceScore", 0)
        total_reports = data.get("totalReports", 0)
        country       = data.get("countryCode", "")

        result["abuse_score"]   = abuse_score
        result["total_reports"] = total_reports
        result["country"]       = country

        if abuse_score >= 80:
            result["score"] = 0
            result["flags"].append(
                f"AbuseIPDB: IP confidence score {abuse_score}% "
                f"({total_reports} reports)"
            )
        elif abuse_score >= 40:
            result["score"] = 2
            result["flags"].append(
                f"AbuseIPDB: IP suspicious score {abuse_score}%"
            )
        elif abuse_score >= 10:
            result["score"] = 3
            result["flags"].append(
                f"AbuseIPDB: IP low abuse score {abuse_score}%"
            )
        else:
            result["score"] = 5   # clean

    except Exception as e:
        result["flags"].append(f"AbuseIPDB check failed: {e}")
        result["score"] = 3

    return result


# ------------------------------------------------------------------ #
#  Shodan — exposed infrastructure                                    #
# ------------------------------------------------------------------ #

def check_shodan(ip: str) -> dict:
    result = {
        "open_ports":     [],
        "vulns":          [],
        "org":            None,
        "score":          0,
        "flags":          [],
    }

    if not SHODAN_KEY:
        result["flags"].append("Shodan API key not set")
        return result

    if not ip:
        result["flags"].append("No IP to check on Shodan")
        return result

    try:
        resp = requests.get(
            f"https://api.shodan.io/shodan/host/{ip}",
            params={"key": SHODAN_KEY},
            timeout=10,
        )

        if resp.status_code == 404:
            result["score"] = 4   # not indexed — neutral
            return result

        resp.raise_for_status()
        data = resp.json()

        open_ports = data.get("ports", [])
        vulns      = list(data.get("vulns", {}).keys())
        org        = data.get("org", "")

        result["open_ports"] = open_ports
        result["vulns"]      = vulns
        result["org"]        = org

        # Critical ports open (suspicious for a legit company)
        suspicious_ports = set(open_ports) & {
            23,     # telnet
            445,    # SMB
            3389,   # RDP
            5900,   # VNC
            6379,   # Redis exposed
            27017,  # MongoDB exposed
        }

        if vulns:
            result["score"] = 1
            result["flags"].append(
                f"Shodan: {len(vulns)} CVEs found: {', '.join(vulns[:3])}"
            )
        elif suspicious_ports:
            result["score"] = 2
            result["flags"].append(
                f"Shodan: Suspicious ports exposed: {suspicious_ports}"
            )
        elif len(open_ports) > 10:
            result["score"] = 3
            result["flags"].append(
                f"Shodan: {len(open_ports)} open ports (high exposure)"
            )
        else:
            result["score"] = 5   # normal exposure

    except Exception as e:
        result["flags"].append(f"Shodan check failed: {e}")
        result["score"] = 3

    return result


# ------------------------------------------------------------------ #
#  MISP — threat intelligence platform                                #
# ------------------------------------------------------------------ #



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


# ------------------------------------------------------------------ #
#  Main S4 scorer                                                      #
# ------------------------------------------------------------------ #

def score_s4(job: dict) -> S4Result:
    DEBUG = False
    """
    CTI scoring — 0 to 25 points.

    Weights:
    VirusTotal  : 0-5
    AbuseIPDB   : 0-5
    HIBP        : 0-5
    Shodan      : 0-5
    MISP        : 0-5
    Total       : 0-25
    """
    flags   = []
    details = {}

    # Extract domain and IP
    raw_url = job.get("company_url_direct") or job.get("company_url") or ""
    domain  = extract_domain(raw_url)
    if DEBUG:
        with open("s4_debug.txt", "a") as f:
            f.write(f"{job}")
            f.write(f"Extracted domain: {domain}\n")
            f.write("-"*40 + "\n")
    if not domain:
        return S4Result(
            score=12,   # neutral — no domain to check
            flags=["No company domain available for CTI check"],
            details={"error": "no_domain"},
        )

    ip = resolve_ip(domain)

    # Run all CTI checks
    vt_result      = check_virustotal(domain)
    abuse_result   = check_abuseipdb(ip) if ip else {"score": 3, "flags": ["No IP resolved"]}
    shodan_result  = check_shodan(ip) if ip else {"score": 3, "flags": ["No IP resolved"]}
    misp_result    = check_misp(domain, ip)

    # Aggregate scores
    total = (
        vt_result["score"]     +
        abuse_result["score"]  +
        shodan_result["score"] +
        misp_result["score"]
    )

    # Cap at 25
    total = min(total, 25)

    # Aggregate flags
    flags = (
        vt_result["flags"]     +
        abuse_result["flags"]  +
        shodan_result["flags"] +
        misp_result["flags"]
    )

    details = {
        "domain":     domain,
        "ip":         ip,
        "virustotal": vt_result,
        "abuseipdb":  abuse_result,
        "shodan":     shodan_result,
        "misp":       misp_result,
    }

    return S4Result(score=total, flags=flags, details=details)