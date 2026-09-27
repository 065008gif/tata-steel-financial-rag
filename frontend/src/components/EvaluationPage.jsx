import { useState } from "react";
import { getEvaluation } from "../api.js";
import {
  Icon,
  LoadError,
  Missing,
  REASON,
  SectionHeading,
  formatRunDate,
  useApi,
} from "./ui.jsx";

/* =========================================================
   EVALUATION
   Figures come from /api/evaluation (latest full run).
   ========================================================= */

const categoryLabels = {
  lookup: "Lookup",
  table_grounded: "Table grounded",
  trend: "Trend",
  ratio: "Ratio",
  yoy: "Year on year",
  composite: "Composite",
  segment: "Segment",
  follow_up: "Follow-up",
  narrative: "Narrative",
  risk_evolution: "Risk evolution",
  scope_trap: "Scope trap",
  abstain: "Abstain",
  verdict: "Verdict",
};

// Hand-graded known limitations (eval/EVALUATION_NOTES.md).
const flaggedAnswers = [
  {
    id: "G1",
    title: "Risk evolution",
    grade: "Correct method, unreliable conclusions",
    detail:
      "Compares the named risks in the Integrated Report risk sections, but called some risks \"new in FY26\" that the FY2022-23 report also discusses (regulatory risk, employee well-being, R&D) and misreported its own search results.",
  },
  {
    id: "G2",
    title: "UK losses and restructuring",
    grade: "Partial",
    detail:
      "Correct UK segment figures and UK government support, but attributed India's new labour-code charge to the UK, linked exceptional provisions to segment results (which exclude them) and omitted the electric-arc-furnace transition.",
  },
];

function categoryLabel(category) {
  return categoryLabels[category] || category.replace(/_/g, " ");
}

function isFull(fraction) {
  if (fraction == null) return true;
  const [found, total] = String(fraction).split("/").map(Number);
  return found === total;
}

/** A record passes when every automated check that applies to it is complete. */
function passes(record) {
  return (
    record.abstention_ok !== false &&
    isFull(record.numeric) &&
    isFull(record.grounded) &&
    isFull(record.mentions)
  );
}

function ratioOf(fraction) {
  const [found, total] = String(fraction || "").split("/").map(Number);
  return total ? found / total : 0;
}

function formatRate(value) {
  return typeof value === "number" ? value.toFixed(2) : "not recorded";
}

export default function EvaluationPage() {
  const [selectedCategory, setSelectedCategory] =
    useState("All categories");

  const evaluation = useApi(getEvaluation, "evaluation");
  const data = evaluation.data;
  const available = data?.available;
  const summary = data?.summary || {};
  const records = data?.records || [];
  const retrieval = summary.tier1_filtered_retrieval || {};

  const categories = [
    "All categories",
    ...records.reduce(
      (list, record) =>
        list.includes(record.category) ? list : [...list, record.category],
      [],
    ),
  ];

  const measures = [
    {
      title: "Numeric accuracy",
      description:
        "Compare extracted values with reviewed reference answers.",
      icon: "chart",
      value: summary.numeric_questions_fully_correct,
      detail: `numeric questions fully correct · ${summary.expected_numbers_found || "not recorded"} expected numbers found`,
    },
    {
      title: "Citation correctness",
      description:
        "Check whether each citation points to the right report and page.",
      icon: "file",
      value: summary.expected_pages_cited,
      detail: "expected pages cited",
    },
    {
      title: "Groundedness",
      description:
        "Assess whether the response is supported by retrieved report text.",
      icon: "shield",
      value: summary.answers_fully_grounded,
      detail: "answers fully grounded (every figure matched to its source)",
    },
    {
      title: "Retrieval quality",
      description:
        "Measure whether relevant passages are found for each question.",
      icon: "search",
      value: `${formatRate(retrieval["hit_rate@4"])} / ${formatRate(retrieval.mrr)}`,
      detail: `Hit Rate@4 / MRR · source pages retrieved: ${summary.source_pages_retrieved || "not recorded"}`,
    },
    {
      title: "Abstention",
      description:
        "Check that Edith avoids unsupported answers when evidence is missing.",
      icon: "check",
      value: summary.abstention_correct,
      detail: "correct: out-of-scope questions refused, no valid question refused",
    },
  ];

  const byCategory = categories.slice(1).map((category) => {
    const items = records.filter((record) => record.category === category);
    return {
      category,
      total: items.length,
      passed: items.filter(passes).length,
    };
  });

  const selectedRecords = records.filter(
    (record) => record.category === selectedCategory,
  );

  const headline = summary.numeric_questions_fully_correct;

  return (
    <main className="page inner-page evaluation-page">

      <div className="page-title-row">

        <div>
          <div className="page-overline">
            Quality and reliability
          </div>

          <h1>Evaluation</h1>

          <p>
            How answer quality is tested before results are treated as
            reliable.
          </p>
        </div>


      </div>


      {evaluation.error && (
        <LoadError error={evaluation.error} onRetry={evaluation.retry} />
      )}


      <section className="evaluation-summary">

        <div className="gauge-wrap">
          <div
            className="evaluation-gauge"
            style={
              headline
                ? { "--gauge-fill": `${Math.round(ratioOf(headline) * 100)}%` }
                : undefined
            }
            data-live={headline ? "true" : undefined}
          >

            <div className="gauge-center">
              <strong title={headline ? undefined : "No evaluation run is available yet"}>
                {headline || <Missing reason="No run yet" />}
              </strong>
              <span>Numeric</span>
            </div>

          </div>
        </div>


        <div className="evaluation-summary-copy">

          <span className="summary-label">
            Evaluation status
          </span>

          {evaluation.loading && <h2>Loading the latest run…</h2>}

          {data && !available && (
            <>
              <h2>No results yet</h2>
              <p>No evaluation run is available on the backend.</p>
            </>
          )}

          {available && (
            <>
              <h2>{headline} numeric questions fully correct</h2>

              <p>
                Latest full run · {formatRunDate(data.run_at)} ·{" "}
                {records.length} questions · {summary.expected_numbers_found}{" "}
                expected numbers found · average {summary.avg_seconds} s and{" "}
                {summary.avg_tool_calls} tool calls per answer.
              </p>
            </>
          )}


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
          title="What is assessed?"
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

              <strong
                className="measure-value"
                title={available && measure.value ? undefined : "No score recorded in the latest run"}
              >
                {available && measure.value ? measure.value : <Missing reason="Not recorded" />}
              </strong>

              <small className="measure-definition">
                {available ? measure.detail : "Measure definition · no score recorded"}
              </small>

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
                A question counts as correct when every automated check that
                applies to it passes: expected numbers, grounding, required
                mentions and abstention.
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
                {category === "All categories" ? category : categoryLabel(category)}
              </button>

            ))}

          </div>


          <div className="category-table">

            {selectedCategory === "All categories" ? (
              <>
                <div className="category-table-head category-results-row">
                  <span>Question category</span>
                  <span>Questions</span>
                  <span>Correct</span>
                </div>

                {byCategory.map((row) => (

                  <div
                    className="category-table-row category-results-row"
                    key={row.category}
                  >
                    <span>{categoryLabel(row.category)}</span>
                    <span>{row.total}</span>
                    <span className={row.passed === row.total ? "result-pass" : "result-partial"}>
                      {row.passed}/{row.total}
                    </span>
                  </div>

                ))}
              </>
            ) : (
              <>
                <div className="category-table-head category-question-row">
                  <span>Question</span>
                  <span>Numbers</span>
                  <span>Pages cited</span>
                  <span>Grounded</span>
                  <span>Time</span>
                </div>

                {selectedRecords.map((record) => (

                  <div
                    className="category-table-row category-question-row"
                    key={record.id}
                  >
                    <span>
                      <b>{record.id}</b> {record.question}
                    </span>
                    <span title={record.numeric ? undefined : "No figures to check for this question"}>
                      {record.numeric || <Missing reason={REASON.nothingToCheck} />}
                    </span>
                    <span title={record.citation ? undefined : "No citation check for this question"}>
                      {record.citation || <Missing reason={REASON.nothingToCheck} />}
                    </span>
                    <span className={isFull(record.grounded) ? "result-pass" : "result-partial"}>
                      {record.grounded || <Missing reason={REASON.nothingToCheck} />}
                    </span>
                    <span>{record.seconds} s</span>
                  </div>

                ))}
              </>
            )}

          </div>

        </section>


        <section className="dashboard-panel flagged-panel">

          <div className="panel-heading">

            <div>
              <h2>Flagged-answer review</h2>

              <p>
                Hand-graded answers that need human checking: the known
                limitations of the current version.
              </p>
            </div>

            <span className="panel-icon warning">
              <Icon name="shield" size={20} />
            </span>

          </div>


          {flaggedAnswers.map((item) => (

            <div className="flagged-empty flagged-item" key={item.id}>

              <div className="flagged-empty-icon">
                <Icon name="shield" size={19} />
              </div>

              <div>
                <strong>
                  {item.id} · {item.title}
                </strong>

                <span className="flagged-grade">{item.grade}</span>

                <p>{item.detail}</p>
              </div>

            </div>

          ))}


          <div className="flagged-placeholder">

            <small>
              Narrative comparison across long report sections is the weakest
              area. Every other hand-graded answer (segments, key audit
              matters, verdict and the three composite scores) was graded
              correct.
            </small>

          </div>

        </section>

      </div>


      <section className="methodology-card">

        <div className="methodology-icon">
          <Icon name="layers" size={22} />
        </div>

        <div>

          <h2>How the evaluation works</h2>

          <p>
            32 questions across categories (lookups, trends, ratios, year-on-year
            changes, composite scores, segments, follow-ups, narrative and risk
            questions, scope traps, abstention and an overall verdict) are run
            automatically against Edith. The answer key was checked against the
            PDF pages (118/118 figures found). Results are scored in four tiers:
            filtered retrieval (Hit Rate@4, MRR), numeric accuracy against the
            answer key, the source pages retrieved and cited, and abstention
            with automatic numeric grounding. Narrative answers are also graded
            by hand.
          </p>

        </div>

      </section>

    </main>
  );
}
