# CodeMap

**Interactive Codebase Intelligence & Dependency Analyzer**

CodeMap points at a local JavaScript/TypeScript repository and gives you an
interactive dependency graph, circular-dependency detection, change-impact
analysis, and a deterministic risk score per file — all from real static
analysis, not guesswork.

> Give CodeMap a repository and understand its architecture, dependencies,
> and change impact in seconds.

---

## Screenshots

*(Add your own screenshots here once you've run CodeMap locally — see
"Capturing screenshots" below for exactly which five to take.)*

1. Full dependency graph
2. File details panel
3. Change-impact analysis
4. Circular dependency highlighted
5. Project stats / architecture breakdown

---

## Features

- **Repository scanning** — recursively finds `.js`/`.jsx`/`.ts`/`.tsx`/`.py` files, skipping `node_modules`, `dist`, `build`, `__pycache__`, and similar directories at the directory-walk level (never even descends into them).
- **JavaScript/TypeScript and Python support** — both languages are parsed, resolved, and graphed through entirely separate pipelines (Python's import system genuinely isn't "JS with different syntax": relative-import "level," dotted absolute paths, and no free syntactic marker for local-vs-external the way JS's `./` prefix gives you one) and merged into a single graph. A `.py` file and a `.js` file with the same base name can never accidentally link to each other — proven with a dedicated test, not just asserted. Python parsing uses the stdlib `ast` module directly, no subprocess needed.
- **Filter and focus** — narrow the graph and file tree by architecture category, minimum risk level, or folder (including subtree scoping); filtered-out nodes are removed from layout entirely rather than just dimmed, so a large repo actually declutters instead of just fading.
- **GitHub Actions CI check** — the same analysis engine, wrapped as a CLI and a composite GitHub Action (`action.yml`), that gates a pull request on newly-introduced circular dependencies or files crossing a risk threshold, posting the result as a PR comment. See "CI/CD integration" below.
- **Local or GitHub URL input** — analyze a directory on your own machine, or paste a public GitHub repo URL (`https://github.com/owner/repo`, optionally `/tree/branch`) and CodeMap downloads a one-shot tarball snapshot, analyzes it, and cleans up the temp files automatically. No `git clone`, no commit history fetched.
- **Sign in with GitHub** — OAuth sign-in gets you your own 5,000/hour GitHub API rate limit (instead of sharing the server's) and the ability to analyze your own private repositories. Entirely optional: every feature above works fully anonymously. See "GitHub sign-in" below.
- **GitHub result caching** — a repeat analysis of the same repo+ref within 10 minutes is served instantly from memory, skipping both the download and the re-parse entirely (a "Force refresh" checkbox bypasses this when you want fresh data sooner). Local paths are never cached — caching your own actively-edited files would risk silently showing stale results.
- **AST-based import extraction** — uses Babel (`@babel/parser` + `@babel/traverse`) via a small Node subprocess, so JSX and TypeScript syntax are understood natively rather than approximated with regex.
- **Local dependency resolution** — resolves relative imports to real files on disk, handling extension guessing and `index` files, with a project-root containment check so a crafted import can't resolve outside the analyzed directory.
- **Interactive dependency graph** — rendered with React Flow, laid out with `dagre` (not naive column-stacking), colored by architecture category, with click-to-highlight for a node's direct dependencies/dependents.
- **Circular dependency detection** — finds every cycle via `networkx.simple_cycles`, and renders the cycle-closing edge as a distinct curved line rather than letting a standard layout algorithm mis-route it.
- **Change-impact analysis** — reverse-graph traversal answering "what breaks if I change this file," split into direct and indirect dependents.
- **Deterministic risk scoring** — a transparent 0–100 score per file (dependents + centrality + complexity + cycle membership), with human-readable reasons, not a black box.
- **Architecture classification** — heuristic path-based categorization (Component, Service, Controller, Model, Util, Hook, Route, etc. for JS; plus Django/Flask-flavored categories for Python — Serializer, Migration, Command, Admin — including filename-exact rules like `views.py`/`models.py`/`urls.py` so Django's common flat per-app layout, with no subfolders at all, is still classified correctly).
- **File tree + search** — browse by folder, or search to jump straight to a file and focus the graph on it.

## What CodeMap intentionally does NOT do

Documented limitations, not oversights:

- No bundler path-alias resolution (webpack `resolve.alias`, tsconfig `paths` like `@/components/Button`) — only relative (`./`, `../`) and absolute (`/`) specifiers resolve to local JS/TS files today.
- Python resolution does not distinguish regular packages (with `__init__.py`) from implicit namespace packages (PEP 420) — any directory is treated as a valid package. Does not support a `src/`-layout Python project where the real package root is nested below the directory you point CodeMap at.
- No re-export detection for Python (JS's `export { x } from "./y"` has a direct concept; Python's equivalent — importing something into `__init__.py` specifically so other code can import it from the package rather than the submodule — is a convention, not syntax, and isn't specially detected).
- No support for other non-JS/TS/Python languages.
- No git history analysis, and GitHub analysis is a snapshot at one ref (branch/commit), not a clone — no commit history is fetched or available.
- GitHub repos over 200MB are rejected before download (configurable in `analyzer/github_fetcher.py`).
- Unauthenticated GitHub API requests are capped at 60/hour per IP by GitHub itself — easy to hit on a shared or cloud IP (this was hit live while building the feature). Set a `GITHUB_TOKEN` environment variable (a plain personal access token, no special scopes needed for public repos) to raise that to 5,000/hour.
- Projects are stored in a single SQLite file with no expiry or eviction — it grows with every analysis (roughly a few MB for a 100-file repo) and is never pruned. Fine for a personal tool or a demo; a public deployment would need a retention policy. SQLite also assumes one server process (see Persistence below).
- Listed circular dependencies are capped at 200 (shortest first) with a "200+" indicator; whether a file is *in* a cycle is always exact. See "Scaling behavior" below.
- Betweenness centrality is skipped above 1500 files in a single repo (returned as `null`) to avoid an expensive computation on very large codebases; degree centrality is always computed.

---

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | React + Vite + Tailwind CSS v4 + React Flow + dagre + Axios |
| Backend | Python + FastAPI |
| Parsing | JS/TS: Node.js + `@babel/parser`/`@babel/traverse`, invoked as a one-shot subprocess. Python: stdlib `ast` module, called directly (no subprocess). |
| Graph analysis | NetworkX |
| Storage | SQLite (stdlib `sqlite3`, no ORM) — persistent, shareable project links |
| Auth | GitHub OAuth (classic OAuth App, authorization-code flow), opaque session cookie, `cryptography` (Fernet) for tokens at rest |

## Architecture

```
React (Vite) — Graph View / File Tree / Details / Impact / Metrics
        │  REST (Axios)
        ▼
FastAPI — /api/analyze, /projects, /files, /impact, /cycles, /metrics
        │
        ▼
Analysis Engine (Python)
  ├─ File Scanner (os.walk + ignore rules)
  ├─ JS/TS pipeline: Parser Bridge → subprocess → Node/Babel AST → imports JSON
  │    ├─ Import Classifier (local vs external)
  │    └─ Path Resolver (extension/index resolution)
  ├─ Python pipeline: stdlib `ast` → imports (no subprocess)
  │    └─ Python Resolver (dotted-path + relative-level resolution;
  │         classification and resolution are the same step here, unlike JS)
  ├─ Architecture Classifier (path-based heuristic, JS + Django/Flask conventions)
  └─ Risk Scorer (dependents + centrality + complexity + cycles)
        │
        ▼
Graph Engine (NetworkX) — ONE graph merging both languages' output
  ├─ Cycle detection
  ├─ Centrality (degree always, betweenness if ≤1500 nodes)
  ├─ Dependency depth (cycle-safe DFS)
  └─ Impact analysis (reverse-graph BFS)
```

---

## Setup (Windows)

### 1. Backend

```powershell
cd backend\parser
npm install

cd ..
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Run the test suite:
```powershell
python -m pytest tests\ -v
```

Start the API:
```powershell
cd app
python -m uvicorn main:app --reload --port 8000
```

### 2. Frontend

In a second terminal:
```powershell
cd frontend
npm install
npm run dev
```

Open the printed URL (normally `http://localhost:5173`).

### 3. Try it

Choose "Local path" or "GitHub URL" using the toggle next to the input box.

For a local path, the bundled demo repo is a good first try:
```
C:\path\to\codemap\examples\demo-repo
```
(Use forward slashes or the path as shown above; a raw Windows backslash
path can occasionally be misread as a JSON escape sequence when typed into
the browser input.)

For a GitHub URL, paste any public repo, e.g.:
```
https://github.com/owner/repo
```
Note: unauthenticated GitHub API requests are capped at 60/hour per IP —
see "What CodeMap intentionally does NOT do" below if you hit that limit.
Signing in with GitHub (optional - see "GitHub sign-in" below) raises this
to your own 5,000/hour and lets you analyze your own private repos.

---

## The demo repo

`examples/demo-repo` is a small, deliberately-constructed app (not a real
product) built to exercise every CodeMap feature at once: multiple
architecture categories, a genuine circular dependency, and one
heavily-depended-on utility file. Actual output from analyzing it:

- **15 files, 23 dependency edges, 1 circular dependency, 1 connected component**
- **Cycle:** `authService.js → userService.js → authService.js` (a realistic pattern — auth needs to look up users, user registration needs to issue tokens)
- **Highest risk file:** `userService.js` (Medium, 44/100) — three dependents, involved in the cycle, moderate centrality
- **Categories represented:** Route, Controller, Service, Model, Component, Hook, Util, and one uncategorized entry point (`app.js`)

These numbers came from actually running CodeMap against the repo, not
estimates — rerun it yourself and you should see the same results (this
demo repo can also serve as a quick regression check that nothing broke).

## The Python demo repo

`examples/demo-repo-python` is the Python twin of `demo-repo` above — the
same route/controller/service/model layering, the same deliberate cycle
pattern, the same over-relied-on validators file, rebuilt in Python
specifically so the two demo repos give a genuine apples-to-apples
comparison of CodeMap analyzing the same application shape in two
languages. Actual output from analyzing it:

- **18 files, 19 dependency edges, 1 circular dependency**
- **Cycle:** `auth_service.py → user_service.py → auth_service.py` (same realistic pattern as the JS version — auth needs to look up users, user registration needs to issue tokens)
- **Highest risk file:** `user_service.py` (Medium, 41/100)
- **Categories represented:** Route, Controller, Service, Model, Util — using the Django/Flask-flavored classification rules, not the JS ones
- **One genuine external dependency detected:** `datetime` (stdlib, from `utils/formatting.py`) — correctly distinguished from the project's own local modules

## CI/CD integration

CodeMap's analysis engine is also available as a CLI (`backend/app/cli.py`)
and wrapped as a composite GitHub Action (`action.yml` at the repo root),
so a PR can be gated on dependency-graph regressions, not just reviewed
manually.

### CLI usage

Run from `backend/app/` (same convention as `uvicorn main:app`):

```bash
# Human-readable summary, no gating
python cli.py analyze ../../examples/demo-repo

# Fail (exit 1) if any file's risk score is 80 or above
python cli.py analyze ../../examples/demo-repo --risk-threshold 80

# Write a baseline snapshot (typically generated from your main branch)
python cli.py analyze ../../examples/demo-repo --output baseline.json

# Compare against that baseline, failing ONLY on a genuinely new cycle -
# pre-existing circular dependencies don't block every future PR
python cli.py analyze ../../examples/demo-repo --baseline baseline.json --fail-on-new-cycle

# Machine-readable output for scripting, or PR-comment-ready markdown
python cli.py analyze ../../examples/demo-repo --format json
python cli.py analyze ../../examples/demo-repo --format markdown
```

Exit codes: `0` = passed, `1` = failed a gating check, `2` = couldn't
analyze the path at all (bad argument, not an analysis result).

### Using the Action in a workflow

```yaml
- uses: actions/checkout@v4
- uses: <owner>/codemap@main   # or a local path via "uses: ./" within this repo
  with:
    path: src
    risk-threshold: '80'
    fail-on-new-cycle: 'true'
    baseline: codemap-baseline.json
```

`.github/workflows/codemap-ci.yml` in this repo is a working, self-contained
example: it runs the Action against `examples/demo-repo`, comparing against
`examples/demo-repo-baseline.json` (generated the same way you'd generate
one for a real project — run the CLI with `--output` against your default
branch and commit the result).

### What I could and couldn't verify from here

Being direct about this rather than implying more confidence than is
warranted: I fully tested the CLI itself (11 automated tests, all running
the actual command as a subprocess — exit codes, baseline diffing, a
genuinely-introduced new cycle correctly detected without false-flagging
a pre-existing baselined one) and validated `action.yml`'s YAML structure
and the exact shell logic each step runs. What I *couldn't* test from this
sandbox is the parts that only exist inside a real GitHub Actions runner —
the PR-comment-posting step (`actions/github-script`) needs a live GitHub
API token and an actual pull request to post to. Push this to a real
GitHub repo, open a PR that touches `examples/demo-repo/`, and that's the
piece to watch for the first time.

## Capturing screenshots

I can't capture browser screenshots directly, but here's exactly what to
grab once the app's running against `examples/demo-repo`:

1. **Full graph** — after analyzing, before clicking anything, fit-to-view.
2. **File details** — click `userService.js`, showing its Medium risk badge and reasons.
3. **Impact analysis** — with `userService.js` still selected, screenshot the "Change impact" panel showing its dependents.
4. **Circular dependency** — zoom into the `authService.js`/`userService.js` pair showing the curved dashed cycle-closing edge.
5. **Project stats** — the right-hand "Project" panel showing file/dependency/cycle counts.

---

## API reference

FastAPI auto-generates interactive docs once the backend is running:
`http://localhost:8000/docs`

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/analyze` | `{ path }` or `{ githubUrl }` → runs the full pipeline, returns a `projectId` |
| GET | `/api/projects/{id}` | Project summary stats |
| GET | `/api/projects/{id}/graph` | Full node + edge list |
| GET | `/api/projects/{id}/files` | Lightweight file list |
| GET | `/api/projects/{id}/files/{path}` | Single file detail |
| GET | `/api/projects/{id}/files/{path}/dependencies` | Direct outgoing deps |
| GET | `/api/projects/{id}/files/{path}/dependents` | Direct incoming deps |
| GET | `/api/projects/{id}/files/{path}/impact` | Change-impact analysis |
| GET | `/api/projects/{id}/cycles` | All detected cycles |
| GET | `/api/projects/{id}/metrics` | Aggregate project metrics |
| GET | `/api/auth/github/login` | Redirects to GitHub's OAuth consent screen |
| GET | `/api/auth/github/callback` | OAuth callback; creates a session, redirects to the frontend |
| GET | `/api/auth/me` | `{ user: { login, avatarUrl } \| null }` for the current session |
| POST | `/api/auth/logout` | Clears the current session |

Every `/api/projects/{id}...` route above is also where private-repo access control lives (see "GitHub sign-in" below) — a private project 404s for anyone but the session that created it.

---

## Persistence and shareable links

Every analysis is saved to a SQLite file and gets a permanent URL, `/p/<projectId>`. Open that URL in any browser and the full interactive view loads from the stored analysis — no re-analysis, nothing to type. The "Copy link" button in the project header copies it.

- **Where the file lives:** `CODEMAP_DB_PATH` if set; otherwise `backend/app/codemap.db`, anchored to that directory regardless of where you launch `uvicorn` from. (Earlier this defaulted to `./codemap.db` relative to the process's working directory - starting the server from a slightly different directory between sessions, e.g. a new terminal or an IDE run config, silently created a second, empty database, which looked exactly like "persistence doesn't work." Fixed; see `backend/tests/test_db_path_default.py`.) Tables are created lazily on first use, never at import time. You do not need to set `CODEMAP_DB_PATH` yourself for local development - it's only there for deployment, where you point it at a persistent disk (see below).
- **Why SQLite, not Postgres:** one process, almost no concurrent writes, and each project is one row of JSON. The tool that fits is the simpler one.
- **What is (and isn't) cached:** GitHub analyses are cached for 10 minutes per repo+ref (persisted, so the cache also survives restarts). Local paths are never cached — caching a folder you're actively editing would silently show stale results.
- **Proof it persists:** `backend/tests/test_persistence.py` runs real separate Python processes that share only the DB file, and importing the store is tested to not create a database file as a side effect.

### Deployment caveat: ephemeral disks

Most hosts (Render, Railway, Fly) give a web service a filesystem that is **wiped on every redeploy**. With the default DB path, every redeploy silently deletes every stored project — and every link you've shared then shows "Project not found."

Fix: attach a persistent disk/volume and point `CODEMAP_DB_PATH` at it. A Render blueprint is included as `render.yaml` (disk mounted at `/var/data`, `CODEMAP_DB_PATH=/var/data/codemap.db`). Two constraints follow from this design:

- **One instance only.** A persistent disk attaches to a single instance, and SQLite is a single-writer database. Don't scale the backend horizontally.
- **Persistent disks are typically a paid-plan feature** — confirm your host's current requirements and pricing.

I have not deployed `render.yaml` to a real Render account; treat it as a starting point and verify it (in particular that Node.js is available in the Python runtime for the parser's `npm install`).

### Client-side routing on static hosts

Deep links like `/p/abc123` are handled by the React app, so a hard page load needs the host to serve `index.html` for unknown paths. `frontend/public/_redirects` (Netlify) and `frontend/vercel.json` (Vercel) are included. Verified locally: a hard load of `/p/<id>` against a production build returns the app, not a 404.

---

## Fixes from testing real repos

Three more problems, found by running CodeMap against real GitHub
repositories (Flask, Express, [crocodilestick/Calibre-Web-Automated](https://github.com/crocodilestick/Calibre-Web-Automated) — 395 files, Python+JS) instead of only the small bundled demo repos.

**1. A long filename crashed the entire GitHub analysis.** Calibre-Web-
Automated contains a test fixture with a 150+ character filename. Combined
with a temp-directory path, Python's `tarfile.extractall` raised
`FileNotFoundError` on Windows (MAX_PATH) — and on any OS, since filenames
are capped around 255 bytes regardless. One unwritable file failed the
*entire* analysis with a bare 500. Fixed two ways: extraction now skips
files the scanner would never read anyway (filtering to supported source
extensions before extracting, not after — faster too), and a single file
that still can't be written is skipped and counted rather than aborting.

**2. A bare 500 told the user the backend was "unreachable."** The frontend
treated "no response" and "server responded with an error" as the same
case. A crash now gets its own FastAPI exception handler that always
returns JSON with a `detail`, and the frontend distinguishes "can't reach
the backend" from "the server returned an error ($status)" — see
`frontend/src/utils/apiError.js`.

**3. A common Python pattern was flagged as 75 broken imports.** Calibre-
Web-Automated's `cps/duplicates.py` does
`from . import db, calibre_db, csrf, config, helper`. `db.py` and
`helper.py` are real files; `calibre_db`, `csrf`, and `config` are
instances built in `cps/__init__.py` (`calibre_db = CalibreDB()`) and
re-exported — a common way to expose package-level singletons. The
resolver assumed every bare `from . import name` must be its own file. Now,
when that fails, it falls back to the containing package's `__init__.py`
(guarded against a false self-loop when `__init__.py` imports from itself).
Python unresolved-import count on that repo: 75 → 1 (the one that's left is
a genuine third-party package). `from .foo import x` is unaffected — `foo`
must still resolve as a real module there.

---

## GitHub sign-in (OAuth)

Sign-in is entirely optional — every feature works fully anonymously, exactly as before this phase. Signing in with GitHub gets you two things:

1. **Your own 5,000/hour GitHub API rate limit**, instead of sharing the server's (or the server's `GITHUB_TOKEN`, if the operator set one).
2. **Access to your own private repositories.** Analyzing a private repo without being signed in correctly fails with "repository not found" — GitHub's API returns a 404 for a private repo to anyone without access, indistinguishable from it not existing, which is the right behavior (not leaking whether a private repo exists).

### Why a classic OAuth App, not a GitHub App

A GitHub App's fine-grained, per-repository installable permissions are the more "correct" design long-term, but need a separate installation flow (choosing which repos to grant, on top of signing in) and hourly-expiring installation tokens that must be refreshed. A classic OAuth App with the `repo` scope gets the two goals above in a quarter of the code. The honest trade-off: `repo` grants read/write on every repo the signed-in user can access, more than this tool ever uses (it only reads). Stated plainly, not hidden — a real next step if this were a product rather than a portfolio piece.

### Private repos and shareable links: the actual design problem

Every analysis gets a `/p/:id` link viewable by anyone who has it — that's the whole point of Phase E. Combined with private-repo analysis, that's a real privacy leak unless addressed directly: a private repo's file structure, import graph, and risk data would otherwise be visible to anyone with the link, signed in or not.

Fixed by ownership, not obscurity: a project analyzed from a private repo is tagged `is_private` and stamped with the creating session's id. Every project-read route goes through one shared access-control check (`_get_record_or_404` in `api/projects.py`) — a private project is invisible to any session but its owner, returning **404, not 403** (a shared link to someone else's private analysis looks identical to a stale or wrong link; existence itself isn't revealed). One test (`test_private_repo_lockdown_covers_every_read_route...`) exists specifically so that adding a new `/projects/{id}/...` route later and forgetting to route it through that check gets caught immediately rather than silently shipping a leak.

The GitHub result cache is scoped the same way: every signed-in user's cache is private to them (keyed by session id), even for a repo that turns out to be public — simpler than trying to determine privacy before the cache check (which happens *before* any GitHub API call, by design, so privacy isn't knowable yet at that point) and it closes the same class of leak.

### Session model

- The session cookie (`codemap_session`) holds only an opaque, unguessable id — the real GitHub token never reaches the browser.
- The token is encrypted at rest (`services/crypto.py`, Fernet) via `CODEMAP_SECRET_KEY`. Unset in local dev, a temporary key is generated per-process with a logged warning — every session is invalidated on the next restart, the same class of problem the old CWD-relative DB-path default caused, but this time intentional and loud rather than silent. Set `CODEMAP_SECRET_KEY` for anything that needs sessions to survive a restart:
  ```
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- Sessions don't expire on a timer — only on sign-out or clearing cookies. A portfolio tool a recruiter might reopen the next day treating that as "silently signed out" seemed like the worse default; logout is still immediate.
- CSRF protection on the handshake: `/github/login` sets a short-lived `state` value in both the redirect URL and an HttpOnly cookie; `/github/callback` rejects the request outright if they don't match, before ever calling GitHub's token-exchange endpoint.

### Setting it up (optional, for local dev or deployment)

**Local dev — use a `.env` file, not `set`/`$env:` every session.** `backend/app/.env` is loaded automatically on startup (via `python-dotenv`) and is already in `.gitignore`, so it never gets committed:

```powershell
cd backend\app
copy .env.example .env
notepad .env
```

Fill in whichever of these you need (everything in `.env.example` is commented with what it's for):

1. Register an OAuth App at <https://github.com/settings/developers> → "New OAuth App". Set its "Authorization callback URL" to `http://localhost:8000/api/auth/github/callback`.
2. Paste the generated Client ID and Client Secret into `CODEMAP_GITHUB_CLIENT_ID` / `CODEMAP_GITHUB_CLIENT_SECRET` in `.env`.
3. Generate a `CODEMAP_SECRET_KEY` (command is in `.env.example`) and paste it in too, so signed-in sessions survive a server restart instead of being invalidated every time.
4. Run `uvicorn main:app --reload --port 8000` as usual — no `set`/`$env:` commands needed, `.env` is picked up automatically.

Leave `.env` absent (or those lines blank) to run CodeMap with sign-in simply not offered — nothing else changes, and this is exactly what every earlier phase of this project already did.

**Deployment** doesn't use `.env` (there's no file to upload on most hosts) — set these as real environment variables in your platform's dashboard instead:
- `CODEMAP_GITHUB_CLIENT_ID`, `CODEMAP_GITHUB_CLIENT_SECRET` — from the OAuth App (register a second one for production, with its callback URL pointed at your deployed backend).
- `CODEMAP_FRONTEND_URL` — your deployed frontend's URL.
- `CODEMAP_SECRET_KEY` — required in practice for deployment (an ephemeral key means every restart signs everyone out).
- `CODEMAP_COOKIE_SECURE=true` — **required once the frontend and backend are on different domains** (the normal case: a Vercel frontend + a Render backend). Browsers refuse cross-site cookies without `SameSite=None; Secure`, which needs HTTPS on both sides. Not needed for local dev — `localhost:5173` and `localhost:8000` count as the same "site" despite the different ports, so `SameSite=Lax` already works there.

### What's verified, and what isn't

Every piece of the OAuth code that doesn't require a real GitHub account is tested and passing: the state-cookie CSRF check, token exchange and session creation (GitHub's endpoints mocked), session lookup/expiry-of-key-rotation handling, token-at-rest encryption, and - most importantly - the full private-repo access-control suite (every read route, every combination of owner/other-user/anonymous). Live in a real browser, I confirmed the "Sign in with GitHub" button does a real round trip to `github.com`'s actual OAuth endpoint with the correct `client_id`/`redirect_uri`/`scope`/`state` intact. **Completing an actual sign-in requires a real registered OAuth App and a real GitHub account to log into, neither of which exists in this sandbox** - so the callback's happy path (token exchange → session → redirect) is verified by mocked tests, not a live end-to-end login. Worth doing yourself once you have real credentials, before relying on this in an interview demo.

---

## Scaling behavior (found by analyzing real repos)

Running CodeMap against real projects (Express, 141 files; Flask, 83 files) found two problems the small demo repos could never show:

1. **Cycle explosion.** Flask's 19-file core has 9,629 distinct elementary cycles. Listing them is unreadable, and enumerating them is unbounded-cost on denser graphs. Now: membership in a cycle comes from strongly connected components (exact, linear time); the listed cycles are capped at 200, shortest first, chosen deterministically, with a `cyclesTruncated` flag and a "200+" display. The CLI's baseline diff compares whole tangled clusters instead of individual cycles when truncated, so unrelated changes can't make a PR check flap.
2. **Layout blow-up.** dagre puts every unconnected file on one rank, so Flask's 60+ isolated files became a single column thousands of pixels tall, pushing the real dependency graph off-screen. Now isolated files are laid out in a compact grid below the connected graph.

Measured (this sandbox): Express (141 files) 1.6s, Flask (83 files) 0.24s,
Calibre-Web-Automated (395 files, Python+JS) 13.2s end to end — almost all
of that last one is the one-shot Node/Babel subprocess parsing ~196 JS
files (12.4s of the 13.2s, profiled with `cProfile`). That subprocess is
unchanged from Phase 1; it hasn't been a bottleneck until a repo this size.
If it becomes one, the fix is parsing in a persistent Node process instead
of spawning fresh each time — not yet done.

---

## Testing

Backend: 183 tests covering the scanner, parser bridge, classifier, resolver,
graph builder (including import-symbol capture and the duplicate-import
merge behavior), cycle detection, metrics, impact analysis, architecture
classification (including Django's flat-file conventions), risk scoring,
the GitHub fetcher (URL parsing, size guard, rate-limit handling, tar-slip
protection — all mocked, network-independent), GitHub result caching
(cache hits skip re-fetching, force-refresh bypasses the cache, local paths
are never cached, entries expire after the TTL), the Python parser and
resolver (every import form, relative-level directory walking, local vs.
external classification, the project-root containment guard), a dedicated
cross-language integration suite (a `.py` and `.js` file sharing a base
name provably never link to each other), the CLI (11 subprocess-level tests
covering exit codes, baseline diffing, and gating logic), and full API
integration (including a regression test for a route-ordering bug caught
during development — see `backend/tests/test_api.py`), SQLite persistence
across real process boundaries, cycle-detection scaling (dense-graph
capping, exact membership, cross-process determinism, baseline-diff
stability when truncated), the default DB path being independent of the
process's launch directory, GitHub tarball extraction (unwritable files
skipped and counted rather than crashing the whole analysis, path-traversal
still rejected, unexpected errors always return JSON), and a Python import
resolver fix (see "Fixes from testing real repos" below), and GitHub OAuth
(state-cookie CSRF protection, token exchange and session creation with
GitHub's endpoints mocked, token-at-rest encryption, and private-repo
access control across every project-read route).

```powershell
cd backend
python -m pytest tests\ -v
```

Frontend: 48 `vitest` tests (jsdom + Testing Library) covering the filter
predicates, the dagre layout (isolated-file grid, no overlaps, feedback
edges), the HomePage analyze-then-navigate flow, the ProjectPage
fetch-by-URL / not-found / backend-down / copy-link (including clipboard
failure) states, and the project stats panel. Run with `npm test` from
`frontend/`.

Known gap: React Flow itself is stubbed in the page tests (jsdom has no
layout engine), so canvas rendering is verified separately in a real
browser, not by the automated suite.

---

## Deployment

With GitHub URL support, a public deployment now makes real sense — anyone
can paste a public repo URL and get results, without needing anything on
the server beforehand. (Local-path mode still only works against whatever
filesystem the backend itself is running on, which is expected: if you
deploy the backend, "local path" means *that server's* files, not the
visitor's laptop. GitHub URL mode is what makes a public demo link work for
anyone else.)

**Backend** — Render or Railway (confirm current pricing and plan
requirements yourself). Both support a standard `uvicorn` process. **Attach
a persistent disk and set `CODEMAP_DB_PATH` (see "Persistence" above) or
every redeploy deletes all saved projects and shared links.**
Set the start command to `uvicorn main:app --host 0.0.0.0 --port $PORT`
from `backend/app/`, and set these environment variables:
- `CODEMAP_DB_PATH` — a path on the persistent disk, e.g. `/var/data/codemap.db`
- `CODEMAP_ALLOWED_ORIGINS` — your deployed frontend's URL (comma-separated if more than one)
- `GITHUB_TOKEN` — recommended for a public deployment for *anonymous* visitors; without it, GitHub's 60-requests/hour limit is shared across every unauthenticated visitor hitting your deployed backend from the same server IP. A token (no special scopes needed for public repos) raises that to 5,000/hour. Signed-in visitors use their own token instead (see "GitHub sign-in" above) and aren't affected by this either way.
- `CODEMAP_GITHUB_CLIENT_ID`, `CODEMAP_GITHUB_CLIENT_SECRET`, `CODEMAP_SECRET_KEY`, `CODEMAP_COOKIE_SECURE=true` — only if offering GitHub sign-in; see "GitHub sign-in" above for what each does. `CODEMAP_COOKIE_SECURE=true` specifically is required once frontend and backend are on different domains (the normal case for Vercel + Render), or the session cookie silently never gets sent.
- `CODEMAP_FRONTEND_URL` — your deployed frontend's URL, so the OAuth callback redirects somewhere real instead of `localhost:5173`.

Make sure Node.js is available in the build environment and that
`backend/parser`'s `npm install` runs as part of your build step.

**Frontend** — Vercel or Netlify. Set the `VITE_API_BASE_URL` build-time
environment variable to your deployed backend's URL (see
`frontend/.env.example`).

Neither platform choice is load-bearing — any host that runs a persistent
Python process with a persistent disk (not just serverless functions,
since this uses a local SQLite file and spawns subprocesses) works for the backend, and any
static host works for the frontend.

---

## Resume bullets

- Built an AST-based static analysis engine for JavaScript/TypeScript repositories that extracts module dependencies and generates interactive codebase architecture graphs.
- Implemented graph-based impact analysis, circular dependency detection, module centrality metrics, and deterministic code-change risk scoring using NetworkX.
- Developed a React + FastAPI developer dashboard with repository exploration, dependency visualization, file-level metrics, architecture classification, and impact analysis.
