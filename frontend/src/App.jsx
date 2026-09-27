import { useEffect, useState } from "react";
import "./App.css";
import "./readability.css";
import {
  getCompany,
  getFinancials,
  getHealth,
  getMetrics,
  getScores,
} from "./api.js";
import AskPage, { DUPONT_QUESTION, PROFIT_TREND_QUESTION } from "./components/AskPage.jsx";
import DashboardPage from "./components/DashboardPage.jsx";
import EvaluationPage from "./components/EvaluationPage.jsx";
import SourcesPage from "./components/SourcesPage.jsx";
import {
  COVERAGE_TEXT,
  Icon,
  LoadError,
  RestatedMark,
  SectionHeading,
  Value,
  formatChangePct,
  formatCrore,
  formatNumber,
  sentenceCase,
  useApi,
} from "./components/ui.jsx";
import { useConversations } from "./useConversations.js";

const pages = ["Home", "Ask Edith", "Dashboard", "Evaluation", "Sources"];

const HEALTH_POLL_MS = 60_000;

function Brand({ compact = false }) {
  return (
    <div className={`brand ${compact ? "brand-compact" : ""}`}>
      <div className="brand-mark">E</div>

      <div className="brand-copy">
        <strong>Edith</strong>
        <span>Tata Steel financial assistant</span>
      </div>
    </div>
  );
}

function Header({ activePage, setActivePage }) {
  const [menuOpen, setMenuOpen] = useState(false);

  function goTo(page) {
    setActivePage(page);
    setMenuOpen(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <header className="site-header">
      <div className="header-inner">
        <button
          className="brand-button"
          onClick={() => goTo("Home")}
          aria-label="Go to home"
        >
          <Brand />
        </button>

        <button
          className="mobile-menu-button"
          onClick={() => setMenuOpen((open) => !open)}
          aria-label={menuOpen ? "Close navigation" : "Open navigation"}
        >
          <Icon name={menuOpen ? "close" : "menu"} size={23} />
        </button>

        <nav className={`main-nav ${menuOpen ? "nav-open" : ""}`}>
          {pages.map((page) => (
            <button
              key={page}
              className={`nav-link ${activePage === page ? "active" : ""}`}
              onClick={() => goTo(page)}
            >
              {page}
            </button>
          ))}
        </nav>

        <div className="header-actions">
          <BackendStatus />

          <button className="header-cta" onClick={() => goTo("Ask Edith")}>
            Ask Edith <Icon name="arrow" size={16} />
          </button>
        </div>
      </div>
    </header>
  );
}

/* Live backend status from /api/health, polled every 60 s. */
function BackendStatus() {
  const [health, setHealth] = useState({ state: "checking", detail: null });

  useEffect(() => {
    let active = true;

    function check() {
      getHealth().then(
        (data) =>
          active &&
          setHealth({
            state: data.status === "ok" ? "live" : "degraded",
            detail: data,
          }),
        () => active && setHealth({ state: "offline", detail: null }),
      );
    }

    check();
    const timer = setInterval(check, HEALTH_POLL_MS);

    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  const labels = {
    checking: "Checking",
    live: "Live",
    degraded: "Degraded",
    offline: "Offline",
  };

  const title =
    health.state === "live" || health.state === "degraded"
      ? `Backend ${health.state} · model ${health.detail.llm_model} · ${
          health.detail.index_points ?? "no"
        } indexed passages · reports ${health.detail.reports.join(", ")}`
      : health.state === "offline"
        ? "Edith's backend is not reachable"
        : "Checking the backend";

  return (
    <span
      className={`backend-status ${health.state}`}
      title={title}
      role="status"
      aria-label={title}
    >
      <i />
      {labels[health.state]}
    </span>
  );
}

/* =========================================================
   HOME PAGE
   ========================================================= */

function HomePage({ setActivePage, onAskEdith }) {
  const [expandedStep, setExpandedStep] = useState(0);

  const steps = [
    {
      number: "01",
      title: "Ask",
      description: "Start with a plain-language question about Tata Steel.",
      detail:
        "Ask about profitability, liquidity, risk, segments, cash flow, or another financial topic.",
      icon: "search",
    },
    {
      number: "02",
      title: "Retrieve",
      description: "Find the relevant passage in connected reports.",
      detail:
        "Edith will retrieve the supporting report text together with its document, reporting period and page reference.",
      icon: "file",
    },
    {
      number: "03",
      title: "Verify",
      description: "Check the answer against its evidence.",
      detail:
        "The answer should be traceable to the cited source. If the evidence is unavailable, Edith should say so rather than invent a figure.",
      icon: "check",
    },
  ];

  return (
    <main className="page home-page">

      {/* HERO */}
      <section className="hero-section">

        <div className="hero-background-glow hero-glow-green" />
        <div className="hero-background-glow hero-glow-blue" />
        <div className="hero-grid-glow" />

        <div className="hero-copy">

          <div className="tata-hero-badge">
            <span className="tata-badge-dot" />
            <span>TATA STEEL</span>
            <small>FINANCIAL RESEARCH</small>
          </div>

          <h1>
            Understand
            <br />
            <span>Tata Steel.</span>
            <br />
            Follow the evidence.
          </h1>

          <p className="hero-description">
            Meet Edith, a financial research assistant built around Tata
            Steel's reports. Ask questions about performance, disclosures and
            financial trends, then trace the answer back to its source.
          </p>

          <div className="hero-actions">
            <button
              className="button button-primary button-large"
              onClick={() => setActivePage("Ask Edith")}
            >
              Ask Edith
              <Icon name="arrow" size={18} />
            </button>

            <button
              className="button button-secondary button-large"
              onClick={() => setActivePage("Dashboard")}
            >
              Explore dashboard
            </button>
          </div>

          <div className="hero-note">
            <span className="note-dot" />
            <span>
              Live · {COVERAGE_TEXT}
            </span>
          </div>

        </div>


        {/* CUSTOM HERO VISUAL */}
        <div
          className="hero-art tata-hero-art"
          aria-label="Tata Steel financial intelligence visual"
        >

          <div className="hero-art-orbit orbit-large" />
          <div className="hero-art-orbit orbit-small" />

          <div className="steel-data-core">

            <div className="tata-wordmark">
              <span>TATA</span>
              <strong>STEEL</strong>
            </div>

            <div className="steel-core-glow" />

            <div className="steel-core-ring ring-one" />
            <div className="steel-core-ring ring-two" />
            <div className="steel-core-ring ring-three" />

            <div className="steel-core-center">
              <span>FINANCIAL</span>
              <strong>INTELLIGENCE</strong>
              <small>EDITH · TATA STEEL</small>
            </div>

            <div className="steel-chart-lines">
              <span />
              <span />
              <span />
              <span />
              <span />
              <span />
            </div>

            <svg
              className="hero-financial-line"
              viewBox="0 0 500 220"
              preserveAspectRatio="none"
            >
              <defs>
                <linearGradient
                  id="heroLineGradient"
                  x1="0"
                  y1="0"
                  x2="1"
                  y2="0"
                >
                  <stop offset="0%" stopColor="#11a985" />
                  <stop offset="52%" stopColor="#27bca0" />
                  <stop offset="100%" stopColor="#4e8ff0" />
                </linearGradient>
              </defs>

              <path
                d="M10 175 C65 155 82 158 120 125 S188 138 224 96 S286 116 325 80 S392 92 430 46 S468 52 495 22"
                fill="none"
                stroke="url(#heroLineGradient)"
                strokeWidth="5"
                strokeLinecap="round"
              />

              <circle cx="120" cy="125" r="6" />
              <circle cx="224" cy="96" r="6" />
              <circle cx="325" cy="80" r="6" />
              <circle cx="430" cy="46" r="6" />
            </svg>

          </div>


          <div className="floating-finance-card finance-card-one">
            <div className="finance-card-icon green">
              <Icon name="chart" size={19} />
            </div>

            <div>
              <small>Financial performance</small>
              <strong>Trace the trend</strong>
            </div>
          </div>


          <div className="floating-finance-card finance-card-two">
            <div className="finance-card-icon blue">
              <Icon name="file" size={19} />
            </div>

            <div>
              <small>Report evidence</small>
              <strong>Page-linked source</strong>
            </div>
          </div>


          <div className="floating-finance-card finance-card-three">
            <div className="finance-status-dot" />
            <span>Evidence trail active</span>
          </div>


          <div className="hero-spark spark-one">✦</div>
          <div className="hero-spark spark-two">✧</div>
          <div className="hero-spark spark-three">✦</div>

        </div>

      </section>


      {/* AT A GLANCE (live data) */}
      <GlanceSection
        setActivePage={setActivePage}
        onAskEdith={onAskEdith}
      />


      {/* TRUST STRIP */}
      <section className="trust-strip">

        <div className="trust-intro">
          <span className="trust-icon">
            <Icon name="shield" size={20} />
          </span>

          <div>
            <strong>Built for financial research</strong>
            <span>
              Clear answers. Visible evidence. No made-up numbers.
            </span>
          </div>
        </div>

        <div className="trust-item">
          <Icon name="file" size={18} />
          Tata Steel reports
        </div>

        <div className="trust-item">
          <Icon name="search" size={18} />
          Plain-language questions
        </div>

        <div className="trust-item">
          <Icon name="check" size={18} />
          Source verification
        </div>

      </section>


      {/* WHAT EDITH DOES */}
      <section className="content-section feature-section">

        <SectionHeading
          eyebrow="WHAT EDITH DOES"
          title="Research Tata Steel without losing the story behind the numbers."
          description="A financial research interface that brings questions, reports, evidence and financial trends into one place."
        />

        <div className="feature-grid">

          <article className="feature-card feature-green">
            <div className="feature-icon">
              <Icon name="search" size={25} />
            </div>

            <span className="feature-number">01 / ASK</span>

            <h3>Ask in plain language</h3>

            <p>
              Ask about profitability, liquidity, risk, segments or a specific
              section of a Tata Steel report.
            </p>

            <button
              className="text-link"
              onClick={() => setActivePage("Ask Edith")}
            >
              Try a question
              <Icon name="arrow" size={16} />
            </button>
          </article>


          <article className="feature-card feature-blue">
            <div className="feature-icon">
              <Icon name="file" size={25} />
            </div>

            <span className="feature-number">02 / TRACE</span>

            <h3>See the supporting passage</h3>

            <p>
              Review the source excerpt alongside the answer, including the
              report, period and page reference.
            </p>

            <button
              className="text-link"
              onClick={() => setActivePage("Ask Edith")}
            >
              See the query view
              <Icon name="arrow" size={16} />
            </button>
          </article>


          <article className="feature-card feature-explore">
            <div className="feature-trend-art" aria-hidden="true">
              <svg viewBox="0 0 220 100" role="presentation">
                <path className="trend-area" d="M4 78 C30 71 35 54 59 60 S94 75 117 49 S151 44 169 31 S196 39 216 8 L216 96 L4 96 Z" />
                <path className="trend-line" d="M4 78 C30 71 35 54 59 60 S94 75 117 49 S151 44 169 31 S196 39 216 8" />
                <circle cx="117" cy="49" r="4" />
                <circle cx="169" cy="31" r="4" />
                <circle cx="216" cy="8" r="4" />
              </svg>
            </div>
            <div className="feature-icon">
              <Icon name="chart" size={25} />
            </div>

            <span className="feature-number">03 / EXPLORE</span>

            <h3>Explore financial trends</h3>

            <p>
              Review statements, trends, financial ratios, composite scores
              and segments from verified report data.
            </p>

            <button
              className="text-link"
              onClick={() => setActivePage("Dashboard")}
            >
              Open dashboard
              <Icon name="arrow" size={16} />
            </button>
          </article>

        </div>

      </section>


      {/* NEW ROADMAP */}
      <section className="content-section roadmap-section">

        <div className="roadmap-heading">

          <div>
            <div className="section-eyebrow">
              THE EDITH WORKFLOW
            </div>

            <h2>
              From question
              <br />
              to evidence.
            </h2>

            <p>
              Three connected steps turn a financial question into a
              traceable answer.
            </p>
          </div>

          <div className="roadmap-stamp">
            <Icon name="layers" size={21} />
            Evidence-first workflow
          </div>

        </div>


        <div className="visual-roadmap">

          <div className="roadmap-line">
            <span className="roadmap-line-progress" />
          </div>


          {steps.map((step, index) => (

            <button
              className={`roadmap-node ${
                expandedStep === index ? "expanded" : ""
              }`}
              key={step.number}
              onClick={() => setExpandedStep(index)}
            >

              <div className="roadmap-node-top">

                <div className="roadmap-node-number">
                  {step.number}
                </div>

                <div className="roadmap-node-icon">
                  <Icon name={step.icon} size={23} />
                </div>

              </div>


              <div className="roadmap-pointer">
                <span />
              </div>


              <h3>{step.title}</h3>

              <p>{step.description}</p>


              {expandedStep === index && (
                <div className="roadmap-detail">
                  {step.detail}
                </div>
              )}


              <span className="roadmap-more">
                {expandedStep === index
                  ? "Current step"
                  : "Explore step"}
              </span>

            </button>

          ))}

        </div>

      </section>


      {/* TATA STEEL FEATURE */}
      <section className="tata-feature">

        <div className="tata-feature-art">

          <div className="tata-glow" />

          <div className="steel-visual">

            <div className="steel-sun" />

            <div className="steel-plant plant-one">
              <i />
              <i />
              <i />
              <i />
            </div>

            <div className="steel-plant plant-two">
              <i />
              <i />
              <i />
            </div>

            <div className="steel-ground" />

          </div>

        </div>


        <div className="tata-feature-copy">

          <div className="section-eyebrow">
            TATA STEEL
          </div>

          <h2>
            One place to explore the story behind the numbers.
          </h2>

          <p>
            Edith is being built around Tata Steel's financial reports.
            Explore reported performance, look for supporting disclosures,
            and understand where each answer comes from.
          </p>

          <div className="tata-feature-points">

            <span>
              <Icon name="check" size={17} />
              Four annual reports, FY2022-23 to FY2025-26
            </span>

            <span>
              <Icon name="check" size={17} />
              Financial statements and disclosures
            </span>

            <span>
              <Icon name="check" size={17} />
              Evidence references and verification status
            </span>

          </div>

          <button
            className="button button-primary"
            onClick={() => setActivePage("Ask Edith")}
          >
            Ask about Tata Steel
            <Icon name="arrow" size={17} />
          </button>

        </div>

      </section>


      {/* CTA */}
      <section className="bottom-cta">

        <div className="bottom-cta-copy">

          <span className="cta-orb">
            <Icon name="spark" size={23} />
          </span>

          <div>
            <h2>Start with a question.</h2>

            <p>
              Ask about Tata Steel's financial reports and follow the evidence.
            </p>
          </div>

        </div>

        <button
          className="button button-light"
          onClick={() => setActivePage("Ask Edith")}
        >
          Open Ask Edith
          <Icon name="arrow" size={17} />
        </button>

      </section>

    </main>
  );
}


/* =========================================================
   HOME · AT A GLANCE (live data)
   ========================================================= */

// Same item list as the Dashboard, so the cached response is shared.
const GLANCE_ITEMS = [
  "revenue_from_operations",
  "profit_for_the_year",
  "net_cash_from_operating",
];

// The four report years (each has a prior year to compare with).
const GLANCE_YEARS = ["FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"];

const TRY_ASKING = [DUPONT_QUESTION, PROFIT_TREND_QUESTION];

function GlanceTile({ label, icon, loading, value, detail, source, tone }) {
  return (
    <article className="metric-card glance-tile">
      <div className="metric-card-top">
        <span>{label}</span>

        <span className="metric-card-icon">
          <Icon name={icon} size={18} />
        </span>
      </div>

      {loading ? (
        <strong className="metric-value-skeleton" />
      ) : (
        <strong className="metric-value">{value}</strong>
      )}

      <div className="metric-card-bottom">
        {detail ? (
          <span className={`zone-chip ${tone || "neutral"}`}>{detail}</span>
        ) : (
          <span />
        )}
      </div>

      {source && <small className="glance-source">{source}</small>}
    </article>
  );
}

/* "About Tata Steel": facts from /api/company, each with its page link. */
function AboutTataSteel() {
  const company = useApi(getCompany, "company");

  if (company.error) {
    return <LoadError error={company.error} onRetry={company.retry} compact />;
  }

  return (
    <div className="about-card">
      <div className="about-card-heading">
        <span className="statement-icon">
          <Icon name="book" size={18} />
        </span>

        <div>
          <h3>{company.data?.title || "About Tata Steel"}</h3>
          {company.data?.source && <small>{company.data.source}</small>}
        </div>
      </div>

      {company.loading ? (
        <>
          <div className="evidence-skeleton wide" />
          <div className="evidence-skeleton" />
        </>
      ) : (
        <ul className="about-facts">
          {company.data.facts.map((fact) => (
            <li key={fact.text}>
              <Icon name="check" size={16} />
              <span>
                {fact.text}{" "}
                <a
                  className="fact-page-link"
                  href={fact.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={`Open the ${fact.report} report at page ${fact.page_label}`}
                >
                  {fact.report}, p. {fact.page_label}
                  <Icon name="external" size={12} />
                </a>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* Short factual bullets, templated from API values only. */
function GlanceBullets({ year, revenue, profit, netDebt, altman, piotroski }) {
  const money = (value) => `₹ ${formatCrore(value)} crore`;
  const change = (entry) =>
    entry ? `, ${formatChangePct(entry.change_pct)} versus ${entry.from}` : "";

  const bullets = [
    revenue.point?.value != null &&
      `Revenue from operations was ${money(revenue.point.value)}${change(revenue.change)}.`,
    profit.point?.value != null &&
      `Profit for the year was ${money(profit.point.value)}${change(profit.change)}.`,
    netDebt != null && `Net debt was ${money(netDebt)}.`,
    altman?.score != null &&
      `Altman Z'' was ${formatNumber(altman.score, 4)}, in the ${altman.interpretation} zone.`,
    piotroski?.score != null &&
      `Piotroski F was ${piotroski.score}/9, rated ${piotroski.interpretation}.`,
  ].filter(Boolean);

  if (bullets.length === 0) return null;

  return (
    <div className="glance-bullets">
      <h3>How its financials look in {year}</h3>

      <ul>
        {bullets.map((text) => (
          <li key={text}>{text}</li>
        ))}
      </ul>
    </div>
  );
}

function GlanceSection({ setActivePage, onAskEdith }) {
  const [year, setYear] = useState(GLANCE_YEARS[GLANCE_YEARS.length - 1]);

  const financials = useApi(
    () => getFinancials(GLANCE_ITEMS, "consolidated"),
    "financials-consolidated",
  );
  const metrics = useApi(() => getMetrics("consolidated"), "metrics-consolidated");
  const scores = useApi(() => getScores("consolidated"), "scores-consolidated");

  function itemData(key) {
    const item = financials.data?.items[key];
    return {
      point: item?.values[year],
      change: item?.yoy_changes.find((entry) => entry.to === year),
    };
  }

  function itemTile(key, label, icon) {
    const { point, change } = itemData(key);

    return (
      <GlanceTile
        key={key}
        label={label}
        icon={icon}
        loading={financials.loading}
        value={
          <>
            <small>₹</small>
            <Value value={point?.value ?? null} restated={point?.restated} />
            <small>cr</small>
          </>
        }
        detail={
          change && (
            <>
              {formatChangePct(change.change_pct)} YoY
              {change.restated_basis && <RestatedMark />}
            </>
          )
        }
        tone={change ? (change.change_pct < 0 ? "distress" : "safe") : null}
        source={point?.source || (financials.error ? "Could not load" : null)}
      />
    );
  }

  const netDebt = metrics.data?.metrics.find((metric) => metric.key === "net_debt");
  const altman = scores.data?.scores.altman_z?.[year];
  const piotroski = scores.data?.scores.piotroski_f?.[year];
  const zoneTone = (label) =>
    ({ safe: "safe", strong: "safe", grey: "grey", average: "grey" })[label] ||
    "distress";
  const loaded = financials.data && metrics.data && scores.data;

  return (
    <section className="content-section glance-section">
      <SectionHeading
        eyebrow="LIVE FROM THE REPORTS"
        title={`Tata Steel at a glance (${year}, consolidated)`}
        description="Reported values with their year-on-year change, straight from the verified statements."
        action={
          <div className="glance-actions">
            <label className="select-control">
              <span>Year</span>
              <select value={year} onChange={(event) => setYear(event.target.value)}>
                {GLANCE_YEARS.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>

            <button className="text-link" onClick={() => setActivePage("Dashboard")}>
              Open dashboard
              <Icon name="arrow" size={16} />
            </button>
          </div>
        }
      />

      <AboutTataSteel />

      <div className="glance-grid">
        {itemTile("revenue_from_operations", "Revenue from operations", "chart")}
        {itemTile("profit_for_the_year", "Profit for the year", "layers")}

        <GlanceTile
          label="Net debt"
          icon="shield"
          loading={metrics.loading}
          value={
            <>
              <small>₹</small>
              <Value value={netDebt?.values[year] ?? null} />
              <small>cr</small>
            </>
          }
          source={
            metrics.error
              ? "Could not load"
              : "Borrowings + lease liabilities − cash, bank balances and current investments"
          }
        />

        <GlanceTile
          label="Altman Z''"
          icon="check"
          loading={scores.loading}
          value={<Value value={altman?.score ?? null} format={(value) => formatNumber(value, 4)} />}
          detail={altman?.interpretation && sentenceCase(`${altman.interpretation} zone`)}
          tone={zoneTone(altman?.interpretation)}
          source={scores.error ? "Could not load" : altman?.thresholds}
        />

        <GlanceTile
          label="Piotroski F"
          icon="spark"
          loading={scores.loading}
          value={piotroski?.score == null ? <Value value={null} /> : `${piotroski.score}/9`}
          detail={sentenceCase(piotroski?.interpretation)}
          tone={zoneTone(piotroski?.interpretation)}
          source={scores.error ? "Could not load" : piotroski?.thresholds}
        />
      </div>

      {loaded && (
        <GlanceBullets
          year={year}
          revenue={itemData("revenue_from_operations")}
          profit={itemData("profit_for_the_year")}
          netDebt={netDebt?.values[year] ?? null}
          altman={altman}
          piotroski={piotroski}
        />
      )}

      <p className="glance-closing">
        <Icon name="spark" size={16} />
        Edith can explain any of these: trends, ratios, DuPont, composite
        scores, segment and region performance, audit matters or an overall
        verdict, with every figure cited.
      </p>

      <div className="try-asking">
        <span className="try-asking-label">
          <Icon name="spark" size={16} />
          Try asking
        </span>

        <div className="try-asking-chips">
          {TRY_ASKING.map((question) => (
            <button
              key={question}
              type="button"
              className="question-chip"
              onClick={() => onAskEdith(question)}
              title="Opens Ask Edith and sends this question"
            >
              {question}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}


/* =========================================================
   FOOTER
   ========================================================= */

function Footer({ setActivePage }) {
  return (
    <footer className="site-footer">

      <div className="footer-main">

        <Brand />

        <p>
          {COVERAGE_TEXT} Every figure is verified against its source page.
          For research and educational use, not investment advice.
        </p>

        <button
          className="footer-link"
          onClick={() => setActivePage("Sources")}
        >
          Sources &amp; limitations
          <Icon name="arrow" size={15} />
        </button>

      </div>


      <div className="footer-bottom">

        <span>
          © Edith · Tata Steel financial assistant
        </span>

        <span>
          Evidence-first financial research
        </span>

      </div>

    </footer>
  );
}


/* =========================================================
   APP
   ========================================================= */

export default function App() {
  const [activePage, setActivePage] = useState("Home");
  const chat = useConversations();

  function goTo(page) {
    setActivePage(page);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // Open Ask Edith and send a question in a new conversation.
  function askEdith(question) {
    goTo("Ask Edith");
    chat.send(question, { fresh: true });
  }

  return (
    <div className="app-shell">

      <Header
        activePage={activePage}
        setActivePage={setActivePage}
      />

      <div
        className="page-transition"
        key={activePage}
      >

        {activePage === "Home" && (
          <HomePage setActivePage={goTo} onAskEdith={askEdith} />
        )}

        {activePage === "Ask Edith" && (
          <AskPage setActivePage={goTo} chat={chat} />
        )}

        {activePage === "Dashboard" && (
          <DashboardPage setActivePage={goTo} onAskEdith={askEdith} />
        )}

        {activePage === "Evaluation" && (
          <EvaluationPage />
        )}

        {activePage === "Sources" && (
          <SourcesPage setActivePage={goTo} />
        )}

      </div>

      <Footer setActivePage={goTo} />

    </div>
  );
}
