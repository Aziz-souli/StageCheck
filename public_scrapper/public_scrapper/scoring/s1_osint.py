# scoring/s1_osint.py
import ssl
import socket
import re
import dns.resolver
import whois
import requests
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse
DEBUG = False

@dataclass
class S1Result:
    score: int          # 0-25
    flags: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


def extract_domain(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        # Remove www.
        domain = re.sub(r'^www\.', '', domain)
        return domain.strip()
    except Exception:
        return None


def check_whois(domain: str) -> dict:
    result = {"age_days": None, "registrar": None, "country": None, "score": 0, "flags": []}
    
    try:
        w = whois.whois(domain)
        
        if DEBUG:
            with open("domain_info.txt", "a") as f:
                f.write(f"{w}\n")
        
        # Extract registrar and country
        result["registrar"] = str(w.registrar or "")
        result["country"] = str(w.country or "")
        
        if isinstance(result["registrar"], list):
            result["registrar"] = result["registrar"][0]
        if isinstance(result["country"], list):
            result["country"] = result["country"][0]

        # Extract creation date
        creation = w.creation_date
        if isinstance(creation, list):
            creation = creation[0]
        if creation:
            if creation.tzinfo:
                creation = creation.replace(tzinfo=None)  # make naive for subtraction
            age = (datetime.utcnow() - creation).days
            result["age_days"] = age

            # Scoring logic
            if age > 365 * 3:       # > 3 years old → very legit
                result["score"] = 7.5
            elif age > 365:         # > 1 year
                result["score"] = 6
            elif age > 180:         # > 6 months
                result["score"] = 3
            elif age > 30:          # > 1 month
                result["score"] = 1.66
            else:
                result["score"] = 0
                result["flags"].append(f"Domain very recent ({age} days old)")
                
    except Exception as e:
        result["flags"].append(f"WHOIS lookup failed: {e}")

    return result


def check_dns(domain: str) -> dict:
    result = {"has_mx": False, "has_spf": False, "has_dkim": False, "score": 0, "flags": []}
    try:
        # MX records
        try:
            mx = dns.resolver.resolve(domain, 'MX')
            result["has_mx"] = len(mx) > 0
        except Exception:
            result["flags"].append("No MX records (no email infrastructure)")

        # SPF (TXT records)
        try:
            txt = dns.resolver.resolve(domain, 'TXT')
            for r in txt:
                if 'spf1' in str(r).lower():
                    result["has_spf"] = True
                    break
        except Exception:
            pass

        # DKIM (common selector)
        try:
            dns.resolver.resolve(f"google._domainkey.{domain}", 'TXT')
            result["has_dkim"] = True
        except Exception:
            pass

        # Score
        score = 0
        if result["has_mx"]:
            score += 3.33
        else:
            result["flags"].append("No MX records")
        if result["has_spf"]:
            score += 2.5
        else:
            result["flags"].append("No SPF record")
        if result["has_dkim"]:
            score += 2.5
        result["score"] = score

    except Exception as e:
        result["flags"].append(f"DNS check failed: {e}")
    return result


def check_ssl(domain: str) -> dict:
    result = {"valid": False, "issuer": None, "expires_in_days": None, "score": 0, "flags": []}
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=domain) as s:
            s.settimeout(5)
            s.connect((domain, 443))
            cert = s.getpeercert()
            result["valid"] = True

            # Expiry
            expires = datetime.strptime(cert['notAfter'], "%b %d %H:%M:%S %Y %Z")
            days_left = (expires - datetime.utcnow()).days
            result["expires_in_days"] = days_left

            # Issuer
            issuer = dict(x[0] for x in cert.get('issuer', []))
            result["issuer"] = issuer.get('organizationName', '')

            if days_left > 30:
                result["score"] = 4
            else:
                result["score"] = 1.67
                result["flags"].append(f"SSL expires in {days_left} days")

    except ssl.SSLError as e:
        result["flags"].append(f"Invalid SSL certificate: {e}")
    except Exception as e:
        result["flags"].append(f"SSL check failed: {e}")
    return result


def check_blacklist(domain: str) -> dict:
    result = {"blacklisted": False, "score": 5, "flags": []}
    # Common DNS blacklists
    blacklists = [
        "zen.spamhaus.org",
        "bl.spamcop.net",
        "dnsbl.sorbs.net",
    ]
    try:
        # Reverse the IP for DNSBL lookup
        ip = socket.gethostbyname(domain)
        reversed_ip = ".".join(reversed(ip.split(".")))
        for bl in blacklists:
            try:
                dns.resolver.resolve(f"{reversed_ip}.{bl}", 'A')
                result["blacklisted"] = True
                result["score"] = 0
                result["flags"].append(f"Domain blacklisted on {bl}")
                break
            except dns.resolver.NXDOMAIN:
                pass  # not blacklisted on this one
    except Exception as e:
        result["flags"].append(f"Blacklist check failed: {e}")
    return result


def check_web_presence(company_name: str, domain: str) -> dict:
    result = {"reachable": False, "score": 0, "flags": []}
    try:
        url = f"https://{domain}"
        resp = requests.get(url, timeout=8, allow_redirects=True)
        if resp.status_code < 400:
            result["reachable"] = True
            result["score"] = 6.67
        else:
            result["flags"].append(f"Website returned {resp.status_code}")
            result["score"] = 1.67
    except requests.exceptions.SSLError:
        result["flags"].append("SSL error on company website")
        result["score"] = 0.83
    except Exception:
        result["flags"].append("Company website unreachable")
        result["score"] = 0
    return result


def score_s1(job: dict) -> S1Result:
    flags = []
    details = {}
    total = 0

    # Extract domain from company_url_direct or company_url
    raw_url = job.get("company_url_direct") or job.get("company_url") or ""
    domain = extract_domain(raw_url)

    if not domain:
        return S1Result(
            score=0,
            flags=["No company URL available for OSINT"],
            details={"error": "no domain"},
        )

    company_name = job.get("company_name", "")

    # Run all checks
    whois_result = check_whois(domain)
    dns_result = check_dns(domain)
    ssl_result = check_ssl(domain)
    blacklist_result = check_blacklist(domain)
    web_result = check_web_presence(company_name, domain)
    if DEBUG:
        with open("s1_debug.txt", "a") as f:
            f.write(f"Job: {job['title']} @ {company_name}\n")
            f.write(f"Domain: {domain}\n")
            f.write(f"WHOIS: {whois_result}\n")
            f.write(f"DNS: {dns_result}\n")
            f.write(f"SSL: {ssl_result}\n")
            f.write(f"Blacklist: {blacklist_result}\n")
            f.write(f"Web Presence: {web_result}\n")
            f.write("-"*40 + "\n")
    # Aggregate
    total = (
        whois_result["score"] +
        dns_result["score"] +
        ssl_result["score"] +
        blacklist_result["score"] +
        web_result["score"]
    )

    # Cap at 25
    total = min(total, 25)

    flags = (
        whois_result["flags"] +
        dns_result["flags"] +
        ssl_result["flags"] +
        blacklist_result["flags"] +
        web_result["flags"]
    )

    details = {
        "domain": domain,
        "whois": whois_result,
        "dns": dns_result,
        "ssl": ssl_result,
        "blacklist": blacklist_result,
        "web": web_result,
    }

    return S1Result(score=total, flags=flags, details=details)