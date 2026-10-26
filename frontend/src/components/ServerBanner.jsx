import { useState } from "react";
import { Loader2, CloudOff, AlertTriangle, X } from "lucide-react";

const REASON_TEXT = {
  provider_refused: "The storage provider is refusing requests, often because a daily limit was reached.",
  timeout: "The storage provider didn't answer in time.",
  unreachable: "The storage provider can't be reached.",
  corrupt: "The saved backup couldn't be read.",
};

// Floats over the page instead of taking layout space: the project page is a
// fixed-height screen, and a banner in the flow would push it into scrolling.
const shell =
  "fixed bottom-4 left-1/2 -translate-x-1/2 z-50 w-[min(92vw,34rem)] rounded-xl border border-line-strong bg-surface shadow-lg px-4 py-3 text-[13px] text-fg flex items-start gap-3";

/**
 * Presentational only: the hook decides the phase. Shows nothing in the normal
 * case (warm server, healthy storage), which is most of the time.
 */
export default function ServerBanner({ phase, elapsedSeconds = 0, storage, onRetry }) {
  const [dismissed, setDismissed] = useState(false);

  if (phase === "waking") {
    return (
      <div role="status" aria-live="polite" className={shell}>
        <Loader2 size={16} className="animate-spin mt-0.5 text-muted flex-shrink-0" aria-hidden="true" />
        <div>
          <p className="font-medium">Waking the server…</p>
          <p className="text-fg-soft mt-0.5">
            The free host sleeps when it's idle, so the first visit can take up to a minute. Hang tight
            {elapsedSeconds > 0 ? ` (${elapsedSeconds}s)` : ""}.
          </p>
        </div>
      </div>
    );
  }

  if (phase === "unreachable") {
    return (
      <div role="alert" className={shell}>
        <CloudOff size={16} className="mt-0.5 text-danger flex-shrink-0" aria-hidden="true" />
        <div className="flex-1">
          <p className="font-medium">The server isn't responding</p>
          <p className="text-fg-soft mt-0.5">It may still be starting up, or it may be down for a moment.</p>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="h-8 px-3 rounded-lg border border-line-strong text-[12.5px] font-medium hover:bg-surface-2 transition-colors"
        >
          Try again
        </button>
      </div>
    );
  }

  if (phase === "ready" && storage?.state === "degraded" && !dismissed) {
    const detail = REASON_TEXT[storage.reason];
    return (
      <div role="status" aria-live="polite" className={shell}>
        <AlertTriangle size={16} className="mt-0.5 text-danger flex-shrink-0" aria-hidden="true" />
        <div className="flex-1">
          <p className="font-medium">Backup storage is offline</p>
          <p className="text-fg-soft mt-0.5">
            You can still analyze repos, but projects saved right now may not survive a server restart,
            and re-analyzing a repo you've seen before can take longer.
            {detail ? ` ${detail}` : ""}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          aria-label="Dismiss"
          className="h-6 w-6 -mr-1 -mt-0.5 inline-flex items-center justify-center rounded-md text-muted hover:text-fg hover:bg-surface-2 transition-colors"
        >
          <X size={14} aria-hidden="true" />
        </button>
      </div>
    );
  }

  return null;
}
