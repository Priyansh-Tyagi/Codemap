import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Wordmark from "../components/Wordmark";
import { analyzeRepository } from "../services/api";

export default function HomePage() {
  const navigate = useNavigate();
  const [sourceMode, setSourceMode] = useState("local"); // "local" | "github"
  const [inputValue, setInputValue] = useState("");
  const [forceRefresh, setForceRefresh] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleAnalyze(e) {
    e.preventDefault();
    const value = inputValue.trim();
    if (!value) return;

    setLoading(true);
    setError(null);
    try {
      const source =
        sourceMode === "github" ? { githubUrl: value, forceRefresh } : { path: value };
      const result = await analyzeRepository(source);
      // The graph is NOT rendered here. Navigating to /p/:id makes the URL the
      // single source of truth, so a fresh analysis and a shared link behave
      // identically.
      navigate(`/p/${result.projectId}`, { state: { cached: Boolean(result.cached) } });
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(detail || "Couldn't reach the backend. Is it running on port 8000?");
      setLoading(false);
    }
  }

  return (
    <div className="h-screen w-screen flex flex-col bg-ink-950">
      <header className="flex items-center gap-3 px-4 h-14 border-b border-ink-700 bg-ink-900 flex-shrink-0">
        <Wordmark />
      </header>

      <main className="flex-1 flex items-center justify-center px-4">
        <div className="w-full max-w-xl">
          <h1 className="font-display text-2xl font-semibold text-parchment-100">
            Chart a codebase.
          </h1>
          <p className="mt-2 text-[13px] text-parchment-500 leading-relaxed">
            Analyze a local repository or a public GitHub repo. Every analysis gets a
            shareable link.
          </p>

          <div className="mt-6">
            <SourceModeToggle mode={sourceMode} onChange={setSourceMode} />
          </div>

          <form onSubmit={handleAnalyze} className="mt-3 flex gap-2 items-center">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              aria-label="Repository source"
              placeholder={
                sourceMode === "github"
                  ? "https://github.com/owner/repo"
                  : "/path/to/a/local/repository"
              }
              className="flex-1 bg-ink-800 border border-ink-600 rounded-sm px-3 py-2 text-[13px] font-mono text-parchment-100 placeholder:text-parchment-700 focus:outline-none focus:border-brass-500"
            />
            <button
              type="submit"
              disabled={loading}
              className="bg-brass-500 hover:bg-brass-400 disabled:opacity-40 text-ink-950 text-[13px] font-medium px-4 py-2 rounded-sm transition-colors whitespace-nowrap"
            >
              {loading ? (sourceMode === "github" ? "Downloading…" : "Analyzing…") : "Analyze"}
            </button>
          </form>

          {sourceMode === "github" && (
            <label className="mt-3 flex items-center gap-1.5 text-[11px] text-parchment-400 cursor-pointer w-fit">
              <input
                type="checkbox"
                checked={forceRefresh}
                onChange={(e) => setForceRefresh(e.target.checked)}
                className="accent-brass-500"
              />
              Force refresh
            </label>
          )}

          {error && (
            <p role="alert" className="mt-4 text-flag-400 text-[12px] font-mono break-words">
              {error}
            </p>
          )}
        </div>
      </main>
    </div>
  );
}

function SourceModeToggle({ mode, onChange }) {
  return (
    <div className="inline-flex items-center bg-ink-800 border border-ink-600 rounded-sm p-0.5">
      <ToggleButton active={mode === "local"} onClick={() => onChange("local")}>
        Local path
      </ToggleButton>
      <ToggleButton active={mode === "github"} onClick={() => onChange("github")}>
        GitHub URL
      </ToggleButton>
    </div>
  );
}

function ToggleButton({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-2.5 py-1 text-[12px] font-mono rounded-sm transition-colors ${
        active ? "bg-brass-500 text-ink-950" : "text-parchment-400 hover:text-parchment-100"
      }`}
    >
      {children}
    </button>
  );
}
