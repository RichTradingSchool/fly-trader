# 시즌 운영 (orangex-perp)

    mkdir -p ~/.config/systemd/user ~/.config/stonkfly
    cp ops/stonkfly@.service ops/stonkfly-dashboard@.service ~/.config/systemd/user/
    # 유닛의 WorkingDirectory/ExecStart는 ~/fly-trader/stonkfly-dashboard 기준이다(다른 위치면 수정).
    printf 'FLY_VENUE_s1=orangex-perp\nFLY_OUT_s1=runs/s1\n' > ~/.config/stonkfly/s1.env
    systemctl --user daemon-reload
    loginctl enable-linger "$USER"
    git tag s1-freeze            # 코드 동결
    systemctl --user enable --now stonkfly@s1 stonkfly-dashboard@s1
    journalctl --user -u stonkfly@s1 -f

- 시즌 중 코드 변경 금지(provenance 해시가 바뀌면 재개 거부). 변경이 필요하면 새 run 디렉터리 = 새 시즌.
- 종료: `touch runs/s1/STOP` 후 `systemctl --user stop stonkfly@s1`.
- `bankrupt`·`accounting-error`·`Checkpoint integrity`는 flyguard가 절대 자동 재개하지 않는다.
  선물 venue에서는 `market-outage`만 자동 재개(`--resume-reviewed`) 대상이고, 그 밖의 모든 halt는
  보류(exit 75 → `RestartPreventExitStatus=75`)한다.
- `clock-skew`: 신선도 베토("Stale or future quote")가 10틱 연속이면 시세가 아니라 이 PC의 시계가
  틀린 것이므로 `market-outage`와 분리해 halt한다(자동 재개 대상 아님). 아래 "시계" 항목대로
  맞춘 뒤 사람이 `--resume-reviewed`로 해제한다.
- flyguard 자체 로그는 `runs/s1/watchdog.log`, 러너 stdout/stderr도 같은 파일에 누적된다.
- Windows: 절전·최대 절전 끄기, 시즌 중 자동 재부팅 보류.
- 시계: 펀딩 정산이 벽시계 기준이라 WSL 절전 복귀 후 스큐가 그대로 손익에 들어간다.
  확인은 `timedatectl`(또는 `date -u`)를 폰·NTP 등 믿을 수 있는 시계와 대조,
  어긋났으면 `sudo hwclock -s`로 맞춘다.
  선결 조건: `sudo apt-get install -y util-linux-extra`(`/usr/sbin/hwclock`) +
  서비스 사용자의 NOPASSWD sudo 규칙. 둘 중 하나라도 없으면 유닛의
  `ExecStartPre` 재동기화도 조용히 건너뛴다.

## halt를 남기지 않는 실패 (조용한 재시작 루프)

원장에 `halted`를 쓰지 않고 종료하는 실패가 있다: 설정/모드 서명 불일치, provenance 게이트,
Bybit 시드 실패, STOP이 있는데 `--resume-reviewed` 같은 운영자 실수. 이때 `halted`는 비어 있어
flyguard가 그대로 러너를 다시 띄우고, 러너는 또 비정상 종료하고, systemd는 30~300초 간격으로
영원히 반복한다. **원장·대시보드에는 아무 흔적이 없고 `journalctl --user -u stonkfly@s1`(또는
`runs/s1/watchdog.log`)에만 보인다.**

그래서 flyguard는 시작할 때마다 원장의 `tick`을 읽어 `runs/s1/flyguard.state`
(`last_tick=`, `stalls=`)에 기록한다. tick이 그대로면 `stalls`가 1씩 오르고, **6이 되면 러너를
띄우지 않고 보류(exit 75)하며 텔레그램으로 알린다.** `market-outage` 자동 재개가 아무 틱도
기록하지 못하고 도는 경우도 같은 카운터에 걸린다.

    cat runs/s1/flyguard.state                 # last_tick / stalls 확인
    journalctl --user -u stonkfly@s1 -n 100    # 실제 종료 사유
    # 원인을 고친 뒤 수동 복구:
    rm runs/s1/flyguard.state
    systemctl --user restart stonkfly@s1

## 무인 7일 운영 전제(WSL2)

- `loginctl enable-linger han` 활성화 필수(이 머신은 2026-09-21 적용 완료). 안 하면 마지막 세션이
  닫히는 순간 `systemd --user` 유닛이 전부 죽는다.
- linger가 있어도 WSL2는 마지막 `wsl.exe` 세션 종료 후 약 8초 뒤 배포판 자체를 종료시켜 유닛을
  모두 죽인다. Windows 쪽 킵얼라이브가 필수: 숨김 `wsl.exe -d Ubuntu-24.04 --exec sleep infinity`
  프로세스를 로그온 시 작업 스케줄러로 띄운다(예: `wscript`나 `-WindowStyle Hidden`으로 숨김 실행).
  시즌 시작 전 `wsl.exe --list --running`으로 배포판이 떠 있는지 반드시 확인.
- `TG_TOKEN`/`TG_CHAT`을 `~/.config/stonkfly/s1.env`에 넣지 않으면 flyguard의 hold·notify 알림이
  전부 조용히 no-op된다(에러 없이 그냥 안 보낸다).
- `s1.env` 샘플:

      FLY_VENUE_s1=orangex-perp
      FLY_OUT_s1=runs/s1
      # FLY_ARGS 없음

- 시즌 전 체크리스트:

      timedatectl                    # 신뢰할 수 있는 시계와 대조(폰·NTP)
      df -h                          # F 드라이브 ≥ 5GB 여유(vhdx 성장분)
      wsl.exe --list --running       # 킵얼라이브로 배포판이 떠 있는지 확인
      systemctl --user status        # linger 활성화 후 상태 확인
      git tag s1-freeze              # 코드 동결

  `ops/**`는 provenance의 `source_sha256`(`stonkfly/**`만 해시) 밖이라 시즌 중에도 flyguard를
  패치할 수 있다. 반대로 `stonkfly/**`는 시즌 중 변경 금지 — 해시가 바뀌면 재개가 거부된다.
