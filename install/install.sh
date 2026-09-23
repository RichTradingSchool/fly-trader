#!/usr/bin/env bash
# 초파리 트레이딩 챌린지 설치 — Ubuntu 22.04/24.04 (Windows는 WSL2 안에서)
#
#   bash install/install.sh                 # 전체 설치
#   bash install/install.sh --data-from DIR # 이미 받아 둔 data/ 폴더를 재사용(1.1 GB 다운로드 생략)
#   bash install/install.sh --no-units      # systemd 유닛 설치 생략
#
# 하는 일: 시스템 패키지(컴파일러) → 파이썬 3.11 가상환경 → 뇌 연결 지도 데이터 다운로드·검증
#          → 가짜 시장 3틱으로 신경 커널 빌드·동작 확인 → systemd 사용자 유닛 설치
set -euo pipefail
REPO="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
cd "$REPO"
DATA_FROM=""; UNITS=1
while [ $# -gt 0 ]; do
  case "$1" in
    --data-from) DATA_FROM=$2; shift 2 ;;
    --no-units) UNITS=0; shift ;;
    *) echo "알 수 없는 옵션: $1" >&2; exit 2 ;;
  esac
done
step() { printf '\n\033[1;35m▶ %s\033[0m\n' "$*"; }
ok() { printf '\033[32m✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[33m! %s\033[0m\n' "$*"; }
t0=$(date +%s)

step "1/6 시스템 확인"
[ -f /etc/os-release ] && . /etc/os-release && echo "OS: ${PRETTY_NAME:-unknown} · CPU $(nproc)코어 · RAM $(free -g | awk '/Mem:/{print $2}') GB"
avail=$(df -Pk "$REPO" | awk 'NR==2{print int($4/1048576)}')
[ "${avail:-0}" -ge 5 ] || warn "여유 디스크가 ${avail} GB입니다. 5 GB 이상 권장"
grep -qi microsoft /proc/version 2>/dev/null && ok "WSL2에서 실행 중"

step "2/6 시스템 패키지 (컴파일러·git·curl)"
need=()
for p in build-essential git curl ca-certificates; do dpkg -s "$p" >/dev/null 2>&1 || need+=("$p"); done
if [ ${#need[@]} -gt 0 ]; then
  echo "설치: ${need[*]} (sudo 비밀번호를 물을 수 있습니다)"
  sudo apt-get update -y && sudo apt-get install -y "${need[@]}"
fi
dpkg -s util-linux-extra >/dev/null 2>&1 || sudo apt-get install -y util-linux-extra >/dev/null 2>&1 || true
ok "g++ $(g++ -dumpversion)"

step "3/6 파이썬 3.11 가상환경 (.venv)"
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null; then
  echo "uv(파이썬 설치 도구)를 설치합니다: https://astral.sh/uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
uv python install 3.11 >/dev/null
[ -x .venv/bin/python ] || uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -e '.[test]'
ok "$(.venv/bin/python --version)"

step "4/6 초파리 뇌 연결 지도 (MaleCNS v1.0, 약 1.1 GB · 한 번만)"
if [ -n "$DATA_FROM" ]; then
  [ -f "$DATA_FROM/graph.npz" ] || { echo "$DATA_FROM 에 graph.npz가 없습니다" >&2; exit 1; }
  [ -e data ] || ln -s "$(readlink -f "$DATA_FROM")" data
  ok "기존 데이터 연결: $DATA_FROM"
elif [ -f data/graph.npz ]; then
  ok "이미 받아 둔 데이터가 있습니다"
else
  .venv/bin/python -m stonkfly prepare
fi
.venv/bin/python -m stonkfly verify >/dev/null && ok "데이터 체크섬 검증 통과"

step "5/6 동작 확인 — 가짜 시장 3틱 (신경 커널 첫 빌드 포함, 1~3분)"
rm -rf runs/install-check
.venv/bin/python -m stonkfly run --venue orangex-perp --fixture --fast --steps 3 --out runs/install-check >/tmp/fly-install-check.log 2>&1 \
  || { tail -30 /tmp/fly-install-check.log; echo "동작 확인 실패 — 위 로그를 확인하세요" >&2; exit 1; }
n=$(wc -l < runs/install-check/events.jsonl)
ok "관측 ${n}회 기록 (runs/install-check)"
echo "대시보드용 뉴런 좌표 캐시를 만듭니다(약 1분)…"
PORT=8799 timeout 240 .venv/bin/python - <<'PY' || warn "대시보드 캐시는 첫 실행 때 만들어집니다"
import os, subprocess, sys, time, urllib.request
p = subprocess.Popen([sys.executable, "dashboard/server.py", "runs/install-check"], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
try:
    for _ in range(220):
        try:
            urllib.request.urlopen("http://127.0.0.1:8799/tick.json", timeout=2); print("dashboard OK"); break
        except Exception:
            time.sleep(1)
finally:
    p.terminate()
PY

step "6/6 운영 도구"
chmod +x fly ops/flyguard.sh
if [ "$UNITS" = 1 ] && systemctl --user show-environment >/dev/null 2>&1; then
  ./fly units
else
  warn "systemd 유닛은 건너뜁니다(나중에 ./fly units). ./fly start 는 백그라운드 실행으로 동작합니다"
fi

printf '\n\033[1;32m설치 완료 (%s초)\033[0m\n' "$(( $(date +%s) - t0 ))"
cat <<'EOF'

다음 단계
  ./fly start s1      시즌 s1 시작 (OrangeX BTC 무기한 공개 시세 · 1,000 USDT · 20배 · 페이퍼)
  ./fly open          3D 방송 화면 열기  →  http://127.0.0.1:8765/room/
  ./fly status        순자산·포지션 확인
  ./fly stop s1       정지 (기록 보존)

초파리 이름·자금은 시즌 시작 전에 ~/.config/stonkfly/s1.env 에서 바꿀 수 있습니다.
EOF
