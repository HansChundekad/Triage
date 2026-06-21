import { useEffect, useRef } from "react";
import type { StreamEvent } from "../types";

const AGENT_ABBR: Record<string, string> = {
  ParserAgent: "Parser", ReproAgent: "Repro", HypothesisAgent: "Hypothesis",
};

export default function LiveLog({ events }: { events: StreamEvent[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [events.length]);

  return (
    <div className="log">
      {events.map((e, i) => {
        if (e.type === "message") {
          return (
            <div className="log__msg" key={i} data-agent={e.from}>
              <span className="log__from">{e.from}</span>
              <span className="log__to">{e.to.map((t) => `@${t}`).join(" ")}</span>
              <span className="log__text">{e.text}</span>
            </div>
          );
        }
        if (e.type === "step") {
          return (
            <div className={`log__step log__step--${e.kind}`} key={i}>
              <span className="log__agent">{AGENT_ABBR[e.agent] ?? e.agent}</span>
              <span className="log__text">{e.text}</span>
            </div>
          );
        }
        return null;
      })}
      <div ref={endRef} />
    </div>
  );
}
