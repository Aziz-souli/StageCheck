// components/ScoreBreakdown.tsx
// ------------------------------------------------------------------ //
//  CTI Details Panel                                                   //
// ------------------------------------------------------------------ //
"use client";
import { useState , useRef, useEffect} from "react";

function CTIDetails({ s4_details }: { s4_details: Record<string, any> }) {
  const platforms = [
    {
      name:    "VirusTotal",
      icon:    "🦠",
      color:   "border-gray-500",
      header:  "bg-gray-700",
      data: [
        {
          label: "Malicious detections",
          value: s4_details?.virustotal?.malicious ?? 0,
          bad:   s4_details?.virustotal?.malicious > 0,
        },
        {
          label: "Suspicious detections",
          value: s4_details?.virustotal?.suspicious ?? 0,
          bad:   s4_details?.virustotal?.suspicious > 0,
        },
        {
          label: "Harmless",
          value: s4_details?.virustotal?.harmless ?? 0,
          bad:   false,
        },
        {
          label: "Score",
          value: `${s4_details?.virustotal?.score ?? "?"}/5`,
          bad:   (s4_details?.virustotal?.score ?? 5) < 3,
        },
      ],
      link: s4_details?.domain
        ? `https://www.virustotal.com/gui/domain/${s4_details.domain}`
        : null,
      verdict:
        (s4_details?.virustotal?.malicious ?? 0) > 0
          ? "MALICIOUS"
          : (s4_details?.virustotal?.suspicious ?? 0) > 0
          ? "SUSPICIOUS"
          : "CLEAN",
    },
    {
      name:   "AbuseIPDB",
      icon:   "🚨",
      color:   "border-gray-500",
      header:  "bg-gray-700",
      data: [
        {
          label: "Abuse confidence score",
          value: `${s4_details?.abuseipdb?.abuse_score ?? 0}%`,
          bad:   (s4_details?.abuseipdb?.abuse_score ?? 0) > 10,
        },
        {
          label: "Total reports",
          value: s4_details?.abuseipdb?.total_reports ?? 0,
          bad:   (s4_details?.abuseipdb?.total_reports ?? 0) > 0,
        },
        {
          label: "Country",
          value: s4_details?.abuseipdb?.country ?? "Unknown",
          bad:   false,
        },
        {
          label: "IP address",
          value: s4_details?.ip ?? "Unknown",
          bad:   false,
        },
      ],
      link: s4_details?.ip
        ? `https://www.abuseipdb.com/check/${s4_details.ip}`
        : null,
      verdict:
        (s4_details?.abuseipdb?.abuse_score ?? 0) >= 80
          ? "HIGH RISK"
          : (s4_details?.abuseipdb?.abuse_score ?? 0) >= 40
          ? "MEDIUM RISK"
          : (s4_details?.abuseipdb?.abuse_score ?? 0) >= 10
          ? "LOW RISK"
          : "CLEAN",
    },
    {
      name:   "Shodan",
      icon:   "📡",
      color:   "border-gray-500",
      header:  "bg-gray-700",
      data: [
        {
          label: "Open ports",
          value:
            s4_details?.shodan?.open_ports?.length > 0
              ? s4_details.shodan.open_ports.slice(0, 8).join(", ")
              : "None detected",
          bad: (s4_details?.shodan?.open_ports?.length ?? 0) > 10,
        },
        {
          label: "CVEs found",
          value: s4_details?.shodan?.vulns?.length ?? 0,
          bad:   (s4_details?.shodan?.vulns?.length ?? 0) > 0,
        },
        {
          label: "CVE list",
          value:
            s4_details?.shodan?.vulns?.length > 0
              ? s4_details.shodan.vulns.slice(0, 3).join(", ")
              : "None",
          bad: (s4_details?.shodan?.vulns?.length ?? 0) > 0,
        },
        {
          label: "Organisation",
          value: s4_details?.shodan?.org ?? "Unknown",
          bad:   false,
        },
      ],
      link: s4_details?.ip
        ? `https://www.shodan.io/host/${s4_details.ip}`
        : null,
      verdict:
        (s4_details?.shodan?.vulns?.length ?? 0) > 0
          ? "VULNERABLE"
          : (s4_details?.shodan?.open_ports?.length ?? 0) > 10
          ? "HIGH EXPOSURE"
          : "NORMAL",
    },
    {
      name:   "MISP",
      icon:   "🕵️",
      color:   "border-gray-500",
      header:  "bg-gray-700",
      data: [
        {
          label: "Threat intel hits",
          value: s4_details?.misp?.hits?.length ?? 0,
          bad:   (s4_details?.misp?.hits?.length ?? 0) > 0,
        },
        ...(s4_details?.misp?.hits ?? []).slice(0, 3).map((hit: any) => ({
          label: hit.category ?? "Hit",
          value: hit.value ?? "",
          bad:   true,
        })),
      ],
      link:    null,
      verdict:
        (s4_details?.misp?.hits?.length ?? 0) >= 3
          ? "HIGH THREAT"
          : (s4_details?.misp?.hits?.length ?? 0) >= 1
          ? "THREAT DETECTED"
          : "CLEAN",
    },
  ];

  const VERDICT_STYLE: Record<string, string> = {
    CLEAN:             "bg-green-900 text-green-300",
    NORMAL:            "bg-green-900 text-green-300",
    "LOW RISK":        "bg-yellow-900 text-yellow-300",
    "MEDIUM RISK":     "bg-orange-900 text-orange-300",
    SUSPICIOUS:        "bg-orange-900 text-orange-300",
    "HIGH EXPOSURE":   "bg-orange-900 text-orange-300",
    BREACHED:          "bg-red-900 text-red-300",
    MALICIOUS:         "bg-red-900 text-red-300",
    VULNERABLE:        "bg-red-900 text-red-300",
    "HIGH RISK":       "bg-red-900 text-red-300",
    "MULTIPLE BREACHES": "bg-red-900 text-red-300",
    "THREAT DETECTED": "bg-red-900 text-red-300",
    "HIGH THREAT":     "bg-red-900 text-red-300",
  };

  return (
    <div className="mt-3 grid grid-cols-1 gap-3">
      {platforms.map((platform) => (
        <div
          key={platform.name}
          className={`rounded-xl border overflow-hidden ${platform.color}`}
        >
          {/* Platform header */}
          <div className={`${platform.header} px-4 py-2 flex items-center
                           justify-between`}>
            <span className="text-sm font-semibold text-white flex
                             items-center gap-2">
              {platform.icon} {platform.name}
            </span>
            <div className="flex items-center gap-2">
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium
                               ${VERDICT_STYLE[platform.verdict] ??
                                 "bg-gray-800 text-gray-300"}`}>
                {platform.verdict}
              </span>
              {platform.link && (
                <a
                  href={platform.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-blue-300 hover:text-blue-200
                             underline transition-colors"
                >
                  View ↗
                </a>
              )}
            </div>
          </div>

          {/* Platform data rows */}
          <div className="px-4 py-3 space-y-2">
            {platform.data.map((row, i) => (
              <div key={i} className="flex items-start justify-between gap-4">
                <span className="text-xs text-gray-400 shrink-0">
                  {row.label}
                </span>
                <span className={`text-xs font-medium text-right break-all ${
                  row.bad ? "text-red-400" : "text-green-400"
                }`}>
                  {String(row.value)}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}




export default function ScoreBreakdown({ s1_score, s4_score, s3_score,
                                         s1_details, s4_details, s3_details }: any) {
  const [showCTI, setShowCTI] = useState(false);
  const modules = [
    {
      name: "Whois/DNS/SSL/Blacklist/web",
      score: s1_score,
      max: 25,
      icon: "🔎",
      details: [
        s1_details?.whois?.age_days
          ? `Domain age: ${s1_details.whois.age_days} days`
          : "Domain age unknown",
        s1_details?.dns?.has_mx ? "✓ MX records present" : "✗ No MX records",
        s1_details?.ssl?.valid ? "✓ Valid SSL certificate" : "✗ SSL issue",
        s1_details?.blacklist?.blacklisted ? "✗ Domain blacklisted" : "✓ Not blacklisted",
        s1_details?.web?.reachable ? "✓ Website reachable" : "✗ Website unreachable",
      ],
    },
    // {
    //   name: "S2 — Cross-site",
    //   score: s2_score,
    //   max: 33,
    //   icon: "🌐",
    //   details: [
    //     `Found on ${s2_details?.cross_site_count ?? 0} other site(s)`,
    //     `Total occurrences: ${s2_details?.total_occurrences ?? 0}`,
    //     s2_details?.found_on_sites?.length > 0
    //       ? `Sites: ${s2_details.found_on_sites.join(", ")}`
    //       : "Not found on other sites",
    //   ],
    // },
    {
      name:  "CTI",
      score: s4_score,
      max:   25,
      icon:  "🛡️",
      color: "bg-red-500",
      details: [
        s4_details?.ip ? `IP: ${s4_details.ip}` : null,
        (s4_details?.virustotal?.malicious ?? 0) > 0
          ? `✗ VT: ${s4_details.virustotal.malicious} malicious`
          : "✓ VirusTotal: clean",
        (s4_details?.abuseipdb?.abuse_score ?? 0) > 0
          ? `✗ AbuseIPDB: ${s4_details.abuseipdb.abuse_score}%`
          : "✓ AbuseIPDB: clean",
        (s4_details?.hibp?.breach_count ?? 0) > 0
          ? `✗ HIBP: ${s4_details.hibp.breach_count} breach(es)`
          : "✓ No breaches",
        (s4_details?.shodan?.vulns?.length ?? 0) > 0
          ? `✗ Shodan: ${s4_details.shodan.vulns.length} CVE(s)`
          : "✓ No CVEs",
        (s4_details?.misp?.hits?.length ?? 0) > 0
          ? `✗ MISP: ${s4_details.misp.hits.length} hit(s)`
          : "✓ MISP: clean",
      ].filter(Boolean) as string[],
    },
    {
      name: "AI Analysis",
      score: s3_score,
      max: 50,
      icon: "🤖",
      details: [
        `Verdict: ${s3_details?.verdict ?? "unknown"}`,
        `Confidence: ${s3_details?.confidence ?? "unknown"}`,
        ...(s3_details?.positive_signals?.slice(0, 2) ?? []).map(
          (s: string) => `✓ ${s}`
        ),
        ...(s3_details?.red_flags?.slice(0, 2) ?? []).map(
          (f: string) => `✗ ${f}`
        ),
      ],
    },
  ];
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const   resetTimer = () => {
    if (timerRef.current !== null) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setShowCTI(false);
    }, 5000);
  };
  useEffect(() => {
    if (showCTI) {
      resetTimer();
    }
    return () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
      }
    };
  }, [showCTI]);

  return (
    <div className=" p-3 border-t border-gray-800 grid grid-cols-3 gap-4 flex  w-full">
      {modules.map((mod) => (
        <div key={mod.name} className="bg-gray-800 rounded-xl p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-gray-300">
              {mod.icon} {mod.name}
            </span>
            <span className="text-xs font-bold text-white">
              {mod.score ?? "?"}/{mod.max}
            </span>
          </div>

          {/* Module score bar */}
          <div className="w-full bg-gray-700 rounded-full h-1 mb-3">
            <div
              className="h-1 rounded-full bg-blue-500"
              style={{ width: `${((mod.score ?? 0) / mod.max) * 100}%` }}
            />
          </div>

          {/* Details */}
          <ul className="space-y-1">
            {mod.details.filter(Boolean).map((d, i) => (
              <li key={i} className="text-xs text-gray-400">{d}</li>
            ))}
          </ul>
        
             {/* ← CTI toggle button — only on S4 card */}
            {mod.name === "CTI" && (
              <button
                onClick={() => setShowCTI(!showCTI)}
                
                className={`
                  mt-3 w-full text-xs py-1.5 rounded-lg border
                  flex items-center justify-center gap-1.5
                  transition-colors font-medium
                  ${showCTI
                    ? "bg-red-900 border-red-700 text-red-300"
                    : "bg-gray-700 border-gray-600 text-gray-300 hover:bg-gray-600"}
                `}
              >
                🛡️ {showCTI ? "Hide CTI details" : "Show CTI details"}
              </button>
            )}
            {/* ── CTI expanded panel ── */}
            {showCTI && mod.name === "CTI" && (
            <div
              onMouseMove={resetTimer}
              onMouseEnter={resetTimer}
              onClick={resetTimer}
              className="fixed top-54 left-6 w-96 p-2 bg-gray-800 rounded-lg shadow-lg z-50"
            >
              <div className="flex items-center gap-2 mb-3">
                <span className="text-sm font-semibold text-gray-200">
                  🛡️ Cyber Threat Intelligence — Full Report
                </span>
                <div className="flex-1 h-px bg-gray-700" />
                <span className="text-xs text-gray-500">
                  Domain: {s4_details?.domain ?? "unknown"}
                  {s4_details?.ip ? ` · IP: ${s4_details.ip}` : ""}
                </span>
              </div>
              <CTIDetails s4_details={s4_details} />
            </div>
            )}
        </div>
      ))}

    </div>
  );
}