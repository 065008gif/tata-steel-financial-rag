import { useState } from "react";
import {
  getFinancials,
  getMetrics,
  getReports,
  getScores,
  getSegments,
} from "../api.js";
import { VERDICT_QUESTION } from "./AskPage.jsx";
import {
  Icon,
  LoadError,
  RestatedMark,
  Sparkline,
  Value,
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

const RESTATED_SEGMENT_NOTE =
  "Restated: a later report presents a different figure for this year; the latest report's figure is shown.";

/* ---------------------------------------------------------
   Helpers
   --------------------------------------------------------- */

function lastYear(years) {
  return years?.[years.length - 1];
}

/** One item's five years from /api/financials or /api/metrics. */
function buildSeries(key, financials, metrics) {
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

  const latest = lastYear(financials.years);

  return {
    years: financials.years,
    points: financials.years.map((year) => ({
      year,
      value: item.values[year]?.value ?? null,
      restated: Boolean(item.values[year]?.restated),
      source: item.values[year]?.source,
    })),
    yoy: item.yoy_changes.find((change) => change.to === latest) || null,
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

function PerformanceChart({ series, label }) {
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

              <linearGradient id="chartStroke" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="#0d9d79" />
                <stop offset="100%" stopColor="#4c8ce8" />
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
              stroke="url(#chartStroke)"
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
              className={`chart-point ${point.index === count - 1 ? "latest" : ""} ${
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
              style={{ left: `${(xAt(index) / CHART_WIDTH) * 100}%` }}
            >
              {point.year}
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
   Page
   --------------------------------------------------------- */

export default function DashboardPage({ setActivePage, onAskEdith }) {
  const [basis, setBasis] = useState("Consolidated");
  const [period, setPeriod] = useState("Annual");
  const [activeMetric, setActiveMetric] = useState("revenue_from_operations");
  const [segmentItem, setSegmentItem] = useState("segment_revenue");

  const scope = basis.toLowerCase();

  const financials = useApi(() => getFinancials(FINANCIAL_ITEMS, scope), `financials-${scope}`);
  const metrics = useApi(() => getMetrics(scope), `metrics-${scope}`);
  const scores = useApi(() => getScores(scope), `scores-${scope}`);
  const segments = useApi(getSegments, "segments");
  const reports = useApi(getReports, "reports");

  const latest = lastYear(financials.data?.years || metrics.data?.years);
  const activeCard = metricCards.find((card) => card.key === activeMetric);
  const activeSeries = buildSeries(activeMetric, financials.data, metrics.data);
  const activeLoading = activeMetric === "net_debt" ? metrics.loading : financials.loading;
  const activeError = activeMetric === "net_debt" ? metrics.error : financials.error;
  const activeRetry = activeMetric === "net_debt" ? metrics.retry : financials.retry;

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

          <label>Period</label>

          <div className="segmented-control">

            {["Annual"].map((item) => (

              <button
                key={item}
                className={period === item ? "selected" : ""}
                onClick={() => setPeriod(item)}
              >
                {item}
              </button>

            ))}

          </div>

        </div>


        <div className="control-note">
          <span className="live-indicator" />
          Showing {basis.toLowerCase()} view · {period.toLowerCase()} periods
          {financials.data && ` · ${financials.data.years[0]} to ${latest}`}
        </div>

      </div>


      <div className="metric-grid">

        {metricCards.map((card) => {
          const series = buildSeries(card.key, financials.data, metrics.data);
          const loading = card.key === "net_debt" ? metrics.loading : financials.loading;
          const failed = card.key === "net_debt" ? metrics.error : financials.error;
          const latestPoint = series?.points[series.points.length - 1];

          return (

            <button
              key={card.key}
              className={`metric-card ${
                activeMetric === card.key ? "metric-active" : ""
              }`}
              onClick={() => setActiveMetric(card.key)}
              title={latestPoint?.source}
            >

              <div className="metric-card-top">

                <span>{card.label}</span>

                <span className="metric-card-icon">
                  <Icon name={card.icon} size={18} />
                </span>

              </div>

              {loading ? (
                <strong className="metric-value-skeleton" />
              ) : failed || !latestPoint ? (
                <strong className="metric-value">
                  <Value value={null} />
                </strong>
              ) : (
                <strong className="metric-value">
                  <small>₹</small>
                  <Value value={latestPoint.value} restated={latestPoint.restated} />
                  <small>cr</small>
                </strong>
              )}

              <div className="metric-card-bottom">
                {loading ? (
                  <span>Loading {latest || "latest year"}…</span>
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
                ) : (
                  <span>{latestPoint?.year} · 5-year trend</span>
                )}

                {card.key === "net_debt" && series ? (
                  <Sparkline
                    values={series.points.map((point) => point.value)}
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
                {activeCard?.label} · {basis} · {period}
              </p>
            </div>


          </div>


          <div className="chart-legend">
            <span>
              <i className="legend-dot green" />
              Reported value
            </span>

            <span>
              <i className="legend-dot blue" />
              Latest year{latest ? ` (${latest})` : ""}
            </span>

            <span className="chart-period-note">
              INR crore · hover a point for its source
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
            <PerformanceChart series={activeSeries} label={activeCard?.label} />
          )}

        </section>


        <section className="dashboard-panel ratios-panel">

          <div className="panel-heading">

            <div>
              <h2>Financial ratios</h2>
              <p>Calculated from verified statement inputs.</p>
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

                const years = metrics.data.years;
                const values = years.map((year) => metric.values[year] ?? null);
                const latestValue = values[values.length - 1];
                const largest = Math.max(
                  ...values.filter((value) => value != null).map(Math.abs),
                );
                const width =
                  latestValue == null || !largest
                    ? 0
                    : (Math.abs(latestValue) / largest) * 100;

                return (

                  <div className="ratio-item" key={key}>

                    <div className="ratio-topline">
                      <span title={metric.formula}>{metric.name}</span>
                      <strong>
                        <Value
                          value={latestValue}
                          format={(value) =>
                            formatMetric(value, metric.unit, metric.decimals)
                          }
                        />
                      </strong>
                    </div>

                    <div className="ratio-track">
                      <i
                        className={latestValue < 0 ? "negative" : ""}
                        style={{
                          width: `${width}%`,
                        }}
                      />
                    </div>

                    <div className="ratio-footline">
                      <small>
                        {lastYear(years)} · {metric.higher_is_better ? "higher" : "lower"} is
                        better
                      </small>
                      <Sparkline
                        values={values}
                        width={58}
                        height={16}
                        label={`${metric.name}, ${years[0]} to ${lastYear(years)}: ${values
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
              Bars compare the latest value with the ratio's own 5-year high;
              the line shows {metrics.data.years[0]} to {lastYear(metrics.data.years)}.
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
                      {scores.data.years.map((year) => (
                        <th scope="col" key={year}>{year}</th>
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

                          {scores.data.years.map((year) => {
                            const result = results[year];
                            const tone = zoneTone(row.key, result);

                            return (
                              <td key={year}>
                                {result?.score == null ? (
                                  <span className="value-missing" title={result?.reason || "Not reported"}>
                                    —
                                  </span>
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
                place of market value.
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
                {basis} · {latest || "latest year"} · values exactly as the
                API reports them.
              </p>
            </div>

            <span className="panel-icon">
              <Icon name="shield" size={20} />
            </span>

          </div>

          <HealthSummary
            financials={financials}
            metrics={metrics}
            scores={scores}
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
                    {segments.data.years.map((year) => (
                      <th scope="col" key={year}>{year}</th>
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

                      {segments.data.years.map((year) => {
                        const value = segment.values?.[year]?.[segmentItem];
                        const source = segment.sources?.[year];
                        const restated = segment.restated?.[year]?.includes(segmentItem);

                        return (
                          <td
                            key={year}
                            className={value < 0 ? "negative" : ""}
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
              Tata Steel India. "—" means the segment was not reported that
              year. <RestatedMark note={RESTATED_SEGMENT_NOTE} /> marks a
              restated value.
            </p>
          </>
        )}

      </section>


      <div className="dashboard-bottom-grid">

        <section className="dashboard-panel statement-panel">

          <div className="panel-heading">

            <div>
              <h2>Statement coverage</h2>
              <p>Report sections behind this dashboard, with the annual report PDFs.</p>
            </div>


          </div>


          {[
            ["Income statement", "Revenue, costs, and profit"],
            ["Balance sheet", "Assets, liabilities, and equity"],
            [
              "Cash flow statement",
              "Operating, investing, and financing cash flows",
            ],
          ].map(([name, detail]) => (

            <div className="statement-row" key={name}>

              <span className="statement-icon">
                <Icon name="file" size={18} />
              </span>

              <div>
                <strong>{name}</strong>
                <small>{detail}</small>

                {reports.data && (
                  <span className="report-links">
                    {reports.data.map((report) => (
                      <a
                        key={report.fiscal_year}
                        href={report.pdf_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={report.title}
                      >
                        {report.fiscal_year}
                        <Icon name="external" size={12} />
                      </a>
                    ))}
                  </span>
                )}
              </div>


            </div>

          ))}

          {reports.error && (
            <LoadError error={reports.error} onRetry={reports.retry} compact />
          )}

        </section>


        <aside className="dashboard-notice">

          <div className="notice-icon">
            <Icon name="shield" size={21} />
          </div>

          <div>

            <h3>Every figure is verified</h3>

            <p>
              Figures come from the reported statements. The balance-sheet
              identity and statement subtotals are checked, restated figures
              are marked, and every source page is one click away.
            </p>

            <div className="notice-footer">
              <span className="notice-dot" />
              Source-linked figures only
            </div>

          </div>

        </aside>

      </div>

    </main>
  );
}

/* ---------------------------------------------------------
   Financial health summary: a factual list, no narrative
   --------------------------------------------------------- */

function HealthSummary({ financials, metrics, scores }) {
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

  const scoreYear = lastYear(scores.data.years);
  const altman = scores.data.scores.altman_z?.[scoreYear];
  const piotroski = scores.data.scores.piotroski_f?.[scoreYear];
  const metricYear = lastYear(metrics.data.years);
  const metric = (key) => metrics.data.metrics.find((item) => item.key === key);
  const currentRatio = metric("current_ratio");
  const debtToEquity = metric("debt_to_equity");
  const netDebt = metric("net_debt");
  const profit = financials.data.items.profit_for_the_year;
  const profitYear = lastYear(financials.data.years);
  const profitChange = profit?.yoy_changes.find((change) => change.to === profitYear);

  const rows = [
    {
      label: `Altman Z'' (${scoreYear})`,
      value: altman?.score == null ? null : formatNumber(altman.score, 4),
      chip: altman && zoneLabel("altman_z", altman),
      tone: zoneTone("altman_z", altman),
    },
    {
      label: `Piotroski F (${scoreYear})`,
      value: piotroski?.score == null ? null : `${piotroski.score}/9`,
      chip: sentenceCase(piotroski?.interpretation),
      tone: zoneTone("piotroski_f", piotroski),
    },
    {
      label: `Current ratio (${metricYear})`,
      value: formatMetric(currentRatio?.values[metricYear], "x", currentRatio?.decimals),
      raw: currentRatio?.values[metricYear],
    },
    {
      label: `Debt-to-equity (${metricYear})`,
      value: formatMetric(debtToEquity?.values[metricYear], "x", debtToEquity?.decimals),
      raw: debtToEquity?.values[metricYear],
    },
    {
      label: `Net debt (${metricYear})`,
      value:
        netDebt?.values[metricYear] == null
          ? null
          : `₹ ${formatCrore(netDebt.values[metricYear])} cr`,
    },
    {
      label: `Profit for the year (${profitYear})`,
      value:
        profit?.values[profitYear]?.value == null
          ? null
          : `₹ ${formatCrore(profit.values[profitYear].value)} cr`,
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
              <Value value={null} />
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
