"""Expose the read-only dashboard to the internet and record the public address.

    python ops/tunnel/tunnel.py runs/s1 [--port 8765] [--cloudflared PATH] [--hook CMD]

Quick tunnel (default, no account): runs `cloudflared tunnel --url http://127.0.0.1:<port>`,
reads the https://<random>.trycloudflare.com address from its log and writes it to
<run>/public-url.txt. The address changes whenever cloudflared restarts, so after every new
address the optional --hook command runs with the address as its last argument (for example a
script that updates feed.json on the web viewer). cloudflared is restarted if it exits.

Fixed address (Cloudflare account + your own domain): set PUBLIC_URL=https://fly.example.com
and TUNNEL_NAME=<named tunnel> (created with `cloudflared tunnel create`, routed with
`cloudflared tunnel route dns`). The script then runs `cloudflared tunnel run <name>` and
records PUBLIC_URL instead.

Only the dashboard's GET routes are reachable (the server refuses every other method), and
everything it serves is the public paper-trading state.
"""

import argparse
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

QUICK_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def record(run, url, hook):
    path = Path(run) / "public-url.txt"
    old = path.read_text().strip() if path.exists() else ""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(url + "\n")
    os.replace(tmp, path)
    print(f"[tunnel] public address: {url}", flush=True)
    if hook and url != old:
        try:
            subprocess.run(shlex.split(hook) + [url], timeout=120, check=False)
        except (OSError, subprocess.SubprocessError) as err:
            print(f"[tunnel] hook failed: {err}", flush=True)


def run_once(args):
    named = os.environ.get("TUNNEL_NAME")
    fixed = os.environ.get("PUBLIC_URL")
    base = [args.cloudflared, "tunnel", "--no-autoupdate", "--protocol", args.protocol]
    cmd = base + (["run", named] if named else ["--url", f"http://127.0.0.1:{args.port}"])
    print(f"[tunnel] starting: {' '.join(cmd)}", flush=True)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    if named and fixed:
        record(args.run, fixed.rstrip("/"), args.hook)
    found = bool(named and fixed)
    for line in proc.stdout:
        sys.stdout.write(line)
        if not found:
            m = QUICK_URL.search(line)
            if m:
                found = True
                record(args.run, m.group(0), args.hook)
    return proc.wait()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("run", help="run directory, e.g. runs/s1 (public-url.txt is written here)")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    p.add_argument("--cloudflared", default=os.environ.get("CLOUDFLARED", "cloudflared"))
    # http2 goes out over TCP 443, which works behind WSL2 NAT and most firewalls (QUIC needs UDP 7844).
    p.add_argument("--protocol", default=os.environ.get("TUNNEL_PROTOCOL", "http2"))
    p.add_argument("--hook", default=os.environ.get("TUNNEL_HOOK", ""),
                   help="command run with the new public address as its last argument")
    args = p.parse_args()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set() or sys.exit(0))
    delay = 5
    while not stop.is_set():
        started = time.monotonic()
        try:
            code = run_once(args)
        except FileNotFoundError:
            sys.exit(f"cloudflared not found ({args.cloudflared}). Install it first: see docs/publish-ko.md")
        print(f"[tunnel] cloudflared exited with {code}; restarting in {delay}s", flush=True)
        time.sleep(delay)
        delay = 5 if time.monotonic() - started > 300 else min(delay * 2, 300)


if __name__ == "__main__":
    main()
