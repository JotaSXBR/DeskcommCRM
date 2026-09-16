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
    print(json.dumps({"ok": r["ok"], "containers": rows}))


if __name__ == "__main__":
    main()
