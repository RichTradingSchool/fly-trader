# 초파리 트레이딩 챌린지 — Windows 설치 도우미
#
# 1) WSL2 + Ubuntu 24.04 확인 (없으면 설치 명령 실행: 관리자 권한과 재부팅이 필요할 수 있음)
# 2) 우분투 안에 저장소를 받고 install/install.sh 실행
# 3) 바탕화면에 "초파리 방송 보기" 바로가기 생성
# 4) (선택) 7일 무인 운영용 킵얼라이브 작업 등록 (관리자 권한 필요)
#
# 실행: install\windows-setup.cmd 를 더블클릭 (또는 PowerShell에서 이 파일 실행)
param(
    [string]$Repo = "https://github.com/RichTradingSchool/fly-trader.git",
    [string]$Distro = "Ubuntu-24.04",
    [string]$Dir = "fly-trader/stonkfly-dashboard"
)
$ErrorActionPreference = "Stop"
function Step($t) { Write-Host "`n▶ $t" -ForegroundColor Magenta }
function Ok($t) { Write-Host "✓ $t" -ForegroundColor Green }
function Warn($t) { Write-Host "! $t" -ForegroundColor Yellow }

Step "1/4 WSL2 · $Distro 확인"
$wslExe = Get-Command wsl.exe -ErrorAction SilentlyContinue
if (-not $wslExe) { throw "wsl.exe가 없습니다. Windows 10 2004 이상 또는 Windows 11이 필요합니다." }
$list = (& wsl.exe --list --quiet 2>$null) -join "`n"
$list = $list -replace "`0", ""
if ($list -notmatch [regex]::Escape($Distro)) {
    $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $admin) {
        Warn "$Distro 가 없습니다. 이 창을 닫고 install\windows-setup.cmd 를 '관리자 권한으로 실행' 하세요."
        Read-Host "Enter를 누르면 닫힙니다"; exit 1
    }
    Write-Host "$Distro 를 설치합니다. 설치가 끝나면 우분투 창에서 사용자 이름·비밀번호를 만드세요."
    & wsl.exe --install -d $Distro
    Warn "재부팅을 요구하면 재부팅한 뒤, 우분투 사용자를 만든 다음 이 설치 도우미를 다시 실행하세요."
    Read-Host "Enter를 누르면 닫힙니다"; exit 0
}
Ok "$Distro 발견"
$sysd = (& wsl.exe -d $Distro -- bash -lc "systemctl --user show-environment >/dev/null 2>&1 && echo on || echo off") -join ""
if ($sysd -notmatch "on") {
    Warn "우분투에서 systemd가 꺼져 있습니다. 켜는 중(비밀번호를 물을 수 있음)…"
    & wsl.exe -d $Distro -- bash -lc "printf '[boot]\nsystemd=true\n' | sudo tee -a /etc/wsl.conf >/dev/null"
    & wsl.exe --shutdown
    Start-Sleep -Seconds 3
}

Step "2/4 저장소 받기 + 설치 (약 10~30분, 대부분 1.1 GB 데이터 다운로드)"
$cmd = "set -e; mkdir -p ~/fly-trader; if [ -d ~/$Dir/.git ]; then cd ~/$Dir && git pull --ff-only; else git clone $Repo ~/$Dir; fi; cd ~/$Dir && bash install/install.sh"
& wsl.exe -d $Distro -- bash -lc $cmd
if ($LASTEXITCODE -ne 0) { throw "설치가 실패했습니다. 위 메시지를 확인하세요." }
Ok "설치 완료"

Step "3/4 바탕화면 바로가기"
$desk = [Environment]::GetFolderPath("Desktop")
Set-Content -Path (Join-Path $desk "초파리 방송 보기.url") -Encoding ASCII -Value "[InternetShortcut]`r`nURL=http://127.0.0.1:8765/room/`r`n"
Ok "바탕화면에 '초파리 방송 보기' 생성"

Step "4/4 (선택) 7일 무인 운영 — WSL 킵얼라이브"
Write-Host "WSL은 창을 모두 닫으면 몇 초 뒤 우분투를 꺼 버려 초파리도 멈춥니다."
Write-Host "로그온할 때 숨은 WSL 세션 하나를 띄워 두는 예약 작업을 등록할 수 있습니다(관리자 권한 필요)."
$ans = Read-Host "지금 등록할까요? (y/N)"
if ($ans -match '^[yY]') {
    $user = (& wsl.exe -d $Distro -- whoami) -join ""
    $action = New-ScheduledTaskAction -Execute "wsl.exe" -Argument "-d $Distro -u $user --exec sleep infinity"
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet -Hidden -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    try {
        Register-ScheduledTask -TaskName "WSL-Keepalive-fly-trader" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
        Start-ScheduledTask -TaskName "WSL-Keepalive-fly-trader"
        Ok "킵얼라이브 등록 (해제: Unregister-ScheduledTask -TaskName WSL-Keepalive-fly-trader)"
    } catch {
        Warn "등록 실패: 관리자 권한 PowerShell에서 다시 실행하세요. ($($_.Exception.Message))"
    }
}

Write-Host "`n다음 단계 (우분투 창에서):" -ForegroundColor Cyan
Write-Host "  cd ~/$Dir"
Write-Host "  ./fly start s1     # 시즌 시작"
Write-Host "  ./fly open         # 3D 방송 화면"
Write-Host "또는 바탕화면의 '초파리 방송 보기'를 여세요. 절전 모드는 꺼 두세요(설정 > 전원)."
Read-Host "`nEnter를 누르면 닫힙니다"
