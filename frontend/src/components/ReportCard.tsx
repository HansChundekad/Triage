import type { ReproReport, Verdict } from "../types";

const VERDICT_LABEL: Record<Verdict, string> = {
  reproduced: "Reproduced",
  not_reproduced: "Not reproduced",
};

// A screenshot_ref is a relative artifact path on the server; only render an
// <img> when it is directly loadable (http(s) or a data: URI), else stay text-only.
function loadable(ref: string): boolean {
  return /^(https?:|data:)/.test(ref);
}

function pct(score: number | null): string {
  return score == null ? "—" : `${Math.round(score * 100)}%`;
}

export default function ReportCard({ report }: { report: ReproReport }) {
  const { issue, verdict, repro_steps, root_cause, evidence, attempts, eval_scores } = report;

  return (
    <article className="report" data-status={verdict}>
      <header className="report__head">
        <h2 className="report__verdict">{issue.title || issue.url}</h2>
        <span className={`pill pill--${verdict}`}>{VERDICT_LABEL[verdict]}</span>
      </header>

      {eval_scores && (
        <section className="report__block report__scores">
          <h3 className="report__h">Evaluation</h3>
          <ul className="scores">
            <li className="scores__item">
              <span className="scores__val">{pct(eval_scores.repro_fidelity)}</span>
              <span className="scores__label">repro fidelity</span>
            </li>
            <li className="scores__item">
              <span className="scores__val">{pct(eval_scores.root_cause_correctness)}</span>
              <span className="scores__label">root-cause correctness</span>
            </li>
          </ul>
        </section>
      )}

      {repro_steps.length > 0 && (
        <section className="report__block">
          <h3 className="report__h">Confirmed repro steps</h3>
          <ol className="steps">
            {repro_steps.map((s) => (
              <li className="steps__item" key={s.n} data-step-status={s.status}>
                <span className={`steps__badge steps__badge--${s.status}`}>{s.status}</span>
                <span className="steps__action">{s.action}</span>
                {loadable(s.screenshot_ref) && (
                  <img
                    className="steps__shot"
                    src={s.screenshot_ref}
                    alt={`Step ${s.n}: ${s.action}`}
                    loading="lazy"
                  />
                )}
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="report__block">
        <h3 className="report__h">Root cause</h3>
        <p className="report__hyp">{root_cause.hypothesis}</p>
        {root_cause.mechanism && <p className="report__mechanism">{root_cause.mechanism}</p>}
        {evidence.console_error && <pre className="report__evidence">{evidence.console_error}</pre>}
        <span className="report__conf">confidence: {root_cause.confidence}</span>
      </section>

      {attempts.length > 0 && (
        <section className="report__block">
          <h3 className="report__h">Browser sessions</h3>
          <ul className="attempts">
            {attempts.map((a) => (
              <li className="attempts__item" key={a.number}>
                <span className="attempts__outcome" data-detected={a.bug_detected}>
                  attempt {a.number} · {a.bug_detected ? "reproduced" : "no repro"}
                </span>
                {a.session_replay_url && (
                  <a href={a.session_replay_url} target="_blank" rel="noopener noreferrer">
                    replay ↗
                  </a>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}
