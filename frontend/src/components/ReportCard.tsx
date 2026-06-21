import type { RunReport } from "../types";

const STATUS_LABEL: Record<RunReport["status"], string> = {
  reproduced: "Reproduced", not_reproduced: "Not reproduced", error: "Error",
};

export default function ReportCard({ report }: { report: RunReport }) {
  return (
    <article className="report" data-status={report.status}>
      <header className="report__head">
        <h2 className="report__verdict">{report.verdict}</h2>
        <span className={`pill pill--${report.status}`}>{STATUS_LABEL[report.status]}</span>
      </header>

      {report.reproSteps.length > 0 && (
        <section className="report__block">
          <h3 className="report__h">Confirmed repro steps</h3>
          <ol className="steps">
            {report.reproSteps.map((s) => (
              <li className="steps__item" key={s.n}>
                <span className="steps__action">{s.action}</span>
                {s.screenshot && (
                  <img className="steps__shot" src={s.screenshot} alt={`Step ${s.n}: ${s.action}`} loading="lazy" />
                )}
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="report__block">
        <h3 className="report__h">Root cause</h3>
        <p className="report__hyp">{report.rootCause.hypothesis}</p>
        {report.rootCause.evidence && <pre className="report__evidence">{report.rootCause.evidence}</pre>}
        <span className="report__conf">confidence: {report.rootCause.confidence}</span>
      </section>

      {report.attempts.length > 0 && (
        <section className="report__block">
          <h3 className="report__h">Browser sessions</h3>
          <ul className="attempts">
            {report.attempts.map((a) => (
              <li className="attempts__item" key={a.n}>
                <span className="attempts__outcome" data-outcome={a.outcome}>attempt {a.n} · {a.outcome}</span>
                <a href={a.replayUrl} target="_blank" rel="noopener noreferrer">replay ↗</a>
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}
