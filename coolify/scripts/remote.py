#!/usr/bin/env python3
"""Dono do payload remoto. O shell só orquestra, nunca carrega código.
Escreva o script num arquivo e rode apontando para ele. Stdlib only."""
import subprocess
import tempfile
import os


def run_script_file(ssh, script_text):
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, encoding="utf-8", newline="\n") as f:
        f.write(script_text)
        path = f.name
    try:
        with open(path, "rb") as fh:
            p = subprocess.run(["ssh", "-o", "BatchMode=yes",
                                "-o", "StrictHostKeyChecking=accept-new",
                                ssh, "bash -s"],
                               stdin=fh, capture_output=True, timeout=600)
        return {"ok": p.returncode == 0, "exit_code": p.returncode,
                "stdout": p.stdout.decode("utf-8", "replace"),
                "stderr": p.stderr.decode("utf-8", "replace")}
    finally:
        os.unlink(path)


def run_lines(ssh, oneliner):
    p = subprocess.run(["ssh", "-o", "BatchMode=yes",
                        "-o", "StrictHostKeyChecking=accept-new",
                        ssh, oneliner], capture_output=True, timeout=120)
    return {"ok": p.returncode == 0, "exit_code": p.returncode,
            "stdout": p.stdout.decode("utf-8", "replace"),
            "stderr": p.stderr.decode("utf-8", "replace")}


def run_stdin_file(ssh, remote_cmd, stdin_path, timeout=600):
    """Roda remote_cmd na VPS com o arquivo local como stdin (ex.: .sql no psql).
    Segredo (URL) vai só na linha de comando remota, nunca no output."""
    with open(stdin_path, "rb") as fh:
        p = subprocess.run(["ssh", "-o", "BatchMode=yes",
                            "-o", "StrictHostKeyChecking=accept-new",
                            ssh, remote_cmd],
                           stdin=fh, capture_output=True, timeout=timeout)
    return {"ok": p.returncode == 0, "exit_code": p.returncode,
            "stdout": p.stdout.decode("utf-8", "replace"),
            "stderr": p.stderr.decode("utf-8", "replace")}
