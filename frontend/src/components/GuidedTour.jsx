import { useEffect, useState } from "react";
import { Compass, Sparkles, X } from "lucide-react";
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
      <span className="block text-[12.5px] font-mono font-medium text-fg group-hover:underline underline-offset-2 truncate">
        {name}
      </span>
      {dir && <span className="block text-[10.5px] font-mono text-faint truncate">{dir}</span>}
    </span>
  );
}

/**
 * The guided tour panel. Two layers, per the project's Phase G constraint:
 *  1. The deterministic tour loads on open with no AI involved.
 *  2. "Narrate with AI" is a separate, explicit opt-in. Its failure only ever
 *     adds an inline notice - the stops already on screen never disappear.
 *
 * Stops are numbered and joined by a line because the tour IS a sequence:
 * the numbering is information (read in this order), not decoration.
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

  // Consecutive stops sharing a stage are grouped under one caption; the
  // running number continues across groups.
  const stages = [];
  stops.forEach((stop, index) => {
    const last = stages[stages.length - 1];
    if (!last || last.name !== stop.stage) stages.push({ name: stop.stage, items: [{ stop, index }] });
    else last.items.push({ stop, index });
  });

  return (
    <div className="absolute top-0 bottom-3 right-3 w-[22rem] max-w-[calc(100%-1.5rem)] rounded-2xl bg-surface border border-line shadow-float flex flex-col z-10 overflow-hidden">
      <div className="flex items-center gap-2 px-4 h-14 border-b border-line flex-shrink-0">
        <Compass size={16} className="text-muted" aria-hidden="true" />
        <h2 className="text-[14px] font-semibold text-fg">Guided tour</h2>
        <div className="flex-1" />
        <button
          type="button"
          onClick={onClose}
          aria-label="Close guided tour"
          className="grid place-items-center w-7 h-7 rounded-lg text-muted hover:text-fg hover:bg-surface-2"
        >
          <X size={15} aria-hidden="true" />
        </button>
      </div>

      <div className="px-4 pt-3" role="group" aria-label="Tour direction">
        <div className="grid grid-cols-2 bg-surface-2 border border-line rounded-lg p-0.5">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              aria-pressed={mode === m.id}
              title={m.hint}
              onClick={() => setMode(m.id)}
              className={`px-2 py-1 text-[12px] font-medium rounded-md transition-colors ${
                mode === m.id ? "bg-surface text-fg shadow-soft" : "text-muted hover:text-fg"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3">
        {status === "loading" && <p className="text-[12.5px] text-muted">Loading tour…</p>}
        {status === "error" && (
          <p role="alert" className="text-[12.5px] text-danger">{narrationError}</p>
        )}
        {status === "ready" && stops.length === 0 && (
          <p className="text-[12.5px] text-muted leading-relaxed">{note || "No files to tour in this project."}</p>
        )}
        {status === "ready" && stops.length > 0 && (
          <>
            {!narrated && (
              <button
                type="button"
                onClick={handleNarrate}
                disabled={narrating}
                className="mb-3 w-full inline-flex items-center justify-center gap-1.5 h-9 rounded-lg border border-line-strong text-[12.5px] font-medium text-fg hover:bg-surface-2 transition-colors disabled:opacity-50"
              >
                <Sparkles size={14} aria-hidden="true" />
                {narrating ? "Narrating…" : "Narrate with AI"}
              </button>
            )}
            {narrationError && (
              <p role="alert" className="mb-3 rounded-lg bg-surface-2 border border-line px-3 py-2 text-[11.5px] text-muted leading-relaxed">
                {narrationError} Showing the deterministic tour.
              </p>
            )}

            <ol className="relative">
              {/* the route line joining the numbered stops */}
              <span className="absolute left-[11px] top-3 bottom-3 w-px bg-line-strong" aria-hidden="true" />
              {stages.map((stage, si) => (
                <li key={`${stage.name}-${si}`} className="relative">
                  <h3 className="relative pl-9 pt-2 pb-1 text-[11.5px] font-medium text-faint">{stage.name}</h3>
                  <ol>
                    {stage.items.map(({ stop, index }) => (
                      <li key={stop.fileId} className="relative pl-9 pb-3.5">
                        <span className="absolute left-0 top-0 grid place-items-center w-[23px] h-[23px] rounded-full bg-surface border border-line-strong text-[11px] font-semibold text-fg-soft tabular-nums">
                          {index + 1}
                        </span>

                        {stop.members?.length > 0 ? (
                          <div>
                            <div className="text-[12.5px] font-medium text-fg">{stop.filePath}</div>
                            <ul className="mt-1.5 space-y-1.5 border-l border-line pl-3">
                              {stop.members.map((m) => (
                                <li key={m.fileId}>
                                  <button type="button" onClick={() => onSelectFile(m.fileId)} className="group text-left w-full">
                                    <FileLabel path={m.filePath} />
                                  </button>
                                </li>
                              ))}
                            </ul>
                          </div>
                        ) : (
                          <button type="button" onClick={() => onSelectFile(stop.fileId)} className="group text-left w-full">
                            <FileLabel path={stop.filePath} />
                          </button>
                        )}

                        {stop.narrative ? (
                          <p className="mt-1 text-[12px] text-fg-soft leading-snug">{stop.narrative}</p>
                        ) : (
                          stop.reasons.map((reason, i) => (
                            <p key={i} className="mt-0.5 text-[11.5px] text-muted leading-snug">{reason}</p>
                          ))
                        )}
                      </li>
                    ))}
                  </ol>
                </li>
              ))}
            </ol>

            {note && <p className="mt-1 border-t border-line pt-3 text-[11.5px] text-faint leading-relaxed">{note}</p>}
          </>
        )}
      </div>
    </div>
  );
}
