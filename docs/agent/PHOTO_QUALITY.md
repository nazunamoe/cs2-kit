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
| `unreadable` | Pillow가 열지 못함 | — |

중복 그룹에서는 **해상도가 가장 크고 선명한 사진**을 대표로 남기고 나머지에 `duplicate_of`를 적습니다. 자동 삭제는 하지 않습니다.

## 조정

```bash
python tools/photo_quality.py --dir photos --blur-min 45 --min-side 800 --dup-distance 1
```

- 하얀 하늘이 많은 VR 캡처는 `clip` 기본값(98%)에서 걸리지 않습니다. 실제 과다 노출은 `--bright-clip`을 낮춰 확인하세요.
- 평평한 벽만 찍은 사진은 `blur`가 낮게 나올 수 있습니다. 숫자만 보고 버리지 말고 원본을 확인하세요.
- 연속 프레임은 `dup-pixel`을 낮춰 더 엄격하게, 다른 각도까지 묶고 싶으면 높여 비교하세요.

## 검증 예

`namsan_xihanulche`의 256장에서 기본값으로 10장이 플래그되었습니다.

- `small` 8장: `*_road*.png`, `*_satellite*.png`
- `duplicate` 2장: 인접 동의 거의 같은 정면 뷰

`blur`/`clip` 오탐은 없었습니다. 이 결과는 파일을 수정하지 않고 JSON으로만 기록됩니다.
