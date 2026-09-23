#!/usr/bin/env bash
# flyguard — optional watchdog for a long-running paper fly.
#
# systemd (user unit `stonkfly@<name>`, see ops/stonkfly@.service) calls this script;
# it inspects the run once, then execs the fly. When the fly exits, systemd calls it again.
#
# It deliberately stays down (exit 75, systemd will not restart) in these cases:
#   1. the run directory contains a STOP file (Stonkfly's manual stop switch)
#   2. a terminal stop was hit ("Loss stop" / "fee exceeded" / "bankrupt" /
#      "accounting-error" / "Checkpoint integrity") — never auto-cleared
#   3. on the orangex-perp venue, any halt other than "market-outage"
#   4. there are unsettled orders (needs manual reconciliation)
#   5. six restarts in a row produced no new ledger tick (see $OUT/flyguard.state) — a startup
#      failure that writes no halt, or a "market-outage" resume loop that records nothing.
#      Clear it with: rm $OUT/flyguard.state && systemctl --user restart stonkfly@<name>
# Every other halt (network timeout, dropped connection, ...) is resumed with
# --resume-reviewed. Optional Telegram notices: set TG_TOKEN and TG_CHAT in an
# EnvironmentFile that stays OUT of git.
#
# Configuration (environment):
#   STONKFLY_REPO     repository root            (default: parent of this script)
#   STONKFLY_PYTHON   python with stonkfly installed (default: $STONKFLY_REPO/.venv/bin/python)
#   FLY_PRODUCT_<name> product for this fly     (default: BTC-USDC)
#   FLY_VENUE_<name>   venue for this fly       (default: coinbase-spot; orangex-perp = 20x perpetual paper)
#   FLY_OUT_<name>     run directory             (default: runs/<name>)
#   FLY_ARGS          extra `stonkfly run` args, e.g. "--products BTC-USDC"
#
# This script never passes --live.
set -uo pipefail

NAME="${1:?usage: flyguard.sh <name>}"
[[ $NAME =~ ^[A-Za-z0-9_-]+$ ]] || { echo "invalid fly name" >&2; exit 75; }
ROOT="${STONKFLY_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
PY="${STONKFLY_PYTHON:-$ROOT/.venv/bin/python}"
HOLD=75
pv="FLY_PRODUCT_$NAME"; ov="FLY_OUT_$NAME"
PRODUCT="${!pv:-BTC-USDC}"
OUT="${!ov:-runs/$NAME}"
vv="FLY_VENUE_$NAME"
VENUE="${!vv:-coinbase-spot}"

cd "$ROOT" || exit 1
mkdir -p "$OUT"
STATE="$OUT/.flyguard"
mkdir -p "$STATE"
LOG="$OUT/watchdog.log"

say() { echo "[flyguard $(date '+%F %T')] $*" | tee -a "$LOG"; }

# Telegram, at most once per 10 minutes per fly unless the second argument is "force".
notify() {
  local stamp="$STATE/notified" now
  now=$(date +%s)
  if [[ "${2:-}" != force && -f $stamp ]] && (( now - $(cat "$stamp") < 600 )); then
    return
  fi
  echo "$now" >"$stamp"
  [[ -n "${TG_TOKEN:-}" && -n "${TG_CHAT:-}" ]] || return
  TG_MSG="stonkfly-$NAME: $1" python3 -c '
import os, urllib.parse, urllib.request
urllib.request.urlopen(
    "https://api.telegram.org/bot%s/sendMessage" % os.environ["TG_TOKEN"],
    data=urllib.parse.urlencode({"chat_id": os.environ["TG_CHAT"], "text": os.environ["TG_MSG"]}).encode(),
    timeout=20,
)' 2>/dev/null || say "Telegram notice failed"
}

if [[ -e $OUT/STOP ]]; then
  say "$OUT/STOP exists: treated as a manual stop, not restarting"
  notify "STOP file found; staying down. Remove $OUT/STOP, then: systemctl --user start stonkfly@$NAME" force
  exit $HOLD
fi

# If another worker (e.g. started by hand) holds the lock, wait and take over afterwards.
touch "$OUT/worker.lock"
waiting=0
until flock -n "$OUT/worker.lock" true; do
  (( waiting )) || say "another worker holds $OUT/worker.lock; waiting"
  waiting=1
  sleep 10
done

if ! STATUS=$("$PY" - "$OUT/ledger.sqlite" <<'PYEOF'
import json, pathlib, sqlite3, sys
p = pathlib.Path(sys.argv[1])
if not p.exists():
    print(""); print(0); print(0); raise SystemExit
db = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
row = db.execute("SELECT value FROM meta WHERE key='halted'").fetchone()
print((json.loads(row[0]) if row else None) or "")
tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
if "orders" in tables:
    print(db.execute("SELECT COUNT(*) FROM orders WHERE status NOT IN ('SETTLED','REJECTED')").fetchone()[0])
else:
    print(0)
row = db.execute("SELECT value FROM meta WHERE key='tick'").fetchone()
print(json.loads(row[0]) if row else 0)
PYEOF
); then
  say "cannot read ledger; retrying later"
  exit 1
fi
HALTED=$(sed -n 1p <<<"$STATUS")
PENDING=$(sed -n 2p <<<"$STATUS")
TICK=$(sed -n 3p <<<"$STATUS")

# Stall counter. Some failures never reach the ledger — a settings/mode mismatch, the provenance
# gate, a failed seed — so systemd restarts a runner that exits non-zero forever and HALTED stays
# empty. A "market-outage" that auto-resumes into the same outage looks the same from here. If the
# tick has not moved in six starts, stay down and say so instead of looping silently.
STALL_FILE="$OUT/flyguard.state"
LAST_TICK=""; STALLS=0
if [[ -f $STALL_FILE ]]; then
  LAST_TICK=$(sed -n 's/^last_tick=//p' "$STALL_FILE")
  STALLS=$(sed -n 's/^stalls=//p' "$STALL_FILE")
fi
[[ $STALLS =~ ^[0-9]+$ ]] || STALLS=0
if [[ -n $LAST_TICK && $TICK == "$LAST_TICK" ]]; then
  STALLS=$((STALLS + 1))
else
  STALLS=0
fi
printf 'last_tick=%s\nstalls=%s\n' "$TICK" "$STALLS" >"$STALL_FILE"
if (( STALLS >= 6 )); then
  say "6 restarts without a new tick (still tick=$TICK); staying down"
  notify "6 restarts without a new tick (tick=$TICK). Check: journalctl --user -u stonkfly@$NAME. Recover: rm $STALL_FILE && systemctl --user restart stonkfly@$NAME" force
  exit $HOLD
fi

ARGS=()
if [[ -n $HALTED ]]; then
  case "$HALTED" in
    *"Loss stop"*|*"fee exceeded"*|*bankrupt*|*accounting-error*|*"Checkpoint integrity"*)
      say "terminal stop ($HALTED); never cleared automatically"
      notify "Terminal stop: $HALTED. Staying down for manual review." force
      exit $HOLD ;;
  esac
  if [[ $VENUE == orangex-perp && $HALTED != market-outage ]]; then
    say "perp halt ($HALTED) is not a market outage; manual review required"
    notify "Perp halted ($HALTED); manual review required." force
    exit $HOLD
  fi
  if (( PENDING > 0 )); then
    say "halted=$HALTED with $PENDING unsettled orders; manual reconciliation required"
    notify "Halted ($HALTED) with $PENDING unsettled orders; manual reconciliation required." force
    exit $HOLD
  fi
  [[ -f $OUT/error.json ]] && mv "$OUT/error.json" "$STATE/error-$(date +%Y%m%d-%H%M%S).json"
  ARGS=(--resume-reviewed)
  say "previous halt was transient ($HALTED); resuming with --resume-reviewed"
  notify "Resumed automatically after: $HALTED"
fi

say "starting venue=$VENUE product=$PRODUCT -> $OUT ${ARGS[*]}"
# shellcheck disable=SC2086
if [[ $VENUE == orangex-perp ]]; then
  exec "$PY" -m stonkfly run --venue orangex-perp --out "$OUT" ${FLY_ARGS:-} "${ARGS[@]}" >>"$LOG" 2>&1
else
  exec "$PY" -m stonkfly run --products "$PRODUCT" --out "$OUT" ${FLY_ARGS:-} "${ARGS[@]}" >>"$LOG" 2>&1
fi
