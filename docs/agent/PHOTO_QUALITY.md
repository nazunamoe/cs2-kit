# 사진 품질 게이트

`tools/photo_quality.py`는 입면 작업 전에 참고 사진의 블러·해상도·중복·노출 이상을 점수화합니다. 파일을 삭제하거나 수정하지 않습니다.

```bash
python tools/photo_quality.py --project my-apt --dir photos --json
python tools/photo_quality.py --project my-apt --dir photos/frames --strict --report work/photo_quality.json
```

## 플래그

| 플래그 | 의미 | 기본 기준 |
|---|---|---|
| `blur` | 초점/흔들림 의심 | Laplacian variance < 30 |
| `small` | 해상도 부족 | 짧은 변 < 600 px |
| `duplicate` | 같은 장면의 중복 | SHA-256 동일 또는 dHash ≤ 2 + 32×32 평균차 ≤ 3 |
| `clip` | 거의 전체가 포화 | 250 이상 픽셀 비율 > 98% |
| `dark` | 거의 전체가 검정 | 5 이하 픽셀 비율 > 98% |
| `flat` | 디테일 없는 단색 | 표준편차 < 8 |
| `low_px_per_m` | 창 폭을 읽기 어려운 캡처 해상도 | `--refs`의 `size_m` 기준 < `--min-px-per-m`(기본 20) |
| `unreadable` | Pillow가 열지 못함 | — |

중복 그룹에서는 **해상도가 가장 크고 선명한 사진**을 대표로 남기고 나머지에 `duplicate_of`를 적습니다. 자동 삭제는 하지 않습니다.

## 캡처 px/m 사전 게이트

`photo_refs.json`이 있으면 등록(photo_plane_map) 전에 벽별 해상도를 계산해 측정 불가 캡처를 미리 막습니다.
사진 폭(px)을 `size_m[0]`으로 나눈 값이며, 20 px/m 미만이면 창 폭을 읽을 수 없습니다.

```bash
python tools/photo_quality.py --project my-apt --dir photos \
  --refs photo_refs.json --min-px-per-m 20 --strict --json
```

- 결과 JSON의 `px_per_m`에 벽별 값이, `refs_without_size`에 `size_m`이 없어 계산하지 못한 항목 수가 남습니다.
- `--strict`면 `low_px_per_m`도 다른 플래그와 같이 exit 1을 냅니다. 등록 후에는 `photo_plane_map --strict`가 같은 기준으로 막습니다.

## 조정

```bash
python tools/photo_quality.py --dir photos --blur-min 45 --min-side 800 --dup-distance 1
```

- 하얀 하늘이 많은 VR 캡처는 `clip` 기본값(98%)에서 걸리지 않습니다. 실제 과다 노출은 `--bright-clip`을 낮춰 확인하세요.
- 평평한 벽만 찍은 사진은 `blur`가 낮게 나올 수 있습니다. 숫자만 보고 버리지 말고 원본을 확인하세요.
- 연속 프레임은 `dup-pixel`을 낮춰 더 엄격하게, 다른 각도까지 묶고 싶으면 높여 비교하세요.

## 그림자 보정 (색 추출용)

입면 사진에서 **그늘진 부분**은 실제로 어두운 벽이 아니라 가림이 걸린 같은 벽입니다. 그래서 색을 뽑을 때는 밝은 흰 벽을 기준으로 보정해야 합니다.

```bash
python tools/shadow_norm.py --image photos/ref101/101_stitched_p16.png \
  --out photos/ref101/101_stitched_p16_lit.png --block 64
```

- 이미지 전체의 밝은 픽셀 상위 2%를 **흰 벽 기준**으로 잡습니다.
- 블록(기본 64 px)마다 그 블록의 밝은 픽셀을 비교해 **gain** 을 만들고, 블록 gain 맵을 부드럽게 보간해 픽셀별 배율을 적용합니다.
- 그늘진 블록은 흰 벽 기준까지 밝아지므로, 같은 재질이 다른 밝기로 찍혔어도 **색이 같게 나옵니다**.
- `--max-gain`(기본 1.8)으로 보정 강도를 제한하고, 밝은 기준이 없는 어두운 사진은 건너뜁니다.

이 보정본은 **색 측정과 알베도 텍스처**용입니다. 화면용 사진에는 쓰지 마세요.

101동 실측 결과:

| 면 | 보정 전 팔레트 | 보정 후 팔레트 |
|---|---|---|
| p16 (흰 벽) | `#98a1a3 #c3cbcd #d9ddde` | `#acbec9 #d5dcdb #f9fcfd` |
| p20 (어두운 벽) | `#2b2d38 #565c74 #717998` | `#404258 #838dac #a5b6e8` |

p20은 보정 전 거의 검게 나왔던 벽이 중간의 청회색으로 올라와, 그늘과 햇빛 부분의 색 차이가 사라집니다.

## 검증 예

`namsan_xihanulche`의 256장에서 기본값으로 10장이 플래그되었습니다.

- `small` 8장: `*_road*.png`, `*_satellite*.png`
- `duplicate` 2장: 인접 동의 거의 같은 정면 뷰

`blur`/`clip` 오탐은 없었습니다. 이 결과는 파일을 수정하지 않고 JSON으로만 기록됩니다.
