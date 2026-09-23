# 웹 링크로 공개하기 · 라이브 방송

초파리 시즌은 **내 PC(WSL2)** 에서 돌아갑니다. 다른 사람이 보게 하는 방법은 세 가지이고, 같이 써도 됩니다.

| 방법 | 보는 사람 | 필요한 것 | 특징 |
|---|---|---|---|
| A. 웹 뷰어 + 터널 | 링크를 연 누구나(휴대폰 포함) | GitHub 계정, cloudflared | 3D 화면이 보는 사람 브라우저에서 돌아감. 데이터만 내 PC에서 |
| B. 터널 주소 직접 공유 | 링크를 연 누구나 | cloudflared | 가장 간단. 주소가 재시작마다 바뀜 |
| C. OBS 라이브 방송 | 유튜브·치지직 시청자 | OBS, 방송 키 | 시청자 수 제한 없음. 내 PC가 화면을 렌더링·송출 |

## 1. 공개 주소 만들기 (Cloudflare 터널)

대시보드는 읽기 전용입니다(GET만 허용, 주문·설정 변경 기능 없음). 터널은 그 대시보드 하나만 인터넷에 연결합니다.

### cloudflared 설치 (WSL 우분투)

Cloudflare 공식 저장소에서 설치합니다([공식 안내](https://pkg.cloudflare.com/index.html)).

```bash
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update && sudo apt-get install -y cloudflared
```

### 퀵 터널 (계정 불필요)

```bash
./fly public s1          # 터널을 systemd 유닛(stonkfly-tunnel@s1)으로 띄우고 주소를 출력
cat runs/s1/public-url.txt
```

- `https://<임의 단어>.trycloudflare.com` 형식입니다. 뒤에 `/room/`을 붙이면 3D 화면, 그냥 열면 연구실 뷰입니다.
- **주소는 터널이 다시 시작될 때마다 바뀝니다**(PC 재부팅 등). 그래서 고정 링크는 아래 웹 뷰어로 만듭니다.
- Cloudflare는 퀵 터널을 테스트용으로 안내합니다(동시 요청 200개 제한, 가동 보장 없음). 시청자가 많거나 오래
  운영하면 고정 주소 방식을 쓰세요.

### 고정 주소 (Cloudflare 계정 + 내 도메인)

```bash
cloudflared tunnel login                      # 브라우저에서 Cloudflare 로그인·도메인 선택
cloudflared tunnel create fly
cloudflared tunnel route dns fly fly.내도메인.com
cat > ~/.cloudflared/config.yml <<EOF
tunnel: fly
credentials-file: $HOME/.cloudflared/<터널 ID>.json
ingress:
  - hostname: fly.내도메인.com
    service: http://127.0.0.1:8765
  - service: http_status:404
EOF
printf 'TUNNEL_NAME=fly\nPUBLIC_URL=https://fly.내도메인.com\n' >> ~/.config/stonkfly/tunnel-s1.env
systemctl --user restart stonkfly-tunnel@s1
```

Cloudflare 대시보드의 캐시 규칙에서 `*/live.json*`, `*/counts.bin*`, `*/input.png*`을 “캐시 사용”으로 두면
주소에 붙은 `?v=` 버전 덕분에 같은 데이터는 내 PC까지 오지 않고 Cloudflare가 대신 응답합니다.

## 2. 웹 뷰어 (GitHub Pages, 고정 링크)

`site/`는 3D 화면·뇌 점구름·폰트를 전부 담은 정적 사이트입니다. 보는 사람의 브라우저가 이 파일들을 GitHub에서
받고, 실시간 데이터(1분마다 약 40 KB)만 터널 주소에서 가져옵니다.

Windows PowerShell에서(gh CLI 로그인 필요: `gh auth login`):

```powershell
gh repo create <계정>/fly-trader --public        # 처음 한 번 (프로그램 저장소를 이미 올렸다면 생략)
powershell -ExecutionPolicy Bypass -File ops\windows\publish-site.ps1 -Owner <계정>
powershell -ExecutionPolicy Bypass -File ops\windows\set-feed.ps1 -Owner <계정> -FromRun s1
```

- 결과: `https://<계정>.github.io/fly-trader/` (첫 배포는 1~2분)
- 터널 주소가 바뀌면 `set-feed.ps1 -FromRun s1`을 다시 실행하거나, `-Register`로 로그온 시 자동 감시를 등록하세요.
- 연결이 없을 때 웹 뷰어는 “데모 시즌”을 보여 주고, 연결되면 자동으로 라이브로 바뀝니다.
- 랜딩 페이지에 거래소 가입 링크를 넣고 싶으면 `publish-site.ps1 -RefUrl <링크>`.

## 3. OBS 라이브 방송 (유튜브 · 치지직)

1. OBS → 설정 → 비디오: 기본 해상도 **1920×1080**, 출력 1920×1080(업로드가 느리면 1280×720), FPS 30
2. 장면 모음 → 가져오기 → `ops/obs/fly-trader-obs.json` → 장면 모음에서 “초파리 트레이딩 방송” 선택
   (브라우저 소스 주소: `http://127.0.0.1:8765/room/?stream=1`)
3. 설정 → 방송: 서비스(YouTube / 치지직 등)를 고르고 **방송 키는 직접** 입력
4. 설정 → 출력: 인코더는 하드웨어(NVENC/QuickSync/AMF)가 있으면 그것을, 없으면 x264 `veryfast`, 비트레이트 4,500~6,000 kbps
5. 방송 시작. 소리가 필요하면 OBS에 배경음·마이크를 따로 추가하세요(3D 화면에는 소리가 없습니다)

x264로 1080p를 인코딩하면 CPU를 많이 씁니다. 초파리 관측(1분마다 약 8초 계산)이 늦어지지 않는지
`./fly status`의 “마지막 기록 N초 전”으로 확인하세요.

## 방송·콘텐츠 제작 시 주의

- “초파리가 스스로 매매한다”, “초파리가 시장을 학습했다”처럼 단정하지 마세요. 매매 규칙은 사람이 설계했고,
  시냅스 변화가 학습의 증거는 아닙니다.
- 페이퍼 트레이딩이며 투자 자문이 아니라는 고지를 화면에 유지하세요(3D 화면 하단 띠).
- 데이터 출처(MaleCNS v1.0, CC BY 4.0)와 오픈소스 크레딧은 화면 하단에 이미 표시됩니다. 지우지 마세요.
