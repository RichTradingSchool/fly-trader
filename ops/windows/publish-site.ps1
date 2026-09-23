# 웹 뷰어를 GitHub Pages에 올립니다 (gh CLI 로그인 필요: gh auth login).
#
#   powershell -ExecutionPolicy Bypass -File ops\windows\publish-site.ps1 -Owner <깃허브 계정> -Repo fly-trader
#   옵션: -Feed https://xxxx.trycloudflare.com   (공개 대시보드 주소, 나중에 set-feed.ps1로 바꿔도 됨)
#         -Guide /home/<you>/guide.pdf           (WSL 경로의 PDF를 사이트에 함께 올림)
#         -RefUrl https://…                      (랜딩 페이지에 거래소 가입 링크를 넣을 때만)
#
# 1) WSL에서 ./fly site 로 site/ 를 빌드  2) gh-pages 브랜치로 강제 푸시  3) Pages 켜기
# 결과 주소: https://<owner>.github.io/<repo>/
param(
    [Parameter(Mandatory = $true)][string]$Owner,
    [string]$Repo = "fly-trader",
    [string]$Feed = "",
    [string]$Guide = "",
    [string]$RefUrl = "",
    [string]$Distro = "Ubuntu-24.04",
    [string]$RepoDir = "fly-trader/stonkfly-dashboard"
)
$ErrorActionPreference = "Stop"
$siteUrl = "https://$($Owner.ToLower()).github.io/$Repo/"
$repoUrl = "https://github.com/$Owner/$Repo"
& gh auth status 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw "gh CLI 로그인이 필요합니다: gh auth login" }

Write-Host "▶ 1/3 사이트 빌드 (WSL)" -ForegroundColor Magenta
$siteArgs = "--out site --repo-url $repoUrl --site-url $siteUrl"
if ($Feed) { $siteArgs += " --feed $Feed" }
if ($Guide) { $siteArgs += " --guide $Guide" }
if ($RefUrl) { $siteArgs += " --ref-url $RefUrl" }
& wsl.exe -d $Distro -- bash -lc "cd ~/$RepoDir && ./fly site $siteArgs"
if ($LASTEXITCODE -ne 0) { throw "사이트 빌드 실패" }
$user = ((& wsl.exe -d $Distro -- whoami) -join "").Trim()
$src = "\\wsl.localhost\$Distro\home\$user\$($RepoDir -replace '/', '\')\site"

Write-Host "▶ 2/3 gh-pages 브랜치로 올리기" -ForegroundColor Magenta
$tmp = Join-Path $env:TEMP "fly-site-publish"
if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
Copy-Item -Recurse $src $tmp
Push-Location $tmp
try {
    git init -q -b gh-pages
    git add -A
    git -c user.name="fly-trader" -c user.email="fly-trader@users.noreply.github.com" commit -q -m "web viewer $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    & gh auth setup-git 2>$null | Out-Null
    git push -f "$repoUrl.git" gh-pages
    if ($LASTEXITCODE -ne 0) { throw "푸시 실패: 저장소가 있는지 확인하세요 (gh repo create $Owner/$Repo --public)" }
} finally { Pop-Location }

Write-Host "▶ 3/3 GitHub Pages 켜기" -ForegroundColor Magenta
& gh api -X POST "repos/$Owner/$Repo/pages" -f "source[branch]=gh-pages" -f "source[path]=/" 2>$null | Out-Null
& gh api "repos/$Owner/$Repo/pages" --jq ".html_url"
Write-Host "완료: $siteUrl (첫 배포는 1~2분 걸립니다)" -ForegroundColor Green
