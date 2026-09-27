# fly-guard — 시즌 동안 WSL을 살려 두고, 웹 뷰어의 feed.json을 터널 주소에 맞춰 둡니다 (관리자 권한 불필요).
#
#   powershell -ExecutionPolicy Bypass -File ops\windows\fly-guard.ps1 -Install    # 설치 + 지금 시작
#   powershell -ExecutionPolicy Bypass -File ops\windows\fly-guard.ps1 -Uninstall  # 해제(프로세스 종료, 시작 프로그램 삭제)
#   로그: %LOCALAPPDATA%\fly-trader\fly-guard.log
#
# 왜 필요한가: WSL은 마지막 wsl.exe 세션이 닫히면 몇 초 뒤 우분투를 꺼 버리고, 그러면 러너·대시보드·터널이 모두 멈춥니다.
# 가드는 1분마다 숨은 `wsl.exe --exec sleep infinity` 세션이 살아 있는지 보고 없으면 다시 띄웁니다(누가 wsl --shutdown을
# 해도 1분 안에 복구). 같은 루프에서 runs/<run>/public-url.txt 와 GitHub Pages의 feed.json을 비교해 다르면 갱신합니다.
# -Install은 시작 프로그램 폴더에 런처를 두고, 지금 실행하는 가드는 WMI로 띄워 이 창·앱을 닫아도 죽지 않게 합니다.
param(
    [string]$Owner = "RichTradingSchool",
    [string]$Repo = "fly-trader",
    [string]$Distro = "Ubuntu-24.04",
    [string]$User = "han",
    [string]$FromRun = "s1",
    [string]$SeasonDir = "fly-trader/stonkfly-dashboard",
    # Where -Install puts the guard (and where it logs). Any folder every process can see.
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "fly-trader"),
    [switch]$Install,
    [switch]$Uninstall
)
$ErrorActionPreference = "Continue"
$home_ = $InstallDir
$startup = [Environment]::GetFolderPath("Startup")
$vbs = Join-Path $startup "fly-trader-guard.vbs"

function Stop-Guards {
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
        Where-Object { $_.CommandLine -match 'fly-guard\.ps1|set-feed\.ps1' -and $_.ProcessId -ne $PID } |
        ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName Terminate | Out-Null }
}

if ($Uninstall) {
    Stop-Guards
    Remove-Item -Force -ErrorAction SilentlyContinue $vbs
    Write-Host "가드 해제: 시작 프로그램 런처 삭제, 실행 중인 가드 종료 (WSL 세션은 그대로 둠)"
    exit 0
}

if ($Install) {
    New-Item -ItemType Directory -Force $home_ -ErrorAction Stop | Out-Null
    $script = Join-Path $home_ "fly-guard.ps1"
    Copy-Item -Force $MyInvocation.MyCommand.Path $script -ErrorAction Stop
    $cmd = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`" -Owner $Owner -Repo $Repo -Distro $Distro -User $User -FromRun $FromRun -SeasonDir $SeasonDir -InstallDir `"$home_`""
    Set-Content -Path $vbs -Value ('CreateObject("WScript.Shell").Run "' + ($cmd -replace '"', '""') + '", 0, False') -Encoding ASCII -ErrorAction Stop
    # The feed-only watcher is superseded by this guard.
    Get-ChildItem $startup -Filter "fly-trader-feed-*.vbs" -ErrorAction SilentlyContinue | Remove-Item -Force
    Stop-Guards
    # Launch through WMI: the new process is a child of the WMI host, not of this shell, so closing
    # this window or the app that ran it cannot take the guard (and the WSL session) down with it.
    $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = "wscript.exe `"$vbs`"" }
    Write-Host "가드 설치: $vbs (로그온 때 자동 실행), 지금 시작함 (wscript pid $($r.ProcessId))"
    exit 0
}

# ---- the guard loop -------------------------------------------------------------------------------------
$log = Join-Path $PSScriptRoot "fly-guard.log"  # next to the running copy of this script
function Log([string]$m) { Add-Content -Path $log -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" -Encoding UTF8 }
Log "guard launching (pid $PID, parent $((Get-CimInstance Win32_Process -Filter "ProcessId=$PID").ParentProcessId))"
$first = $false
$mutex = [System.Threading.Mutex]::new($true, "Local\fly-trader-guard", [ref]$first)
if (-not $first) { Log "another guard is running; exiting"; exit 0 }  # one guard per logon session

function Read-RunUrl {
    $out = (& wsl.exe -d $Distro -u $User -- cat "/home/$User/$SeasonDir/runs/$FromRun/public-url.txt" 2>$null) -join ""
    return $out.Trim().TrimEnd("/")
}
function Get-RemoteFeed {
    $b64 = (& gh api "repos/$Owner/$Repo/contents/feed.json?ref=gh-pages" --jq ".content" 2>$null) -join ""
    if (-not $b64) { return "" }
    try { return ([string](([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(($b64 -replace '\s', '')))) | ConvertFrom-Json).feed).TrimEnd("/") }
    catch { return "" }
}
function Publish-Feed([string]$feed) {
    $body = [ordered]@{ feed = $feed; updated = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") } | ConvertTo-Json -Compress
    $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($body + "`n"))
    $sha = (& gh api "repos/$Owner/$Repo/contents/feed.json?ref=gh-pages" --jq ".sha" 2>$null)
    $a = @("api", "-X", "PUT", "repos/$Owner/$Repo/contents/feed.json", "-f", "message=feed: $feed", "-f", "content=$b64", "-f", "branch=gh-pages")
    if ($sha) { $a += @("-f", "sha=$sha") }
    & gh @a --jq ".commit.sha" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Log "feed.json -> $feed" } else { Log "feed.json update failed ($LASTEXITCODE)" }
}

Log "guard started (pid $PID)"
$keep = $null
while ($true) {
    if ($null -eq $keep -or $keep.HasExited) {
        if ($null -ne $keep) { Log "keepalive ended (exit $($keep.ExitCode)); starting a new one" }
        $keep = Start-Process -FilePath "wsl.exe" -ArgumentList "-d $Distro -u $User --exec sleep infinity" -WindowStyle Hidden -PassThru
        Log "keepalive started (pid $($keep.Id))"
        Start-Sleep -Seconds 20  # let systemd bring the season units up before looking for the tunnel
    }
    try {
        $local = Read-RunUrl
        if ($local -match '^https://') {
            $remote = Get-RemoteFeed
            if ($local -ne $remote) { Publish-Feed $local }
        }
    } catch { Log "feed check: $($_.Exception.Message)" }
    Start-Sleep -Seconds 60
}
