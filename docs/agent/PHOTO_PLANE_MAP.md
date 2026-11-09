# 사진 평면 → 모델 벽 매핑 (photo_plane_map)

캡처(네이버 VR 등)는 **자신의 평면**을 장면 미터로 알고 있고, 모델(`generic_spec*.json`)은
**자신의 벽 링**을 모델 미터로 알고 있다. 둘은 서로를 모르므로, 사진에서 잰 창 열을 모델에
놓으려면 먼저 "이 사진 평면이 모델의 어느 벽에, 몇 미터 지점부터 붙는가"를 등록해야 한다.

`tools/photo_plane_map.py`가 그 등록을 대신한다.

## 사용

```bash
python tools/photo_plane_map.py --project namsan_xihanulche \
  --meta photos/ref101/101_meta.json --mass generic_spec_xrx.json \
  --refs photo_refs_stitched2.json --out work/plane_to_edge.json
```

| 옵션 | 뜻 |
|---|---|
| `--meta` | 캡처 메타 (`<dong>_meta.json`). `footprint_m`, `walls`, `shots`가 필요 |
| `--mass` | 모델 매스 json. 없으면 프로젝트의 `generic_spec*.json` 중 가장 큰 것 |
| `--volume` | 매스 파일 안의 볼륨 id (여러 볼륨이면 지정) |
| `--refs` | photo_refs json. 각 평면의 **파일** 해상도(px/m)만 읽는다 |
| `--min-len` | 이보다 짧은 평면은 무시 (기본 6 m) |
| `--min-px-per-m` | 캡처 해상도가 이보다 낮으면 경고 (기본 20) |
| `--max-perp` | 평면과 모델 벽의 허용 거리 (기본 1.5 m) |
| `--out` | 결과 json (기본 `work/plane_to_edge.json`) |
| `--json` | 표 대신 json 전체 출력 |

## 하는 일

1. **등록** — 캡처 외곽선(`footprint_m`)을 모델 링에 강체 변환(회전+평행이동)으로 맞춘다.
   회전은 0.5° 격자 탐색, 평행이동은 0.05 m 격자 정밀도. 등록 잔차(residual)를 함께 출력하므로
   두 외곽선이 얼마나 어긋났는지 알 수 있다.
2. **평면 → 벽** — 캡처의 정확한 평면(`naver_vr.reference_walls_of`)마다
   - 덮는 모델 벽 번호와 길이
   - **사진 왼쪽 끝이 그 벽의 몇 m 지점**인지 (`photo_left_m`) → 여기서 `u`를 미터로 바꿀 수 있다
   - 사진이 벽 방향과 **반대인지**(`mirrored`) → 반전이면 창 순서가 뒤집힌다
   - 덮는 비율(`coverage_ratio`), 벽에서 떨어진 거리(`perp_m`)
3. **해상도** — `px_per_m_capture`(캡처 투영 기준)와 `px_per_m_file`(ref 파일 기준)을 따로 낸다.

## 결과 읽는 법

```
plane  grp      len_m edge      left_m   right_m  cover    perp  cap_px file_px  warn
4      0         9.54 0           9.64      0.10   0.99    0.59    13.0    40.0
16     4        14.99 11         14.98      0.00   1.00    0.56    12.6    40.0
```

- 평면 16 → 모델 벽 11. 사진 왼쪽 끝은 그 벽의 **14.98 m 지점**(벽 반대쪽 끝)이고, 사진 오른쪽
  끝이 0.00 m 지점이다. → `u = 0` 은 벽의 14.98 m, `u = 1` 은 0.00 m.
- `mirrored = true` 이므로 **열 순서를 뒤집어야** 한다.
- `perp_m` 은 평면과 모델 벽의 거리. 1.5 m 를 넘으면 매스 외곽선이 사진과 다른 것이므로 먼저 매스를
  손봐야 한다.

```python
m = edge_offset + (edge_offset_end - edge_offset) * u     # 사진 u -> 모델 벽 미터
if mirrored:
    m = edge_len - m                                       # 순서 뒤집기
```

## 해상도 규칙 (중요)

**리샘플된 파일의 해상도는 정보량이 아니다.** 이어붙인 평면 이미지를 40 px/m로 만들어도
원본 사진이 12 px/m 이면 같은 정보다. 그래서 이 도구는 두 값을 따로 낸다.

- `px_per_m_capture` — 캡처 사진에서 그 평면이 실제로 차지하는 픽셀 밀도. **실제 측정 한계**.
- `px_per_m_file` — ref 파일 자체의 밀도. 업스케일이면 값만 커진다.

측정 가능 기준(경험값):

| 용도 | 필요 px/m |
|---|---|
| 창 폭·위치 | 20 이상 |
| 루버 슬랫 구분 | 30 이상 |

경고가 뜨면 **사진을 다시 캡쳐**해야 한다. 캡처 폭을 크게(`--width 0.8`), 브라우저 뷰포트를
크게 잡으면 px/m이 바로 올라간다. 101동 캡처는 `--width 0.4` + 1366 px 뷰포트라 10~13 px/m 였고,
그래서 35 m 면은 창 폭을 읽을 수 없었다.

## 경고 종류

- `capture resolution ... too low` — 측정 불가. 재캡쳐 필요.
- `the ref file is resampled up` — 파일 해상도가 실제 정보량보다 높음(오해 금지).
- `photo covers only N% of the model edge` — 사진이 벽 일부만 덮음. 나머지는 다른 사진/추정.
- `photo reaches outside the model edge` — 사진이 모델 벽 밖으로 나감. 오프셋 확인 필요.
- `model edge N has no photo plane` — 그 벽은 사진 근거가 없음. generic 리듬 유지.

## 함께 쓰는 도구

- `tools/facade_read.py` — 평면 사진에서 창 열을 읽는다. 이 도구의 `photo_left_m`/`mirrored`로
  열 좌표를 모델 미터에 붙인다.
- `tools/qa/plane_compare.py` — 같은 평면을 사진/모델로 나란히 비교.

## 한계

- 등록은 외곽선 모양 기준이라 **대칭 건물이 잘못 붙을 수 있다**. 잔차가 크거나 벽 번호가 이상하면
  눈으로 photo|model 비교를 돌려 확인한다.
- 모델 매스는 캡처 외곽선과 다를 수 있다(이 101은 잔차 평균 0.40 m / 최대 1.63 m).
  `perp_m` 이 큰 평면은 모델을 먼저 손봐야 한다.
- 사진의 **방향**(어느 쪽이 도로 쪽)은 여전히 가정이다. 이 도구는 위치만 정한다.
