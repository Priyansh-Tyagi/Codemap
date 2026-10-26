"""
End-to-end replication drill. Runs the REAL entrypoint.sh, the REAL Litestream
binary and the REAL app against a folder-as-bucket replica (no cloud account).

Run inside the image:   docker run --rm codemap-api:dev python /srv/codemap/docker/e2e_replication.py
Run on a Linux box:     CODEMAP_HOME=/path/with/app+parser+docker  python e2e_replication.py

Scenarios (each maps to a risk we were worried about):
  S1  cold start + first boot            S2  graceful stop forwards SIGTERM, final sync
  S3  host disk wiped -> restore         S4  damaged local DB -> quarantine + restore
  S5  replica unreachable -> starts DEGRADED (no replication), says so via /api/status
  S9  provider answers 403 (free-tier cap) -> degraded, and the provider sees ZERO writes
  S10 a degraded run never touches the real DB path or the backup history
  S6  DB / -wal / -shm are owner-only    S7  data-loss window on a hard kill (stale-data risk)
  S8  two instances overlap (deploy)     -> measures what really happens
"""
import json, os, shutil, signal, sqlite3, subprocess, sys, tempfile, time, urllib.request, urllib.error

HOME = os.environ.get("CODEMAP_HOME", "/srv/codemap")
SAMPLE = os.environ.get("E2E_SAMPLE_DIR", os.path.join(HOME, "app"))
WORK = tempfile.mkdtemp(prefix="cm-e2e-")
REPLICA = os.path.join(WORK, "replica")
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""), flush=True)


S3_ENDPOINT = os.environ.get("E2E_S3_ENDPOINT", "")   # set => test the real S3 config, not the folder one
S3_BUCKET = os.environ.get("E2E_S3_BUCKET", "codemap-e2e")


def clear_replica():
    """Empty the replica between scenarios (folder, or every object in the bucket)."""
    if not S3_ENDPOINT:
        shutil.rmtree(REPLICA, ignore_errors=True)
        return
    import boto3
    b = boto3.resource("s3", endpoint_url=S3_ENDPOINT, aws_access_key_id="test",
                       aws_secret_access_key="test", region_name="us-east-1").Bucket(S3_BUCKET)
    b.objects.all().delete()


def env_for(port, db, replica=REPLICA, extra=None):
    e = dict(os.environ)
    e.update({
        "CODEMAP_HOME": HOME, "CODEMAP_DB_PATH": db, "PORT": str(port),
        "LITESTREAM_ENABLED": "true",
        "LITESTREAM_CONFIG": os.path.join(HOME, "docker", "litestream.yml" if S3_ENDPOINT else "litestream.file.yml"),
        "LITESTREAM_FILE_REPLICA_PATH": replica,
        "CODEMAP_ALLOW_LOCAL_PATHS": "true",  # test only: lets us analyze a folder without GitHub
    })
    if S3_ENDPOINT:
        e.update({"LITESTREAM_BUCKET": S3_BUCKET, "LITESTREAM_ENDPOINT": S3_ENDPOINT,
                  "LITESTREAM_ACCESS_KEY_ID": "test", "LITESTREAM_SECRET_ACCESS_KEY": "test",
                  "LITESTREAM_REGION": "us-east-1", "LITESTREAM_FORCE_PATH_STYLE": "true",
                  "LITESTREAM_PATH": "codemap"})
    e.update(extra or {})
    return e


def start(name, port, db, **kw):
    kw["extra"] = dict(kw.get("extra") or {}, CODEMAP_STORAGE_STATUS_FILE=os.path.join(WORK, f"{name}.status.json"))
    log = open(os.path.join(WORK, f"{name}.log"), "w")
    p = subprocess.Popen(["sh", os.path.join(HOME, "docker", "entrypoint.sh")],
                         env=env_for(port, db, **kw), stdout=log, stderr=subprocess.STDOUT,
                         start_new_session=True)
    p.logpath = log.name
    return p


def logtext(p):
    return open(p.logpath).read()


def http(port, path, body=None, timeout=60):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"} if body is not None else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def wait_up(port, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        try:
            http(port, "/api/health", timeout=2)
            return True
        except Exception:
            time.sleep(0.4)
    return False


def analyze(port):
    r = http(port, "/api/analyze", {"path": SAMPLE})
    return r.get("projectId") or r.get("project_id")


def nodes(port, pid):
    try:
        return len(http(port, f"/api/projects/{pid}/graph")["nodes"])
    except Exception:
        return None


def stop(p, sig=signal.SIGTERM, timeout=40):
    try:
        os.kill(p.pid, sig)
    except ProcessLookupError:
        return p.returncode
    try:
        return p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        return "TIMEOUT"


def hard_kill(p):
    os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    p.wait()


def wipe_db(db):
    for s in ("", "-wal", "-shm", "-litestream", ".degraded", ".degraded-wal", ".degraded-shm"):
        path = db + s
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)


def procs_left():
    """PIDs of running uvicorn servers. Reads /proc: python:slim has no pgrep/procps."""
    found = []
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) == os.getpid():
            continue
        try:
            cmd = open(f"/proc/{name}/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        toks = cmd.split()
        if not toks or os.path.basename(toks[0]) in ("sh", "bash", "dash"):
            continue   # a shell whose command LINE merely mentions uvicorn is not a server
        if "main:app" in toks and any(os.path.basename(t) == "uvicorn" for t in toks):
            found.append(name)
    return found


def running(*words):
    """True if some process has every word as an argv entry (by basename). Reads /proc."""
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) == os.getpid():
            continue
        try:
            toks = open(f"/proc/{name}/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace").split()
        except OSError:
            continue
        if toks and os.path.basename(toks[0]) not in ("sh", "bash", "dash") and \
                all(any(os.path.basename(t) == w for t in toks) for w in words):
            return True
    return False


def status(port):
    try:
        return http(port, "/api/status", timeout=10)
    except Exception:
        return {}


def mode(path):
    return oct(os.stat(path).st_mode & 0o777)


def probe_replica():
    """Restore the replica to a scratch file with the real binary and inspect it."""
    out = os.path.join(WORK, "probe.db")
    for s in ("", "-wal", "-shm"):
        if os.path.exists(out + s): os.remove(out + s)
    env = env_for(0, out)
    r = subprocess.run(["litestream", "restore", "-config", env["LITESTREAM_CONFIG"], "-if-replica-exists", "-o", out, out],
                       env=env, capture_output=True, text=True)
    c = subprocess.run([sys.executable, os.path.join(HOME, "docker", "check_db.py"), out], capture_output=True, text=True)
    ids = set()
    try:
        _c = sqlite3.connect(f"file:{out}?mode=ro", uri=True)
        ids = {row[0] for row in _c.execute("SELECT project_id FROM projects")}
        _c.close()
    except Exception:
        pass
    return r.returncode, c.stdout.strip(), ids


print(f"workdir {WORK}\nsample  {SAMPLE}\n")
DB = os.path.join(WORK, "data", "codemap.db")

# ---------------------------------------------------------------- S1 / S2
print("S1 cold start, first boot, then analyze")
clear_replica()   # a bucket (unlike the per-run temp folder) can hold data from an earlier run
p = start("s1", 18001, DB)
up = wait_up(18001)
check("server comes up through entrypoint+litestream", up, "" if up else logtext(p)[-600:])
check("first boot detected (empty replica)", "first boot" in logtext(p))
pid1 = analyze(18001) if up else None
n1 = nodes(18001, pid1) if pid1 else None
check("analysis saved and readable", bool(pid1) and n1 and n1 > 5, f"project={pid1} nodes={n1}")
time.sleep(3)

print("S2 graceful stop (what Render sends on spin-down/deploy)")
t = time.time(); rc = stop(p)
check("SIGTERM exits cleanly", rc == 0, f"rc={rc} in {time.time()-t:.1f}s")
check("no orphaned uvicorn after stop", not procs_left(), str(procs_left()))

# ---------------------------------------------------------------- S3
print("S3 host disk wiped (Render cold start) -> restore from replica")
wipe_db(DB)
p = start("s3", 18001, DB)
up = wait_up(18001)
check("restored and started", up, "" if up else logtext(p)[-600:])
check("log says restored + integrity ok", "restore OK" in logtext(p) and "integrity=ok" in logtext(p))
n = nodes(18001, pid1) if up else None
check("SAME project, SAME graph after restore", n == n1, f"before={n1} after={n}")

# ---------------------------------------------------------------- S6
print("S6 file permissions while running")
# SQLite deletes -wal/-shm when the last connection closes, so on an idle server
# they simply do not exist. Hold a reader open and commit a write, so the sidecar
# files are guaranteed to exist while we look at them (a 'missing' file proves nothing).
_reader = sqlite3.connect(DB, timeout=10)
_reader.execute("BEGIN"); _reader.execute("SELECT COUNT(*) FROM projects").fetchone()
_writer = sqlite3.connect(DB, timeout=10)
_writer.execute("INSERT OR REPLACE INTO github_cache (cache_key, project_id, cached_at) VALUES ('e2e-probe','x',0)")
_writer.commit()
for s_ in ("", "-wal", "-shm"):
    f = DB + s_
    check(f"codemap.db{s_} exists and is 0600", os.path.exists(f) and mode(f) == "0o600", mode(f) if os.path.exists(f) else "missing")
_writer.execute("DELETE FROM github_cache WHERE cache_key='e2e-probe'"); _writer.commit()
_writer.close(); _reader.close()
stop(p)

# ---------------------------------------------------------------- S4
print("S4 damaged local DB (volume case) -> quarantined, restored")
with open(DB, "r+b") as f:
    f.seek(100); f.write(os.urandom(4096))
for s in ("-wal", "-shm"):
    if os.path.exists(DB + s): os.remove(DB + s)
p = start("s4", 18001, DB)
up = wait_up(18001)
check("started anyway", up, "" if up else logtext(p)[-700:])
lt = logtext(p)
check("damage detected", "integrity=" in lt and ("FAILED" in lt or "error" in lt))
check("damaged file kept for forensics", any(".corrupt-" in x for x in os.listdir(os.path.dirname(DB))))
n = nodes(18001, pid1) if up else None
check("data intact after recovery", n == n1, f"nodes={n}")
stop(p)

# ---------------------------------------------------------------- S5
print("S5 replica unreachable + no local DB -> must start DEGRADED, not refuse and not replicate")
wipe_db(DB)
bad = {"LITESTREAM_CONFIG": os.path.join(HOME, "docker", "litestream.yml"),
       "LITESTREAM_BUCKET": "nope", "LITESTREAM_ENDPOINT": "http://127.0.0.1:1",
       "LITESTREAM_ACCESS_KEY_ID": "x", "LITESTREAM_SECRET_ACCESS_KEY": "y",
       "LITESTREAM_REGION": "us-east-1", "LITESTREAM_FORCE_PATH_STYLE": "true",
       "LITESTREAM_RESTORE_TIMEOUT": "15"}
t = time.time()
p = start("s5", 18002, DB, extra=bad)
up = wait_up(18002)
lt = logtext(p)
st = status(18002).get("storage", {})
check("the app comes up anyway, in bounded time", bool(up) and time.time() - t < 75, f"{time.time()-t:.0f}s")
check("/api/status says degraded, with a fixed reason code",
      st.get("state") == "degraded" and st.get("reason") in ("timeout", "unreachable"), str(st))
check("restore was bounded, not an endless silent retry", "timed out" in lt)
check("NO replication process is running", not running("litestream", "replicate"))
pid = analyze(18002) if up else None
check("analysis still works while degraded", bool(pid and nodes(18002, pid)))
check("the real DB path was never created (degraded runs on its own file)",
      not os.path.exists(DB) and os.path.exists(DB + ".degraded"))
stop(p)
check("clean stop, nothing orphaned", not procs_left())


# ---------------------------------------------------------------- S9
print("S9 provider answers 403 'cap exceeded' (the B2 free-tier incident)")
import http.server as _hs   # NOT 'import http.server': that would shadow the http() helper
import threading
class Deny(_hs.BaseHTTPRequestHandler):
    reads = 0
    writes = 0   # PUT / POST / DELETE: anything that could change the bucket
    def _deny(self):
        if self.command in ("GET", "HEAD"): Deny.reads += 1
        else: Deny.writes += 1
        body = b'<?xml version="1.0"?><Error><Code>AccessDenied</Code><Message>Transaction cap exceeded</Message></Error>'
        self.send_response(403); self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    do_GET = do_PUT = do_HEAD = do_POST = do_DELETE = _deny
    def log_message(self, *a): pass
srv = _hs.ThreadingHTTPServer(("127.0.0.1", 0), Deny)
threading.Thread(target=srv.serve_forever, daemon=True).start()
deny_env = {"LITESTREAM_CONFIG": os.path.join(HOME, "docker", "litestream.yml"),
            "LITESTREAM_BUCKET": "capped", "LITESTREAM_ENDPOINT": f"http://127.0.0.1:{srv.server_address[1]}",
            "LITESTREAM_ACCESS_KEY_ID": "x", "LITESTREAM_SECRET_ACCESS_KEY": "y",
            "LITESTREAM_REGION": "us-east-1", "LITESTREAM_FORCE_PATH_STYLE": "true",
            "LITESTREAM_RESTORE_TIMEOUT": "30"}
wipe_db(DB)
p = start("s9", 18004, DB, extra=deny_env)
up = wait_up(18004)
lt = logtext(p)
st = status(18004).get("storage", {})
check("starts instead of crash-looping on a 403", bool(up))
check("/api/status: degraded, reason provider_refused", st.get("state") == "degraded" and st.get("reason") == "provider_refused", str(st))
check("explains the likely cause in plain words in the log", "HINT" in lt and "daily request cap" in lt)
check("the provider's own error text is not echoed into the status", "Transaction cap" not in json.dumps(st))
pid = analyze(18004) if up else None
time.sleep(6)   # long enough for any replicator to have tried to write
check("the denied provider saw ZERO writes (bucket untouched)", Deny.writes == 0, f"reads={Deny.reads} writes={Deny.writes}")
check("NO replication process is running", not running("litestream", "replicate"))
check("analysis still works while degraded", bool(pid and nodes(18004, pid)))
stop(p)


# ---------------------------------------------------------------- S10
print("S10 a degraded run must not damage the real DB path or the backup history")
clear_replica(); wipe_db(DB)
p = start("s10a", 18020, DB); wait_up(18020)
px = analyze(18020); time.sleep(3)
stop(p)                                   # graceful: final sync, X is in the backup
wipe_db(DB)                               # an ephemeral host loses its disk
p = start("s10b", 18021, DB, extra=deny_env); wait_up(18021)   # provider refuses -> degraded
py = analyze(18021)
stop(p)
check("after the degraded run the real DB path is still absent", not os.path.exists(DB))
p = start("s10c", 18022, DB); up = wait_up(18022)                # provider is back
check("next start restores the ORIGINAL backup (project X is back)", bool(up and px and nodes(18022, px)))
check("what was saved while degraded is gone, as documented", not (py and nodes(18022, py)))
stop(p)
time.sleep(1)
code, summary, ids = probe_replica()
check("the backup itself still restores and still holds X", code == 0 and px in ids, summary)
srv.shutdown()

# ---------------------------------------------------------------- S7
print("S7 hard kill (SIGKILL = OOM kill) - how much recent data can be lost?")
for delay in (0.0, 0.5, 2.0, 5.0):
    clear_replica(); wipe_db(DB)
    p = start("s7", 18003, DB); wait_up(18003)
    pid = analyze(18003)
    time.sleep(delay)
    hard_kill(p); time.sleep(0.5)
    wipe_db(DB)
    p = start("s7b", 18003, DB); up = wait_up(18003)
    survived = bool(up and pid and nodes(18003, pid))
    print(f"      killed {delay:>3}s after the save -> {'SURVIVED' if survived else 'LOST'}")
    stop(p)
print("      (informational: this is the replication-lag window, not a pass/fail)")

# ---------------------------------------------------------------- S8
print("S8 two instances overlap on one replica (Render deploy overlap)")
clear_replica()
dbA, dbB = os.path.join(WORK, "A", "codemap.db"), os.path.join(WORK, "B", "codemap.db")
A = start("A", 18011, dbA); wait_up(18011)
pa1 = analyze(18011); time.sleep(3)
B = start("B", 18012, dbB); upB = wait_up(18012)
check("new instance restored the old one's data while old is still running", bool(upB and nodes(18012, pa1)))
pa2 = analyze(18011)          # old instance keeps taking traffic during overlap
pb1 = analyze(18012)          # new instance takes traffic too
time.sleep(4)
ra, rb = stop(A), stop(B)
time.sleep(1)
code, summary, ids = probe_replica()
print(f"      replica after overlap: restore rc={code}  {summary}")
print(f"      saved before overlap (pa1): {'KEPT' if pa1 in ids else 'LOST'}")
print(f"      saved on OLD instance during overlap (pa2): {'KEPT' if pa2 in ids else 'LOST'}")
print(f"      saved on NEW instance during overlap (pb1): {'KEPT' if pb1 in ids else 'LOST'}")
bad_words = ("error", "conflict", "mismatch", "diverg", "fatal")
for name, x in (("old", A), ("new", B)):
    hits = [l for l in logtext(x).splitlines() if any(w in l.lower() for w in bad_words) and "entrypoint" not in l]
    print(f"      {name} instance log lines that look like trouble: {len(hits)}")
    for l in hits[:4]: print("        ", l[:200])
print("      (informational: see report for interpretation)")

print(f"\n{sum(results)}/{len(results)} checks passed   (logs and files in {WORK})")
sys.exit(0 if all(results) else 1)
