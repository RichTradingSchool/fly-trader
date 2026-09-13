#!/usr/bin/env bash
# flyguard — optional watchdog for a long-running paper fly.
#
# systemd (user unit `stonkfly@<name>`, see ops/stonkfly@.service) calls this script;
# it inspects the run once, then execs the fly. When the fly exits, systemd calls it again.
#
# It deliberately stays down (exit 75, systemd will not restart) in three cases:
#   1. the run directory contains a STOP file (Stonkfly's manual stop switch)
#   2. a financial stop was hit ("Loss stop" / "fee exceeded") — never auto-cleared
#   3. there are unsettled orders (needs manual reconciliation)
# Every other halt (network timeout, dropped connection, ...) is resumed with
# --resume-reviewed. Optional Telegram notices: set TG_TOKEN and TG_CHAT in an
# EnvironmentFile that stays OUT of git.
#
# Configuration (environment):
#   STONKFLY_REPO     repository root            (default: parent of this script)
#   STONKFLY_PYTHON   python with stonkfly installed (default: $STONKFLY_REPO/.venv/bin/python)
#   FLY_PRODUCT_<name> product for this fly     (default: BTC-USDC)
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

cd "$ROOT" || exit 1
mkdir -p "$OUT"
STATE="$OUT/.flyguard"
mkdir -p "$STATE"
LOG="$OUT.log"

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
    print(""); print(0); raise SystemExit
db = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
row = db.execute("SELECT value FROM meta WHERE key='halted'").fetchone()
print((json.loads(row[0]) if row else None) or "")
print(db.execute("SELECT COUNT(*) FROM orders WHERE status NOT IN ('SETTLED','REJECTED')").fetchone()[0])
PYEOF
); then
  say "cannot read ledger; retrying later"
  exit 1
fi
HALTED=$(sed -n 1p <<<"$STATUS")
PENDING=$(sed -n 2p <<<"$STATUS")

ARGS=()
if [[ -n $HALTED ]]; then
  case "$HALTED" in
    *"Loss stop"*|*"fee exceeded"*)
      say "financial stop ($HALTED); never cleared automatically"
      notify "Financial stop: $HALTED. Staying down for manual review." force
      exit $HOLD ;;
  esac
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

say "starting $PRODUCT -> $OUT ${ARGS[*]}"
# shellcheck disable=SC2086
exec "$PY" -m stonkfly run --products "$PRODUCT" --out "$OUT" ${FLY_ARGS:-} "${ARGS[@]}" >>"$LOG" 2>&1
