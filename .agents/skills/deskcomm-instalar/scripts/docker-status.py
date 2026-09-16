#!/usr/bin/env python3
"""Lista contêineres do host remoto e devolve JSON normalizado.

Evita `docker ps --format '{{...}}'` montado à mão, que o PowerShell via SSH
desfigura. Uso:
  python3 docker-status.py --ssh root@HOST [--ssh-opts "-i chave"] [--project UUID] [--all]
"""
import argparse
import json
import shlex
import subprocess


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ssh", required=True)
    ap.add_argument("--ssh-opts", default="")
    ap.add_argument("--project", default="")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    inner = ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"]
    if args.all:
        inner.append("--all")
    if args.project:
        inner += ["--filter", f"label=com.docker.compose.project={args.project}"]

    cmd = ["ssh"]
    if args.ssh_opts:
        cmd += shlex.split(args.ssh_opts)
    cmd += [args.ssh] + inner

    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        print(json.dumps({"ok": False, "stderr": proc.stderr.decode("utf-8", "replace")}))
        return proc.returncode

    containers = []
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        containers.append({"name": parts[0], "image": parts[1], "status": parts[2]})
    print(json.dumps({"ok": True, "containers": containers}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
