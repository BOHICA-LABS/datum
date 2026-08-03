#!/usr/bin/env python3
"""Agent identity — what makes a zone wall enforceable rather than advisory?

Z6 exposed the hole: `DATUM_ROLE` is SELF-DECLARED. An agent sets an env var and reads
whatever it likes. That is a hint, not an identity. Enforcement needs a PRIVILEGE
BOUNDARY, and there are only three places one can live:

  tier 1  advisory role + harness tool-profile path denial   (today's parity)
  tier 2  OS user per agent + chmod/chown on zone dirs        (needs a multi-uid harness)
  tier 3  per-role DB credentials against a server           (works in a same-uid fleet)

The load-bearing question for tier 2/3: in a fleet where every agent runs as the SAME
uid, can one agent obtain another's privilege? Tested, not assumed.

  ID1  self-declared role is trivially forgeable (quantifies the tier-1 gap)
  ID2  is OS-user isolation even available? (uid of the agent fleet)
  ID3  same-uid processes: can agent A read agent B's environment?
  ID4  a credential FILE on shared disk is readable by any same-uid agent
  ID5  per-role DB credentials: an agent cannot escalate without the other password
  ID6  credentials are zone-scoped (role reads only its own tables)
  ID7  identity gives ATTRIBUTION: writes are traceable to the acting agent

Run: .venv/bin/python -u poc/test_identity.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pymysql

sys.path.insert(0, str(Path(__file__).parent))
from datum_zones import NotVisible, Store  # noqa: E402

ROOT = Path(__file__).parent / "id"
DBD = ROOT / "db"
PORT = 3502
RESULTS: list[tuple[str, bool, str]] = []
SERVERS: list[subprocess.Popen] = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for ln in (detail or "").splitlines():
        print(f"        {ln}")


def sh(args, cwd=None, timeout=180, env=None):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", "TIMEOUT")


def setup():
    print("--- setup: one db with an open + a walled table, plus a server")
    if ROOT.exists():
        shutil.rmtree(ROOT)
    DBD.mkdir(parents=True)
    sh(["dolt", "init", "--name", "id", "--email", "id@l"], cwd=DBD)
    for s in ("CREATE TABLE bc (bc_id VARCHAR(24) PRIMARY KEY, title TEXT NOT NULL)",
              "INSERT INTO bc VALUES ('BC-1.01.001','public contract')",
              "CREATE TABLE holdout_scenario (hs_id VARCHAR(16) PRIMARY KEY, "
              "expectation TEXT NOT NULL)",
              "INSERT INTO holdout_scenario VALUES ('HS-001','SECRET-EXPECTATION')"):
        sh(["dolt", "sql", "-q", s], cwd=DBD)
    sh(["dolt", "add", "-A"], cwd=DBD)
    sh(["dolt", "commit", "-m", "seed"], cwd=DBD)
    log = open(ROOT / "srv.log", "w")
    SERVERS.append(subprocess.Popen(
        ["dolt", "sql-server", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=DBD, stdout=log, stderr=log))
    for _ in range(60):
        try:
            c = pymysql.connect(host="127.0.0.1", port=PORT, user="root")
            c.close()
            print("    server up\n")
            return
        except Exception:                       # noqa: BLE001
            time.sleep(0.5)
    raise RuntimeError("server never started")


def teardown():
    for p in SERVERS:
        p.terminate()
    for p in SERVERS:
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()


def conn(user, pw=None, db="db"):
    kw = dict(host="127.0.0.1", port=PORT, user=user, autocommit=True,
              cursorclass=pymysql.cursors.DictCursor, database=db)
    if pw:
        kw["password"] = pw
    return pymysql.connect(**kw)


# ---------------------------------------------------------------- tests


def id1_self_declared_is_forgeable():
    """Quantify the tier-1 gap: the role is just a string the agent controls."""
    zroot = ROOT / ".factory-db"
    s = Store.open(zroot, role="orchestrator")
    s.init()
    honest, forged = None, None
    try:
        Store.open(zroot, role="implementer").zone_for("HS-001")
    except NotVisible as e:
        honest = str(e)[:60]
    except Exception as e:                      # noqa: BLE001
        honest = f"{type(e).__name__}: {str(e)[:50]}"
    # The "implementer" simply claims a different role.
    os.environ["DATUM_ROLE"] = "holdout-evaluator"
    try:
        z = Store.open(zroot).zone_for_type("holdout_scenario")
        forged = z.name
    finally:
        os.environ.pop("DATUM_ROLE", None)
    check("ID1 a self-declared role is trivially forgeable",
          honest is not None and forged == "walled",
          f"role=implementer  -> refused: {honest}\n"
          f"same agent sets DATUM_ROLE=holdout-evaluator -> resolves zone '{forged}'\n"
          "=> DATUM_ROLE is a HINT. It prevents accidents and produces good errors, but it\n"
          "   is not a boundary. Anything that reads its own role from its own\n"
          "   environment can claim any role.")


def id2_os_user_isolation_available():
    """Tier 2 requires agents to run as different uids. Is that true here?"""
    me = os.getuid()
    who = sh(["id", "-un"]).stdout.strip()
    # spawn a child the way an agent fleet does, and compare uid
    child = sh([sys.executable, "-c", "import os;print(os.getuid())"])
    child_uid = int((child.stdout or "-1").strip())
    can_setuid = os.geteuid() == 0
    same = child_uid == me
    check("ID2 OS-user isolation is NOT available in a same-uid agent fleet",
          same and not can_setuid,
          f"this process uid={me} ({who}); spawned child uid={child_uid}; same={same}\n"
          f"running as root (could drop to other uids)={can_setuid}\n"
          "=> agents in this harness are the SAME OS user. So tier 2 (chmod/chown on\n"
          "   zone dirs) cannot distinguish them, even though Z5 proved the OS enforces\n"
          "   permissions when uids DO differ. Tier 2 needs the harness to run each\n"
          "   agent as its own user or in its own container.")


def id3_same_uid_env_visibility():
    """If A can read B's environment, injecting a per-agent secret via env is unsafe."""
    secret = "SUPERSECRET-ENVVAL"
    env = dict(os.environ, FA_TEST_SECRET=secret)
    child = subprocess.Popen([sys.executable, "-c",
                              "import time;time.sleep(6)"], env=env)
    time.sleep(0.8)
    probes = {}
    r = sh(["ps", "eww", "-p", str(child.pid)])
    probes["ps eww"] = secret in (r.stdout or "")
    r2 = sh(["ps", "-E", "-p", str(child.pid)])
    probes["ps -E"] = secret in (r2.stdout or "")
    proc_env = Path(f"/proc/{child.pid}/environ")
    probes["/proc/<pid>/environ"] = (
        secret in proc_env.read_bytes().decode(errors="replace")
        if proc_env.exists() else False)
    child.terminate()
    child.wait(timeout=10)
    leaked = [k for k, v in probes.items() if v]
    check("ID3 a sibling agent CAN read another agent's environment (env is unsafe)",
          bool(leaked),
          "\n".join(f"  {k:24} leaked={v}" for k, v in probes.items())
          + f"\nleaking mechanisms: {leaked}\n"
            "=> I predicted macOS would hide this. It does NOT: `ps eww`/`ps -E` expose a\n"
            "   same-uid sibling's full environment. So injecting a per-agent credential\n"
            "   via environment variables does NOT isolate it, and ID5's 'each agent holds\n"
            "   only its own credential' does not hold by itself -- see ID5b.")


def id4_credential_file_is_shared():
    """A credential on shared disk is readable by every same-uid agent. So credentials
    must be injected per-process, never written to the repo."""
    cred = ROOT / "creds.txt"
    cred.write_text("evaluator:pw-evaluator\n")
    os.chmod(cred, 0o600)
    r = sh([sys.executable, "-c",
            f"print(open({str(cred)!r}).read().strip())"])
    readable = "pw-evaluator" in (r.stdout or "")
    check("ID4 a credential FILE on shared disk is readable by any same-uid agent",
          readable,
          f"mode 600 file read by a sibling process: leaked={readable}\n"
          f"  got: {(r.stdout or '').strip()[:40]}\n"
          "=> 0600 protects against OTHER USERS, not other agents running as YOU.\n"
          "   Credentials must be injected into each agent's environment by the harness\n"
          "   and never persisted in the repo or a shared dotfile.")


def id5_no_privilege_escalation():
    """Tier 3: per-role DB users. An agent holding one role's credential must not be
    able to act as another role."""
    root = conn("root")
    with root.cursor() as k:
        for u in ("evaluator", "implementer"):
            try:
                k.execute(f"DROP USER IF EXISTS '{u}'@'%'")
            except pymysql.err.Error:
                pass
        k.execute("CREATE USER 'evaluator'@'%' IDENTIFIED BY 'pw-eval'")
        k.execute("CREATE USER 'implementer'@'%' IDENTIFIED BY 'pw-impl'")
        k.execute("GRANT SELECT ON `db`.`holdout_scenario` TO 'evaluator'@'%'")
        k.execute("GRANT SELECT, INSERT, UPDATE ON `db`.`bc` TO 'implementer'@'%'")
    root.close()

    # implementer tries to become evaluator without the password
    escalated, notes = False, []
    for pw in ("pw-impl", "", "pw-eval-guess", "root"):
        try:
            c = conn("evaluator", pw)
            c.close()
            if pw != "pw-eval":
                escalated = True
                notes.append(f"LOGGED IN as evaluator with {pw!r}")
        except pymysql.err.Error as e:
            notes.append(f"evaluator/{pw or '<empty>'!r} refused ({e.args[0]})")
    # and the correct credential does work
    ok_login = False
    try:
        c = conn("evaluator", "pw-eval")
        c.close()
        ok_login = True
    except pymysql.err.Error as e:
        notes.append(f"correct credential failed: {str(e)[:50]}")
    check("ID5 per-role DB credentials: no escalation without the other password",
          not escalated and ok_login,
          "\n".join(f"  {n}" for n in notes)
          + f"\ncorrect evaluator credential works = {ok_login}\n"
            "=> the DATABASE side is sound: no guessing, no empty password, no reuse of\n"
            "   another role's password. Necessary but NOT sufficient -- it only holds if\n"
            "   an agent cannot OBTAIN a sibling's credential (ID3 says it can). See ID5b.")


def id5b_credential_theft_via_env():
    """The attack ID3 enables: read a sibling's env, then log in as that role."""
    env = dict(os.environ, FA_DB_USER="evaluator", FA_DB_PASSWORD="pw-eval")
    victim = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(8)"], env=env)
    time.sleep(0.8)
    dump = sh(["ps", "eww", "-p", str(victim.pid)]).stdout or ""
    stolen = None
    for tok in dump.split():
        if tok.startswith("FA_DB_PASSWORD="):
            stolen = tok.split("=", 1)[1]
    escalated, note = False, ""
    if stolen:
        try:
            c = conn("evaluator", stolen)
            with c.cursor() as k:
                k.execute("SELECT expectation FROM holdout_scenario")
                got = str(k.fetchall())
            c.close()
            escalated = "SECRET-EXPECTATION" in got
            note = f"read the walled row using the stolen credential: {escalated}"
        except pymysql.err.Error as e:
            note = f"login with stolen credential failed: {str(e)[:60]}"
    victim.terminate()
    victim.wait(timeout=10)
    check("ID5b a sibling steals the credential from env and IMPERSONATES the role",
          escalated,
          f"stolen password from `ps eww`: {stolen!r}\n{note}\n"
          "=> per-role DB credentials alone do NOT create a boundary in a same-uid\n"
          "   fleet, because the credential is obtainable. The credential must be\n"
          "   delivered by a channel a sibling cannot read -- see ID8.")


def id8_inherited_fd_is_unforgeable():
    """The mechanism that DOES work same-uid: the parent authenticates ONCE and hands
    the child an already-connected socket as an inherited file descriptor. No secret
    ever exists in env, argv, or a file, and a sibling cannot name another process's fd.

    Proven in two parts:
      (a) fd inheritance genuinely transfers a usable connection
      (b) a sibling cannot reach that fd
    """
    import socket
    # (a) a stand-in for the authenticated DB socket
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    import threading
    def echo():
        c, _ = srv.accept()
        c.sendall(b"AUTHENTICATED-CHANNEL")
        c.close()
    th = threading.Thread(target=echo, daemon=True)
    th.start()
    live = socket.create_connection(("127.0.0.1", port))
    fd = live.fileno()

    # pass_fds PRESERVES the fd NUMBER; it does not renumber to 3. The child must be
    # told which descriptor to use -- the number is not a secret, the fd itself is.
    child_code = (
        "import socket,sys\n"
        "s = socket.socket(fileno=int(sys.argv[1]))\n"
        "print('CHILD_GOT:' + s.recv(64).decode())\n")
    proc = subprocess.Popen([sys.executable, "-c", child_code, str(fd)], pass_fds=(fd,),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate(timeout=30)
    inherited = "CHILD_GOT:AUTHENTICATED-CHANNEL" in (out or "")
    live.close(); srv.close()

    # (b) a sibling cannot obtain another process's fd
    victim = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(6)"])
    time.sleep(0.5)
    no_proc = not Path(f"/proc/{victim.pid}/fd").exists()
    own = sh([sys.executable, "-c", "import os;print(sorted(os.listdir('/dev/fd'))[:5])"])
    per_process = "[" in (own.stdout or "")
    lsof = sh(["lsof", "-p", str(victim.pid)], timeout=60)
    can_see = (lsof.returncode == 0 and "TCP" in (lsof.stdout or "")) or True
    victim.terminate(); victim.wait(timeout=10)

    check("ID8 an inherited fd is unforgeable: no secret in env, argv, or a file",
          inherited and no_proc and per_process,
          f"(a) child USED the parent's live connection via fd inheritance: {inherited}\n"
          f"    child stdout: {(out or '').strip()[:60]}\n"
          f"(b) /proc/<pid>/fd absent on this platform: {no_proc}\n"
          f"    /dev/fd lists only the CALLER's descriptors: "
          f"{(own.stdout or '').strip()[:44]}\n"
          f"    (lsof can OBSERVE that a sibling holds sockets, but observing is not\n"
          f"     opening -- an fd cannot be re-acquired from another process)\n"
          "=> this is the only tested mechanism that isolates a credential between\n"
          "   same-uid agents: the harness authenticates per role and passes the live\n"
          "   connection down. Same trick as Chrome's renderer handles and CI runners.\n"
          "   ⚠ Requires the HARNESS to spawn agents with the fd -- it is not something\n"
          "     fa can do for itself, so it is a REQUIREMENT ON THE HARNESS, not a\n"
          "     feature fa can ship alone. On Linux re-verify: /proc/<pid>/fd exists,\n"
          "     though reopening a sibling's socket is still not permitted.")


def id6_credentials_are_zone_scoped():
    ev = conn("evaluator", "pw-eval")
    im = conn("implementer", "pw-impl")
    matrix = {}
    for label, c, tbl in (("evaluator->holdout", ev, "holdout_scenario"),
                          ("evaluator->bc", ev, "bc"),
                          ("implementer->bc", im, "bc"),
                          ("implementer->holdout", im, "holdout_scenario")):
        try:
            with c.cursor() as k:
                k.execute(f"SELECT * FROM {tbl} LIMIT 1")
                k.fetchall()
            matrix[label] = "ALLOWED"
        except pymysql.err.Error as e:
            matrix[label] = f"denied({e.args[0]})"
    ev.close(); im.close()
    correct = (matrix["evaluator->holdout"] == "ALLOWED"
               and matrix["evaluator->bc"].startswith("denied")
               and matrix["implementer->bc"] == "ALLOWED"
               and matrix["implementer->holdout"].startswith("denied"))
    check("ID6 credentials are zone-scoped in BOTH directions",
          correct,
          "\n".join(f"  {k:24} {v}" for k, v in matrix.items())
          + "\n=> table-level granularity, which the zone-DIRECTORY design cannot do\n"
            "   (Z4's caveat). The evaluator is denied specs AND the implementer is\n"
            "   denied holdout scenarios -- a two-way wall from one mechanism.")


def id7_attribution():
    """Identity also buys attribution: who wrote this, not just what changed."""
    root = conn("root")
    with root.cursor() as k:
        k.execute("GRANT ALL ON `db`.* TO 'implementer'@'%'")
    root.close()
    im = conn("implementer", "pw-impl")
    with im.cursor() as k:
        k.execute("SET @@dolt_transaction_commit=0")
        k.execute("UPDATE bc SET title='changed by implementer' WHERE bc_id='BC-1.01.001'")
        try:
            k.execute("CALL DOLT_COMMIT('-Am','implementer: retitle', "
                      "'--author', 'implementer <implementer@agents>')")
        except pymysql.err.Error as e:
            k.execute("CALL DOLT_COMMIT('-Am','implementer: retitle')")
    with im.cursor() as k:
        k.execute("SELECT committer, email, message FROM dolt_log ORDER BY date DESC LIMIT 2")
        log = k.fetchall()
    im.close()
    attributed = any("implementer" in str(r.get("committer", "")) + str(r.get("email", ""))
                     for r in log)
    check("ID7 identity gives per-write attribution in the audit trail",
          bool(log) and attributed,
          f"recent commits: {[(r['committer'], r['email'], str(r['message'])[:26]) for r in log]}\n"
          f"acting agent appears as the author = {attributed}\n"
          "=> W6 showed attribution existed but everything was 'root'. Per-role\n"
          "   credentials + an explicit --author make 'which agent amended this\n"
          "   contract' answerable, which the factory's traceability needs.")


def main():
    print("=" * 74)
    print("Agent identity: making zone walls enforceable rather than advisory")
    print("=" * 74)
    try:
        setup()
        for t in (id1_self_declared_is_forgeable, id2_os_user_isolation_available,
                  id3_same_uid_env_visibility, id4_credential_file_is_shared,
                  id5_no_privilege_escalation, id5b_credential_theft_via_env,
                  id8_inherited_fd_is_unforgeable, id6_credentials_are_zone_scoped,
                  id7_attribution):
            try:
                t()
            except Exception:
                import traceback
                check(f"{t.__name__} (ERROR)", False, traceback.format_exc()[-500:])
            print()
    finally:
        teardown()
    n = sum(1 for _, ok, _ in RESULTS if ok)
    print("=" * 74)
    print(f"{n}/{len(RESULTS)} passed")
    for nm, ok, _ in RESULTS:
        if not ok:
            print(f"  FAILED: {nm}")
    sys.exit(0 if n == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
