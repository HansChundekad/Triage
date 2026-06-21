import { useState } from "react";
import { isGithubIssueUrl } from "../api";

export default function UrlInput(
  { onRun, disabled }: { onRun: (mode: "live" | "replay", url: string) => void; disabled: boolean }
) {
  const [url, setUrl] = useState("");
  const valid = isGithubIssueUrl(url);
  return (
    <form
      className="urlbar"
      onSubmit={(e) => { e.preventDefault(); if (valid && !disabled) onRun("live", url.trim()); }}
    >
      <input
        type="url" className="urlbar__input" placeholder="Paste a GitHub issue URL…"
        value={url} onChange={(e) => setUrl(e.target.value)} disabled={disabled}
        aria-label="GitHub issue URL"
      />
      <button type="submit" className="btn btn--primary" disabled={!valid || disabled}>Run</button>
      <button type="button" className="btn btn--ghost" disabled={disabled}
        onClick={() => onRun("replay", "demo")}>Demo</button>
    </form>
  );
}
