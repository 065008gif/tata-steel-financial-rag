import { useEffect, useLayoutEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { COVERAGE_TEXT, Icon, StatusPill } from "./ui.jsx";

/* =========================================================
   ASK EDITH
   ========================================================= */

export const VERDICT_QUESTION =
  "Give an overall verdict on Tata Steel's financial health in FY2025-26.";

export const PROFIT_TREND_QUESTION =
  "How has Tata Steel's consolidated profit for the year changed from FY2022-23 to FY2025-26?";

export const DUPONT_QUESTION =
  "Run a DuPont analysis of Tata Steel's consolidated ROE for FY2025-26.";

// Short labels in the sidebar; each sends its full question.
export const suggestedQuestions = [
  {
    category: "Trends",
    label: "Profit trend, FY23 to FY26",
    question: PROFIT_TREND_QUESTION,
  },
  {
    category: "Ratios",
    label: "DuPont analysis of ROE",
    question: DUPONT_QUESTION,
  },
  {
    category: "Scores",
    label: "Altman, Piotroski, Beneish",
    question:
      "What are Tata Steel's Altman Z'', Piotroski F and Beneish M scores for FY2025-26?",
  },
  {
    category: "Segments",
    label: "India vs Netherlands vs UK",
    question:
      "Compare the EBITDA of Tata Steel's India, Netherlands and UK segments in FY2024-25 and FY2025-26.",
  },
  {
    category: "Verdict",
    label: "Overall verdict",
    question: VERDICT_QUESTION,
  },
  {
    category: "Try to trick it",
    label: "Can it predict FY2027-28?",
    question: "What will Tata Steel's revenue be in FY2027-28?",
    note: "Edith refuses what the reports can't answer",
  },
];

const FOLLOW_UP_EXAMPLE = "And in FY2023-24?";

const markdownComponents = {
  table: ({ node: _node, ...props }) => (
    <div className="answer-table-wrap">
      <table {...props} />
    </div>
  ),
  a: ({ node: _node, ...props }) => (
    <a {...props} target="_blank" rel="noopener noreferrer" />
  ),
};

function citationLabel(citation) {
  const page = citation.page_label || (citation.pdf_page ? `PDF p. ${citation.pdf_page}` : null);
  return [citation.report, citation.section, page].filter(Boolean).join(" · ");
}

function VerificationBadge({ verification }) {
  if (!verification) return null;

  const {
    status,
    figures_grounded: grounded,
    figures_total: total,
    unverified_figures: unverified = [],
  } = verification;

  if (status === "verified") {
    return (
      <StatusPill tone="verified">
        Verified · {grounded}/{total} figures
      </StatusPill>
    );
  }

  if (status === "partially_verified") {
    return (
      <div className="verification-partial">
        <StatusPill tone="partial">
          Partially verified · {grounded}/{total}
        </StatusPill>

        {unverified.length > 0 && (
          <small>
            Not matched to a source: {unverified.join(", ")}
          </small>
        )}
      </div>
    );
  }

  return <StatusPill tone="neutral">No figures to verify</StatusPill>;
}

function ElapsedSeconds({ startedAt }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  return <>{Math.max(0, Math.floor((now - startedAt) / 1000))} s</>;
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  return (
    <button type="button" className="answer-action" onClick={copy}>
      <Icon name={copied ? "check" : "copy"} size={15} />
      {copied ? "Copied" : "Copy answer"}
    </button>
  );
}

function PendingAnswer({ turn, onCancel }) {
  return (
    <div className="assistant-message answer-pending" aria-live="polite">
      <div className="assistant-message-avatar">E</div>

      <div className="assistant-message-body">
        <span>Edith · Working on it</span>

        <div className="typing-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </div>

        <div className="evidence-placeholder">
          <div className="evidence-placeholder-top">
            <span>
              <Icon name="search" size={17} />
              Fetching figures and checking sources
            </span>

            <span className="pending-elapsed">
              <Icon name="clock" size={15} />
              <ElapsedSeconds startedAt={turn.startedAt} />
            </span>
          </div>

          <div className="evidence-skeleton wide" />
          <div className="evidence-skeleton" />

          <div className="pending-footer">
            <small>Usually 10-60 seconds; the first question may take 2-3 minutes.</small>

            <button
              type="button"
              className="button button-secondary pending-cancel"
              onClick={onCancel}
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ErrorAnswer({ turn, onRetry }) {
  return (
    <div className="assistant-message" role="alert">
      <div className="assistant-message-avatar">E</div>

      <div className="assistant-message-body">
        <span>Edith · {turn.cancelled ? "Cancelled" : "No answer"}</span>

        <div className="answer-error">
          <Icon name="shield" size={18} />
          <p>{turn.error}</p>
        </div>

        <button type="button" className="text-link answer-retry" onClick={onRetry}>
          Retry
          <Icon name="refresh" size={15} />
        </button>
      </div>
    </div>
  );
}

function AnswerMessage({ response }) {
  const {
    answer_markdown: markdown,
    verification,
    citations = [],
    steps = [],
    model,
    elapsed_seconds: elapsed,
  } = response;
  const warnings = verification?.warnings || [];

  return (
    <div className="assistant-message">
      <div className="assistant-message-avatar">E</div>

      <div className="assistant-message-body">
        <div className="answer-meta">
          <span>Edith</span>
          <VerificationBadge verification={verification} />
          <CopyButton text={markdown} />
        </div>

        {warnings.length > 0 && (
          <ul className="answer-warnings">
            {warnings.map((warning) => (
              <li key={warning}>
                <Icon name="shield" size={14} />
                {warning}
              </li>
            ))}
          </ul>
        )}

        <div className="answer-markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {markdown}
          </ReactMarkdown>
        </div>

        <div className="evidence-placeholder evidence-citations">
          <div className="evidence-placeholder-top">
            <span>
              <Icon name="file" size={17} />
              Supporting evidence
            </span>
          </div>

          {citations.length > 0 ? (
            <div className="citation-list">
              {citations.map((citation) => (
                <a
                  key={`${citation.report}-${citation.page_label || citation.pdf_page}`}
                  className="citation-chip"
                  href={citation.pdf_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  title="Open the report at this page"
                >
                  <Icon name="file" size={14} />
                  {citationLabel(citation)}
                  <Icon name="external" size={13} />
                </a>
              ))}
            </div>
          ) : (
            <small>No report pages were cited for this answer.</small>
          )}
        </div>

        <details className="answer-steps">
          <summary>
            <Icon name="layers" size={15} />
            How this answer was produced
          </summary>

          {steps.length > 0 ? (
            <ol>
              {steps.map((step, index) => (
                <li key={`${step.tool}-${index}`}>
                  <b>{step.tool}</b>
                  {step.description}
                </li>
              ))}
            </ol>
          ) : (
            <p>No tools were needed for this answer.</p>
          )}

          <small>
            Model · {model} · {elapsed} s
          </small>
        </details>
      </div>
    </div>
  );
}

export default function AskPage({ setActivePage, chat }) {
  const [question, setQuestion] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const chatContentRef = useRef(null);
  const textareaRef = useRef(null);

  const { conversations, active, activeId } = chat;
  const turns = active?.turns || [];
  const isPending = turns.some((turn) => turn.status === "pending");
  const lastTurn = turns[turns.length - 1];

  // The app area fills the viewport below the sticky header.
  useLayoutEffect(() => {
    const header = document.querySelector(".site-header");
    if (!header) return undefined;

    const root = document.documentElement;
    const update = () =>
      root.style.setProperty("--site-header-h", `${header.offsetHeight}px`);
    update();

    const observer = new ResizeObserver(update);
    observer.observe(header);
    return () => observer.disconnect();
  }, []);

  // Keep the newest message in view.
  useEffect(() => {
    const element = chatContentRef.current;
    if (!element || turns.length === 0) return;
    element.scrollTo({ top: element.scrollHeight, behavior: "smooth" });
  }, [activeId, turns.length, lastTurn?.status]);

  function askQuestion(value = question) {
    const trimmed = value.trim();
    if (!trimmed || isPending) return;

    chat.send(trimmed);
    setQuestion("");
  }

  function startNewConversation() {
    chat.startNew();
    setQuestion("");
    textareaRef.current?.focus();
  }

  function fillFollowUpExample() {
    setQuestion(FOLLOW_UP_EXAMPLE);
    textareaRef.current?.focus();
  }

  return (
    <main className="page inner-page ask-page">
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
                key={item.question}
                type="button"
                className={`suggestion-item ${item.note ? "suggestion-trick" : ""}`}
                onClick={() => askQuestion(item.question)}
                disabled={isPending}
                title={item.question}
              >
                <span>{item.category}</span>
                <strong>{item.label}</strong>
                {item.note && <small>{item.note}</small>}
                <Icon name="arrow" size={16} />
              </button>
            ))}
          </div>

          <button
            type="button"
            className="follow-up-hint"
            onClick={fillFollowUpExample}
          >
            <Icon name="spark" size={15} />
            <span>
              Follow-ups work. After a lookup, try <b>“{FOLLOW_UP_EXAMPLE}”</b>
            </span>
          </button>

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
              <b>Links to the cited pages</b>
            </div>

            <div className="sidebar-info-row">
              <span>Status</span>
              <b>Verified / partially verified, with each figure checked</b>
            </div>
          </div>

          <div className="sidebar-recent">
            <div className="recent-heading">
              <span className="recent-dot" />
              <b>Recent conversations</b>
            </div>

            {conversations.length > 0 ? (
              <div className="recent-question-list">
                {conversations.map((conversation) => (
                  <button
                    type="button"
                    key={conversation.id}
                    className={`recent-question ${
                      activeId === conversation.id ? "active" : ""
                    }`}
                    onClick={() => chat.open(conversation.id)}
                    title={conversation.title}
                  >
                    {conversation.title}
                    {conversation.turns.length > 1 &&
                      ` · ${conversation.turns.length} questions`}
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

        <div className="ask-main">
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

          <section className="chat-panel">
            <div className="chat-panel-header">
              <div className="chat-avatar">E</div>

              <div className="chat-header-copy">
                <strong>Edith</strong>
                <span>Report research assistant</span>
              </div>
            </div>

            <div className="chat-content" ref={chatContentRef}>
              {turns.length === 0 ? (
                <div className="welcome-message">
                  <div className="welcome-icon">
                    <Icon name="spark" size={24} />
                  </div>

                  <div>
                    <h2>Hello, I'm Edith.</h2>

                    <p>
                      Ask a question about Tata Steel's financial reports.
                      I'll look up the reported figures, work out what the
                      question needs, and show the pages each figure comes
                      from.
                    </p>

                    <div className="welcome-callout">
                      <Icon name="book" size={18} />

                      <ul>
                        <li>
                          {COVERAGE_TEXT} Consolidated and standalone.
                        </li>
                        <li>
                          Every figure in an answer is checked against its
                          source and cited to the report page.
                        </li>
                        <li>
                          Follow-up questions work, e.g. “{FOLLOW_UP_EXAMPLE}”
                          after a lookup.
                        </li>
                        <li>
                          Answers usually take 10-60 seconds; the first
                          question may take 2-3 minutes.
                        </li>
                      </ul>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="conversation">
                  {turns.map((turn) => (
                    <div className="conversation-turn" key={turn.id}>
                      <div className="user-message">
                        <span>You</span>
                        <p>{turn.question}</p>
                      </div>

                      {turn.status === "pending" && (
                        <PendingAnswer
                          turn={turn}
                          onCancel={() => chat.cancel(turn.id)}
                        />
                      )}

                      {turn.status === "error" && (
                        <ErrorAnswer
                          turn={turn}
                          onRetry={() => chat.retry(active.id, turn.id)}
                        />
                      )}

                      {turn.status === "done" && turn.response && (
                        <AnswerMessage response={turn.response} />
                      )}
                    </div>
                  ))}
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
                ref={textareaRef}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={(event) => {
                  if (
                    event.key === "Enter" &&
                    !event.shiftKey &&
                    !event.nativeEvent.isComposing
                  ) {
                    event.preventDefault();
                    askQuestion();
                  }
                }}
                placeholder={
                  turns.length > 0
                    ? "Ask a follow-up question…"
                    : "Ask about Tata Steel's financial reports…"
                }
                rows={2}
                maxLength={2000}
                aria-label="Ask a question"
              />

              <div className="composer-bottom">
                <span>
                  <span className="composer-lock">
                    <Icon name="shield" size={13} />
                  </span>
                  Answers are verified against the source pages
                </span>

                <button
                  type="submit"
                  className="button button-primary"
                  disabled={!question.trim() || isPending}
                >
                  Send
                  <Icon name="arrow" size={16} />
                </button>
              </div>
            </form>
          </section>
        </div>
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
          See evaluation results
          <Icon name="arrow" size={15} />
        </button>
      </div>
    </main>
  );
}
