# 360 사진 원근 크롭

`tools/crop_360.py`는 equirectangular(2:1) 360 사진에서 일반 원근 사진을 잘라냅니다. 결과는 `photos/`에 넣어 다른 입면 사진과 똑같이 `photo_refs.json`·`agent.py evidence`에 쓸 수 있습니다. 원본 360 사진은 수정하지 않습니다.

```bash
python tools/crop_360.py --project my-apt \
  --image photos/pano.jpg \
  --yaws 0,90,180,270 --fov 90 --size 1600x1200 \
  --out photos/crops
```

- `--yaws`: 쉼표로 구분한 방위각. `0`은 equirect 이미지의 중앙 열, 양수는 오른쪽입니다.
- `--pitch`: 위(+)·아래(-) 시선 각도.
- `--fov`: 수평 화각(1~170°). 90°가 일반적인 입면 크롭입니다.
- `--size`: 출력 해상도. 원본에서 충분한 픽셀이 남는지 먼저 확인하세요.
- `--out`: 폴더(여러 yaw) 또는 파일 하나(단일 yaw).
- `--dry-run`, `--json` 지원.

## 한계

- 360 사진이 2:1 equirectangular여야 합니다. 일반 파노라마 스티칭은 하지 않습니다.
- 크롭은 원근 투영일 뿐 실측이 아닙니다. 벽 폭·층고는 `photo_refs`의 `size_m`이나 GLB/도면으로 보정하세요.
- 롤(기울기) 보정은 없습니다. 수평이 기울어진 사진은 편집기에서 먼저 바로잡는 편이 좋습니다.
- 크롭 후에도 창·간판·나무가 섞이면 `paint_exclude`로 제외하고 `_mask.png`를 확인하세요.
