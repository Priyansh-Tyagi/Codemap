import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FolderOpen, GitBranch, Loader2 } from "lucide-react";
import Wordmark from "../components/Wordmark";
import AuthStatus from "../components/AuthStatus";
import ThemeToggle from "../components/ThemeToggle";
import HeroGraph from "../components/HeroGraph";
import { analyzeRepository, getServerConfig } from "../services/api";
import { describeApiError } from "../utils/apiError";

// Real, public repos that analyze well - so a visitor can see a result in
// one click instead of having to find a repo first.
const EXAMPLES = ["pallets/flask", "expressjs/express", "fastapi/full-stack-fastapi-template"];

export default function HomePage() {
  const navigate = useNavigate();
  // GitHub first: a deployed server can't read a visitor's local folders, so
  // this is the path almost everyone takes. Local path stays one click away.
  const [sourceMode, setSourceMode] = useState("github"); // "local" | "github"
  const [inputValue, setInputValue] = useState("");
  const [forceRefresh, setForceRefresh] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  // Shown on screen, and the value comes straight from the URL - anyone can
  // craft a link whose ?auth_error= reads like an official instruction. React
  // escapes it (no script risk), but strip control characters and cap the
  // length so it can't be a long, convincing message.
  const [authError] = useState(() => {
    const raw = new URLSearchParams(window.location.search).get("auth_error");
    return raw ? raw.replace(/[\u0000-\u001f\u007f-\u009f]/g, " ").trim().slice(0, 160) : null;
  });
  // Local-folder analysis is disabled on public servers (it would let any
  // visitor browse the server's own files), so only offer it if this server says so.
  const [allowLocal, setAllowLocal] = useState(false);
  useEffect(() => {
    let cancelled = false;
    getServerConfig().then((cfg) => {
      if (cancelled) return;
      setAllowLocal(cfg.allowLocalPaths);
      if (!cfg.allowLocalPaths) setSourceMode("github");
    });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleAnalyze(e) {
    e.preventDefault();
    const value = inputValue.trim();
    if (!value) return;

    setLoading(true);
    setError(null);
    try {
      const source = sourceMode === "github" ? { githubUrl: value, forceRefresh } : { path: value };
      const result = await analyzeRepository(source);
      // The graph is NOT rendered here. Navigating to /p/:id makes the URL the
      // single source of truth, so a fresh analysis and a shared link behave
      // identically.
      navigate(`/p/${result.projectId}`, { state: { cached: Boolean(result.cached) } });
    } catch (err) {
      setError(describeApiError(err));
      setLoading(false);
    }
  }

  function tryExample(slug) {
    setSourceMode("github");
    setInputValue(`https://github.com/${slug}`);
    setError(null);
  }

  return (
    <div className="min-h-screen flex flex-col bg-page">
      <header className="h-14 px-5 flex items-center gap-3 flex-shrink-0">
        <Wordmark />
        <div className="flex-1" />
        <ThemeToggle />
        <AuthStatus />
      </header>

      <main className="flex-1 w-full max-w-6xl mx-auto px-5 sm:px-8 py-8 grid lg:grid-cols-[minmax(0,30rem)_minmax(0,1fr)] gap-12 items-center">
        <div>
          <h1 className="text-[2.6rem] sm:text-5xl font-semibold tracking-[-0.035em] leading-[1.04] text-fg">
            See how your code fits together.
          </h1>
          <p className="mt-4 text-[15.5px] leading-relaxed text-muted max-w-md">
            Map every import in a repository, find circular dependencies, and see which files a change could break.
          </p>

          <form
            onSubmit={handleAnalyze}
            className="mt-8 rounded-2xl bg-surface border border-line shadow-float p-3"
          >
            {allowLocal && (
              <div role="group" aria-label="Source type" className="inline-flex bg-surface-2 border border-line rounded-lg p-0.5">
                <ModeButton active={sourceMode === "github"} onClick={() => setSourceMode("github")} Icon={GitBranch}>
                  GitHub URL
                </ModeButton>
                <ModeButton active={sourceMode === "local"} onClick={() => setSourceMode("local")} Icon={FolderOpen}>
                  Local path
                </ModeButton>
              </div>
            )}

            <div className="mt-3 flex gap-2">
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                aria-label="Repository source"
                placeholder={sourceMode === "github" ? "https://github.com/owner/repo" : "/path/to/a/local/repository"}
                className="flex-1 min-w-0 h-11 bg-surface-2 border border-line rounded-xl px-3.5 text-[14px] font-mono text-fg placeholder:text-faint hover:border-line-strong focus:outline-none focus:border-fg transition-colors"
              />
              <button
                type="submit"
                disabled={loading}
                className="inline-flex items-center justify-center gap-2 h-11 px-5 rounded-xl bg-accent text-accent-fg text-[14px] font-medium hover:opacity-90 disabled:opacity-50 transition-opacity whitespace-nowrap"
              >
                {loading && <Loader2 size={15} className="animate-spin" aria-hidden="true" />}
                {loading ? (sourceMode === "github" ? "Downloading…" : "Analyzing…") : "Analyze"}
              </button>
            </div>

            {sourceMode === "github" && (
              <div className="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-0.5">
                <label className="flex items-center gap-2 text-[12px] text-muted cursor-pointer">
                  <input
                    type="checkbox"
                    checked={forceRefresh}
                    onChange={(e) => setForceRefresh(e.target.checked)}
                    className="w-3.5 h-3.5 accent-[var(--accent)]"
                  />
                  Force refresh
                </label>
                <p className="text-[12px] text-faint">Sign in with GitHub for private repos and a higher rate limit.</p>
              </div>
            )}
          </form>

          <div className="mt-5 flex flex-wrap items-center gap-2">
            <span className="text-[12.5px] text-muted mr-1">Try one:</span>
            {EXAMPLES.map((slug) => (
              <button
                key={slug}
                type="button"
                onClick={() => tryExample(slug)}
                className="h-7 px-2.5 rounded-full border border-line-strong text-[12px] font-mono text-fg-soft hover:text-fg hover:bg-surface transition-colors"
              >
                {slug}
              </button>
            ))}
          </div>

          {authError && (
            <p role="alert" className="mt-4 text-danger text-[13px] break-words">{authError}</p>
          )}
          {error && (
            <p role="alert" className="mt-4 text-danger text-[13px] break-words">{error}</p>
          )}
        </div>

        <div className="hidden lg:block rounded-3xl bg-stage border border-line p-6"
             style={{ backgroundImage: "radial-gradient(var(--dot) 1.4px, transparent 1.4px)", backgroundSize: "22px 22px" }}>
          <HeroGraph />
        </div>
      </main>
    </div>
  );
}

function ModeButton({ active, onClick, Icon, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-[12.5px] font-medium rounded-md transition-colors ${
        active ? "bg-surface text-fg shadow-soft" : "text-muted hover:text-fg"
      }`}
    >
      <Icon size={14} aria-hidden="true" />
      {children}
    </button>
  );
}
