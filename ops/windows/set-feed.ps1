# 웹 뷰어가 읽을 공개 대시보드 주소(feed.json)를 GitHub Pages에 반영합니다 (gh CLI 로그인 필요).
#
#   ... set-feed.ps1 -Owner <계정> -Url https://xxxx.trycloudflare.com   # 주소를 직접 지정
#   ... set-feed.ps1 -Owner <계정> -FromRun s1                           # WSL의 runs/s1/public-url.txt에서 읽기
#   ... set-feed.ps1 -Owner <계정> -FromRun s1 -Watch                    # 1분마다 확인, 바뀌면 반영(계속 실행)
#   ... set-feed.ps1 -Owner <계정> -FromRun s1 -Register                 # 위 -Watch를 로그온 시 숨김 실행으로 등록
#
# 퀵 터널 주소는 PC가 재부팅되거나 터널이 다시 시작되면 바뀝니다. -Watch가 그때마다 따라갑니다.
param(
    [Parameter(Mandatory = $true)][string]$Owner,
    [string]$Repo = "fly-trader",
    [string]$Url = "",
    [string]$FromRun = "",
    [switch]$Watch,
    [switch]$Register,
    [string]$Distro = "Ubuntu-24.04",
    [string]$RepoDir = "fly-trader/stonkfly-dashboard"
)
$ErrorActionPreference = "Stop"

function Read-RunUrl {
    $out = (& wsl.exe -d $Distro -- bash -lc "cat ~/$RepoDir/runs/$FromRun/public-url.txt 2>/dev/null") -join ""
    return $out.Trim()
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
    Write-Host "$(Get-Date -Format 'HH:mm:ss') feed.json → $feed" -ForegroundColor Green
}

if ($Register) {
    if (-not $FromRun) { throw "-Register에는 -FromRun이 필요합니다" }
    $self = $MyInvocation.MyCommand.Path
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$self`" -Owner $Owner -Repo $Repo -FromRun $FromRun -Watch"
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet -Hidden -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName "fly-trader-feed-$FromRun" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName "fly-trader-feed-$FromRun"
    Write-Host "등록: fly-trader-feed-$FromRun (해제: Unregister-ScheduledTask -TaskName fly-trader-feed-$FromRun)" -ForegroundColor Green
    exit 0
}

if ($Url) { Publish-Feed $Url; exit 0 }
if (-not $FromRun) { throw "-Url 또는 -FromRun 중 하나를 지정하세요" }
$last = ""
do {
    try {
        $u = Read-RunUrl
        if ($u -and $u -ne $last) { Publish-Feed $u; $last = $u }
    } catch { Write-Warning $_.Exception.Message }
    if ($Watch) { Start-Sleep -Seconds 60 }
} while ($Watch)
