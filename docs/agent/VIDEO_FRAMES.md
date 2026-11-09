# 영상 워크스루에서 프레임 추출

`tools/video_frames.py`는 현장 답사·드론 영상에서 일정 간격으로 정지 프레임을 뽑습니다. 결과 JPEG는 `photos/`에 넣어 일반 사진처럼 `agent.py photos`, `observe`, `photo_refs.json`에 쓸 수 있습니다. 원본 영상은 수정하지 않습니다.

## 준비

ffmpeg가 필요합니다. 시스템 ffmpeg가 없으면 파이썬 패키지로 설치합니다.

```bash
pip install imageio-ffmpeg
python tools/video_frames.py --check --json
```

`--check`는 사용할 ffmpeg 경로와 버전을 출력합니다. `--ffmpeg <path>`로 직접 지정할 수도 있습니다.

## 실행

```bash
python tools/video_frames.py --project my-apt \
  --video photos/walk.mp4 \
  --every 2.0 --width 1600 \
  --out photos/frames
```

- `--every`: 프레임 간격(초). 2초면 1분 영상에서 약 30장입니다.
- `--start` / `--end`: 필요한 구간만 초 단위로 자릅니다.
- `--width`: 출력 폭. 0이면 원본 크기를 유지합니다.
- `--limit`: 최대 장수. 긴 영상에서 먼저 20~30장만 뽑아 확인할 때 씁니다.
- `--quality`: JPEG 품질(2~31, 낮을수록 고화질).
- `--dry-run`, `--json` 지원.

출력 이름은 `<prefix>_0001.jpg` 형식입니다. `--prefix`를 주지 않으면 영상 파일명을 씁니다.

## 한계

- 프레임은 촬영 시점의 원근 사진입니다. 흔들림·모션 블러·압축 열화는 보정하지 않습니다.
- 영상에서 자동으로 벽을 정합하거나 시점을 추정하지 않습니다. 층수·베이·색은 `observe`/`evidence`로 기록하고, 필요하면 `photo_observe` 스킬로 한 벽씩 판독하세요.
- 같은 벽이 여러 프레임에 나오면 가장 정면이고 선명한 1~2장만 `photo_refs`에 쓰는 편이 좋습니다.
- 영상 프레임은 실측이 아닙니다. 치수는 `size_m`, GLB, 도면으로 보정합니다.
