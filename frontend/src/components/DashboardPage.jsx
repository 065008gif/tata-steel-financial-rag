import { useState } from "react";
import {
  getFinancials,
  getMetrics,
  getRegions,
  getScores,
  getSegments,
  getStatements,
} from "../api.js";
import { VERDICT_QUESTION } from "./AskPage.jsx";
import {
  COMPARATIVE_NOTE,
  COMPARATIVE_YEAR,
  Icon,
  LoadError,
  Missing,
  NEEDS_PRIOR_YEAR_NOTE,
  RestatedMark,
  Sparkline,
  Value,
  YearLabel,
  formatChangePct,
  formatCrore,
  formatMetric,
  formatNumber,
  sentenceCase,
  useApi,
} from "./ui.jsx";

/* =========================================================
   DASHBOARD
   Every value comes from the API; the frontend only formats
   it and scales it to fit bars and charts.
   ========================================================= */

const FINANCIAL_ITEMS = [
  "revenue_from_operations",
  "profit_for_the_year",
  "net_cash_from_operating",
];

const metricCards = [
  { key: "revenue_from_operations", label: "Revenue from operations", icon: "chart" },
  { key: "profit_for_the_year", label: "Profit for the year", icon: "layers" },
  { key: "net_cash_from_operating", label: "Operating cash flow", icon: "book" },
  { key: "net_debt", label: "Net debt", icon: "shield" },
];

const RATIO_KEYS = [
  "current_ratio",
  "debt_to_equity",
  "interest_coverage",
  "net_profit_margin",
  "ebitda_margin",
  "roe",
];

const scoreRows = [
  {
    key: "altman_z",
    name: "Altman Z''",
    meaning: "Bankruptcy-risk score, book-equity variant.",
    decimals: 4,
  },
  {
    key: "piotroski_f",
    name: "Piotroski F",
    meaning: "Nine pass/fail checks of profitability, leverage, liquidity and efficiency (0-9).",
    decimals: 0,
  },
  {
    key: "beneish_m",
    name: "Beneish M",
    meaning: "Earnings-manipulation screen.",
    decimals: 4,
  },
];

const FALLBACK_YEARS = ["FY2021-22", "FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"];

// Region filter: the six geographic regions from /api/regions, in this order.
const REGION_KEYS = ["india", "netherlands", "uk", "europe", "south_east_asia", "rest_of_world"];

const GROUP_LEVEL_NOTE = "Group-level only: the reports don't break this down by region";

const statementRows = [
  ["profit_and_loss", "Income statement", "Revenue, costs, and profit"],
  ["balance_sheet", "Balance sheet", "Assets, liabilities, and equity"],
  ["cash_flow", "Cash flow statement", "Operating, investing, and financing cash flows"],
];

const RESTATED_SEGMENT_NOTE =
  "Restated: a later report presents a different figure for this year; the latest report's figure is shown.";

/* ---------------------------------------------------------
   Helpers
   --------------------------------------------------------- */

function lastYear(years) {
  return years?.[years.length - 1];
}

/** Why a year-on-year change is missing: FY2021-22 has no prior year. */
function missingChangeNote(year) {
  return year === COMPARATIVE_YEAR ? NEEDS_PRIOR_YEAR_NOTE : "Not reported";
}

/** The small "Group-level only" note shown while a region is selected. */
function GroupLevelNote({ region }) {
  if (!region) return null;
  return (
    <span className="group-level-note" title={GROUP_LEVEL_NOTE}>
      <Icon name="layers" size={13} />
      {GROUP_LEVEL_NOTE}
    </span>
  );
}

/** One item's five years from /api/financials or /api/metrics. */
function buildSeries(key, financials, metrics, selectedYear) {
  if (key === "net_debt") {
    const metric = metrics?.metrics.find((item) => item.key === "net_debt");
    if (!metric) return null;

    return {
      years: metrics.years,
      points: metrics.years.map((year) => ({
        year,
        value: metric.values[year] ?? null,
        restated: false,
        source: "Borrowings + lease liabilities − cash, bank balances and current investments",
      })),
      yoy: null,
    };
  }

  const item = financials?.items[key];
  if (!item) return null;

  const year = selectedYear || lastYear(financials.years);

  return {
    years: financials.years,
    points: financials.years.map((year) => ({
      year,
      value: item.values[year]?.value ?? null,
      restated: Boolean(item.values[year]?.restated),
      source: item.values[year]?.source,
    })),
    yoy: item.yoy_changes.find((change) => change.to === year) || null,
  };
}

function zoneTone(scoreKey, result) {
  const label = (result?.interpretation || result?.zone || "").toLowerCase();

  if (scoreKey === "beneish_m") {
    return label.includes("flag") ? "distress" : "safe";
  }

  if (["safe", "strong"].includes(label)) return "safe";
  if (["grey", "average"].includes(label)) return "grey";
  if (["distress", "weak"].includes(label)) return "distress";
  return "neutral";
}

function zoneLabel(scoreKey, result) {
  const label = result?.interpretation || result?.zone || "";

  if (scoreKey === "altman_z") return label ? sentenceCase(`${label} zone`) : "";
  if (scoreKey === "beneish_m") {
    return label.toLowerCase().includes("flag") ? "Flag" : "No flag";
  }
  return sentenceCase(label);
}

function formatScore(row, score) {
  if (score == null) return null;
  return row.decimals === 0 ? `${score}/9` : formatNumber(score, row.decimals);
}

/** Round, "nice" gridline values for the chart (display scaling only). */
function niceStep(raw) {
  const exponent = Math.floor(Math.log10(raw));
  const base = 10 ** exponent;
  const fraction = raw / base;
  const nice =
    fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10;
  return nice * base;
}

function chartScale(values) {
  let low = Math.min(...values);
  let high = Math.max(...values);

  if (low === high) {
    low -= Math.abs(low) * 0.1 || 1;
    high += Math.abs(high) * 0.1 || 1;
  }

  let step = niceStep((high - low) / 3);
  let start = Math.floor(low / step) * step;

  while (start + step * 3 < high) {
    step = niceStep(step * 1.01);
    start = Math.floor(low / step) * step;
  }

  return { start, step };
}

/* ---------------------------------------------------------
   Performance chart (Edith's chart style, real data)
   --------------------------------------------------------- */

const CHART_WIDTH = 700;
const CHART_HEIGHT = 250;
const GRID_Y = [195, 140, 85, 30]; // Edith's gridlines, bottom to top
const X_PAD = 36;

function PerformanceChart({ series, label, selectedYear }) {
  const [hovered, setHovered] = useState(null);
  const present = series.points.filter((point) => point.value != null);

  if (present.length === 0) {
    return (
      <div className="chart-area">
        <div className="chart-empty-overlay">
          <span className="chart-empty-icon">
            <Icon name="chart" size={24} />
          </span>
          <strong>Not reported</strong>
          <p>The reports contain no values for this item.</p>
        </div>
      </div>
    );
  }

  const { start, step } = chartScale(present.map((point) => point.value));
  const span = step * 3;
  const count = series.points.length;
  const xAt = (index) =>
    X_PAD + (index * (CHART_WIDTH - X_PAD * 2)) / Math.max(count - 1, 1);
  const yAt = (value) =>
    GRID_Y[0] - ((value - start) / span) * (GRID_Y[0] - GRID_Y[3]);

  const coords = series.points
    .map((point, index) =>
      point.value == null ? null : { ...point, index, x: xAt(index), y: yAt(point.value) },
    )
    .filter(Boolean);

  const line = coords
    .map((point, index) => {
      if (index === 0) return `M${point.x} ${point.y}`;
      const previous = coords[index - 1];
      const mid = (point.x - previous.x) / 2;
      return `C${previous.x + mid} ${previous.y} ${point.x - mid} ${point.y} ${point.x} ${point.y}`;
    })
    .join(" ");
  const first = coords[0];
  const last = coords[coords.length - 1];
  const area = `${line} L${last.x} 220 L${first.x} 220 Z`;
  const zeroY = start < 0 && start + span > 0 ? yAt(0) : null;
  const animationKey = `${label}-${coords.map((point) => point.value).join("|")}`;

  return (
    <>
      <div className="chart-area chart-live">
        <div className="chart-y-labels chart-y-live" aria-hidden="true">
          {GRID_Y.map((y, index) => (
            <span key={y} style={{ top: `${(y / CHART_HEIGHT) * 100}%` }}>
              {formatNumber(start + step * index, 0)}
            </span>
          ))}
        </div>

        <div className="chart-plot">
          <svg
            className="performance-chart"
            viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
            preserveAspectRatio="none"
            role="img"
            aria-label={`${label}, INR crore, ${series.points
              .map((point) => `${point.year}: ${formatCrore(point.value)}`)
              .join("; ")}`}
          >
            <defs>
              <linearGradient id="chartFillGreen" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#0f9b79" stopOpacity=".23" />
                <stop offset="100%" stopColor="#0f9b79" stopOpacity="0" />
              </linearGradient>

            </defs>

            {GRID_Y.map((y) => (
              <line
                key={y}
                x1="0"
                y1={y}
                x2={CHART_WIDTH}
                y2={y}
                className="chart-gridline"
              />
            ))}

            {zeroY != null && (
              <line
                x1="0"
                y1={zeroY}
                x2={CHART_WIDTH}
                y2={zeroY}
                className="chart-zero-line"
              />
            )}

            <path
              key={`area-${animationKey}`}
              d={area}
              fill="url(#chartFillGreen)"
              className="chart-area-fill"
            />

            <path
              key={`line-${animationKey}`}
              d={line}
              fill="none"
              stroke="#0d9d79"
              strokeWidth="3.5"
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
              className="chart-line-animated"
            />
          </svg>

          {coords.map((point) => (
            <button
              type="button"
              key={point.year}
              className={`chart-point ${point.year === selectedYear ? "selected" : ""} ${
                hovered === point.index ? "active" : ""
              }`}
              style={{
                left: `${(point.x / CHART_WIDTH) * 100}%`,
                top: `${(point.y / CHART_HEIGHT) * 100}%`,
              }}
              onMouseEnter={() => setHovered(point.index)}
              onMouseLeave={() => setHovered(null)}
              onFocus={() => setHovered(point.index)}
              onBlur={() => setHovered(null)}
              aria-label={`${point.year}: ${formatCrore(point.value)} crore`}
            />
          ))}

          {coords
            .filter((point) => point.year === selectedYear && hovered !== point.index)
            .map((point) => (
              <span
                key={`label-${point.year}`}
                className={`chart-point-label ${point.x > CHART_WIDTH * 0.8 ? "align-right" : ""} ${
                  point.y < CHART_HEIGHT * 0.3 ? "below" : ""
                }`}
                style={{
                  left: `${(point.x / CHART_WIDTH) * 100}%`,
                  top: `${(point.y / CHART_HEIGHT) * 100}%`,
                }}
                aria-hidden="true"
              >
                ₹ {formatCrore(point.value)} cr
              </span>
            ))}

          {hovered != null && coords.find((point) => point.index === hovered) && (
            <ChartTooltip point={coords.find((point) => point.index === hovered)} />
          )}
        </div>
      </div>

      <div className="chart-x-labels chart-x-live">
        <div className="chart-x-track">
          {series.points.map((point, index) => (
            <span
              key={point.year}
              className={point.year === selectedYear ? "selected" : ""}
              style={{ left: `${(xAt(index) / CHART_WIDTH) * 100}%` }}
            >
              <YearLabel year={point.year} />
            </span>
          ))}
        </div>
      </div>
    </>
  );
}

function ChartTooltip({ point }) {
  const alignRight = point.x > CHART_WIDTH * 0.7;

  return (
    <div
      className={`chart-tooltip ${alignRight ? "align-right" : ""}`}
      style={{
        left: `${(point.x / CHART_WIDTH) * 100}%`,
        top: `${(point.y / CHART_HEIGHT) * 100}%`,
      }}
      role="status"
    >
      <small>{point.year}</small>
      <strong>
        ₹ {formatCrore(point.value)} cr
        {point.restated && <RestatedMark />}
      </strong>
      {point.source && <span>{point.source}</span>}
    </div>
  );
}

/* ---------------------------------------------------------
   Region view (from /api/regions; all arithmetic in the backend)
   --------------------------------------------------------- */

function regionYearsText(region, years) {
  const present = years.filter((year) => region.values[year]);
  if (present.length === 0) return "no year";
  return present.length === 1
    ? present[0]
    : `${present[0]} to ${present[present.length - 1]}`;
}

function RegionView({ region, years, year }) {
  const [item, setItem] = useState("segment_revenue");
  const values = region.values[year];
  const absentNote = `${region.name} is reported only for ${regionYearsText(region, years)}`;
  const pct = (value) => (value == null ? null : `${formatNumber(value, 2)}%`);

  const stats = [
    { label: "Revenue (segment)", value: values?.segment_revenue, crore: true },
    { label: "EBITDA", value: values?.ebitda, crore: true },
    { label: "EBITDA margin", value: pct(values?.ebitda_margin_pct) },
    {
      label: "Share of group revenue",
      value: pct(values?.share_of_group_external_revenue_pct),
      note: "External revenue as a share of the group's external revenue",
    },
    {
      label: "Share of group EBITDA",
      value: pct(values?.share_of_group_ebitda_pct),
      note: "Share of the group's EBITDA after inter-segment eliminations",
    },
  ];

  const sourceText = (fy) =>
    (region.values[fy]?.sources || [])
      .map((source) => `${source.report} report, page ${source.page_label}`)
      .join("; ");

  const series = {
    years,
    points: years.map((fy) => ({
      year: fy,
      value: region.values[fy]?.[item] ?? null,
      restated: Object.values(region.values[fy]?.restated || {}).some((items) =>
        items.includes(item),
      ),
      source: sourceText(fy),
    })),
  };

  return (
    <section className="dashboard-panel region-panel">
      <div className="panel-heading">
        <div>
          <h2>Region view: {region.name}</h2>
          <p>
            Consolidated segment note · <YearLabel year={year} /> · INR crore
            {values?.components?.length > 0 &&
              ` · Includes ${values.components.map((component) => component.name).join(", ")}`}
          </p>
        </div>

        <span className="panel-icon">
          <Icon name="layers" size={20} />
        </span>
      </div>

      <div className="region-stats">
        {stats.map((stat) => (
          <div className="region-stat" key={stat.label} title={stat.note}>
            <span>{stat.label}</span>
            <strong>
              {stat.value == null ? (
                <Missing note={absentNote} />
              ) : stat.crore ? (
                <>
                  <small>₹</small> {formatCrore(stat.value)} <small>cr</small>
                </>
              ) : (
                stat.value
              )}
            </strong>
          </div>
        ))}
      </div>

      <div className="region-trend">
        <div className="chart-legend">
          <span>
            <i className="legend-dot green" />
            {item === "ebitda" ? "EBITDA" : "Revenue (segment)"}
          </span>

          <span>
            <i className="legend-dot blue" />
            Selected year: {year}
          </span>

          <div className="segmented-control">
            {[
              ["segment_revenue", "Revenue"],
              ["ebitda", "EBITDA"],
            ].map(([key, label]) => (
              <button
                key={key}
                className={item === key ? "selected" : ""}
                onClick={() => setItem(key)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <PerformanceChart
          series={series}
          label={`${region.name} ${item === "ebitda" ? "EBITDA" : "revenue"}`}
          selectedYear={year}
        />
      </div>

      <p className="panel-footnote region-sources">
        Sources:{" "}
        {values?.sources?.length ? (
          values.sources.map((source) => (
            <a
              key={`${source.report}-${source.page_label}`}
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              title="Open the report at this page"
            >
              {source.report} report, page {source.page_label}
              <Icon name="external" size={12} />
            </a>
          ))
        ) : (
          <Missing note={absentNote} />
        )}
        {" "}Hover a point for the source of each year. Shares use the group
        total after inter-segment eliminations, so a loss-making region has a
        negative EBITDA share.
      </p>
    </section>
  );
}

/* ---------------------------------------------------------
   Page
   --------------------------------------------------------- */

export default function DashboardPage({ setActivePage, onAskEdith }) {
  const [basis, setBasis] = useState("Consolidated");
  const [selectedYear, setSelectedYear] = useState(null);
  const [regionKey, setRegionKey] = useState("all");
  const [activeMetric, setActiveMetric] = useState("revenue_from_operations");
  const [segmentItem, setSegmentItem] = useState("segment_revenue");

  const scope = basis.toLowerCase();

  const financials = useApi(() => getFinancials(FINANCIAL_ITEMS, scope), `financials-${scope}`);
  const metrics = useApi(() => getMetrics(scope), `metrics-${scope}`);
  const scores = useApi(() => getScores(scope), `scores-${scope}`);
  const segments = useApi(getSegments, "segments");
  const statements = useApi(() => getStatements(scope), `statements-${scope}`);
  const regions = useApi(getRegions, "regions");

  const years = financials.data?.years || metrics.data?.years || FALLBACK_YEARS;
  const year = selectedYear || lastYear(years);
  const regionOptions = REGION_KEYS.map((key) =>
    regions.data?.regions.find((region) => region.key === key),
  ).filter(Boolean);
  const region =
    regionKey === "all" ? null : regionOptions.find((item) => item.key === regionKey);

  const activeCard = metricCards.find((card) => card.key === activeMetric);
  const activeSeries = buildSeries(activeMetric, financials.data, metrics.data, year);
  const activeLoading = activeMetric === "net_debt" ? metrics.loading : financials.loading;
  const activeError = activeMetric === "net_debt" ? metrics.error : financials.error;
  const activeRetry = activeMetric === "net_debt" ? metrics.retry : financials.retry;
  const selectedCol = (fy) => (fy === year ? "selected-year" : undefined);

  return (
    <main className="page inner-page dashboard-page">

      <div className="page-title-row">

        <div>
          <div className="page-overline">
            Tata Steel · Financial overview
          </div>

          <h1>Dashboard</h1>

          <p>
            A working view of statements, financial trends and key ratios.
          </p>
        </div>


      </div>


      <div className="dashboard-controls">

        <div className="control-group">

          <label>Reporting basis</label>

          <div className="segmented-control">

            {["Consolidated", "Standalone"].map((item) => (

              <button
                key={item}
                className={basis === item ? "selected" : ""}
                onClick={() => setBasis(item)}
              >
                {item}
              </button>

            ))}

          </div>

        </div>


        <div className="control-group">

          <label htmlFor="dashboard-year">Year</label>

          <div className="select-control">
            <select
              id="dashboard-year"
              value={year}
              onChange={(event) => setSelectedYear(event.target.value)}
            >
              {years.map((item) => (
                <option key={item} value={item}>
                  {item}
                  {item === COMPARATIVE_YEAR ? " (comparative column)" : ""}
                </option>
              ))}
            </select>
          </div>

        </div>


        <div className="control-group">

          <label htmlFor="dashboard-region">Region</label>

          <div className="select-control">
            <select
              id="dashboard-region"
              value={regionKey}
              onChange={(event) => setRegionKey(event.target.value)}
              disabled={!regions.data}
            >
              <option value="all">All regions</option>
              {regionOptions.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>

        </div>


        <div className="control-note">
          <span className="live-indicator" />
          Showing {basis.toLowerCase()} view · <YearLabel year={year} />
        </div>

      </div>

      {regions.error && (
        <LoadError error={regions.error} onRetry={regions.retry} compact />
      )}

      {region && regions.data && (
        <RegionView region={region} years={regions.data.years} year={year} />
      )}

      {region && (
        <div className="group-level-row">
          <GroupLevelNote region={region} />
        </div>
      )}

      <div className="metric-grid">

        {metricCards.map((card) => {
          const series = buildSeries(card.key, financials.data, metrics.data, year);
          const loading = card.key === "net_debt" ? metrics.loading : financials.loading;
          const failed = card.key === "net_debt" ? metrics.error : financials.error;
          const point = series?.points.find((item) => item.year === year);

          return (

            <button
              key={card.key}
              className={`metric-card ${
                activeMetric === card.key ? "metric-active" : ""
              }`}
              onClick={() => setActiveMetric(card.key)}
              title={point?.source}
            >

              <div className="metric-card-top">

                <span>{card.label}</span>

                <span className="metric-card-icon">
                  <Icon name={card.icon} size={18} />
                </span>

              </div>

              {loading ? (
                <strong className="metric-value-skeleton" />
              ) : failed || !point ? (
                <strong className="metric-value">
                  <Value value={null} />
                </strong>
              ) : (
                <strong className="metric-value">
                  <small>₹</small>
                  <Value value={point.value} restated={point.restated} />
                  <small>cr</small>
                </strong>
              )}

              <div className="metric-card-bottom">
                {loading ? (
                  <span>Loading {year}…</span>
                ) : failed ? (
                  <span>Could not load</span>
                ) : series?.yoy ? (
                  <span
                    className={`metric-change ${
                      series.yoy.change_pct < 0 ? "down" : "up"
                    }`}
                    title={`Change ${formatCrore(series.yoy.change)} crore from ${series.yoy.from} to ${series.yoy.to}`}
                  >
                    {formatChangePct(series.yoy.change_pct)} vs {series.yoy.from}
                    {series.yoy.restated_basis && (
                      <RestatedMark note="Compared on a restated basis: the prior year as presented in the latest report." />
                    )}
                  </span>
                ) : card.key !== "net_debt" && series ? (
                  <span>
                    YoY <Missing note={missingChangeNote(year)} />
                  </span>
                ) : (
                  <span>
                    <YearLabel year={year} /> · 5-year trend
                  </span>
                )}

                {card.key === "net_debt" && series ? (
                  <Sparkline
                    values={series.points.map((item) => item.value)}
                    highlightIndex={series.years.indexOf(year)}
                    width={72}
                    height={24}
                    label="Net debt, five-year trend"
                  />
                ) : (
                  <span className="metric-mini-line" />
                )}
              </div>

            </button>

          );
        })}

      </div>

      {(financials.error || metrics.error) && (
        <LoadError
          error={financials.error || metrics.error}
          onRetry={() => {
            if (financials.error) financials.retry();
            if (metrics.error) metrics.retry();
          }}
        />
      )}


      <div className="dashboard-main-grid">

        <section className="dashboard-panel performance-panel">

          <div className="panel-heading">

            <div>
              <h2>Financial performance</h2>
              <p>
                {activeCard?.label} · {basis} · {years[0]} to {lastYear(years)}
              </p>
              <GroupLevelNote region={region} />
            </div>


          </div>


          <div className="chart-legend">
            <span>
              <i className="legend-dot green" />
              {activeCard?.label}
            </span>

            <span>
              <i className="legend-dot blue" />
              Selected year: {year}
            </span>

            <span className="chart-period-note">
              INR crore · hover a point for its value and source
            </span>
          </div>

          {activeLoading ? (
            <div className="chart-area">
              <div className="chart-empty-overlay">
                <span className="chart-empty-icon">
                  <Icon name="chart" size={24} />
                </span>
                <strong>Loading figures…</strong>
              </div>
            </div>
          ) : activeError || !activeSeries ? (
            <LoadError error={activeError} onRetry={activeRetry} compact />
          ) : (
            <PerformanceChart
              series={activeSeries}
              label={activeCard?.label}
              selectedYear={year}
            />
          )}

        </section>


        <section className="dashboard-panel ratios-panel">

          <div className="panel-heading">

            <div>
              <h2>Financial ratios</h2>
              <p>Calculated from verified statement inputs.</p>
              <GroupLevelNote region={region} />
            </div>

            <span className="panel-icon">
              <Icon name="layers" size={20} />
            </span>

          </div>


          <div className="ratio-list">

            {metrics.loading &&
              RATIO_KEYS.map((key) => (
                <div className="ratio-item" key={key}>
                  <div className="ratio-topline">
                    <span className="metric-value-skeleton ratio-skeleton" />
                  </div>
                  <div className="ratio-track" />
                </div>
              ))}

            {metrics.error && (
              <LoadError error={metrics.error} onRetry={metrics.retry} compact />
            )}

            {metrics.data &&
              RATIO_KEYS.map((key) => {
                const metric = metrics.data.metrics.find((item) => item.key === key);
                if (!metric) return null;

                const metricYears = metrics.data.years;
                const values = metricYears.map((fy) => metric.values[fy] ?? null);
                const selectedValue = metric.values[year] ?? null;
                const largest = Math.max(
                  ...values.filter((value) => value != null).map(Math.abs),
                );
                const width =
                  selectedValue == null || !largest
                    ? 0
                    : (Math.abs(selectedValue) / largest) * 100;

                return (

                  <div className="ratio-item" key={key}>

                    <div className="ratio-topline">
                      <span title={metric.formula}>{metric.name}</span>
                      <strong>
                        <Value
                          value={selectedValue}
                          missingNote={
                            year === COMPARATIVE_YEAR
                              ? "Needs the average of FY2020-21 and FY2021-22 equity; FY2020-21 is outside the four reports"
                              : "Not reported"
                          }
                          format={(value) =>
                            formatMetric(value, metric.unit, metric.decimals)
                          }
                        />
                      </strong>
                    </div>

                    <div className="ratio-track">
                      <i
                        className={selectedValue < 0 ? "negative" : ""}
                        style={{
                          width: `${width}%`,
                        }}
                      />
                    </div>

                    <div className="ratio-footline">
                      <small>
                        {year} · {metric.higher_is_better ? "higher" : "lower"} is
                        better
                      </small>
                      <Sparkline
                        values={values}
                        highlightIndex={metricYears.indexOf(year)}
                        width={96}
                        height={26}
                        label={`${metric.name}, ${metricYears[0]} to ${lastYear(metricYears)}: ${values
                          .map((value) => formatMetric(value, metric.unit, metric.decimals))
                          .join(", ")}`}
                      />
                    </div>

                  </div>

                );
              })}

          </div>

          {metrics.data && (
            <p className="panel-footnote">
              Bars compare the {year} value with the ratio's own 5-year high;
              the line shows {metrics.data.years[0]} to {lastYear(metrics.data.years)},
              with {year} marked.
            </p>
          )}

        </section>

      </div>


      <div className="dashboard-main-grid dashboard-insight-grid">

        <section className="dashboard-panel scores-panel">

          <div className="panel-heading">

            <div>
              <h2>Composite scores</h2>
              <p>
                {basis} · Altman Z'', Piotroski F and Beneish M for each year,
                computed from the reported statements.
              </p>
              <GroupLevelNote region={region} />
            </div>

            <span className="panel-icon">
              <Icon name="check" size={20} />
            </span>

          </div>

          {scores.loading && <div className="evidence-skeleton wide" />}

          {scores.error && (
            <LoadError error={scores.error} onRetry={scores.retry} compact />
          )}

          {scores.data && (
            <>
              <div className="table-scroll">
                <table className="data-table scores-table">
                  <thead>
                    <tr>
                      <th scope="col">Score</th>
                      {scores.data.years.map((fy) => (
                        <th scope="col" key={fy} className={selectedCol(fy)}>
                          <YearLabel year={fy} />
                        </th>
                      ))}
                    </tr>
                  </thead>

                  <tbody>
                    {scoreRows.map((row) => {
                      const results = scores.data.scores[row.key] || {};
                      const thresholds = Object.values(results).find(
                        (result) => result?.thresholds,
                      )?.thresholds;

                      return (
                        <tr key={row.key}>
                          <th scope="row">
                            <strong>{row.name}</strong>
                            <small>
                              {row.meaning}
                              {thresholds && ` ${thresholds}.`}
                            </small>
                          </th>

                          {scores.data.years.map((fy) => {
                            const result = results[fy];
                            const tone = zoneTone(row.key, result);

                            return (
                              <td key={fy} className={selectedCol(fy)}>
                                {result?.score == null ? (
                                  <Missing
                                    note={
                                      fy === COMPARATIVE_YEAR
                                        ? NEEDS_PRIOR_YEAR_NOTE
                                        : sentenceCase(result?.reason) || "Not reported"
                                    }
                                  />
                                ) : (
                                  <>
                                    <b>{formatScore(row, result.score)}</b>
                                    <span className={`zone-chip ${tone}`}>
                                      {zoneLabel(row.key, result)}
                                    </span>
                                  </>
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <p className="panel-footnote">
                Altman Z'' uses the actual retained earnings from each report's
                "Other equity" note (verified on the page) and book equity in
                place of market value. FY2021-22 comes from the FY2022-23
                report's comparative column; Piotroski F and Beneish M compare
                with the prior year, so they need FY2020-21, which is outside
                the four reports.
                <button
                  type="button"
                  className="text-link"
                  onClick={() => setActivePage("Sources")}
                >
                  How these are calculated
                  <Icon name="arrow" size={14} />
                </button>
              </p>
            </>
          )}

        </section>


        <section className="dashboard-panel health-panel">

          <div className="panel-heading">

            <div>
              <h2>Financial health summary</h2>
              <p>
                {basis} · {year} · values exactly as the API reports them.
              </p>
              <GroupLevelNote region={region} />
            </div>

            <span className="panel-icon">
              <Icon name="shield" size={20} />
            </span>

          </div>

          <HealthSummary
            financials={financials}
            metrics={metrics}
            scores={scores}
            year={year}
          />

          <button
            type="button"
            className="button button-primary health-ask"
            onClick={() => onAskEdith(VERDICT_QUESTION)}
          >
            Ask Edith for the full verdict
            <Icon name="arrow" size={16} />
          </button>

        </section>

      </div>


      <section className="dashboard-panel segments-panel">

        <div className="panel-heading">

          <div>
            <h2>Segments</h2>
            <p>
              Consolidated only: segments are reported in the consolidated
              statements, so this card does not change with the basis toggle.
              INR crore.
            </p>
          </div>

          <div className="segmented-control">
            {[
              ["segment_revenue", "Revenue"],
              ["segment_results", "EBITDA"],
            ].map(([key, label]) => (
              <button
                key={key}
                className={segmentItem === key ? "selected" : ""}
                onClick={() => setSegmentItem(key)}
              >
                {label}
              </button>
            ))}
          </div>

        </div>

        {segments.loading && <div className="evidence-skeleton wide" />}

        {segments.error && (
          <LoadError error={segments.error} onRetry={segments.retry} compact />
        )}

        {segments.data && (
          <>
            <div className="table-scroll">
              <table className="data-table segments-table">
                <thead>
                  <tr>
                    <th scope="col">
                      {segmentItem === "segment_results"
                        ? "Segment EBITDA (segment results)"
                        : "Segment revenue"}
                    </th>
                    {segments.data.years.map((fy) => (
                      <th scope="col" key={fy} className={selectedCol(fy)}>
                        <YearLabel year={fy} />
                      </th>
                    ))}
                  </tr>
                </thead>

                <tbody>
                  {[
                    ...segments.data.segments,
                    { ...segments.data.eliminations, rowClass: "subtotal-row" },
                    { ...segments.data.totals, rowClass: "total-row" },
                  ].map((segment) => (
                    <tr key={segment.key} className={segment.rowClass || ""}>
                      <th scope="row">{segment.name}</th>

                      {segments.data.years.map((fy) => {
                        const value = segment.values?.[fy]?.[segmentItem];
                        const source = segment.sources?.[fy];
                        const restated = segment.restated?.[fy]?.includes(segmentItem);

                        return (
                          <td
                            key={fy}
                            className={[value < 0 ? "negative" : "", selectedCol(fy) || ""]
                              .join(" ")
                              .trim() || undefined}
                            title={
                              source && value != null
                                ? `${source.report} report, page ${source.page_label}`
                                : undefined
                            }
                          >
                            <Value
                              value={value}
                              restated={restated}
                              restatedNote={RESTATED_SEGMENT_NOTE}
                              missingNote="The segment was not reported this year"
                            />
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="panel-footnote">
              {segments.data.note} Tata Steel Europe was reported until
              FY2023-24 and is split into Netherlands and UK operations from
              FY2024-25; Tata Steel Long Products (FY2021-22) was merged into
              Tata Steel India. "n/a" means the segment was not reported that
              year. <RestatedMark note={RESTATED_SEGMENT_NOTE} /> marks a
              restated value.
            </p>
          </>
        )}

      </section>


      <section className="dashboard-panel statement-panel statement-panel-full">

        <div className="panel-heading">

          <div>
            <h2>Statement coverage</h2>
            <p>
              {basis} primary statements behind this dashboard. Each chip opens
              only that statement's pages from the annual report.
            </p>
          </div>


        </div>


        {statementRows.map(([key, name, detail]) => (

          <div className="statement-row" key={key}>

            <span className="statement-icon">
              <Icon name="file" size={18} />
            </span>

            <div>
              <strong>{name}</strong>
              <small>{detail}</small>

              {statements.data && (
                <span className="report-links">
                  {statements.data.years.map((fy) => {
                    const entry = statements.data.statements[fy]?.[key];
                    if (!entry) return null;

                    const pages = entry.page_labels.join("-");
                    const title = `${name}, ${fy} (${scope}): ${entry.report} report, ${
                      entry.page_labels.length > 1 ? "pages" : "page"
                    } ${entry.page_labels.join(", ")}${
                      fy === COMPARATIVE_YEAR ? `. ${COMPARATIVE_NOTE}` : ""
                    }`;

                    return (
                      <a
                        key={fy}
                        className={selectedCol(fy)}
                        href={entry.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={title}
                      >
                        <YearLabel year={fy} />
                        <em>{pages}</em>
                        <Icon name="external" size={12} />
                      </a>
                    );
                  })}
                </span>
              )}
            </div>


          </div>

        ))}

        {statements.loading && <div className="evidence-skeleton wide" />}

        {statements.error && (
          <LoadError error={statements.error} onRetry={statements.retry} compact />
        )}

      </section>

    </main>
  );
}

/* ---------------------------------------------------------
   Financial health summary: a factual list, no narrative
   --------------------------------------------------------- */

function HealthSummary({ financials, metrics, scores, year }) {
  if (financials.loading || metrics.loading || scores.loading) {
    return (
      <div className="health-list">
        <div className="evidence-skeleton wide" />
        <div className="evidence-skeleton" />
        <div className="evidence-skeleton wide" />
      </div>
    );
  }

  const failed = financials.error || metrics.error || scores.error;
  if (failed) {
    return (
      <LoadError
        error={failed}
        onRetry={() => {
          if (financials.error) financials.retry();
          if (metrics.error) metrics.retry();
          if (scores.error) scores.retry();
        }}
        compact
      />
    );
  }

  const altman = scores.data.scores.altman_z?.[year];
  const piotroski = scores.data.scores.piotroski_f?.[year];
  const metric = (key) => metrics.data.metrics.find((item) => item.key === key);
  const currentRatio = metric("current_ratio");
  const debtToEquity = metric("debt_to_equity");
  const netDebt = metric("net_debt");
  const profit = financials.data.items.profit_for_the_year;
  const profitChange = profit?.yoy_changes.find((change) => change.to === year);

  const rows = [
    {
      label: `Altman Z'' (${year})`,
      value: altman?.score == null ? null : formatNumber(altman.score, 4),
      chip: altman?.score != null && zoneLabel("altman_z", altman),
      tone: zoneTone("altman_z", altman),
    },
    {
      label: `Piotroski F (${year})`,
      value: piotroski?.score == null ? null : `${piotroski.score}/9`,
      chip: sentenceCase(piotroski?.interpretation),
      tone: zoneTone("piotroski_f", piotroski),
      missingNote: year === COMPARATIVE_YEAR ? NEEDS_PRIOR_YEAR_NOTE : undefined,
    },
    {
      label: `Current ratio (${year})`,
      value: formatMetric(currentRatio?.values[year], "x", currentRatio?.decimals),
      raw: currentRatio?.values[year],
    },
    {
      label: `Debt-to-equity (${year})`,
      value: formatMetric(debtToEquity?.values[year], "x", debtToEquity?.decimals),
      raw: debtToEquity?.values[year],
    },
    {
      label: `Net debt (${year})`,
      value:
        netDebt?.values[year] == null
          ? null
          : `₹ ${formatCrore(netDebt.values[year])} cr`,
    },
    {
      label: `Profit for the year (${year})`,
      value:
        profit?.values[year]?.value == null
          ? null
          : `₹ ${formatCrore(profit.values[year].value)} cr`,
      chip: profitChange && `${formatChangePct(profitChange.change_pct)} YoY`,
      tone: profitChange ? (profitChange.change_pct < 0 ? "distress" : "safe") : null,
    },
  ];

  return (
    <ul className="health-list">
      {rows.map((row) => (
        <li key={row.label}>
          <span>{row.label}</span>
          <strong>
            {row.value == null || ("raw" in row && row.raw == null) ? (
              <Missing note={row.missingNote || "Not reported"} />
            ) : (
              row.value
            )}
          </strong>
          {row.chip && <span className={`zone-chip ${row.tone || "neutral"}`}>{row.chip}</span>}
        </li>
      ))}
    </ul>
  );
}
