#!/usr/bin/env python3
"""Roda um arquivo de script no host remoto via SSH, byte a byte via stdin.

O shell local só orquestra; o payload mora no arquivo, nunca no argv.
Uso:
  python3 remote.py --ssh root@HOST --script-file x.sh
  python3 remote.py --ssh root@HOST --in-container db --exec "psql -U u -d d -v ON_ERROR_STOP=1" --script-file q.sql --capture
"""
import argparse
import shlex
import subprocess
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ssh", required=True)
    ap.add_argument("--script-file", required=True)
    ap.add_argument("--ssh-opts", default="")
    ap.add_argument("--in-container", default="")
    ap.add_argument("--exec", default="bash -s")
    ap.add_argument("--capture", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.script_file, "rb") as f:
        payload = f.read()

    cmd = ["ssh"]
    if args.ssh_opts:
        cmd += shlex.split(args.ssh_opts)
    if args.in_container:
        remote = ["docker", "exec", "-i", args.in_container] + shlex.split(args.exec)
    else:
        remote = ["bash", "-s"]
    # Um único argumento remoto (ver docker-status.py): o ssh junta argv com
    # espaços e o shell remoto repartiria valores com espaços/TABs/aspas.
    cmd += [args.ssh, shlex.join(remote)]

    if args.dry_run:
        print(" ".join(shlex.quote(c) for c in cmd) + " < " + args.script_file)
        return 0

    proc = subprocess.run(cmd, input=payload, capture_output=args.capture)
    if args.capture:
        sys.stdout.write(proc.stdout.decode("utf-8", "replace"))
        sys.stderr.write(proc.stderr.decode("utf-8", "replace"))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
