#!/usr/bin/env python3
"""Tổng hợp log trong out/ thành báo cáo JSON và gửi về n8n (Wait node resume URL)."""
import json
import os
import re
import sys
import urllib.request

WS = os.environ.get("GITHUB_WORKSPACE", ".")
OUT = os.path.join(WS, "out")
REQ_RE = re.compile(r"\[((?:R|F)\d+)\]")
ANALYZE_RES = [
    # flutter analyze:  error • message • lib/a.dart:1:2 • code
    re.compile(r"^\s*(error|warning|info)\s+•\s+(.*?)\s+•\s+(\S+:\d+:\d+)\s+•\s+(\S+)\s*$"),
    # dart analyze:     error - lib/a.dart:1:2 - message - code
    re.compile(r"^\s*(error|warning|info)\s+-\s+(\S+:\d+:\d+)\s+-\s+(.*?)\s+-\s+(\S+)\s*$"),
]


def read(name, default=""):
    try:
        with open(os.path.join(OUT, name), encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return default


def code(name):
    try:
        return int(read(name, "").strip())
    except ValueError:
        return None


def tail(text, n=40, limit=4000):
    lines = [l for l in text.splitlines() if l.strip()]
    return "\n".join(lines[-n:])[-limit:]


def parse_analyze(text):
    issues = []
    for line in text.splitlines():
        for i, rx in enumerate(ANALYZE_RES):
            m = rx.match(line)
            if not m:
                continue
            if i == 0:
                sev, msg, loc, rule = m.groups()
            else:
                sev, loc, msg, rule = m.groups()
            issues.append({"severity": sev, "message": msg, "location": loc, "code": rule})
            break
    count = lambda s: sum(1 for x in issues if x["severity"] == s)
    order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda x: order.get(x["severity"], 3))
    return {"errors": count("error"), "warnings": count("warning"), "infos": count("info"), "issues": issues[:60]}


def parse_tests(jsonl):
    tests, errors, results = {}, {}, {}
    suites = {}
    for line in jsonl.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        t = ev.get("type")
        if t == "suite":
            s = ev.get("suite", {})
            suites[s.get("id")] = s.get("path", "")
        elif t == "testStart":
            te = ev.get("test", {})
            tests[te.get("id")] = {"name": te.get("name", ""), "suite": suites.get(te.get("suiteID"), "")}
        elif t == "error":
            errors.setdefault(ev.get("testID"), []).append(str(ev.get("error", ""))[:1500])
        elif t == "testDone":
            results[ev.get("testID")] = ev
    total = passed = failed = skipped = 0
    failures, by_req = [], {}
    for tid, ev in results.items():
        info = tests.get(tid, {"name": "?", "suite": ""})
        name = info["name"]
        is_loading = name.startswith("loading ")
        if ev.get("hidden") and ev.get("result") == "success":
            continue
        if ev.get("skipped"):
            skipped += 1
            continue
        if is_loading and ev.get("result") == "success":
            continue
        total += 1
        ok = ev.get("result") == "success"
        m = REQ_RE.search(name)
        req = m.group(1) if m else "?"
        by_req.setdefault(req, {"passed": 0, "failed": 0})
        if ok:
            passed += 1
            by_req[req]["passed"] += 1
        else:
            failed += 1
            by_req[req]["failed"] += 1
            file = os.path.relpath(info["suite"], os.path.join(WS, "app")) if info["suite"] else ""
            label = ("Lỗi biên dịch/nạp file test: " + file) if is_loading else name
            failures.append({"name": label, "file": file, "error": "\n".join(errors.get(tid, []))[:1500]})
    return {"total": total, "passed": passed, "failed": failed, "skipped": skipped,
            "byRequirement": by_req, "failures": failures[:40]}


def main():
    run_key = os.environ.get("RUN_KEY", "")
    rnd = os.environ.get("ROUND", "")
    deploy_ok = os.environ.get("DEPLOY_OUTCOME") == "success"
    checkout_ok = os.environ.get("CHECKOUT_OUTCOME", "success") == "success"

    pub_code = code("pub.code")
    analyze = parse_analyze(read("analyze.log"))
    tests = parse_tests(read("test.jsonl"))
    if tests["total"] == 0 and read("test.err").strip():
        tests["stderr"] = tail(read("test.err"), 30)
    try:
        arch = json.loads(read("arch.json", "{}") or "{}")
    except ValueError:
        arch = {"issues": ["Không chạy được kiểm tra kiến trúc: " + tail(read("arch.err"), 5)], "warnings": [], "features": []}
    fmt_changed = [l.replace("Changed ", "").strip() for l in read("format.log").splitlines() if l.startswith("Changed ")]
    build_code = code("build.code")

    report = {
        "runKey": run_key,
        "round": rnd,
        "branch": os.environ.get("BRANCH", ""),
        "runUrl": os.environ.get("RUN_URL", ""),
        "flutterVersion": (read("version.log").splitlines() or [""])[0],
        "checkoutOk": checkout_ok,
        "pub": {"ok": pub_code == 0, "log": "" if pub_code == 0 else tail(read("pub.log"), 30)},
        "analyze": analyze,
        "format": {"changed": fmt_changed[:30]},
        "tests": tests,
        "architecture": {"issues": arch.get("issues", []), "warnings": arch.get("warnings", []), "features": arch.get("features", [])},
        "build": {"ok": build_code == 0, "log": "" if build_code == 0 else tail(read("build.log"), 40)},
        "deployOk": deploy_ok,
        "previewUrl": f"{os.environ.get('PAGES_BASE', '')}/{run_key}/r{rnd}/" if deploy_ok else "",
    }
    body = json.dumps(report, ensure_ascii=False).encode("utf-8")
    with open(os.path.join(WS, "report.json"), "wb") as fh:
        fh.write(body)

    url = os.environ.get("CALLBACK_URL", "")
    if not url:
        print("Không có CALLBACK_URL – bỏ qua gửi báo cáo")
        return 0
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                print("Đã gửi báo cáo, HTTP", resp.status)
                return 0
        except Exception as exc:  # noqa: BLE001
            print("Gửi báo cáo lỗi (lần", attempt + 1, "):", type(exc).__name__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
