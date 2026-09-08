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

- **Repository scanning** — recursively finds `.js`/`.jsx`/`.ts`/`.tsx` files, skipping `node_modules`, `dist`, `build`, and similar directories at the directory-walk level (never even descends into them).
- **Filter and focus** — narrow the graph and file tree by architecture category, minimum risk level, or folder (including subtree scoping); filtered-out nodes are removed from layout entirely rather than just dimmed, so a large repo actually declutters instead of just fading.
- **Local or GitHub URL input** — analyze a directory on your own machine, or paste a public GitHub repo URL (`https://github.com/owner/repo`, optionally `/tree/branch`) and CodeMap downloads a one-shot tarball snapshot, analyzes it, and cleans up the temp files automatically. No `git clone`, no commit history fetched.
- **GitHub result caching** — a repeat analysis of the same repo+ref within 10 minutes is served instantly from memory, skipping both the download and the re-parse entirely (a "Force refresh" checkbox bypasses this when you want fresh data sooner). Local paths are never cached — caching your own actively-edited files would risk silently showing stale results.
- **AST-based import extraction** — uses Babel (`@babel/parser` + `@babel/traverse`) via a small Node subprocess, so JSX and TypeScript syntax are understood natively rather than approximated with regex.
- **Local dependency resolution** — resolves relative imports to real files on disk, handling extension guessing and `index` files, with a project-root containment check so a crafted import can't resolve outside the analyzed directory.
- **Interactive dependency graph** — rendered with React Flow, laid out with `dagre` (not naive column-stacking), colored by architecture category, with click-to-highlight for a node's direct dependencies/dependents.
- **Circular dependency detection** — finds every cycle via `networkx.simple_cycles`, and renders the cycle-closing edge as a distinct curved line rather than letting a standard layout algorithm mis-route it.
- **Change-impact analysis** — reverse-graph traversal answering "what breaks if I change this file," split into direct and indirect dependents.
- **Deterministic risk scoring** — a transparent 0–100 score per file (dependents + centrality + complexity + cycle membership), with human-readable reasons, not a black box.
- **Architecture classification** — heuristic path-based categorization (Component, Service, Controller, Model, Util, Hook, Route, etc.).
- **File tree + search** — browse by folder, or search to jump straight to a file and focus the graph on it.

## What CodeMap intentionally does NOT do

Documented limitations, not oversights:

- No bundler path-alias resolution (webpack `resolve.alias`, tsconfig `paths` like `@/components/Button`) — only relative (`./`, `../`) and absolute (`/`) specifiers resolve to local files today.
- No Python or other non-JS/TS language support.
- No git history analysis, and GitHub analysis is a snapshot at one ref (branch/commit), not a clone — no commit history is fetched or available.
- GitHub repos over 200MB are rejected before download (configurable in `analyzer/github_fetcher.py`).
- Unauthenticated GitHub API requests are capped at 60/hour per IP by GitHub itself — easy to hit on a shared or cloud IP (this was hit live while building the feature). Set a `GITHUB_TOKEN` environment variable (a plain personal access token, no special scopes needed for public repos) to raise that to 5,000/hour.
- Project data lives in server memory (a plain dict) — restarting the backend loses every analyzed project. Fine for a local tool you run yourself; not suitable for a multi-user deployment as-is.
- Betweenness centrality is skipped above 1500 files in a single repo (returned as `null`) to avoid an expensive computation on very large codebases; degree centrality is always computed.

---

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | React + Vite + Tailwind CSS v4 + React Flow + dagre + Axios |
| Backend | Python + FastAPI |
| Parsing | Node.js + `@babel/parser`/`@babel/traverse`, invoked as a one-shot subprocess |
| Graph analysis | NetworkX |
| Storage | In-memory (see limitations above) |

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
  ├─ Parser Bridge → subprocess → Node/Babel AST → imports JSON
  ├─ Import Classifier (local vs external)
  ├─ Path Resolver (extension/index resolution)
  ├─ Architecture Classifier (path-based heuristic)
  └─ Risk Scorer (dependents + centrality + complexity + cycles)
        │
        ▼
Graph Engine (NetworkX)
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

---

## Testing

Backend: 85 tests covering the scanner, parser bridge, classifier, resolver,
graph builder, cycle detection, metrics, impact analysis, architecture
classification, risk scoring, the GitHub fetcher (URL parsing, size guard,
rate-limit handling, tar-slip protection — all mocked, network-independent),
GitHub result caching (cache hits skip re-fetching, force-refresh bypasses
the cache, local paths are never cached, entries expire after the TTL), and
full API integration (including a regression test for a route-ordering bug
caught during development — see `backend/tests/test_api.py`).

```powershell
cd backend
python -m pytest tests\ -v
```

Frontend: `vitest` covers pure logic factored out of components — currently
the filter predicates (category/risk/folder, including combined-filter and
folder-subtree-boundary cases). Run with `npm test` from `frontend/`. Not
every piece of frontend logic has a matching test yet (dagre layout and
feedback-edge detection were verified manually during development rather
than committed as automated tests) - this is a real gap, not a claim that
coverage is complete.

---

## Deployment

With GitHub URL support, a public deployment now makes real sense — anyone
can paste a public repo URL and get results, without needing anything on
the server beforehand. (Local-path mode still only works against whatever
filesystem the backend itself is running on, which is expected: if you
deploy the backend, "local path" means *that server's* files, not the
visitor's laptop. GitHub URL mode is what makes a public demo link work for
anyone else.)

**Backend** — Render or Railway (free tiers exist as of writing; confirm
current pricing yourself). Both support a standard `uvicorn` process.
Set the start command to `uvicorn main:app --host 0.0.0.0 --port $PORT`
from `backend/app/`, and set these environment variables:
- `CODEMAP_ALLOWED_ORIGINS` — your deployed frontend's URL (comma-separated if more than one)
- `GITHUB_TOKEN` — strongly recommended for a public deployment; without it, GitHub's 60-requests/hour limit is shared across *every visitor* hitting your deployed backend from the same server IP, and will get exhausted fast. A token (no special scopes needed for public repos) raises that to 5,000/hour.

Make sure Node.js is available in the build environment and that
`backend/parser`'s `npm install` runs as part of your build step.

**Frontend** — Vercel or Netlify. Set the `VITE_API_BASE_URL` build-time
environment variable to your deployed backend's URL (see
`frontend/.env.example`).

Neither platform choice is load-bearing — any host that runs a persistent
Python process (not just serverless functions, since this uses an
in-memory store and spawns subprocesses) works for the backend, and any
static host works for the frontend.

---

## Resume bullets

- Built an AST-based static analysis engine for JavaScript/TypeScript repositories that extracts module dependencies and generates interactive codebase architecture graphs.
- Implemented graph-based impact analysis, circular dependency detection, module centrality metrics, and deterministic code-change risk scoring using NetworkX.
- Developed a React + FastAPI developer dashboard with repository exploration, dependency visualization, file-level metrics, architecture classification, and impact analysis.
