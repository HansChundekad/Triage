import { useRef, useState } from "react";
import UrlInput from "./components/UrlInput";
import LiveLog from "./components/LiveLog";
import { startLiveRun, startReplayRun } from "./api";
import type { RunReport, RunPhase, StreamEvent } from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

type Status = "idle" | "running" | "report" | "error";

export default function App() {
  const [status, setStatus] = useState<Status>("idle");
  const [phase, setPhase] = useState<RunPhase | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [report, setReport] = useState<RunReport | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const cancelRef = useRef<null | (() => void)>(null);

  function onEvent(e: StreamEvent) {
    setEvents((prev) => [...prev, e]);
    if (e.type === "status") setPhase(e.phase);
    if (e.type === "report") { setReport(e.report); setStatus("report"); }
    if (e.type === "error") { setErrorMsg(e.message); setStatus("error"); }
  }

  function onRun(mode: "live" | "replay", url: string) {
    cancelRef.current?.();
    setEvents([]); setReport(null); setErrorMsg(""); setPhase(null); setStatus("running");
    cancelRef.current = mode === "replay"
      ? startReplayRun(onEvent)
      : startLiveRun(API_BASE, url, onEvent);
  }

  return (
    <div className="shell">
      <header className="brand" role="banner">
        <span className="wordmark">Triage</span>
        <span className="tagline">reproduces your bugs by using your app</span>
      </header>

      <UrlInput onRun={onRun} disabled={status === "running"} />

      {status === "error" && <div className="banner banner--error" role="alert">{errorMsg}</div>}

      {status !== "idle" && (
        <main className="stage">
          {/* LiveLog (Task 6) */}
          <section aria-label="run log" className="pane pane--log">
            <LiveLog events={events} />
            {phase && <div className="phase">phase: {phase}</div>}
          </section>
          {/* BrowserView (Task 7) + ReportCard (Task 8) mount here later */}
          {report && <pre className="pane pane--report">{JSON.stringify(report, null, 2)}</pre>}
        </main>
      )}
    </div>
  );
}
