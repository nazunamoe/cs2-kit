# -*- coding: utf-8 -*-
"""Fast-forward the kit branches and report drift between them.

  python tools/sync_branches.py                 # fetch, ff local branches, report drift
  python tools/sync_branches.py --check --json  # no writes; exit 1 on any drift
  python tools/sync_branches.py --branches opencode_work claude

The tool only ever fast-forwards. It never rebases, force-pushes, merges, or pushes.
A branch that is ahead of its remote or has diverged is reported, not rewritten.
Cross-branch drift is the number of commits that exist on one branch but not the other,
which is what happens when a change is committed to one branch and not cherry-picked.
"""
import argparse
import json
import subprocess
import sys

DEFAULT_BRANCHES = ["opencode_work", "claude"]


def git(*args, check=True):
    r = subprocess.run(["git", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise SystemExit("git %s failed:\n%s" % (" ".join(args), (r.stdout + r.stderr).strip()))
    return r


def rev(ref):
    r = git("rev-parse", "--verify", "--quiet", ref, check=False)
    return r.stdout.strip() if r.returncode == 0 else None


def counts(a, b):
    out = git("rev-list", "--left-right", "--count", "%s...%s" % (a, b)).stdout.split()
    return int(out[0]), int(out[1])


def fast_forward(branch, target, current):
    if branch == current:
        git("merge", "--ff-only", target)
    else:
        git("branch", "-f", branch, target)


def subject(ref):
    return git("log", "-1", "--format=%h %s", ref, check=False).stdout.strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--branches", nargs="+", default=DEFAULT_BRANCHES)
    ap.add_argument("--check", action="store_true", help="report only; exit 1 when anything is not in sync")
    ap.add_argument("--no-fetch", action="store_true", help="use the refs already fetched")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if not a.no_fetch:
        git("fetch", a.remote, "--prune")

    current = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    report = {"remote": a.remote, "current": current, "branches": [], "drift": []}
    problems = 0

    for branch in a.branches:
        remote_ref = "%s/%s" % (a.remote, branch)
        local, upstream = rev(branch), rev(remote_ref)
        entry = {"branch": branch,
                 "local": local[:8] if local else None,
                 "remote": upstream[:8] if upstream else None,
                 "subject": subject(branch) if local else None}
        if not local or not upstream:
            entry["status"] = "missing"
            problems += 1
        else:
            ahead, behind = counts(branch, remote_ref)
            entry["ahead"], entry["behind"] = ahead, behind
            if ahead == 0 and behind == 0:
                entry["status"] = "current"
            elif ahead == 0:
                entry["status"] = "behind"
                if a.check:
                    problems += 1
                else:
                    fast_forward(branch, remote_ref, current)
                    entry["status"] = "fast-forwarded"
                    entry["local"] = rev(branch)[:8]
            elif behind == 0:
                entry["status"] = "ahead"
                problems += 1
            else:
                entry["status"] = "diverged"
                problems += 1
        report["branches"].append(entry)

    for i, left in enumerate(a.branches):
        for right in a.branches[i + 1:]:
            if not rev(left) or not rev(right):
                continue
            only_left, only_right = counts(left, right)
            if only_left or only_right:
                report["drift"].append({"left": left, "right": right,
                                        "only_left": only_left, "only_right": only_right})
                if a.check:
                    problems += 1

    report["status"] = "OK" if problems == 0 else "DRIFT"

    if a.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print("[sync] remote %s, current %s" % (a.remote, current))
        for e in report["branches"]:
            extra = ""
            if e.get("ahead") or e.get("behind"):
                extra = "  ahead %d / behind %d" % (e["ahead"], e["behind"])
            print("  %-14s %-15s %s%s" % (e["branch"], e["status"], e.get("local") or "-", extra))
        for d in report["drift"]:
            print("  drift %s <-> %s: %d / %d commits"
                  % (d["left"], d["right"], d["only_left"], d["only_right"]))
        print("[sync] %s" % report["status"])
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
