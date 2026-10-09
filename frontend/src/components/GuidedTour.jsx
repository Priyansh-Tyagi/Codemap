import { useEffect, useState } from "react";
import { getProjectTour, narrateProjectTour } from "../services/api";
import { describeApiError } from "../utils/apiError";

const MODES = [
  { id: "trace", label: "Top-down", hint: "Start at the entry points and follow what they import" },
  { id: "foundation", label: "Core first", hint: "Start with the files everything else is built on" },
];

/** Filename first and bright, folder underneath and dim - the old single
 * truncated path hid exactly the part that distinguishes one file from another. */
function FileLabel({ path }) {
  const clean = path.replace(/\\/g, "/");
  const i = clean.lastIndexOf("/");
  const name = clean.slice(i + 1);
  const dir = i >= 0 ? clean.slice(0, i) : "";
  return (
    <span className="block min-w-0" title={path}>
      <span className="block text-[12px] font-mono text-parchment-200 group-hover:text-brass-400 truncate">
        {name}
      </span>
      {dir && <span className="block text-[10px] font-mono text-parchment-700 truncate">{dir}</span>}
    </span>
  );
}

/**
 * The guided tour panel. Two layers, per the project's Phase G constraint:
 *  1. The deterministic tour loads on open with no AI involved.
 *  2. "Narrate with AI" is a separate, explicit opt-in. Its failure only ever
 *     adds an inline notice - the stops already on screen never disappear.
 */
export default function GuidedTour({ projectId, onSelectFile, onClose }) {
  const [mode, setMode] = useState("trace");
  const [status, setStatus] = useState("loading"); // loading | ready | error
  const [stops, setStops] = useState([]);
  const [note, setNote] = useState(null);
  const [narrating, setNarrating] = useState(false);
  const [narrationError, setNarrationError] = useState(null);
  const [narrated, setNarrated] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    setNarrated(false);
    setNarrationError(null);
    getProjectTour(projectId, mode)
      .then((data) => {
        if (cancelled) return;
        setStops(data.stops);
        setNote(data.note ?? null);
        setStatus("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setStatus("error");
        setNarrationError(describeApiError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, mode]);

  async function handleNarrate() {
    setNarrating(true);
    setNarrationError(null);
    try {
      const data = await narrateProjectTour(projectId, mode);
      setStops(data.stops);
      setNarrated(data.narrated);
      if (!data.narrated && data.narrationError) setNarrationError(data.narrationError);
    } catch (err) {
      // The endpoint degrades gracefully (200 + narrationError) for every
      // AI-side failure, so reaching here means the REQUEST failed - still
      // never breaks the stops already on screen.
      setNarrationError(describeApiError(err));
    } finally {
      setNarrating(false);
    }
  }

  // Group consecutive stops that share a stage, as headings.
  const stages = [];
  for (const stop of stops) {
    if (stages.length === 0 || stages[stages.length - 1].name !== stop.stage) {
      stages.push({ name: stop.stage, stops: [stop] });
    } else {
      stages[stages.length - 1].stops.push(stop);
    }
  }

  return (
    <div className="absolute inset-y-0 right-0 w-80 bg-ink-900 border-l border-ink-700 flex flex-col z-10">
      <div className="flex items-center gap-2 px-4 h-14 border-b border-ink-700 flex-shrink-0">
        <h2 className="font-display text-[14px] font-semibold text-parchment-100">Guided tour</h2>
        <div className="flex-1" />
        <button
          type="button"
          onClick={onClose}
          aria-label="Close guided tour"
          className="text-parchment-500 hover:text-parchment-200 text-[13px]"
        >
          ✕
        </button>
      </div>

      <div className="px-4 pt-3" role="group" aria-label="Tour direction">
        <div className="inline-flex w-full bg-ink-800 border border-ink-600 rounded-sm p-0.5">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              aria-pressed={mode === m.id}
              title={m.hint}
              onClick={() => setMode(m.id)}
              className={`flex-1 px-2 py-1 text-[11px] font-mono rounded-sm transition-colors ${
                mode === m.id ? "bg-brass-500 text-ink-950" : "text-parchment-400 hover:text-parchment-100"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3">
        {status === "loading" && <p className="text-[12px] text-parchment-500">Loading tour…</p>}
        {status === "error" && (
          <p role="alert" className="text-[12px] text-flag-400">{narrationError}</p>
        )}
        {status === "ready" && stops.length === 0 && (
          <p className="text-[12px] text-parchment-500 leading-relaxed">
            {note || "No files to tour in this project."}
          </p>
        )}
        {status === "ready" && stops.length > 0 && (
          <>
            {!narrated && (
              <button
                type="button"
                onClick={handleNarrate}
                disabled={narrating}
                className="mb-3 w-full border border-brass-700 hover:border-brass-500 text-brass-400 text-[12px] font-mono px-3 py-1.5 rounded-sm transition-colors disabled:opacity-40"
              >
                {narrating ? "Narrating…" : "✨ Narrate with AI"}
              </button>
            )}
            {narrationError && (
              <p role="alert" className="mb-3 text-[11px] text-parchment-500 leading-relaxed">
                {narrationError} Showing the deterministic tour.
              </p>
            )}
            {stages.map((stage, si) => (
              <div key={`${stage.name}-${si}`} className="mb-4">
                <h3 className="text-[10px] uppercase tracking-wide text-parchment-600 mb-1.5">
                  {stage.name}
                </h3>
                <ol className="space-y-2.5">
                  {stage.stops.map((stop) => (
                    <li key={stop.fileId}>
                      {stop.members?.length > 0 ? (
                        <div>
                          <div className="text-[12px] font-mono text-parchment-300">{stop.filePath}</div>
                          <ul className="mt-1 ml-2 pl-2 border-l border-ink-600 space-y-1">
                            {stop.members.map((m) => (
                              <li key={m.fileId}>
                                <button
                                  type="button"
                                  onClick={() => onSelectFile(m.fileId)}
                                  className="group text-left w-full"
                                >
                                  <FileLabel path={m.filePath} />
                                </button>
                              </li>
                            ))}
                          </ul>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => onSelectFile(stop.fileId)}
                          className="group text-left w-full"
                        >
                          <FileLabel path={stop.filePath} />
                        </button>
                      )}
                      {stop.narrative ? (
                        <p className="text-[11px] text-parchment-400 leading-snug mt-0.5">{stop.narrative}</p>
                      ) : (
                        stop.reasons.map((reason, i) => (
                          <p key={i} className="text-[11px] text-parchment-600 leading-snug">{reason}</p>
                        ))
                      )}
                    </li>
                  ))}
                </ol>
              </div>
            ))}
            {note && <p className="text-[11px] text-parchment-600 leading-relaxed border-t border-ink-700 pt-3">{note}</p>}
          </>
        )}
      </div>
    </div>
  );
}
