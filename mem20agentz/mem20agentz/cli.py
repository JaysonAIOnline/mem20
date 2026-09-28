"""mem20agentz CLI (sub-phase 2.1 slice).

Commands so far: version, config, profiles, sessions, status, pause, resume,
doctor, logs. Later slices add chat (agent loop), bridges, cron, kanban, etc.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from typing import Optional

from . import __version__
from ._substrate import Backend, BackendSealed, get_backend

import functools

try:
    from mem20cliz import json_main
except ImportError as _exc:  # never fail silently: a hidden fallback looks like success
    import sys as _sys

    def json_main(func):
        @functools.wraps(func)
        def _warn(*a, **k):
            _sys.stderr.write(
                "warning: mem20cliz unavailable, --json disabled for this CLI (%s)\n" % _exc
            )
            return func(*a, **k)

        return _warn

_runtime_log: Optional[pathlib.Path] = None


def _log_path() -> pathlib.Path:
    if _runtime_log is not None:
        return _runtime_log
    return pathlib.Path.home() / ".mem20agentz" / "runtime" / "mem20agentz.log"


def _backend():
    return get_backend()


# ------------------------------------------------------------------ status
_CURRENT = pathlib.Path.home() / ".mem20agentz" / "runtime" / "CURRENT_PROFILE"
_PAUSE = pathlib.Path.home() / ".mem20agentz" / "runtime" / "PAUSED"


def current_profile(default: str = "mem20") -> str:
    try:
        return _CURRENT.read_text().strip() or default
    except OSError:
        return default


def set_current(name: str) -> None:
    _CURRENT.parent.mkdir(parents=True, exist_ok=True)
    _CURRENT.write_text(name)


def set_paused(paused: bool, reason: str = "") -> None:
    _PAUSE.parent.mkdir(parents=True, exist_ok=True)
    if paused:
        _PAUSE.write_text(reason or "user-initiated pause")
    else:
        try:
            _PAUSE.unlink()
        except OSError:
            pass


def is_paused() -> bool:
    return _PAUSE.exists()


# ------------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mem20agentz",
                                description="mem20 agent platform")
    p.add_argument("--version", "-V", action="version",
                   version=f"mem20agentz {__version__}")
    p.add_argument("-z", "--oneshot", metavar="PROMPT",
                   help="one-shot mode: send a single prompt and print ONLY "
                        "the final reply to stdout (no banner/spinner). "
                        "Approvals are auto-bypassed.")
    p.add_argument("-m", "--model", default=None,
                   help="model override for this invocation")
    p.add_argument("-t", "--toolsets", default="skills",
                   help="comma-separated toolsets: skills,none (default skills)")
    p.add_argument("-r", "--resume", default=None, metavar="SESSION",
                   help="resume a session by id, or 'latest' for the most "
                        "recent session of the active profile")
    p.add_argument("--session", default=None,
                   help="explicit session id to run under (one-shot/chat)")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("config", help="show the active configuration")
    sub.add_parser("status", help="profile + pause status")
    sub.add_parser("pause", help="pause the platform (emergency stop)")
    sub.add_parser("resume", help="resume after a pause")
    sub.add_parser("doctor", help="basic environment checks")
    sub.add_parser("logs", help="tail the runtime log (default: last 40 lines)")

    sp = sub.add_parser("profiles", help="manage profiles")
    spsub = sp.add_subparsers(dest="prof_cmd", required=True)
    spsub.add_parser("list", help="list known profiles")
    sp_c = spsub.add_parser("create", help="create a profile")
    sp_c.add_argument("name")
    sp_c.add_argument("--identity", default="")
    sp_c.add_argument("--capabilities", nargs="*", default=[])
    sp_c.add_argument("--values", nargs="*", default=[])
    sp_now = spsub.add_parser("current", help="show active profile")
    sp_now.add_argument("name", nargs="?", help="set active profile")

    se = sub.add_parser("sessions", help="manage sessions")
    sesub = se.add_subparsers(dest="ses_cmd", required=True)
    sesub.add_parser("list", help="list sessions for the active profile")
    se_n = sesub.add_parser("new", help="start a new session")
    se_n.add_argument("--title", default="")
    se_n.add_argument("--profile", default=None)
    se_r = sesub.add_parser("prune", help="archive old sessions")
    se_r.add_argument("--keep", type=int, default=0)
    se_r.add_argument("--profile", default=None)

    sub.add_parser("chat", help="interactive chat REPL (resumable)")

    sk = sub.add_parser("skills", help="skills store: catalog/bundles/sync/curator")
    sks = sk.add_subparsers(dest="skill_cmd", required=True)
    sk_list = sks.add_parser("catalog", help="list/search procedural skills")
    sk_list.add_argument("--query", default="")
    sk_b = sks.add_parser("bundles", help="list bundles")
    sk_add = sks.add_parser("add", help="add skills to a bundle")
    sk_add.add_argument("bundle")
    sk_add.add_argument("skills", nargs="+")
    sk_rm = sks.add_parser("remove", help="remove skills from a bundle")
    sk_rm.add_argument("bundle")
    sk_rm.add_argument("skills", nargs="+")
    sk_sync = sks.add_parser("sync", help="reconcile a bundle with mem20")
    sk_sync.add_argument("bundle")
    sk_cur = sks.add_parser("curator", help="report stale/unreferenced bundles")
    sk_exp = sks.add_parser("export", help="export a bundle to yaml")
    sk_exp.add_argument("bundle")
    sk_exp.add_argument("path")
    sk_imp = sks.add_parser("import", help="import a bundle from yaml")
    sk_imp.add_argument("path")

    pl = sub.add_parser("plugins", help="plugin registry")
    pls = pl.add_subparsers(dest="plugin_cmd", required=True)
    pls.add_parser("list", help="discover + validate plugins")
    pl_l = pls.add_parser("load", help="load a plugin's entry callable")
    pl_l.add_argument("name")

    pe = sub.add_parser("pets", help="petdex companions")
    pes = pe.add_subparsers(dest="pet_cmd", required=True)
    pes.add_parser("list", help="list pets")
    pe_a = pes.add_parser("adopt", help="adopt a pet")
    pe_a.add_argument("name")
    pe_a.add_argument("species", default="cb", nargs="?")
    pe_c = pes.add_parser("care", help="feed/play/rest a pet")
    pe_c.add_argument("name")
    pe_c.add_argument("act", choices=("feed", "play", "rest"))

    skn = sub.add_parser("skins", help="display themes")
    skns = skn.add_subparsers(dest="skin_cmd", required=True)
    skns.add_parser("list", help="list skins")
    skn_a = skns.add_parser("create", help="create a skin")
    skn_a.add_argument("name")
    skn_a.add_argument("--banner", default=None)
    skn_a.add_argument("--primary", default=None)
    skn_c = skns.add_parser("apply", help="make a skin active")
    skn_c.add_argument("name")

    hk = sub.add_parser("hooks", help="lifecycle shell hooks")
    hks = hk.add_subparsers(dest="hook_cmd", required=True)
    hk_s = hks.add_parser("set", help="register a hook")
    hk_s.add_argument("event", choices=__import__("mem20agentz.hooks",
                                                  fromlist=["EVENTS"]).EVENTS)
    hk_s.add_argument("name")
    hk_s.add_argument("command")
    hk_u = hks.add_parser("unset", help="remove a hook")
    hk_u.add_argument("event")
    hk_u.add_argument("name")
    hk_f = hks.add_parser("fire", help="fire a hook event now")
    hk_f.add_argument("event")
    hk_f.add_argument("--payload", default="{}")

    prj = sub.add_parser("projects", help="named workspaces")
    prjs = prj.add_subparsers(dest="proj_cmd", required=True)
    prjs.add_parser("list", help="list projects")
    prj_c = prjs.add_parser("create", help="create a project")
    prj_c.add_argument("name")
    prj_c.add_argument("--description", default="")
    prj_cu = prjs.add_parser("current", help="print active project")
    prj_a = prjs.add_parser("archive", help="archive a project")
    prj_a.add_argument("name")

    cr = sub.add_parser("cron", help="scheduled jobs")
    crs = cr.add_subparsers(dest="cron_cmd", required=True)
    crs.add_parser("list", help="list jobs")
    cr_a = crs.add_parser("add", help="add a job")
    cr_a.add_argument("name")
    cr_a.add_argument("schedule")
    cr_a.add_argument("--prompt", default="")
    cr_a.add_argument("--command", default="")
    cr_a.add_argument("--profile", default="mem20")
    cr_r = crs.add_parser("remove", help="remove a job")
    cr_r.add_argument("name")
    cr_n = crs.add_parser("next", help="next run time")
    cr_n.add_argument("name")
    cr_x = crs.add_parser("run", help="run a job now")
    cr_x.add_argument("name")
    cr_s = crs.add_parser("serve", help="run the scheduler loop")

    kb = sub.add_parser("kanban", help="boards and cards")
    kbs = kb.add_subparsers(dest="kanban_cmd", required=True)
    kb_boards = kbs.add_parser("boards")
    kbb = kb_boards.add_subparsers(dest="kb_boards_cmd", required=True)
    kbb.add_parser("list")
    kb_bs = kbb.add_parser("create")
    kb_bs.add_argument("name")
    kbb_d = kbb.add_parser("delete")
    kbb_d.add_argument("name")

    pp = sub.add_parser("pipeline", help="mem20 *z production pipelines")
    pps = pp.add_subparsers(dest="pipeline_cmd", required=True)
    pps.add_parser("fleet", help="inventory of the *z subsystem fleet")
    pps.add_parser("specs", help="scan + materialize the Desktop/1+2 specs")
    pr = pps.add_parser("run", help="run a spec pipeline as a build")
    pr.add_argument("name")
    pk = pps.add_parser("peek", help="live view into a running build")
    pk.add_argument("build_id", nargs="?")
    pk.add_argument("--phase", default=None)
    pk.add_argument("--tail", type=int, default=40)
    kb_cs = kbs.add_parser("cards")
    kbc = kb_cs.add_subparsers(dest="kb_cards_cmd", required=True)
    kbc_l = kbc.add_parser("list")
    kbc_l.add_argument("board")
    kbc_l.add_argument("--status", default="")
    kbc_a = kbc.add_parser("add")
    kbc_a.add_argument("board")
    kbc_a.add_argument("title")
    kbc_a.add_argument("--assignee", default="")
    kbc_a.add_argument("--tag", action="append", default=[])
    kbc_m = kbc.add_parser("move")
    kbc_m.add_argument("board")
    kbc_m.add_argument("card")
    kbc_m.add_argument("column")

    wh = sub.add_parser("webhooks", help="webhook listener")
    whs = wh.add_subparsers(dest="webhook_cmd", required=True)
    wh_r = whs.add_parser("register", help="register a route")
    wh_r.add_argument("route")
    wh_r.add_argument("--handler", default="")
    whrs = whs.add_parser("routes", help="list registered routes")
    wh_sp = whs.add_parser("serve", help="start listener (foreground)")
    wh_sp.add_argument("--port", type=int, default=0)

    gw = sub.add_parser("gateway", help="messaging gateway daemon")
    gws = gw.add_subparsers(dest="gateway_cmd", required=True)
    gw_sv = gws.add_parser("serve", help="start the gateway daemon")
    gw_sv.add_argument("--bridges", default=None,
                       help="comma-separated bridge names (else config "
                            "gateway.bridges)")
    gw_lb = gws.add_parser("loopback-deliver",
                           help="enter a message into the loopback bridge")
    gw_lb.add_argument("chat_id")
    gw_lb.add_argument("text", nargs="+")
    gw_lr = gws.add_parser("loopback-recv",
                           help="collect replies transmitted by the loopback "
                                "bridge for a chat")
    gw_lr.add_argument("chat_id")
    gws.add_parser("status", help="list bridges and pairing")
    gw_p = gws.add_parser("pair", help="authorize a chat")
    gw_p.add_argument("platform")
    gw_p.add_argument("chat_id")
    gw_u = gws.add_parser("unpair", help="revoke a chat")
    gw_u.add_argument("platform")
    gw_u.add_argument("chat_id")

    wg = sub.add_parser("webgateway", help="HTTP web gateway + dashboard")
    wgs = wg.add_subparsers(dest="web_cmd", required=True)
    wg_sv = wgs.add_parser("serve", help="start the web gateway")
    wg_sv.add_argument("--port", type=int, default=0)
    wg_sv.add_argument("--host", default="127.0.0.1")
    wgs.add_parser("status", help="dashboard JSON status")

    dt = sub.add_parser("desktop", help="unified mem20 frontend")
    dts = dt.add_subparsers(dest="desktop_cmd", required=True)
    dt_sv = dts.add_parser("serve", help="start the unified desktop app")
    dt_sv.add_argument("--port", type=int, default=0)
    dt_sv.add_argument("--host", default="127.0.0.1")
    dt_sv.add_argument("--both", action="store_true",
                       help="also serve the :18778 dashboard "
                            "(unified desktop + dashboard)")
    dts.add_parser("status", help="desktop frontend summary (no server)")

    mcp = sub.add_parser("mcp", help="model context protocol")
    mcps = mcp.add_subparsers(dest="mcp_cmd", required=True)
    mcp_sv = mcps.add_parser("serve", help="expose skills over JSON-RPC")
    mcp_sv.add_argument("--port", type=int, default=0)
    mcp_in = mcps.add_parser("initialize", help="client: handshake")
    mcp_in.add_argument("url", help="server base url (http://host:port)")
    mcp_ls = mcps.add_parser("list", help="client: list tools")
    mcp_ls.add_argument("url", help="server base url (http://host:port)")
    mcp_cl = mcps.add_parser("call", help="client: call a tool")
    mcp_cl.add_argument("url")
    mcp_cl.add_argument("tool")
    mcp_cl.add_argument("args", nargs="?", default="{}")

    acp = sub.add_parser("acp", help="peer-agent communication bridge")
    acps = acp.add_subparsers(dest="acp_cmd", required=True)
    acp_sv = acps.add_parser("serve", help="start the peer bridge")
    acp_sv.add_argument("--port", type=int, default=0)
    acp_sv.add_argument("--host", default="127.0.0.1")

    cmpu = sub.add_parser("computer", help="computer-use primitives")
    cmpus = cmpu.add_subparsers(dest="computer_cmd", required=True)
    cmpu_r = cmpus.add_parser("run", help="run a shell command")
    cmpu_r.add_argument("command")
    cmpu_r.add_argument("--timeout", type=float, default=30.0)
    cmpu_s = cmpus.add_parser("shot", help="capture the display")
    cmpu_s.add_argument("path", nargs="?", default=None)
    cmpu_rd = cmpus.add_parser("read", help="read a file")
    cmpu_rd.add_argument("path")
    cmpu_wr = cmpus.add_parser("write", help="write a file")
    cmpu_wr.add_argument("path")
    cmpu_wr.add_argument("text")

    orcmd = sub.add_parser("oreo", help="OREO: NL -> graph -> runnable app")
    ors = orcmd.add_subparsers(dest="oreo_cmd", required=True)
    or_b = ors.add_parser("build",
                          help="build a runnable app from natural language")
    or_b.add_argument("nl", help="natural-language program to build")
    or_b.add_argument("--host", default="127.0.0.1")
    or_b.add_argument("--port", type=int, default=0)
    or_s = ors.add_parser("status", help="list stored graphs (oreo store)")
    or_s.add_argument("--kind", default=None)
    or_e = ors.add_parser("editor", help="serve the talk+draw editor as a route")
    or_e.add_argument("--build", default="editor-default")
    or_e.add_argument("--host", default="127.0.0.1")
    or_e.add_argument("--port", type=int, default=0)
    or_e.add_argument("--forever", action="store_true",
                      help="serve_forever (blocking)")

    bu = sub.add_parser("backup", help="archive/restore ledger + config")
    bus = bu.add_subparsers(dest="backup_cmd", required=True)
    bu_e = bus.add_parser("export", help="write gzipped archive + sha256")
    bu_e.add_argument("--out", default=None)
    bu_r = bus.add_parser("restore", help="replay archive into the ledger")
    bu_r.add_argument("path")
    bu_r.add_argument("--profile", default=None)

    ia = sub.add_parser("import-agent",
                        help="import Claude Code / Codex transcript as session")
    ia.add_argument("path")
    ia.add_argument("--kind", default="auto",
                    choices=["auto", "claude", "codex"])
    ia.add_argument("--profile", default="mem20")
    ia.add_argument("--session-id", default=None)

    mig = sub.add_parser("migration",
                         help="config schema + foreign-setup migration")
    migs = mig.add_subparsers(dest="migration_cmd", required=True)
    migs.add_parser("config", help="apply default schema migrations")
    mig_c = migs.add_parser("claw", help="import an mem20 claw plugin memory export")
    mig_c.add_argument("manifest")
    mig_c.add_argument("--profile", default="mem20")

    sub.add_parser("parity", help="CLI parity sweep: every command --help")

    sec = sub.add_parser("secrets", help="secrets vault (values never printed)")
    secs = sec.add_subparsers(dest="secrets_cmd", required=True)
    secs.add_parser("list", help="list keys")
    secs.add_parser("status", help="describe sources, never values")
    sec_st = secs.add_parser("get", help="resolve a key (presence only)")
    sec_st.add_argument("key")
    sec_set = secs.add_parser("set", help="store into the local vault")
    sec_set.add_argument("key")
    sec_set.add_argument("value")
    sec_del = secs.add_parser("delete", help="remove from the local vault")
    sec_del.add_argument("key")

    eg = sub.add_parser("egress", help="egress firewall (iron-proxy)")
    egs = eg.add_subparsers(dest="egress_cmd", required=True)
    eg_chk = egs.add_parser("check", help="evaluate a url against policy")
    eg_chk.add_argument("url")
    eg_sv = egs.add_parser("serve", help="loopback forward proxy (foreground)")
    eg_sv.add_argument("--port", type=int, default=18782)
    eg_sv.add_argument("--host", default="127.0.0.1")

    ll = sub.add_parser("llms", help="LLM providers, fallback, mixture-of-agents")
    lls = ll.add_subparsers(dest="llms_cmd", required=True)
    lls.add_parser("list", help="list providers + models + key presence")
    ll_c = lls.add_parser("call", help="single call (with fallback)")
    ll_c.add_argument("prompt")
    ll_c.add_argument("--model")
    ll_c.add_argument("--provider")
    ll_c.add_argument("--temperature", type=float, default=0.7)
    ll_m = lls.add_parser("moa", help="mixture-of-agents over providers")
    ll_m.add_argument("prompt")
    ll_m.add_argument("--proposers", type=int, default=3)
    ll_m.add_argument("--providers",
                     help="comma-separated provider names (else all)")

    au = sub.add_parser("auth", help="auth key ring, rotation pool, proxy")
    aus = au.add_subparsers(dest="auth_cmd", required=True)
    aus.add_parser("status", help="per-provider key presence (never values)")
    au_p = aus.add_parser("proxyserve",
                          help="key-hiding OpenAI-compatible proxy")
    au_p.add_argument("--port", type=int, default=18784)
    au_p.add_argument("--host", default="127.0.0.1")

    seccmd = sub.add_parser("security", help="OSV audit + guardrails")
    seccmds = seccmd.add_subparsers(dest="security_cmd", required=True)
    seccmds.add_parser("verify", help="full doctor report")
    osv_p = seccmds.add_parser("osv", help="dependency vulnerability scan")
    osv_p.add_argument("--pkg", action="append", default=[],
                       help="name==version (repeatable; else from manifest)")

    return p


def _out(obj) -> None:
    if isinstance(obj, str):
        print(obj)
    else:
        print(json.dumps(obj, indent=2, default=str))


@json_main
def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not getattr(args, "cmd", None) and not args.oneshot:
        build_parser().print_help()
        return 0

    b = _backend()
    from .profiles import Profiles
    from .sessions import Sessions

    active = current_profile()

    if args.oneshot is not None:
        return _run_one(args, b, active)

    if args.cmd == "chat":
        return _run_chat(args, b, active)

    if args.cmd == "config":
        from .config import Config, load_config
        cfg = load_config()
        _out(cfg.data)
    elif args.cmd == "status":
        _out({"profile": active,
              "paused": is_paused(),
              "pause_reason": _PAUSE.read_text().strip() if is_paused() else None})
    elif args.cmd == "pause":
        set_paused(True, args.reason if hasattr(args, "reason") else "")
        _out({"paused": True})
    elif args.cmd == "resume":
        set_paused(False)
        _out({"paused": False})
    elif args.cmd == "doctor":
        return _cmd_doctor(b, args)
    elif args.cmd == "security":
        return _cmd_security(b, args)
    elif args.cmd == "secrets":
        return _cmd_secrets(b, args)
    elif args.cmd == "egress":
        return _cmd_egress(b, args)
    elif args.cmd == "llms":
        return _cmd_llms(b, args)
    elif args.cmd == "auth":
        return _cmd_auth(b, args)
    elif args.cmd == "logs":
        _logs(getattr(args, "n", None))
    elif args.cmd == "profiles":
        profs = Profiles(b)
        if args.prof_cmd == "list":
            _out({"profiles": profs.list(), "current": active})
        elif args.prof_cmd == "create":
            prof = profs.create(args.name, args.identity, args.capabilities,
                                args.values)
            _out({"created": prof.name, "namespace": prof.namespace,
                  "self_model": prof.self_model})
        elif args.prof_cmd == "current":
            if args.name:
                set_current(args.name)
                _out({"current": args.name})
            else:
                _out({"current": active})
    elif args.cmd == "sessions":
        sess = Sessions(b, default_profile=active)
        profile = getattr(args, "profile", None) or active
        if args.ses_cmd == "list":
            _out({"sessions": sess.list(profile)})
        elif args.ses_cmd == "new":
            sid = sess.new(profile, args.title)
            _out({"created": sid, "profile": profile})
        elif args.ses_cmd == "prune":
            _out({"archived": sess.prune(profile, keep=args.keep)})
    elif args.cmd == "skills":
        _cmd_skills(b, args)
    elif args.cmd == "plugins":
        _cmd_plugins(args)
    elif args.cmd == "pets":
        _cmd_pets(b, args)
    elif args.cmd == "skins":
        _cmd_skins(args)
    elif args.cmd == "hooks":
        _cmd_hooks(b, args)
    elif args.cmd == "projects":
        _cmd_projects(args)
    elif args.cmd == "cron":
        return _cmd_cron(b, args)
    elif args.cmd == "kanban":
        _cmd_kanban(b, args)
    elif args.cmd == "pipeline":
        return _cmd_pipeline(args)
    elif args.cmd == "webhooks":
        _cmd_webhooks(b, args)
    elif args.cmd == "gateway":
        return _cmd_gateway(b, args)
    elif args.cmd == "webgateway":
        return _cmd_webgateway(b, args)
    elif args.cmd == "desktop":
        return _cmd_desktop(b, args)
    elif args.cmd == "backup":
        return _cmd_backup(b, args)
    elif args.cmd == "import-agent":
        return _cmd_import_agent(b, args)
    elif args.cmd == "migration":
        return _cmd_migration(b, args)
    elif args.cmd == "parity":
        return _cmd_parity(b, args)
    elif args.cmd == "mcp":
        return _cmd_mcp(b, args)
    elif args.cmd == "acp":
        return _cmd_acp(b, args)
    elif args.cmd == "computer":
        return _cmd_computer(b, args)
    elif args.cmd == "oreo":
        return _cmd_oreo(b, args)
    return 0


# ------------------------------------------------------------ oneshot/chat
def _toolsets_arg(raw: str) -> tuple:
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    return tuple(p for p in parts if p in ("skills", "none")) or ("skills",)


def _resolve_session(b, active: str, resume: Optional[str],
                     explicit: Optional[str]) -> str:
    from .sessions import Sessions
    if explicit:
        return explicit
    if not resume:
        return ""
    sess = Sessions(b, default_profile=active)
    rows = sess.list(active)
    if resume == "latest" and rows:
        return rows[0]["session_id"]
    for row in rows:
        if row["session_id"].startswith(resume) or resume in row["title"]:
            return row["session_id"]
    return ""


def _history_for(b, profile: str, session_id: str) -> list[dict]:
    msgs = b.session_messages(profile, session_id, k=20)
    out = []
    for m in msgs:
        role = "assistant" if "assistant" in (m.get("tags") or []) else "user"
        if isinstance(m, dict) and m.get("content"):
            out.append({"role": role, "content": m["content"]})
    return out


def _run_one(args, b, active: str) -> int:
    from .agentz import AgentCore, persist_turn
    from .config import load_config
    from .sessions import Sessions

    cfg = load_config()
    toolsets = _toolsets_arg(args.toolsets or "skills")
    profile = active
    sid = _resolve_session(b, profile, args.resume, args.session)
    created = False
    if not sid:
        sid = Sessions(b, default_profile=profile).new(
            title=args.oneshot[:48])
        created = True
    try:
        history = _history_for(b, profile, sid)
    except Exception:  # noqa: BLE001
        history = []
    core = AgentCore(backend=b, profile=profile, model=args.model,
                     approvals="auto", toolsets=toolsets, history=history)
    result = core.run(args.oneshot)
    persist_turn(b, profile, sid, args.oneshot, result.text)
    if not result.text.startswith("[brain error]"):
        print(result.text)
    else:
        print(result.text)
    return 0


def _run_chat(args, b, active: str) -> int:
    from .agentz import AgentCore, persist_turn
    from .config import load_config
    from .sessions import Sessions

    cfg = load_config()
    toolsets = _toolsets_arg(args.toolsets or "skills")
    profile = active
    sid = _resolve_session(b, profile, args.resume, args.session)
    created = False
    if not sid:
        sid = Sessions(b, default_profile=profile).new(title="interactive")
        created = True
    print(f"mem20agentz chat [{profile} {sid}]  (/quit /new /help)")
    history = []
    try:
        history = _history_for(b, profile, sid)
    except Exception:  # noqa: BLE001
        pass

    def ask(tool: str, args_: str) -> bool:
        while True:
            ans = input(f"  allow tool '{tool}' ({args_[:40]!r})? [y/N] ").strip().lower()
            if ans in ("y", "yes"):
                return True
            if ans in ("n", "no", ""):
                return False

    try:
        while True:
            try:
                line = input("[you] ").strip()
            except EOFError:
                break
            if not line:
                continue
            if line in ("/quit", "/exit"):
                break
            if line == "/new":
                sid = Sessions(b, default_profile=profile).new(title="interactive")
                history = []
                print(f"[session {sid}]")
                continue
            if line == "/help":
                print("  /quit /exit  /new   (lines are run as prompts)")
                continue
            core = AgentCore(backend=b, profile=profile, model=args.model,
                             approvals=cfg.get("approvals", "auto"),
                             toolsets=toolsets, history=history,
                             approve_tool=ask if cfg.get("approvals") == "ask"
                             else None)
            result = core.run(line)
            print(f"[mem20agentz] {result.text}")
            history += [{"role": "user", "content": line},
                        {"role": "assistant", "content": result.text}]
            persist_turn(b, profile, sid, line, result.text)
    except KeyboardInterrupt:
        pass
    print()
    return 0


def _cmd_skills(b, args) -> None:
    from .skills import SkillsStore
    store = SkillsStore(b)
    if args.skill_cmd == "catalog":
        _out({"skills": [{"name": s.name, "description": s.description}
                         for s in store.catalog(args.query)]})
    elif args.skill_cmd == "bundles":
        _out({"bundles": store.bundles()})
    elif args.skill_cmd == "add":
        _out(store.bundle_add(args.bundle, args.skills))
    elif args.skill_cmd == "remove":
        _out(store.bundle_remove(args.bundle, args.skills))
    elif args.skill_cmd == "sync":
        _out(store.sync(args.bundle))
    elif args.skill_cmd == "curator":
        _out(store.curator())
    elif args.skill_cmd == "export":
        store.export_bundle(args.bundle, args.path)
        _out({"exported": args.bundle, "to": str(args.path)})
    elif args.skill_cmd == "import":
        _out(store.import_bundle(args.path))


def _cmd_plugins(args) -> None:
    from .plugins import PluginRegistry
    reg = PluginRegistry()
    if args.plugin_cmd == "list":
        _out({"plugins": [reg.validate(m.name, raise_on_error=False)
                          for m in reg.discover()]})
    elif args.plugin_cmd == "load":
        entry = reg.load(args.name)
        _out({"loaded": args.name,
              "has_entry": entry is not None})
    return None


def _cmd_pets(b, args) -> None:
    from .pets import Petdex
    petdex = Petdex(b)
    if args.pet_cmd == "list":
        _out({"pets": [pet.name for pet in petdex.list()]})
    elif args.pet_cmd == "adopt":
        pet = petdex.adopt(args.name, args.species)
        _out({"adopted": pet.name, "species": pet.species,
              "stats": pet.stats})
    elif args.pet_cmd == "care":
        pet = petdex.care(args.name, args.act)
        if pet is None:
            _out({"error": f"no such pet: {args.name}"})
        else:
            _out({"name": pet.name, "act": args.act, "stats": pet.stats})


def _cmd_skins(args) -> None:
    from .skin import Skins
    skins = Skins()
    if args.skin_cmd == "list":
        _out({"skins": skins.list(), "active": skins.active()})
    elif args.skin_cmd == "create":
        skin = skins.create(args.name, args.banner,
                            {"primary": args.primary} if args.primary else None)
        _out({"created": skin.name, "banner": skin.banner})
    elif args.skin_cmd == "apply":
        ok = skins.apply(args.name)
        _out({"applied": args.name} if ok else {"error": "unknown skin"})


def _cmd_hooks(b, args) -> None:
    from .hooks import HookRegistry
    registry = HookRegistry()
    if args.hook_cmd == "set":
        registry.set(args.event, args.name, args.command)
        _out({"set": args.event, "name": args.name})
    elif args.hook_cmd == "unset":
        _out({"removed": registry.unset(args.event, args.name)})
    elif args.hook_cmd == "fire":
        _out({"results": registry.fire(args.event, json.loads(args.payload))})


def _cmd_projects(args) -> None:
    from .projects import Projects
    projects = Projects()
    if args.proj_cmd == "list":
        _out({"projects": [p.to_dict() for p in projects.list()]})
    elif args.proj_cmd == "create":
        _out(projects.create(args.name, args.description).to_dict())
    elif args.proj_cmd == "current":
        _out({"current": projects.current()})
    elif args.proj_cmd == "archive":
        project = projects.archive(args.name)
        _out({"archived": args.name} if project else {"error": "no such project"})


def _cmd_cron(b, args) -> int:
    from .cron import Cron, Job
    cron = Cron(backend=b)
    try:
        if args.cron_cmd == "list":
            _out({"jobs": cron.list()})
        elif args.cron_cmd == "add":
            kind = "command" if args.command else "prompt"
            target = args.command or args.prompt
            if not target:
                _out({"error": "need --prompt or --command"})
                return 1
            cron.add(Job(name=args.name, schedule=args.schedule,
                         type_=kind, target=target,
                         profile=args.profile))
            _out({"added": args.name, "schedule": args.schedule,
                  "type": kind})
        elif args.cron_cmd == "remove":
            _out({"removed": cron.remove(args.name)})
        elif args.cron_cmd == "next":
            _out({"job": args.name, "next": cron.next_run(args.name)})
        elif args.cron_cmd == "run":
            _out(cron.run(args.name, backend=b))
        elif args.cron_cmd == "serve":
            from .cron import serve
            try:
                serve(cron, backend=b)
            except KeyboardInterrupt:
                return 0
    except Exception as exc:  # noqa: BLE001
        _out({"error": str(exc)})
        return 1
    return 0


def _cmd_kanban(b, args) -> None:
    from .kanban import Kanban
    kanban = Kanban()
    if args.kanban_cmd == "boards":
        if args.kb_boards_cmd == "list":
            _out({"boards": kanban.board_names()})
        elif args.kb_boards_cmd == "create":
            board = kanban.create_board(args.name)
            _out({"board": board.name, "columns": board.columns})
        elif args.kb_boards_cmd == "delete":
            _out({"deleted": kanban.delete_board(args.name)})
    elif args.kanban_cmd == "cards":
        if args.kb_cards_cmd == "list":
            _out({"cards": kanban.list_cards(args.board, args.status)})
        elif args.kb_cards_cmd == "add":
            card = kanban.add_card(args.board, args.title,
                                   assignee=args.assignee,
                                   tags=tuple(args.tag))
            _out(card if card else {"error": "no such board"})
        elif args.kb_cards_cmd == "move":
            card = kanban.move_card(args.board, args.card, args.column)
            _out({"moved": args.card, "to": args.column} if card
                 else {"error": "no such board/card/column"})


def _cmd_pipeline(args) -> int:
    from . import production

    if args.pipeline_cmd == "fleet":
        rows = [{"name": f["name"], "version": f["version"],
                 "scripts": f["scripts"]} for f in production.fleet()]
        _out({"fleet": rows})
    elif args.pipeline_cmd == "specs":
        specs = production.ensure_specs()
        _out({"specs": [{"name": s["name"], "agents": s["agents"],
                         "phases": len(s["phases"]),
                         "flags": s["flags"]} for s in specs]})
    elif args.pipeline_cmd == "run":
        bid = production.run(args.name)
        print(bid)
    elif args.pipeline_cmd == "peek":
        view = production.peek(args.build_id, args.phase, args.tail)
        if not view.get("build_id"):
            _out(view)
            return 1
        print("build:", view["build_id"], "| status:", view["status"],
              "| current_phase:", view["current_phase"])
        for x in view["phases"]:
            print(f"  phase {x['id']} {x['name']}: {x['status']} "
                  f"| {(x.get('gate') or '')[:60]}")
        if view.get("phase") is not None:
            print(f"-- live log tail for phase {view['phase']} --")
            for line in view["phase_log_tail"]:
                print("   ", line)
            print("-- artifacts --")
            for a in view["artifacts"]:
                print("   ", a["path"], f"({a['bytes']}B)")
    return 0


def _cmd_webhooks(b, args) -> None:
    from .webhooks import WebhookServer
    server = WebhookServer(ledger=b)
    if args.webhook_cmd == "register":
        route = args.route
        if args.handler:
            def handler(body, route=route):
                return _run_cmd(args.handler, route, body)
            server.register(route, handler)
            _out({"registered": route})
        else:
            _out({"registered": route,
                  "note": "undelivered calls will be logged to ledger"})
    elif args.webhook_cmd == "routes":
        _out({"routes": server.routes()})
    elif args.webhook_cmd == "serve":
        url = server.serve(args.port)
        print(f"webhook listener on {url}/webhook/<route>")
        try:
            import time
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            server.stop()


def _run_cmd(handler: str, route: str, body: bytes) -> str:
    import subprocess
    proc = subprocess.run(handler, shell=True, capture_output=True,
                          text=True, input=body.decode("utf-8", "replace"),
                          timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-200:])
    return proc.stdout[-400:]


def _cmd_gateway(b, args) -> int:
    from .gateway import Gateway
    gateway = Gateway(backend=b)
    if args.gateway_cmd == "serve":
        names = None
        if getattr(args, "bridges", None):
            names = [n.strip() for n in args.bridges.split(",") if n.strip()]
        try:
            gateway.serve(names)
        except KeyboardInterrupt:
            gateway.stop()
        except Exception as exc:  # noqa: BLE001  (auth/transport failures)
            _out({"error": str(exc), "tip": "set MEM20AGENTZ_TELEGRAM_TOKEN "
                  "or TELEGRAM_BOT_TOKEN then retry, or use "
                  "--bridges loopback"})
            return 1
        return 0
    if args.gateway_cmd == "status":
        # load bridges read-only to reflect configured transports
        gateway.load()
        _out(gateway.status())
        return 0
    if args.gateway_cmd == "loopback-deliver":
        from .bridges.loopback import LoopbackTransport
        _out(LoopbackTransport().deliver(
            args.chat_id, " ".join(args.text)))
        return 0
    if args.gateway_cmd == "loopback-recv":
        from .bridges.loopback import LoopbackTransport
        _out({"chat_id": args.chat_id,
              "replies": LoopbackTransport().collect(args.chat_id)})
        return 0
    bridge = Bridge_peek(args.platform)
    if args.gateway_cmd == "pair":
        _out({"platform": args.platform, "pairs": bridge.pair(args.chat_id)})
    elif args.gateway_cmd == "unpair":
        _out({"platform": args.platform,
              "removed": bridge.unpair(args.chat_id)})
    return 0


def _cmd_webgateway(b, args) -> int:
    from .gateway_web import WebGateway, build_web_factory
    wg = WebGateway(backend=b, agent_factory=build_web_factory(b))
    if args.web_cmd == "serve":
        url = wg.serve(port=args.port, host=args.host)
        print(f"[webgateway] {url}", file=sys.stderr)
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            wg.stop()
        return 0
    if args.web_cmd == "status":
        _out(wg.status())
        return 0
    return 1


def _cmd_desktop(b, args) -> int:
    from .desktop import (Frontend, build_office_factory,
                          default_office_port,
                          default_dashboard_port)
    fe = Frontend(backend=b, agent_factory=build_office_factory(b))
    if args.desktop_cmd == "serve":
        port = args.port or default_office_port()
        if getattr(args, "both", False):
            urls = fe.serve_both(desktop_port=port,
                                 dashboard_port=default_dashboard_port(),
                                 host=args.host)
            print(f"[mem20] desktop   {urls[0]}  (unified tabs)",
                  file=sys.stderr)
            print(f"[mem20] dashboard {urls[1]}", file=sys.stderr)
        else:
            url = fe.serve(port=port, host=args.host)
            print(f"[mem20] desktop {url}", file=sys.stderr)
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            fe.stop()
        return 0
    if args.desktop_cmd == "status":
        _out({"service": "mem20", "desktop_port": default_office_port(),
              "dashboard_port": default_dashboard_port(),
              "endpoints": [
                  "GET / (unified tabs: office/kanban/production/settings/chat)",
                  "GET /office", "GET /kanban", "GET /production",
                  "GET /settings", "GET /dashboard", "GET /status",
                  "GET /health", "POST /chat",
                  "POST /production/run", "POST /settings"]})
        return 0
    return 1


def _cmd_backup(b, args) -> int:
    from .backup import Backup
    bk = Backup(backend=b)
    if args.backup_cmd == "export":
        _out(bk.export(out=args.out))
        return 0
    if args.backup_cmd == "restore":
        _out(bk.restore(args.path, profile=args.profile))
        return 0
    return 1


def _cmd_import_agent(b, args) -> int:
    from .import_agent import import_agent
    _out(import_agent(b, args.path, profile=args.profile, kind=args.kind,
                      session_id=args.session_id))
    return 0


def _cmd_migration(b, args) -> int:
    from .migration import Migrator
    mig = Migrator(backend=b)
    if args.migration_cmd == "config":
        _out(mig.config())
        return 0
    if args.migration_cmd == "claw":
        _out(mig.claw(args.manifest, profile=args.profile))
        return 0
    return 1


def _cmd_parity(b, args) -> int:
    import argparse
    import os
    import subprocess

    parser = build_parser()
    names: list[str] = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            names = sorted(action.choices)
            break
    if not names:
        return _out({"checked": 0, "error": "no subcommands found"}) or 1
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", "/opt/mem20/mem20agentz")
    env.setdefault("MEM20AGENTZ_BACKEND", "fake")
    base = [sys.executable, "-m", "mem20agentz.cli"]
    rows = []
    failed = []
    for name in names:
        try:
            run = subprocess.run(base + [name, "--help"],
                                 capture_output=True, env=env,
                                 text=True, timeout=30)
        except subprocess.TimeoutExpired:
            rows.append({"cmd": name, "help": False, "error": "timeout"})
            failed.append(name)
            continue
        ok = run.returncode == 0
        rows.append({"cmd": name, "help": ok})
        if not ok:
            failed.append(name)
    _out({"checked": len(rows), "ok": len(rows) - len(failed),
          "failed": failed, "commands": rows})
    return 1 if failed else 0


def _cmd_mcp(b, args) -> int:
    if args.mcp_cmd == "serve":
        from .mcp import McpServer
        server = McpServer(backend=b)
        url = server.serve(port=args.port)
        print(f"[mcp] {url}/mcp", file=sys.stderr)
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            server.stop()
        return 0
    from .mcp import McpClient
    client = McpClient(args.url)
    try:
        if args.mcp_cmd == "initialize":
            _out(client.initialize())
        elif args.mcp_cmd == "list":
            _out({"tools": client.list_tools()})
        elif args.mcp_cmd == "call":
            args_json = {}
            try:
                import json as _json
                args_json = _json.loads(args.args or "{}")
                if not isinstance(args_json, dict):
                    raise ValueError
            except ValueError:
                _out({"error": "args must be a JSON object"})
                return 1
            _out({"tool": args.tool, "result": client.call_tool(
                args.tool, args_json)})
        return 0
    except Exception as exc:  # noqa: BLE001
        _out({"error": str(exc)})
        return 1
    finally:
        client.close()


def _cmd_acp(b, args) -> int:
    from .acp import AcpServer, build_acp_factory
    server = AcpServer(backend=b, agent_factory=build_acp_factory(b))
    if args.acp_cmd == "serve":
        url = server.serve(port=args.port, host=args.host)
        print(f"[acp] {url}/acp "
              f"(token={'set' if server.requires_token() else 'not set'})",
              file=sys.stderr)
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            server.stop()
        return 0
    return 1


def _cmd_computer(b, args) -> int:
    from .computer_use import ComputerUse
    computer = ComputerUse()
    if args.computer_cmd == "run":
        _out(computer.run(args.command, timeout=args.timeout))
    elif args.computer_cmd == "shot":
        _out(computer.shot(args.path))
    elif args.computer_cmd == "read":
        _out(computer.read(args.path))
    elif args.computer_cmd == "write":
        _out(computer.write(args.path, args.text))
    return 0


def _cmd_oreo(b, args) -> int:
    import sys as _s
    from .oreo import build as oreo_build
    from .oreo import status as oreo_status
    if args.oreo_cmd == "build":
        _out(oreo_build(args.nl, backend=b,
                        host=args.host, port=args.port))
    elif args.oreo_cmd == "status":
        _out(oreo_status(backend=b))
    elif args.oreo_cmd == "editor":
        from .oreditor import OreoEditor
        ed = OreoEditor(backend=b, build=args.build,
                        host=args.host, port=args.port)
        if args.forever:
            ed.serve_forever(port=args.port, host=args.host)
            return 0
        _out({"ok": True, "build": args.build,
              "url": ed.serve(port=args.port, host=args.host)})
    return 0


def Bridge_peek(platform: str):
    from .bridge import Bridge
    return Bridge(platform, _NullTransport())


class _NullTransport:
    def send(self, chat_id, text):
        return None

    def poll(self, timeout=0.0):
        return None
    def send(self, chat_id, text):
        return None

    def poll(self, timeout=0.0):
        return None


def _cmd_doctor(b, args) -> int:
    from .security import Doctor
    report = Doctor(backend=b).run()
    _out(report)
    return 0 if report["ok"] else 1


def _cmd_security(b, args) -> int:
    from .security import Doctor, OsvScanner
    if args.security_cmd == "osv":
        from .security import OsvScanner, parse_pypi
        packages = None
        if getattr(args, "pkg", None):
            packages = []
            for spec in args.pkg:
                name, _, ver = spec.partition("==")
                if not name or not ver:
                    _out({"error": f"invalid package spec {spec!r} "
                                   "(expected name==version)"})
                    return 1
                packages.append(parse_pypi(name.strip(), ver.strip()))
        result = OsvScanner(packages=packages).scan()
        _out(result)
        return 0 if result["ok"] else 1
    if args.security_cmd == "verify":
        report = Doctor(backend=b).run()
        _out(report)
        return 0 if report["ok"] else 1
    return 1


def _cmd_secrets(b, args) -> int:
    from .secrets import Secrets, SecretsError
    s = Secrets()
    try:
        if args.secrets_cmd == "list":
            _out({"keys": s.list_keys()})
        elif args.secrets_cmd == "status":
            _out({"sources": s.sources_health(), "keys": s.describe()})
        elif args.secrets_cmd == "get":
            _out(s.source_of(args.key))
        elif args.secrets_cmd == "set":
            _out(s.write(args.key, args.value))
        elif args.secrets_cmd == "delete":
            _out(s.delete(args.key))
        return 0
    except SecretsError as exc:
        _out({"error": str(exc)})
        return 1


def _cmd_egress(b, args) -> int:
    if args.egress_cmd == "check":
        from .egress import default_policy
        policy = default_policy()
        _out({"url": args.url, **policy.check(args.url)})
        return 0
    if args.egress_cmd == "serve":
        from .egress import EgressProxy, default_policy
        from .secrets import Secrets
        secrets = Secrets()
        proxy = EgressProxy(default_policy(), secrets.get)
        url = proxy.serve(port=args.port)
        print(f"[egress] proxy {url}", file=sys.stderr)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            proxy.stop()
        return 0
    return 1


def _cmd_llms(b, args) -> int:
    from .config import load_config
    from .llm import (AllProvidersFailed, KNOWN_PROVIDERS, Provider, Router,
                      moa, parse_prompt, providers_from_config)
    from .auth import KeyRing
    from .secrets import Secrets

    cfg = load_config()
    keyring = KeyRing(secrets=Secrets())
    providers = providers_from_config(cfg)

    if args.llms_cmd == "list":
        names = sorted({p.name for p in providers}) or \
            sorted(KNOWN_PROVIDERS)
        rows = keyring.status(names,
                              {p.name: p.api_key for p in providers})
        _out({"providers": rows,
              "configured": [p.describe() for p in providers]})
        return 0

    if args.llms_cmd == "call":
        if getattr(args, "provider", None):
            providers = [p for p in providers
                         if p.name == args.provider] or [
                             _named_provider(args.provider, cfg)]
        router = Router(providers, keyring=keyring, substrate=b)
        try:
            result = router.complete(parse_prompt(args.prompt),
                                     model=getattr(args, "model", None),
                                     temperature=args.temperature)
        except AllProvidersFailed as exc:
            _out({"error": "all providers failed",
                  "attempts": exc.errors})
            return 1
        _out(result)
        return 0

    if args.llms_cmd == "moa":
        wanted = [x.strip() for x in
                  (getattr(args, "providers", "") or "").split(",")
                  if x.strip()]
        if wanted:
            selected = [p for p in providers if p.name in wanted]
            selected += [_named_provider(n, cfg) for n in wanted
                         if not any(p.name == n for p in selected)]
            providers = selected
        if not providers:
            providers = [_named_provider("nvidia", cfg)]
        router = Router(providers, keyring=keyring, substrate=b)
        try:
            result = moa(args.prompt, router,
                         proposers=args.proposers)
        except AllProvidersFailed as exc:
            _out({"error": "mixture-of-agents failed",
                  "attempts": exc.errors})
            return 1
        _out(result)
        return 0
    return 1


def _named_provider(name: str, cfg) -> Provider:
    from .llm import KNOWN_PROVIDERS, Provider
    known = KNOWN_PROVIDERS.get(name, {})
    base = cfg.model.get("base_url") if cfg.model else None
    if name == (cfg.model.get("provider") if cfg.model else None):
        base = cfg.model.get("base_url")
    p = Provider(name=name, base_url=str(base or known.get("base_url", "")),
                 model=str(known.get("model", "")),
                 key_env=str(known.get("key_env", "")))
    return p


def _cmd_auth(b, args) -> int:
    from .config import load_config
    from .auth import AuthProxy, AuthProxyConfig, KeyRing
    from .llm import KNOWN_PROVIDERS, Router, providers_from_config
    from .secrets import Secrets

    cfg = load_config()
    keyring = KeyRing(secrets=Secrets())
    providers = providers_from_config(cfg) or \
        [_named_provider(n, cfg) for n in ("nvidia", "groq", "openrouter")]

    if args.auth_cmd == "status":
        rows = keyring.status([p.name for p in providers],
                              {p.name: p.api_key for p in providers})
        pools = [{"provider": p.name,
                  "pooled_keys": len([k for k in
                                      ("_API_KEY_2", "_API_KEY_3", "_API_KEY_4")
                                      if keyring._env.get(
                                          f"MEM20AGENTZ_"
                                          f"{p.name.upper().replace('-', '_')}"
                                          f"{k}")])}
                 for p in providers]
        _out({"providers": rows, "pools": pools})
        return 0

    if args.auth_cmd == "proxyserve":
        token = None
        env_token = keyring._env.get("MEM20AGENTZ_AUTH_PROXY_TOKEN")
        if env_token:
            token = env_token
        proxy = AuthProxy(Router(providers, keyring=keyring, substrate=b),
                          keyring=keyring,
                          config=AuthProxyConfig(host=args.host,
                                                 port=args.port, token=token))
        url = proxy.serve()
        print(f"[auth] proxy {url} (client sends no provider key "
              f"{'[token-gated]' if token else ''})", file=sys.stderr)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            proxy.stop()
        return 0
    return 1


def _doctor() -> None:
    _cmd_doctor(_backend(), type("_A", (), {"cmd": "doctor"})())
    checks = []
    from .config import load_config
    try:
        cfg = load_config()
        checks.append(("config", "ok", str(cfg.path)))
    except Exception as exc:  # noqa: BLE001
        checks.append(("config", "fail", str(exc)))
    try:
        b = _backend()
        rec = b.recall(topic="self-model", tags=["mem20agentz", "self_model"],
                       k=1)
        checks.append(("memory", "ok", f"{len(rec)} self-model(s)"))
    except BackendSealed as exc:
        checks.append(("memory", "sealed", str(exc)))
    except Exception as exc:  # noqa: BLE001
        checks.append(("memory", "fail", str(exc)))
    _out({"checks": checks})


def _logs(n: Optional[int]) -> None:
    path = _log_path()
    if not path.exists():
        print(f"no log at {path}")
        return
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = lines[-(n or 40):]
    sys.stdout.write("\n".join(tail) + ("\n" if tail else ""))


if __name__ == "__main__":
    raise SystemExit(main())
