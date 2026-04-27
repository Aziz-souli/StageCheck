"use client";

import { useState, useRef, useEffect, useMemo } from "react";
import { Search, Loader2, Filter, X, Shield } from "lucide-react";
import JobCard from "./components/JobCard";

// ------------------------------------------------------------------ //
//  Types                                                               //
// ------------------------------------------------------------------ //

type Job = {
  title:             string;
  company_name:      string;
  company_logo:      string;
  company_url:       string;
  job_url:           string;
  location:          string;
  salary:            string;
  contract_type:     string;
  remote_type:       string;
  date_posted:       string;
  origine:           string;
  description:       string;
  score: number | null;
  label: "legit" | "suspicious" | "fake" | "unscored";
  credibility_flags: string[];
  s1_score:          number;
  s3_score:          number;
  s4_score:          number;
  s1_details:        Record<string, any>;
  s3_details:        Record<string, any>;
  s4_details:        Record<string, any>;
};

type FilterLabel = "all" | "legit" | "suspicious" | "fake" | "unscored";

// ------------------------------------------------------------------ //
//  Constants                                                           //
// ------------------------------------------------------------------ //

const FILTER_OPTIONS: {
  label: FilterLabel;
  color: string;
  icon:  string;
}[] = [
  { label: "all",        color: "bg-gray-700 text-gray-200",    icon: "🔍" },
  { label: "legit",      color: "bg-green-900 text-green-300",  icon: "✅" },
  { label: "suspicious", color: "bg-yellow-900 text-yellow-300",icon: "⚠️" },
  { label: "fake",       color: "bg-red-900 text-red-300",      icon: "❌" },
  { label: "unscored",   color: "bg-gray-800 text-gray-400",    icon: "⏳" },
];

const API_BASE = "http://localhost:8000";

// ------------------------------------------------------------------ //
//  Page                                                                //
// ------------------------------------------------------------------ //

export default function Home() {
  const [query,        setQuery]        = useState("");
  const [jobs,         setJobs]         = useState<Job[]>([]);
  const [loading,      setLoading]      = useState(false);
  const [done,         setDone]         = useState(false);
  const [status,       setStatus]       = useState("");
  const [activeFilter, setActiveFilter] = useState<FilterLabel>("all");
  const [minScore,     setMinScore]     = useState(0);
  const [showFilters,  setShowFilters]  = useState(false);
  const [error,        setError]        = useState("");

  const eventSourceRef = useRef<EventSource | null>(null);

  // ── Derived state ─────────────────────────────────────────────── //

  const counts = useMemo(() => ({
    all:        jobs.length,
    legit:      jobs.filter((j) => j.label === "legit").length,
    suspicious: jobs.filter((j) => j.label === "suspicious").length,
    fake:       jobs.filter((j) => j.label === "fake").length,
    unscored:   jobs.filter((j) =>
      !j.label || j.label === "unscored"
    ).length,
  }), [jobs]);

  const filteredJobs = useMemo(() => {
    return jobs
      .filter((job) => {
        if (activeFilter !== "all" && job.label !== activeFilter)
          return false;
        if (minScore > 0 && (job.score ?? 0) < minScore)
          return false;
        return true;
      })
      .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  }, [jobs, activeFilter, minScore]);

  // ── Stats for header ──────────────────────────────────────────── //

  const avgScore = useMemo(() => {
    const scored = jobs.filter((j) => j.score !== null);
    if (!scored.length) return null;
    return Math.round(
      scored.reduce((sum, j) => sum + (j.score ?? 0), 0) /
        scored.length
    );
  }, [jobs]);

  // ── Search handler ────────────────────────────────────────────── //

  const handleSearch = async () => {
    if (!query.trim()) return;

    // Reset
    setJobs([]);
    setDone(false);
    setLoading(true);
    setError("");
    setStatus("Début de la recherche...");
    setActiveFilter("all");
    setMinScore(0);
    setShowFilters(false);

    // Close existing SSE
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    try {
      // Start search
      const res = await fetch(`${API_BASE}/api/search`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({
          query,
          // country:       "FR",
          // contract_type: "internship",
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Search failed");
      }

      const { search_id } = await res.json();
      setStatus("Spiders started — waiting for results...");

      // Connect SSE
      const es = new EventSource(`${API_BASE}/api/stream/${search_id}`);
      eventSourceRef.current = es;

      es.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === "connected") {
          setStatus("Connected — scraping in progress...");

        } else if (data.type === "job") {
          const job: Job = {
            ...data.job,
            label: data.job.label ?? "unscored",
            score: data.job.score ?? null,
          };
          setJobs((prev) => [job, ...prev]);
          setStatus("Réception des résultats en temps réel...");

        } else if (data.type === "done") {
          setLoading(false);
          setDone(true);
          setStatus("Search complete.");
          es.close();

        } else if (data.type === "error") {
          setLoading(false);
          setError(data.message || "An error occurred");
          es.close();
        }
      };

      es.onerror = () => {
        setLoading(false);
        setStatus("");
        setError("Connection lost. Please try again.");
        es.close();
      };

    } catch (e: any) {
      setLoading(false);
      setError(e.message || "Search failed. Is the backend running?");
    }
  };

  // ── Stop handler ──────────────────────────────────────────────── //

  const handleStop = async () => {
    eventSourceRef.current?.close();
    setLoading(false);
    setDone(true);
    setStatus("Search stopped.");
    await fetch(`${API_BASE}/api/stop`, { method: "POST" }).catch(() => {});
  };

  // ── Cleanup on unmount ────────────────────────────────────────── //

  useEffect(() => {
    return () => eventSourceRef.current?.close();
  }, []);

  // ── Render ────────────────────────────────────────────────────── //

  return (
    <main className="min-h-screen bg-gray-950 text-white">

      {/* ════════════════════════════════════════════════════════════
          Header
      ════════════════════════════════════════════════════════════ */}
      <div className="bg-gray-900 border-b border-gray-800 px-6 py-8">
        <div className="max-w-5xl mx-auto">

          {/* Title */}
          <div className="flex items-center justify-between mb-1">
            <h1 className="text-3xl font-bold flex items-center gap-2">
              <Shield className="w-8 h-8 text-blue-400" />
              Vérificateur de crédibilité des stages
            </h1>
            {jobs.length > 0 && avgScore !== null && (
              <div className="text-right">
                <div className="text-2xl font-bold text-white">
                  {avgScore}
                  <span className="text-sm text-gray-500">/100</span>
                </div>
                <div className="text-xs text-gray-500">score moyen</div>
              </div>
            )}
          </div>

          <p className="text-gray-400 mb-6 text-sm">
            OSINT en temps réel · Analyse IA · Évaluation CTI
          </p>

          {/* Search bar */}
          <div className="flex gap-3">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="ex: cybersécurité, data science, finance..."
              className="flex-1 bg-gray-800 border border-gray-700 rounded-xl
                         px-5 py-3 text-white placeholder-gray-500
                         focus:outline-none focus:border-blue-500
                         focus:ring-1 focus:ring-blue-500 transition-colors"
            />
            {loading ? (
              <button
                onClick={handleStop}
                className="bg-red-700 hover:bg-red-600 px-6 py-3 rounded-xl
                           font-semibold flex items-center gap-2 transition-colors"
              >
                <X className="w-5 h-5" />
                Stop
              </button>
            ) : (
              <button
                onClick={handleSearch}
                disabled={!query.trim()}
                className="bg-blue-600 hover:bg-blue-500
                           disabled:bg-gray-800 disabled:text-gray-600
                           disabled:cursor-not-allowed px-6 py-3 rounded-xl
                           font-semibold flex items-center gap-2 transition-colors"
              >
                <Search className="w-5 h-5" />
                Recherche
              </button>
            )}
          </div>

          {/* Status */}
          {(status || loading) && !error && (
            <div className="mt-3 flex items-center gap-2 text-sm text-gray-400">
              {loading && (
                <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
              )}
              {status}
              {loading && (
                <Loader2 className="w-3.5 h-3.5 animate-spin ml-1" />
              )}
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mt-3 flex items-center gap-2 text-sm text-red-400
                            bg-red-950 border border-red-800 rounded-lg px-4 py-2">
              ❌ {error}
              <button
                onClick={() => setError("")}
                className="ml-auto text-red-600 hover:text-red-400"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Live stats bar */}
        </div>
      </div>

      {/* ════════════════════════════════════════════════════════════
          Filter bar
      ════════════════════════════════════════════════════════════ */}
      {jobs.length > 0 && (
        <div className="bg-gray-900 border-b border-gray-800 px-6 py-3 sticky top-0 z-10">
          <div className="max-w-5xl mx-auto">
            <div className="flex flex-wrap items-center gap-2">

              {/* Label filter pills */}
              <span className="text-gray-500 text-xs flex items-center gap-1">
                <Filter className="w-3 h-3" /> Filter:
              </span>

              {FILTER_OPTIONS.map(({ label, color, icon }) => (
                <button
                  key={label}
                  onClick={() => setActiveFilter(label as FilterLabel)}
                  className={`
                    px-3 py-1 rounded-full text-xs font-medium
                    flex items-center gap-1.5 transition-all border
                    ${activeFilter === label
                      ? `${color} border-current scale-105 shadow-lg`
                      : "bg-transparent border-gray-700 text-gray-500 hover:border-gray-500"}
                  `}
                >
                  <span>{icon}</span>
                  <span className="capitalize">{label}</span>
                  <span className="bg-black/30 px-1.5 py-0.5 rounded-full">
                    {counts[label]}
                  </span>
                </button>
              ))}

              {/* Min score toggle */}
              <button
                onClick={() => setShowFilters(!showFilters)}
                className="ml-auto text-xs text-gray-500 hover:text-gray-300
                           flex items-center gap-1 transition-colors"
              >
                {showFilters
                  ? <><X className="w-3 h-3" /> Hide</>
                  : <><Filter className="w-3 h-3" /> Min score</>}
              </button>
            </div>

            {/* Min score slider */}
            {showFilters && (
              <div className="mt-3 flex items-center gap-4">
                <span className="text-xs text-gray-400 whitespace-nowrap">
                  Min score:{" "}
                  <span className="text-white font-bold">{minScore}</span>
                </span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={minScore}
                  onChange={(e) => setMinScore(Number(e.target.value))}
                  className="flex-1 accent-blue-500"
                />
                <span className="text-xs text-gray-500">100</span>
                {minScore > 0 && (
                  <button
                    onClick={() => setMinScore(0)}
                    className="text-xs text-blue-400 hover:text-blue-300"
                  >
                    Reset
                  </button>
                )}
              </div>
            )}

            {/* Results summary */}
            <div className="mt-2 text-xs text-gray-600">
              Affichage de {filteredJobs.length} de {jobs.length} stages
              {loading && " — plus à venir..."}
              {activeFilter !== "all" || minScore > 0
                ? " (filtrés)"
                : ""}
            </div>
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════════════════════
          Results
      ════════════════════════════════════════════════════════════ */}
      <div className="max-w-5xl mx-auto px-6 py-8 min-w-[50%] %]">

        {/* Empty state */}
        {jobs.length === 0 && !loading && !done && !error && (
          <div className="text-center py-24">
            <div className="text-6xl mb-4">🛡️</div>
            <p className="text-gray-400 text-lg font-medium">
                  Recherche de stages 
            </p>
            <p className="text-gray-600 text-sm mt-2 max-w-md mx-auto">
              Les résultats sont évalués en temps réel grâce à l'OSINT, la détection intersites, l'analyse par IA et le renseignement sur les cybermenaces.
            </p>
            <div className="mt-8 grid grid-cols-3 gap-4 max-w-lg mx-auto">
              {[
                { icon: "🔎", label: "OSINT",     desc: "Domain, DNS, SSL, web, blacklists" },
                { icon: "🤖", label: "AI",         desc: "LLM analysis" },
                { icon: "🛡️", label: "CTI",        desc: "VirusTotal, AbuseIPDB, Shodan, MISP" },
              ].map(({ icon, label, desc }) => (
                <div key={label}
                     className="bg-gray-900 rounded-xl p-3 text-center">
                  <div className="text-2xl mb-1">{icon}</div>
                  <div className="text-xs font-medium text-gray-300">
                    {label}
                  </div>
                  <div className="text-xs text-gray-600 mt-0.5">{desc}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* No results after filter */}
        {filteredJobs.length === 0 && jobs.length > 0 && (
          <div className="text-center bg-bpy-16">
            <div className="text-4xl mb-3">🔍</div>
            <p className="text-gray-500">
            Aucun stage ne correspond aux filtres actuels.
            </p>
            <button
              onClick={() => {
                setActiveFilter("all");
                setMinScore(0);
              }}
              className="mt-3 text-blue-400 hover:text-blue-300 text-sm"
            >
              Clear filters
            </button>
          </div>
        )}

        {/* Job cards */}
        <div className="space-y-4 min-w-full">
          {filteredJobs.map((job, i) => (
            <JobCard key={`${job.job_url}-${i}`} job={job} />
          ))}
        </div>

        {/* Done footer */}
        {done && jobs.length > 0 && (
          <div className="text-center text-gray-600 text-sm mt-10 pb-4">
            ✅ Search complete — {jobs.length} internships found
            {avgScore !== null && ` · score moyen ${avgScore}/100`}
          </div>
        )}
      </div>
    </main>
  );
}