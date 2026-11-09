# 네이버 VR 메타데이터만으로 매스 초안

`tools/xrx_mass.py`는 `data.xrx.json`의 동별 외곽선과 층 높이만 읽어 `generic_spec.json` 매스 초안을 만듭니다. 사진·텍스처·입면 근거는 만들지 않습니다.

```bash
python tools/xrx_mass.py --project my-apt \
  --xrx photos/data.xrx.json --dongs 101 --force --json
```

출력:

- `generic_spec.json`: `volumes`(동별 footprint·height), `openings`/`attachments`는 비어 있음
- `previews/xrx/shape.png`: 평면 미리보기
- `previews/xrx/shape_report.json`: 높이·면적·경고

## 좌표와 방향

- xrx 장면 좌표는 미터 단위입니다(`capture/naver_vr.py`의 벽 길이와 일치).
- 기본값은 가장 긴 외벽이 `-Y`(정면)를 향하도록 자동 회전하고, x를 0 중심, y 최솟값을 0으로 맞춥니다.
- 회전이 틀리면 `--front-deg 180`으로 뒤집거나 `--no-rotate`로 장면 축을 유지합니다.
- 여러 동을 고르면 상대 위치를 유지한 채 하나의 spec에 들어갑니다. 단일 에셋이면 `--dongs 101`처럼 하나만 고르세요.

## 옵션

- `--simplify 0.6`: 외곽선 단순화 허용 오차(m). 너무 작으면 점이 많아지고, 너무 크면 날개가 뭉개집니다.
- `--min-area 20`: 이보다 작은 외곽선은 버립니다.
- `--floor-height 2.9`: `slices`가 없을 때 층수로 높이를 추정합니다.
- `--force`: 기존 `generic_spec.json`을 덮어씁니다.

## 만든 뒤

1. `previews/xrx/shape.png`에서 정면·날개·단차를 확인합니다.
2. `--template generic` 프로젝트의 `generic_spec.json`으로 옮기거나 그대로 사용합니다.
3. 창·상가·루버는 사진(`photo_refs`, `evidence`)으로 `openings`/`attachments`에 추가합니다.
4. `python tools/agent.py cycle --project P --generator P_cs2.py --mode quick --label mass --json`로 매스부터 확인합니다.

## 한계

- 동별로 **하나의 볼륨**만 만듭니다. `slices`의 중간 단차·포디움·옥상 장비는 반영하지 않습니다.
- 외곽선 고리가 여러 개면 가장 큰 것만 남기고 경고를 기록합니다.
- `slices`가 없거나 비정상이면 층수 × 층고로 추정하며 `height_source`에 표시합니다.
- 입면·재질·창 근거는 전혀 없습니다. 이 파일은 매스 검토용이며, 사진 대조 없이 PASS로 보고하면 안 됩니다.
- 실제 검증: `125062`의 101동(109.8 m, 617.7 m²)과 112동(57.8 m, 371.4 m²)으로 생성·스키마 검증·`build_volume_spec` 빌드까지 확인했습니다.
