import { useState } from "react";
import "./App.css";

const pages = ["Home", "Ask Edith", "Dashboard", "Evaluation"];

const suggestedQuestions = [
  {
    category: "Profitability",
    question: "How does Tata Steel discuss profitability?",
  },
  {
    category: "Liquidity",
    question: "Where can I find the cash flow discussion?",
  },
  {
    category: "Risk",
    question: "What risks are described in the report?",
  },
  {
    category: "Segments",
    question: "Where is segment performance discussed?",
  },
];

function Icon({ name, size = 22 }) {
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

        <button className="header-cta" onClick={() => goTo("Ask Edith")}>
          Ask Edith <Icon name="arrow" size={16} />
        </button>
      </div>
    </header>
  );
}

function StatusPill({ children, tone = "pending" }) {
  return (
    <span className={`status-pill ${tone}`}>
      {children}
    </span>
  );
}

function SectionHeading({ eyebrow, title, description, action }) {
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


/* =========================================================
   HOME PAGE
   ========================================================= */

function HomePage({ setActivePage }) {
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
            Meet Edith — a financial research assistant built around Tata
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
              Prototype interface · Financial figures will only appear after
              source data is connected and checked.
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

          <div className="tata-wordmark">
            <span>TATA</span>
            <strong>STEEL</strong>
          </div>

          <div className="steel-data-core">

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
              Review statements, trends and financial ratios once verified
              report data becomes available.
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
              Annual and quarterly reporting
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
   ASK EDITH
   ========================================================= */
function AskPage({ setActivePage }) {
  const [question, setQuestion] = useState("");
  const [submittedQuestion, setSubmittedQuestion] = useState("");
  const [showWelcome, setShowWelcome] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [recentQuestions, setRecentQuestions] = useState([]);

  function askQuestion(value = question) {
    const trimmed = value.trim();

    if (!trimmed) return;

    setQuestion(trimmed);
    setSubmittedQuestion(trimmed);
    setRecentQuestions((items) => [
      trimmed,
      ...items.filter((item) => item !== trimmed),
    ].slice(0, 5));
    setShowWelcome(false);
  }

  function startNewConversation() {
    setQuestion("");
    setSubmittedQuestion("");
    setShowWelcome(true);
  }

  function openRecentConversation(item) {
    setQuestion(item);
    setSubmittedQuestion(item);
    setShowWelcome(false);
  }

  return (
    <main className="page inner-page ask-page">
      <div className="page-title-row">
        <div>
          <div className="page-overline">
            Tata Steel report assistant
          </div>

          <h1>Ask Edith</h1>

          <p>
            Ask about Tata Steel's financial reports and inspect the evidence
            that would support an answer.
          </p>
        </div>
      </div>

      <div
        className={`ask-layout ${
          sidebarCollapsed ? "sidebar-collapsed" : ""
        }`}
      >
        <aside
          className="ask-sidebar"
          aria-label="Conversation sidebar"
        >
          <button
            type="button"
            className="sidebar-toggle"
            onClick={() =>
              setSidebarCollapsed((collapsed) => !collapsed)
            }
            aria-label={
              sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"
            }
            title={
              sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"
            }
          >
            {sidebarCollapsed ? "Show sidebar" : "Hide sidebar"}
          </button>

          <button
            type="button"
            className="new-chat sidebar-new-chat"
            onClick={startNewConversation}
            aria-label="Start a new conversation"
          >
            <span>+ New conversation</span>
            <Icon name="spark" size={16} />
          </button>

          <div className="sidebar-heading">
            <div className="sidebar-heading-icon">
              <Icon name="spark" size={19} />
            </div>

            <div>
              <h2>Explore a topic</h2>
              <p>Choose a prompt to get started.</p>
            </div>
          </div>

          <div className="suggestion-list">
            {suggestedQuestions.map((item) => (
              <button
                key={item.category}
                type="button"
                className="suggestion-item"
                onClick={() => askQuestion(item.question)}
              >
                <span>{item.category}</span>
                <strong>{item.question}</strong>
                <Icon name="arrow" size={16} />
              </button>
            ))}
          </div>

          <div className="sidebar-info">
            <div className="sidebar-info-title">
              <Icon name="shield" size={18} />
              What Edith will show
            </div>

            <div className="sidebar-info-row">
              <span>Source</span>
              <b>Tata Steel reports</b>
            </div>

            <div className="sidebar-info-row">
              <span>Reference</span>
              <b>Report, year, page</b>
            </div>

            <div className="sidebar-info-row">
              <span>Evidence</span>
              <b>Supporting excerpt</b>
            </div>

            <div className="sidebar-info-row">
              <span>Status</span>
              <b>Verified or not verified</b>
            </div>
          </div>

          <div className="sidebar-recent">
            <div className="recent-heading">
              <span className="recent-dot" />
              <b>Recent conversations</b>
            </div>

            {recentQuestions.length > 0 ? (
              <div className="recent-question-list">
                {recentQuestions.map((item, index) => (
                  <button
                    type="button"
                    key={`${item}-${index}`}
                    className={`recent-question ${
                      submittedQuestion === item ? "active" : ""
                    }`}
                    onClick={() => openRecentConversation(item)}
                    title={item}
                  >
                    {item}
                  </button>
                ))}
              </div>
            ) : (
              <small className="recent-empty">
                Your questions will appear here after you start a
                conversation.
              </small>
            )}
          </div>
        </aside>

        <section className="chat-panel">
          <div className="chat-panel-header">
            <div className="chat-avatar">E</div>

            <div className="chat-header-copy">
              <strong>Edith</strong>
              <span>Report research assistant</span>
            </div>
          </div>

          <div className="chat-content">
            {showWelcome ? (
              <div className="welcome-message">
                <div className="welcome-icon">
                  <Icon name="spark" size={24} />
                </div>

                <div>
                  <h2>Hello, I'm Edith.</h2>

                  <p>
                    Ask a question about Tata Steel's financial reports.
                    When the report library is connected, I'll retrieve
                    the relevant passage and show its citation with the
                    answer.
                  </p>

                  <div className="welcome-callout">
                    <Icon name="book" size={18} />

                    <span>
                      Prototype mode: report search is not connected yet,
                      so answers cannot be verified against source
                      documents.
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="conversation">
                <div className="user-message">
                  <span>You</span>
                  <p>{submittedQuestion}</p>
                </div>

                <div className="assistant-message">
                  <div className="assistant-message-avatar">
                    E
                  </div>

                  <div className="assistant-message-body">
                    <span>Edith · Source unavailable</span>

                    <h3>
                      I can't verify this from a report yet.
                    </h3>

                    <p>
                      The Tata Steel report library is not connected in
                      this prototype. I won't invent financial figures
                      or claim a report supports an answer without
                      retrieving its text.
                    </p>

                    <div className="evidence-placeholder">
                      <div className="evidence-placeholder-top">
                        <span>
                          <Icon name="file" size={17} />
                          Supporting evidence
                        </span>
                      </div>

                      <div className="evidence-skeleton wide" />
                      <div className="evidence-skeleton" />

                      <small>
                        Document title, reporting period, page number
                        and exact excerpt will appear here.
                      </small>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          <form
            className="chat-composer"
            onSubmit={(event) => {
              event.preventDefault();
              askQuestion();
            }}
          >
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask about Tata Steel's financial reports…"
              rows={2}
              aria-label="Ask a question"
            />

            <div className="composer-bottom">
              <span>
                <span className="composer-lock">
                  <Icon name="shield" size={13} />
                </span>
                Prototype only · No live report search
              </span>

              <button
                type="submit"
                className="button button-primary"
                disabled={!question.trim()}
              >
                Send
                <Icon name="arrow" size={16} />
              </button>
            </div>
          </form>
        </section>
      </div>

      <div className="ask-page-links">
        <button
          className="text-link"
          onClick={() => setActivePage("Dashboard")}
        >
          Open financial dashboard
          <Icon name="arrow" size={15} />
        </button>

        <button
          className="text-link"
          onClick={() => setActivePage("Evaluation")}
        >
          Review evaluation design
          <Icon name="arrow" size={15} />
        </button>
      </div>
    </main>
  );
}



/* =========================================================
   DASHBOARD
   ========================================================= */

function DashboardPage() {
  const [basis, setBasis] = useState("Consolidated");
  const [period, setPeriod] = useState("Annual");
  const [activeMetric, setActiveMetric] = useState("Revenue");

  const metrics = [
    "Revenue",
    "Operating profit",
    "Cash flow",
    "Net debt",
  ];

  const ratios = [
    "Operating margin",
    "Current ratio",
    "Debt to equity",
    "Return on capital",
  ];

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

            {["Annual", "Quarterly"].map((item) => (

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
        </div>

      </div>


      <div className="metric-grid">

        {metrics.map((metric, index) => (

          <button
            key={metric}
            className={`metric-card ${
              activeMetric === metric ? "metric-active" : ""
            }`}
            onClick={() => setActiveMetric(metric)}
          >

            <div className="metric-card-top">

              <span>{metric}</span>

              <span className="metric-card-icon">
                <Icon
                  name={
                    index === 0
                      ? "chart"
                      : index === 1
                        ? "layers"
                        : index === 2
                          ? "book"
                          : "shield"
                  }
                  size={18}
                />
              </span>

            </div>

            <strong className="metric-value-skeleton" />

            <div className="metric-card-bottom">
              <span>Awaiting connected data</span>
              <span className="metric-mini-line" />
            </div>

          </button>

        ))}

      </div>


      <div className="dashboard-main-grid">

        <section className="dashboard-panel performance-panel">

          <div className="panel-heading">

            <div>
              <h2>Financial performance</h2>
              <p>
                {activeMetric} · {basis} · {period}
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
              Prior period
            </span>

            <span className="chart-period-note">
              Illustrative layout only
            </span>
          </div>


          <div className="chart-area">

            <div className="chart-y-labels">
              <span>—</span>
              <span>—</span>
              <span>—</span>
              <span>—</span>
            </div>


            <svg
              className="performance-chart"
              viewBox="0 0 700 250"
              preserveAspectRatio="none"
              role="img"
              aria-label="Empty chart preview; no financial values loaded"
            >

              <defs>

                <linearGradient
                  id="chartFillGreen"
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop
                    offset="0%"
                    stopColor="#0f9b79"
                    stopOpacity=".23"
                  />

                  <stop
                    offset="100%"
                    stopColor="#0f9b79"
                    stopOpacity="0"
                  />
                </linearGradient>


                <linearGradient
                  id="chartStroke"
                  x1="0"
                  y1="0"
                  x2="1"
                  y2="0"
                >
                  <stop offset="0%" stopColor="#0d9d79" />
                  <stop offset="100%" stopColor="#4c8ce8" />
                </linearGradient>

              </defs>


              {[30, 85, 140, 195].map((y) => (
                <line
                  key={y}
                  x1="0"
                  y1={y}
                  x2="700"
                  y2={y}
                  className="chart-gridline"
                />
              ))}


              <path
                d="M0 168 C65 155 85 122 145 133 S245 174 300 118 S390 74 445 97 S540 128 590 63 S650 45 700 30 L700 220 L0 220 Z"
                fill="url(#chartFillGreen)"
                className="chart-area-fill"
              />


              <path
                d="M0 168 C65 155 85 122 145 133 S245 174 300 118 S390 74 445 97 S540 128 590 63 S650 45 700 30"
                fill="none"
                stroke="url(#chartStroke)"
                strokeWidth="3.5"
                strokeLinecap="round"
                className="chart-line-animated"
              />


              <path
                d="M0 185 C70 176 90 155 145 167 S240 193 300 160 S390 135 445 149 S535 166 590 125 S650 110 700 98"
                fill="none"
                stroke="#4c8ce8"
                strokeWidth="2"
                strokeDasharray="5 7"
                opacity=".75"
              />

            </svg>


            <div className="chart-empty-overlay">

              <span className="chart-empty-icon">
                <Icon name="chart" size={24} />
              </span>

              <strong>Chart preview</strong>

              <p>
                Connect and verify report figures to populate this trend.
              </p>

            </div>

          </div>


          <div className="chart-x-labels">
            <span>Period 1</span>
            <span>Period 2</span>
            <span>Period 3</span>
            <span>Period 4</span>
            <span>Period 5</span>
          </div>

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

            {ratios.map((ratio, index) => (

              <div className="ratio-item" key={ratio}>

                <div className="ratio-topline">
                  <span>{ratio}</span>
                  <strong>—</strong>
                </div>

                <div className="ratio-track">
                  <i
                    style={{
                      width: `${[72, 52, 64, 44][index]}%`,
                    }}
                  />
                </div>

                <small>Waiting for source values</small>

              </div>

            ))}

          </div>

        </section>

      </div>


      <div className="dashboard-bottom-grid">

        <section className="dashboard-panel statement-panel">

          <div className="panel-heading">

            <div>
              <h2>Statement coverage</h2>
              <p>Report sections planned for this dashboard.</p>
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
              </div>


            </div>

          ))}

        </section>


        <aside className="dashboard-notice">

          <div className="notice-icon">
            <Icon name="shield" size={21} />
          </div>

          <div>

            <h3>No financial figures are loaded</h3>

            <p>
              These panels are layout previews. Values and charts will appear
              only after source data is connected, extracted, and checked.
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


/* =========================================================
   EVALUATION
   ========================================================= */

function EvaluationPage() {
  const [selectedCategory, setSelectedCategory] =
    useState("All categories");

  const categories = [
    "All categories",
    "Profitability",
    "Liquidity",
    "Risk",
    "Segments",
  ];

  const measures = [
    {
      title: "Numeric accuracy",
      description:
        "Compare extracted values with reviewed reference answers.",
      icon: "chart",
    },
    {
      title: "Citation correctness",
      description:
        "Check whether each citation points to the right report and page.",
      icon: "file",
    },
    {
      title: "Groundedness",
      description:
        "Assess whether the response is supported by retrieved report text.",
      icon: "shield",
    },
    {
      title: "Retrieval quality",
      description:
        "Measure whether relevant passages are found for each question.",
      icon: "search",
    },
    {
      title: "Abstention",
      description:
        "Check that Edith avoids unsupported answers when evidence is missing.",
      icon: "check",
    },
  ];

  const rows = [
    "Profitability",
    "Liquidity",
    "Risk",
    "Segments",
  ].filter(
    (item) =>
      selectedCategory === "All categories" ||
      selectedCategory === item,
  );

  return (
    <main className="page inner-page evaluation-page">

      <div className="page-title-row">

        <div>
          <div className="page-overline">
            Quality and reliability
          </div>

          <h1>Evaluation</h1>

          <p>
            How answer quality will be tested before results are treated as
            reliable.
          </p>
        </div>


      </div>


      <section className="evaluation-summary">

        <div className="gauge-wrap">
          <div className="evaluation-gauge">

            <div className="gauge-center">
              <strong>—</strong>
              <span>Score</span>
            </div>

          </div>
        </div>


        <div className="evaluation-summary-copy">

          <span className="summary-label">
            Evaluation status
          </span>

          <h2>No results yet</h2>

          <p>
            Scores will be shown after testing Edith against a reviewed
            evaluation set. This prototype does not report a performance
            score.
          </p>


        </div>


        <div className="evaluation-set-card">

          <div className="set-card-icon">
            <Icon name="book" size={20} />
          </div>

          <div>
            <strong>Evaluation set</strong>

            <span>
              A reviewed question set, reference answers and source passages define the basis for reliability checks.
            </span>

          </div>

        </div>

      </section>


      <section className="content-section evaluation-measures">

        <SectionHeading
          title="What will be assessed?"
          description="Each measure addresses a different part of the evidence chain."
        />

        <div className="evaluation-card-grid">

          {measures.map((measure, index) => (

            <article
              className="evaluation-measure-card"
              key={measure.title}
              style={{
                "--delay": `${index * 75}ms`,
              }}
            >

              <div className="measure-top">

                <span className="measure-icon">
                  <Icon name={measure.icon} size={21} />
                </span>


              </div>

              <h3>{measure.title}</h3>

              <p>{measure.description}</p>

              <small className="measure-definition">Measure definition · no score recorded</small>

            </article>

          ))}

        </div>

      </section>


      <div className="evaluation-lower-grid">

        <section className="dashboard-panel category-panel">

          <div className="panel-heading">

            <div>
              <h2>Results by question category</h2>

              <p>
                Once an evaluation set is available, results can be grouped
                by question type.
              </p>
            </div>

            <span className="panel-icon">
              <Icon name="chart" size={20} />
            </span>

          </div>


          <div
            className="category-filter"
            role="group"
            aria-label="Filter question categories"
          >

            {categories.map((category) => (

              <button
                key={category}
                className={
                  selectedCategory === category
                    ? "selected"
                    : ""
                }
                onClick={() => setSelectedCategory(category)}
              >
                {category}
              </button>

            ))}

          </div>


          <div className="category-table">

            <div className="category-table-head">
              <span>Question category</span>
            </div>

            {rows.map((row) => (

              <div
                className="category-table-row"
                key={row}
              >
                <span>{row}</span>

              </div>

            ))}

          </div>

        </section>


        <section className="dashboard-panel flagged-panel">

          <div className="panel-heading">

            <div>
              <h2>Flagged-answer review</h2>

              <p>
                A review queue can surface responses that need human checking.
              </p>
            </div>

            <span className="panel-icon warning">
              <Icon name="shield" size={20} />
            </span>

          </div>


          <div className="flagged-empty">

            <div className="flagged-empty-icon">
              <Icon name="check" size={21} />
            </div>

            <div>
              <strong>No reviewed answers yet</strong>

              <p>
                Flagged examples will appear here after evaluation runs.
              </p>
            </div>

          </div>


          <div className="flagged-placeholder">

            <div className="flagged-placeholder-line" />
            <div className="flagged-placeholder-line short" />

            <small>
              Example queue preview · no live evaluation records
            </small>

          </div>

        </section>

      </div>


      <section className="methodology-card">

        <div className="methodology-icon">
          <Icon name="layers" size={22} />
        </div>

        <div>

          <h2>How the evaluation will work</h2>

          <p>
            Create a reviewed set of questions with reference answers and
            supporting report pages. Run Edith on those questions, then
            compare the response, retrieved evidence and citations with the
            reviewed references. Report results only after the test data and
            scoring method have been defined.
          </p>

        </div>

      </section>

    </main>
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
          A report-based research prototype. Financial figures will be
          presented only when supported by connected and checked sources.
          For research and educational use, not investment advice.
        </p>

        <button
          className="footer-link"
          onClick={() => setActivePage("Evaluation")}
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
          <HomePage setActivePage={setActivePage} />
        )}

        {activePage === "Ask Edith" && (
          <AskPage setActivePage={setActivePage} />
        )}

        {activePage === "Dashboard" && (
          <DashboardPage />
        )}

        {activePage === "Evaluation" && (
          <EvaluationPage />
        )}

      </div>

      <Footer setActivePage={setActivePage} />

    </div>
  );
}
