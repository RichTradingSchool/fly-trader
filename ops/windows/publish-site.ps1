# 웹 뷰어를 GitHub Pages에 올립니다 (gh CLI 로그인 필요: gh auth login).
#
#   powershell -ExecutionPolicy Bypass -File ops\windows\publish-site.ps1 -Owner <깃허브 계정> [-Repo fly-trader]
#   옵션: -Feed https://xxxx.trycloudflare.com   공개 대시보드 주소 (생략하면 WSL의 runs/<FeedRun>/public-url.txt)
#         -Guide /home/<you>/…/guide.pdf         사이트에 함께 올릴 PDF (생략하면 저장소의 docs/guide-ko.pdf가 있으면 사용)
#         -RefUrl https://…                      랜딩 페이지에 거래소 가입 링크를 넣을 때만
#         커뮤니티 링크·사이트 주소 기본값은 ops/site/site.json
#
# 1) WSL에서 site/ 빌드  2) gh-pages 브랜치로 강제 푸시  3) Pages 켜기
# 결과 주소: https://<owner>.github.io/<repo>/
param(
    [Parameter(Mandatory = $true)][string]$Owner,
    [string]$Repo = "fly-trader",
    [string]$Feed = "",
    [string]$FeedRun = "s1",
    [string]$Guide = "",
    [string]$RefUrl = "",
    [string]$Distro = "Ubuntu-24.04",
    [string]$RepoDir = "fly-trader/stonkfly-dashboard",
    [string]$SeasonDir = "fly-trader/stonkfly-dashboard"
)
# Native tools (gh, git, wsl) write progress to stderr; with "Stop" PowerShell 5.1 would turn that into
# a terminating error, so failures are checked through $LASTEXITCODE instead.
$ErrorActionPreference = "Continue"
$siteUrl = "https://$($Owner.ToLower()).github.io/$Repo/"
$repoUrl = "https://github.com/$Owner/$Repo"
& gh auth status 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw "gh CLI 로그인이 필요합니다: gh auth login" }

if (-not $Feed) {
    $Feed = ((& wsl.exe -d $Distro -- bash -lc "cat ~/$SeasonDir/runs/$FeedRun/public-url.txt 2>/dev/null") -join "").Trim()
    if ($Feed) { Write-Host "공개 대시보드 주소: $Feed" } else { Write-Host "공개 주소가 없어 데모로 올립니다 (나중에 set-feed.ps1)" -ForegroundColor Yellow }
}
if (-not $Guide) {
    $has = ((& wsl.exe -d $Distro -- bash -lc "test -f ~/$RepoDir/docs/guide-ko.pdf && echo yes") -join "").Trim()
    if ($has -eq "yes") { $Guide = "docs/guide-ko.pdf" }
}

Write-Host "▶ 1/3 사이트 빌드 (WSL)" -ForegroundColor Magenta
$siteArgs = "--out site --repo-url $repoUrl --site-url $siteUrl --run ~/$SeasonDir/runs/$FeedRun"
if ($Feed) { $siteArgs += " --feed $Feed" }
if ($Guide) { $siteArgs += " --guide $Guide" }
if ($RefUrl) { $siteArgs += " --ref-url $RefUrl" }
& wsl.exe -d $Distro -- bash -lc "cd ~/$RepoDir && .venv/bin/python ops/site/build_site.py $siteArgs"
if ($LASTEXITCODE -ne 0) { throw "사이트 빌드 실패" }
$user = ((& wsl.exe -d $Distro -- whoami) -join "").Trim()
$src = "\\wsl.localhost\$Distro\home\$user\$($RepoDir -replace '/', '\')\site"

Write-Host "▶ 2/3 gh-pages 브랜치로 올리기" -ForegroundColor Magenta
$tmp = Join-Path $env:TEMP "fly-site-publish"
if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp -ErrorAction Stop }
Copy-Item -Recurse $src $tmp -ErrorAction Stop
Push-Location $tmp
try {
    git init -q -b gh-pages
    git -c core.autocrlf=false add -A
    git -c user.name="fly-trader" -c user.email="fly-trader@users.noreply.github.com" commit -q -m "web viewer $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    git push -f "$repoUrl.git" gh-pages
    if ($LASTEXITCODE -ne 0) { throw "푸시 실패: 저장소가 있는지 확인하세요 (gh repo create $Owner/$Repo --public)" }
} finally { Pop-Location }

Write-Host "▶ 3/3 GitHub Pages 켜기" -ForegroundColor Magenta
& gh api "repos/$Owner/$Repo/pages" --silent 2>$null
if ($LASTEXITCODE -ne 0) {
    & gh api -X POST "repos/$Owner/$Repo/pages" -f "source[branch]=gh-pages" -f "source[path]=/" --silent
}
Write-Host "완료: $siteUrl (배포에 1~2분 걸립니다)" -ForegroundColor Green
