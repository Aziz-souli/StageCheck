// components/JobCard.tsx
"use client";

import { useState } from "react";
import {
  MapPin, Building2, Calendar, Wifi, DollarSign,
  ExternalLink, ChevronDown, ChevronUp, Shield
} from "lucide-react";
import ScoreBreakdown from "./ScoreBreakdown";

const LABEL_STYLES = {
  legit:      "bg-green-900 text-green-300 border border-green-700",
  suspicious: "bg-yellow-900 text-yellow-300 border border-yellow-700",
  fake:       "bg-red-900 text-red-300 border border-red-700",
  unscored:   "bg-gray-800 text-gray-400 border border-gray-700",
};

const LABEL_ICONS = {
  legit:      "✅",
  suspicious: "⚠️",
  fake:       "❌",
  unscored:   "⏳",
};

type CredibilityLabel = keyof typeof LABEL_STYLES;

export default function JobCard({ job }: { job: any }) {
  const [expanded, setExpanded] = useState(false);
  const label = (job.label as CredibilityLabel) ?? "unscored";
  const score = job.score ?? null;
  
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5
                    hover:border-gray-600 transition-colors">
      {/* Top row */}
      <div className="flex items-start gap-4">
        {/* Company logo */}
        <div className="w-12 h-12 rounded-xl bg-gray-800 flex items-center
                        justify-center overflow-hidden shrink-0">
          {job.company_logo ? (
            <img src={job.company_logo} alt={job.company_name}
                 className="w-full h-full object-contain" />
          ) : (
            <Building2 className="w-6 h-6 text-gray-500" />
          )}
        </div>

        {/* Title + company */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="font-semibold text-white text-lg leading-tight">
                {job.title}
              </h2>
              <p className="text-blue-400 text-sm mt-0.5">
                {job.company_name}
              </p>
            </div>

            {/* Score badge */}
            <div className="shrink-0 text-right">
              <div className={`inline-flex items-center gap-1.5 px-3 py-1
                              rounded-full text-sm font-medium ${LABEL_STYLES[label]}`}>
                <span>{LABEL_ICONS[label]}</span>
                <span className="capitalize">{label}</span>
                {score !== null && (
                  <span className="font-bold">{score}/100</span>
                )}
              </div>
            </div>
          </div>

          {/* Score bar */}
          {score !== null && (
            <div className="mt-2 w-full bg-gray-800 rounded-full h-1.5">
              <div
                className={`h-1.5 rounded-full transition-all ${
                  score >= 70 ? "bg-green-500" :
                  score >= 40 ? "bg-yellow-500" : "bg-red-500"
                }`}
                style={{ width: `${score}%` }}
              />
            </div>
          )}
        </div>
      </div>

      {/* Meta info */}
      <div className="mt-4 flex flex-wrap gap-3 text-sm text-gray-400">
        {job.location && (
          <span className="flex items-center gap-1">
            <MapPin className="w-3.5 h-3.5" /> {job.location}
          </span>
        )}
        {job.salary && (
          <span className="flex items-center gap-1">
            <DollarSign className="w-3.5 h-3.5" /> {job.salary}
          </span>
        )}
        {job.remote_type && (
          <span className="flex items-center gap-1">
            <Wifi className="w-3.5 h-3.5" /> {job.remote_type}
          </span>
        )}
        {job.date_posted && (
          <span className="flex items-center gap-1">
            <Calendar className="w-3.5 h-3.5" /> {job.date_posted}
          </span>
        )}
        {job.origine && (
          <span className="bg-gray-800 px-2 py-0.5 rounded-full text-xs">
            {job.origine}
          </span>
        )}
      </div>

      {/* Description preview */}
      {job.description && (
        <p className="mt-3 text-gray-400 text-sm line-clamp-2">
          {job.description.replace(/<[^>]+>/g, '')}
        </p>
      )}

      {/* Flags */}
      {job.credibility_flags?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2  rounded-lg p-3">
          {job.credibility_flags.slice(0, 3).map((flag: string, i: number) => (
            <span key={i}
                  className="text-xs bg-gray-800 text-gray-400 px-2 py-1 rounded-lg">
              ⚑ {flag}
            </span>
          ))}
        <button
            onClick={() => window.open(job.job_url, "_blank", "noopener,noreferrer")}
            className="ml-auto flex items-center gap-1 text-sm text-white bg-blue-600
               hover:bg-blue-500 transition-colors px-3 py-2 rounded-md
               focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            View offer <ExternalLink className="w-3.5 h-3.5" />
        </button>
        </div>
      )}

      {/* Expand/collapse */}
      <div className=" flex items-center justify-between">

   
      <ScoreBreakdown
          s1_score={job.s1_score}
          s3_score={job.s3_score}
          s4_score={job.s4_score}
          s1_details={job.s1_details}
          s3_details={job.s3_details}
          s4_details={job.s4_details}
        />

      {/* {expanded && (
        <ScoreBreakdown
          s1_score={job.s1_score}
          s2_score={job.s2_score}
          s3_score={job.s3_score}
          s1_details={job.s1_details}
          s2_details={job.s2_details}
          s3_details={job.s3_details}
        />
      )} */}
      {/* <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1 text-sm text-gray-500
                     hover:text-gray-300 transition-colors"
        >
          <Shield className="w-4 h-4" />
          Score breakdown
          {expanded
            ? <ChevronUp className="w-4 h-4" />
            : <ChevronDown className="w-4 h-4" />}
        </button> */}
        
    </div>
  </div>
  );
}