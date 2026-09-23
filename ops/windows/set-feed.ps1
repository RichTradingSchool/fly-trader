# 웹 뷰어가 읽을 공개 대시보드 주소(feed.json)를 GitHub Pages에 반영합니다 (gh CLI 로그인 필요).
#
#   ... set-feed.ps1 -Owner <계정> -Url https://xxxx.trycloudflare.com   # 주소를 직접 지정
#   ... set-feed.ps1 -Owner <계정> -FromRun s1                           # WSL의 runs/s1/public-url.txt에서 읽어 한 번 반영
#   ... set-feed.ps1 -Owner <계정> -FromRun s1 -Watch                    # 1분마다 비교해 다르면 반영(계속 실행)
#   ... set-feed.ps1 -Owner <계정> -FromRun s1 -Startup                  # -Watch를 로그온 때 숨김 실행(관리자 권한 불필요)
#   ... set-feed.ps1 -Owner <계정> -FromRun s1 -Register                 # 같은 일을 작업 스케줄러로(관리자 권한 필요할 수 있음)
#
# 퀵 터널 주소는 PC가 재부팅되거나 터널이 다시 시작되면 바뀝니다. -Watch가 그때마다 따라갑니다.
# -Startup 해제: 시작 프로그램 폴더의 fly-trader-feed-<run>.vbs 삭제
param(
    [Parameter(Mandatory = $true)][string]$Owner,
    [string]$Repo = "fly-trader",
    [string]$Url = "",
    [string]$FromRun = "",
    [switch]$Watch,
    [switch]$Startup,
    [switch]$Register,
    [string]$Distro = "Ubuntu-24.04",
    [string]$SeasonDir = "fly-trader/stonkfly-dashboard"
)
# Native tools (gh, git, wsl) write progress to stderr; with "Stop" PowerShell 5.1 would turn that into
# a terminating error, so failures are checked through $LASTEXITCODE instead.
$ErrorActionPreference = "Continue"

function Read-RunUrl {
    $out = (& wsl.exe -d $Distro -- bash -lc "cat ~/$SeasonDir/runs/$FromRun/public-url.txt 2>/dev/null") -join ""
    return $out.Trim().TrimEnd("/")
}

function Get-RemoteFeed {
    $b64 = (& gh api "repos/$Owner/$Repo/contents/feed.json?ref=gh-pages" --jq ".content" 2>$null) -join ""
    if (-not $b64) { return "" }
    try {
        $json = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(($b64 -replace '\s', ''))) | ConvertFrom-Json
        return ([string]$json.feed).TrimEnd("/")
    } catch { return "" }
}

function Publish-Feed([string]$feed) {
    $feed = $feed.TrimEnd("/")
    if ($feed -notmatch '^https://') { throw "https:// 주소가 필요합니다: $feed" }
    $body = [ordered]@{ feed = $feed; updated = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") } | ConvertTo-Json -Compress
    $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($body + "`n"))
    $sha = (& gh api "repos/$Owner/$Repo/contents/feed.json?ref=gh-pages" --jq ".sha" 2>$null)
    $a = @("api", "-X", "PUT", "repos/$Owner/$Repo/contents/feed.json", "-f", "message=feed: $feed", "-f", "content=$b64", "-f", "branch=gh-pages")
    if ($sha) { $a += @("-f", "sha=$sha") }
    & gh @a --jq ".commit.sha" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "feed.json 업데이트 실패" }
    Write-Host "$(Get-Date -Format 'MM-dd HH:mm:ss') feed.json → $feed" -ForegroundColor Green
}

if ($Startup -or $Register) {
    if (-not $FromRun) { throw "-Startup/-Register에는 -FromRun이 필요합니다" }
    # Keep a copy outside WSL so the logon launcher does not depend on a \\wsl.localhost path.
    $home_ = Join-Path $env:LOCALAPPDATA "fly-trader"
    New-Item -ItemType Directory -Force $home_ -ErrorAction Stop | Out-Null
    $script = Join-Path $home_ "set-feed.ps1"
    Copy-Item -Force $MyInvocation.MyCommand.Path $script -ErrorAction Stop
    $cmd = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`" -Owner $Owner -Repo $Repo -FromRun $FromRun -Distro $Distro -SeasonDir $SeasonDir -Watch"
    if ($Register) {
        $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ($cmd -replace '^powershell\.exe ', '')
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        $settings = New-ScheduledTaskSettingsSet -Hidden -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
        Register-ScheduledTask -TaskName "fly-trader-feed-$FromRun" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
        Start-ScheduledTask -TaskName "fly-trader-feed-$FromRun"
        Write-Host "등록: 작업 스케줄러 fly-trader-feed-$FromRun" -ForegroundColor Green
    } else {
        $vbs = Join-Path ([Environment]::GetFolderPath("Startup")) "fly-trader-feed-$FromRun.vbs"
        $line = 'CreateObject("WScript.Shell").Run "' + ($cmd -replace '"', '""') + '", 0, False'
        Set-Content -Path $vbs -Value $line -Encoding ASCII -ErrorAction Stop
        Start-Process -FilePath "wscript.exe" -ArgumentList "`"$vbs`""
        Write-Host "등록: $vbs (로그온 때 자동 실행, 지금도 시작함)" -ForegroundColor Green
    }
    exit 0
}

if ($Url) { Publish-Feed $Url; exit 0 }
if (-not $FromRun) { throw "-Url 또는 -FromRun 중 하나를 지정하세요" }
do {
    try {
        $local = Read-RunUrl
        if ($local) {
            $remote = Get-RemoteFeed
            if ($local -ne $remote) { Publish-Feed $local }
        }
    } catch { Write-Warning $_.Exception.Message }
    if ($Watch) { Start-Sleep -Seconds 60 }
} while ($Watch)
