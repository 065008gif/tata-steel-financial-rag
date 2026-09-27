import { useEffect, useState } from "react";

/* =========================================================
   SHARED UI
   Edith's Icon, StatusPill and SectionHeading (unchanged apart
   from three extra icon paths), plus display helpers for API data.
   Nothing here computes a financial figure: values are formatted
   exactly as the API returns them.
   ========================================================= */

export function Icon({ name, size = 22 }) {
  const paths = {
    spark: (
      <>
        <path d="M12 2.8 14.2 9.8 21.2 12 14.2 14.2 12 21.2 9.8 14.2 2.8 12 9.8 9.8 12 2.8Z" />
        <path d="m19 2 .6 2.4L22 5l-2.4.6L19 8l-.6-2.4L16 5l2.4-.6L19 2Z" />
      </>
    ),

    search: (
      <>
        <circle cx="10.8" cy="10.8" r="6.8" />
        <path d="m16 16 5 5" />
      </>
    ),

    file: (
      <>
        <path d="M6 2.8h8l4.5 4.5v13.9H6z" />
        <path d="M14 2.8v5h4.5M9 12h6M9 16h6" />
      </>
    ),

    check: (
      <>
        <path d="m4 12.5 5 5L20 6.5" />
        <circle cx="12" cy="12" r="9" />
      </>
    ),

    chart: (
      <>
        <path d="M3 20V4M3 20h18" />
        <path d="m6 15 4-4 3 2 6-7" />
        <path d="M16 6h3v3" />
      </>
    ),

    arrow: <path d="M4 12h15m-6-6 6 6-6 6" />,

    menu: (
      <>
        <path d="M4 7h16M4 12h16M4 17h16" />
      </>
    ),

    close: <path d="m6 6 12 12M18 6 6 18" />,

    book: (
      <>
        <path d="M3.5 5.5A3 3 0 0 1 6.5 3H20v16H6.5a3 3 0 0 0-3 3z" />
        <path d="M3.5 5.5v16M7.5 7h8M7.5 11h8" />
      </>
    ),

    shield: (
      <>
        <path d="M12 2.8 20 6v5.4c0 5.2-3.4 8.5-8 10.2-4.6-1.7-8-5-8-10.2V6z" />
        <path d="m8.5 12 2.3 2.3 4.8-5" />
      </>
    ),

    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3.5 2" />
      </>
    ),

    layers: (
      <>
        <path d="m12 3 9 5-9 5-9-5z" />
        <path d="m3 12 9 5 9-5M3 16l9 5 9-5" />
      </>
    ),

    copy: (
      <>
        <rect x="8.5" y="8.5" width="12" height="12" rx="2.5" />
        <path d="M15.5 8.5V6a2.5 2.5 0 0 0-2.5-2.5H6A2.5 2.5 0 0 0 3.5 6v7A2.5 2.5 0 0 0 6 15.5h2.5" />
      </>
    ),

    external: (
      <>
        <path d="M14 4h6v6M20 4l-9 9" />
        <path d="M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10" />
      </>
    ),

    refresh: (
      <>
        <path d="M20 11a8 8 0 1 0-2.3 5.7" />
        <path d="M20 4v7h-7" />
      </>
    ),
  };

  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] || paths.spark}
    </svg>
  );
}

export function StatusPill({ children, tone = "pending" }) {
  return (
    <span className={`status-pill ${tone}`}>
      {children}
    </span>
  );
}

export function SectionHeading({ eyebrow, title, description, action }) {
  return (
    <div className="section-heading">
      <div>
        {eyebrow && <div className="section-eyebrow">{eyebrow}</div>}
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>

      {action && <div className="section-heading-action">{action}</div>}
    </div>
  );
}


/* ---------------------------------------------------------
   Formatting (display only)
   --------------------------------------------------------- */

const MINUS = "−";

export function formatNumber(value, decimals = 2) {
  if (value == null || Number.isNaN(value)) return "n/a";
  const text = Math.abs(value).toLocaleString("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return value < 0 ? `${MINUS}${text}` : text;
}

/** INR crore with Indian grouping and 2 decimals, e.g. 2,32,139.94 */
export function formatCrore(value) {
  return formatNumber(value, 2);
}

/** A percentage change exactly as the API gives it, e.g. +6.22% */
export function formatChangePct(value) {
  if (value == null) return "n/a";
  return `${value > 0 ? "+" : ""}${formatNumber(value, 2)}%`;
}

/** A metric from /api/metrics with its unit and the API's decimals. */
export function formatMetric(value, unit, decimals = 2) {
  if (value == null) return "n/a";
  if (unit === "x") return `${formatNumber(value, decimals)}x`;
  if (unit === "%") return `${formatNumber(value, decimals)}%`;
  return formatNumber(value, decimals);
}

/** "distress zone" -> "Distress zone" */
export function sentenceCase(text) {
  if (!text) return text;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function formatRunDate(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/* ---------------------------------------------------------
   Value markers
   --------------------------------------------------------- */

export function RestatedMark({
  note = "Restated: the later report presents a different figure for this year; the latest report's figure is shown.",
}) {
  return (
    <sup className="restated-mark" title={note} aria-label={note}>
      R
    </sup>
  );
}

/** A value, or "n/a" with a tooltip (default "Not reported") when it is null. */
export function Value({
  value,
  format = formatCrore,
  restated = false,
  restatedNote,
  missingNote = "Not reported",
}) {
  if (value == null) return <Missing note={missingNote} />;

  return (
    <>
      {format(value)}
      {restated && <RestatedMark note={restatedNote} />}
    </>
  );
}

/** "n/a" with a tooltip explaining why the value is missing. */
export function Missing({ note = "Not reported" }) {
  return (
    <span className="value-missing" title={note} aria-label={`n/a: ${note}`}>
      n/a
    </span>
  );
}

/* ---------------------------------------------------------
   Years and coverage (standard wording)
   --------------------------------------------------------- */

export const COMPARATIVE_YEAR = "FY2021-22";
export const COMPARATIVE_NOTE = "From the FY2022-23 report's comparative column";
export const NEEDS_PRIOR_YEAR_NOTE = "Needs FY2020-21, which is outside the four reports";
export const COVERAGE_TEXT =
  "Figures cover FY2021-22 to FY2025-26, taken from Tata Steel's four annual reports (FY2022-23 to FY2025-26; FY2021-22 from the comparative column of the FY2022-23 report).";

/** Small info marker for FY2021-22 (comparative-column year). */
export function ComparativeMark() {
  return (
    <sup className="comparative-mark" title={COMPARATIVE_NOTE} aria-label={COMPARATIVE_NOTE}>
      i
    </sup>
  );
}

/** A fiscal-year label, with the info marker when it is FY2021-22. */
export function YearLabel({ year }) {
  return (
    <>
      {year}
      {year === COMPARATIVE_YEAR && <ComparativeMark />}
    </>
  );
}

/* ---------------------------------------------------------
   Sparkline: a tiny 5-year trend drawn in Edith's chart colours.
   The values are only scaled to fit the box.
   --------------------------------------------------------- */

let sparklineCount = 0;

export function Sparkline({ values, width = 64, height = 20, label, highlightIndex }) {
  const [gradientId] = useState(() => `sparkStroke${++sparklineCount}`);
  const present = values
    .map((value, index) => ({ value, index }))
    .filter((point) => point.value != null);

  if (present.length < 2) {
    return <span className="metric-mini-line" aria-hidden="true" />;
  }

  const min = Math.min(...present.map((point) => point.value));
  const max = Math.max(...present.map((point) => point.value));
  const span = max - min || 1;
  const step = (width - 4) / Math.max(values.length - 1, 1);
  const points = present.map((point) => {
    const x = 2 + point.index * step;
    const y = 2 + (1 - (point.value - min) / span) * (height - 4);
    return [x, y];
  });
  // Mark the selected year when given, otherwise the latest point.
  const markIndex = present.findIndex((point) => point.index === highlightIndex);
  const last = points[markIndex >= 0 ? markIndex : points.length - 1];

  return (
    <svg
      className="mini-sparkline"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={label || "Five-year trend"}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#0d9d79" />
          <stop offset="100%" stopColor="#4c8ce8" />
        </linearGradient>
      </defs>

      <polyline
        points={points.map(([x, y]) => `${x},${y}`).join(" ")}
        fill="none"
        stroke={`url(#${gradientId})`}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      <circle
        cx={last[0]}
        cy={last[1]}
        r={highlightIndex != null ? 3 : 2.2}
        className={highlightIndex != null ? "sparkline-selected" : undefined}
      />
    </svg>
  );
}

/* ---------------------------------------------------------
   Data loading
   --------------------------------------------------------- */

/**
 * Loads data with `load()` whenever `key` changes.
 * Returns { data, error, loading, retry }.
 */
export function useApi(load, key) {
  const [state, setState] = useState({ key: null, data: null, error: null });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;

    load().then(
      (data) => active && setState({ key, data, error: null }),
      (error) => active && setState({ key, data: null, error }),
    );

    return () => {
      active = false;
    };
    // `load` is recreated on every render; `key` identifies the request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt]);

  const current = state.key === key;

  return {
    data: current ? state.data : null,
    error: current ? state.error : null,
    loading: !current,
    retry: () => {
      setState((previous) => ({ ...previous, key: null }));
      setAttempt((value) => value + 1);
    },
  };
}

/** A friendly inline error with a Retry button, in Edith's notice style. */
export function LoadError({ error, onRetry, compact = false }) {
  return (
    <div className={`load-error ${compact ? "compact" : ""}`} role="alert">
      <Icon name="shield" size={17} />
      <span>{error?.message || "Something went wrong while loading this data."}</span>
      {onRetry && (
        <button type="button" className="text-link" onClick={onRetry}>
          Retry
          <Icon name="refresh" size={14} />
        </button>
      )}
    </div>
  );
}
