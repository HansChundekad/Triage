import type { SessionInfo } from "../types";

export default function BrowserView({ session, live }: { session: SessionInfo | null; live: boolean }) {
  if (!session) {
    return (
      <div className="browser browser--empty">
        <p className="browser__hint">No live session yet — the browser appears once ReproAgent starts.</p>
      </div>
    );
  }
  const label = live ? "Open live session ↗" : "Watch replay ↗";
  const href = live ? session.liveViewUrl : session.replayUrl;
  return (
    <div className="browser">
      {live && (
        <iframe
          className="browser__frame" src={session.liveViewUrl}
          title={`Browserbase session ${session.sessionId}`}
          sandbox="allow-scripts allow-same-origin"
        />
      )}
      <a className="browser__link" href={href} target="_blank" rel="noopener noreferrer">
        {label}<span className="browser__sid">{session.sessionId} · attempt {session.attempt}</span>
      </a>
    </div>
  );
}
