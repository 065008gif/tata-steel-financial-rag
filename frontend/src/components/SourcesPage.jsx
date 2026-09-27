import { getReports } from "../api.js";
import {
  COMPARATIVE_NOTE,
  COVERAGE_TEXT,
  Icon,
  LoadError,
  SectionHeading,
  useApi,
} from "./ui.jsx";

/* =========================================================
   SOURCES & METHODOLOGY
   ========================================================= */

const pipeline = [
  {
    title: "Parse the statements",
    description:
      "The balance sheet, profit and loss and cash flow statements of each report are extracted into canonical line items, consolidated and standalone.",
    icon: "file",
  },
  {
    title: "Verify",
    description:
      "Assets must equal equity plus liabilities, subtotals must add up, and figures restated in a later report are flagged.",
    icon: "check",
  },
  {
    title: "Index",
    description:
      "The report text is chunked and indexed for hybrid search (keyword and semantic), filtered by report and section.",
    icon: "layers",
  },
  {
    title: "Answer",
    description:
      "The model plans the answer, but tools fetch and compute every number: lookups, ratios, changes, scores and segments.",
    icon: "search",
  },
  {
    title: "Check",
    description:
      "Every figure in the answer is matched to its source data; unmatched figures are listed and the answer is marked partially verified.",
    icon: "shield",
  },
  {
    title: "Cite",
    description:
      "Each answer links to the report pages it relies on, opening the PDF at that page.",
    icon: "book",
  },
];

const limitations = [
  "Annual data only: there are no quarterly results.",
  "Narrative comparison across long report sections (for example, how risks changed between years) is the weakest area; check those answers against the cited pages.",
  "Answers take 10-60 seconds, occasionally longer for multi-step analyses.",
  "For research and education only. Nothing here is investment advice.",
];

export default function SourcesPage({ setActivePage }) {
  const reports = useApi(getReports, "reports");

  return (
    <main className="page inner-page sources-page">

      <div className="page-title-row">

        <div>
          <div className="page-overline">
            Sources and methodology
          </div>

          <h1>Sources</h1>

          <p>
            Where Edith's figures come from, how they are checked, and what
            the current version cannot do.
          </p>
        </div>

      </div>


      <section className="sources-block">

        <SectionHeading
          eyebrow="THE REPORTS"
          title="Four Tata Steel annual reports"
          description={`Integrated Reports & Annual Accounts. ${COVERAGE_TEXT}`}
        />

        {reports.error && (
          <LoadError error={reports.error} onRetry={reports.retry} />
        )}

        <div className="report-grid">

          {reports.loading &&
            [0, 1, 2, 3].map((index) => (
              <div className="dashboard-panel report-card" key={index}>
                <div className="evidence-skeleton wide" />
                <div className="evidence-skeleton" />
              </div>
            ))}

          {reports.data && (() => {
            const comparative = reports.data.find(
              (report) => report.fiscal_year === "FY2022-23",
            );

            return comparative ? (
              <div className="dashboard-panel report-card report-card-comparative">
                <span className="statement-icon">
                  <Icon name="layers" size={18} />
                </span>

                <div>
                  <span className="report-year" title={COMPARATIVE_NOTE}>
                    FY2021-22
                  </span>
                  <strong>
                    FY2021-22: figures from the comparative column of the
                    FY2022-23 report
                  </strong>
                  <small>
                    <a href={comparative.pdf_url} target="_blank" rel="noopener noreferrer">
                      Open the FY2022-23 report
                      <Icon name="external" size={12} />
                    </a>
                  </small>
                </div>
              </div>
            ) : null;
          })()}

          {reports.data?.map((report) => (

            <div className="dashboard-panel report-card" key={report.fiscal_year}>

              <span className="statement-icon">
                <Icon name="file" size={18} />
              </span>

              <div>
                <span className="report-year">{report.fiscal_year}</span>
                <a
                  className="report-card-link"
                  href={report.pdf_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  title="Open the report PDF (local copy)"
                >
                  <strong>{report.title}</strong>
                </a>
                <small>
                  {report.pages ? `${report.pages} pages · ` : ""}PDF (local copy)
                  {report.official_url && (
                    <>
                      {" · "}
                      <a
                        className="official-link"
                        href={report.official_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title="The official copy on tatasteel.com"
                      >
                        tatasteel.com
                      </a>
                    </>
                  )}
                </small>
              </div>

              <a
                className="report-card-open"
                href={report.pdf_url}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Open the ${report.fiscal_year} report PDF`}
              >
                <Icon name="external" size={16} />
              </a>

            </div>

          ))}

        </div>

      </section>


      <section className="sources-block">

        <SectionHeading
          eyebrow="HOW IT WORKS"
          title="From report to cited answer."
        />

        <div className="evaluation-card-grid pipeline-grid">

          {pipeline.map((step, index) => (

            <article
              className="evaluation-measure-card"
              key={step.title}
              style={{
                "--delay": `${index * 75}ms`,
              }}
            >

              <div className="measure-top">

                <span className="measure-icon">
                  <Icon name={step.icon} size={21} />
                </span>

                <span className="pipeline-number">
                  {String(index + 1).padStart(2, "0")}
                </span>

              </div>

              <h3>{step.title}</h3>

              <p>{step.description}</p>

            </article>

          ))}

        </div>

      </section>


      <section className="sources-block sources-two-up">

        <div className="methodology-card" id="scores">

          <div className="methodology-icon">
            <Icon name="chart" size={22} />
          </div>

          <div>

            <h2>Composite scores</h2>

            <p>
              Altman Z'' (book-equity variant), Piotroski F and Beneish M are
              computed in code from the verified statements, consolidated and
              standalone, FY2021-22 to FY2025-26 (FY2021-22 from the
              FY2022-23 report's comparative column; Piotroski F and Beneish
              M need FY2020-21, so they start in FY2022-23). Altman X2 uses the actual
              retained earnings from each report's "Other equity" note, each
              value verified on its page. Disclosed proxies: X4 uses book equity
              instead of market value (not in the reports) and EBIT is taken as
              profit before tax plus finance costs. Piotroski and Beneish compare
              each year with the prior year as presented in the same report.
            </p>

          </div>

        </div>


        <div className="methodology-card">

          <div className="methodology-icon">
            <Icon name="layers" size={22} />
          </div>

          <div>

            <h2>Segments</h2>

            <p>
              Segment revenue and segment results (segment EBITDA: before
              exceptional items, interest, tax and depreciation) come from the
              consolidated "Segment reporting" note of each report. Every value
              is checked on its page, segments plus eliminations reconcile to
              the printed total, and restated values are marked. Tata Steel
              Europe is split into Netherlands and UK operations from FY2024-25,
              and Tata Steel Long Products was merged into Tata Steel India.
            </p>

          </div>

        </div>

      </section>


      <section className="methodology-card sources-note">

        <div className="methodology-icon">
          <Icon name="spark" size={22} />
        </div>

        <div>

          <h2>Built with Claude Code, then independently verified</h2>

          <p>
            The composite scores module, the page-verified retained earnings
            and the segment extraction were built with Claude Code from
            written briefs, with automated tests. Each result was then checked
            independently: scores recomputed by hand from the statements,
            retained earnings and segment values located on the PDF pages, and
            the tests re-run.
          </p>

        </div>

      </section>


      <section className="dashboard-panel limitations-panel">

        <div className="panel-heading">

          <div>
            <h2>Limitations</h2>
            <p>What the current version of Edith cannot do well.</p>
          </div>

          <span className="panel-icon warning">
            <Icon name="shield" size={20} />
          </span>

        </div>

        <ul className="limitations-list">
          {limitations.map((item) => (
            <li key={item}>
              <Icon name="check" size={16} />
              {item}
            </li>
          ))}
        </ul>

        <button
          type="button"
          className="text-link"
          onClick={() => setActivePage("Evaluation")}
        >
          See the evaluation results
          <Icon name="arrow" size={15} />
        </button>

      </section>

    </main>
  );
}
