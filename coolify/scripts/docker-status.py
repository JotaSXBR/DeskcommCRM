#!/usr/bin/env python3
"""Inventário brownfield read-only. Nunca destrói. Stdlib only.
Uso: python3 docker-status.py --ssh root@IP [--all]"""
import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from remote import run_lines  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ssh", required=True)
    p.add_argument("--all", action="store_true")
    a = p.parse_args()
    flag = "-a" if a.all else ""
    r = run_lines(a.ssh, "docker ps %s --format '{{.Names}}|{{.Image}}|{{.Status}}'" % flag)
    rows = [l for l in (r["stdout"] or "").splitlines() if l.strip()]
    out = {"ok": r["ok"], "containers": rows}
    m = run_lines(a.ssh, "free -m | awk '/^Mem:/{print $7}'")
    d = run_lines(a.ssh, "df -m / | awk 'NR==2{print $4}'")
    try:
        out["ram_mb_free"] = int((m["stdout"] or "").strip().split("\n")[-1])
    except (ValueError, IndexError):
        out["ram_mb_free"] = -1
    try:
        out["disk_mb_free"] = int((d["stdout"] or "").strip().split("\n")[-1])
    except (ValueError, IndexError):
        out["disk_mb_free"] = -1
    out["warnings"] = []
    if out["ram_mb_free"] != -1 and out["ram_mb_free"] < 3300:
        out["warnings"].append("ram_baixa")
    if out["disk_mb_free"] != -1 and out["disk_mb_free"] < 20480:
        out["warnings"].append("disco_baixo")
    print(json.dumps(out))


if __name__ == "__main__":
    main()
