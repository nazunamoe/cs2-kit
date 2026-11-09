# LOD 자동 후보 생성

`tools/lod_auto.py`는 내보낸 `.blend`의 main 메시에서 **LOD1/LOD2 후보**를 만듭니다. 원본 `.blend`는 수정하지 않고, 후보를 별도 파일로 저장한 뒤 `lod_check`로 구멍을 확인합니다.

```bash
python tools/lod_auto.py --project my-apt --asset output/<asset> --check --json
```

출력:

```text
output/<asset>/_lod_auto/<asset>_lod_auto.blend
  objects: <asset>_lod_auto, <asset>_lod_auto_LOD1, <asset>_lod_auto_LOD2
```

## 동작

1. `<asset>.blend`에서 `<asset>` 메시를 찾습니다. 없으면 가장 큰 메시를 사용합니다.
2. Blender Decimate(COLLAPSE)로 LOD1/LOD2를 만듭니다.
   - LOD1: `--lod1-ratio` (기본 0.35, main의 50% 미만)
   - LOD2: `--lod2-tris` (기본 500)에 맞춰 비율 계산
3. 후보 `.blend`를 저장합니다.
4. `--check`면 `lod_check --quick`, `--check-full`이면 64시점 전체 검사를 실행합니다.

## 옵션

- `--out`: 후보 폴더. 기본은 `<asset 폴더>/_lod_auto`.
- `--blender`: Blender 실행 파일. 기본은 `tools/blender_path.txt` 또는 자동 탐색.
- `--max-tris`: main 메시의 **하드 상한**. 기본 95000(킷 경고 한계). 넘으면 `FAIL`(exit 1).
- `--max-lod1-tris`: LOD1 하드 상한. 기본은 `--max-tris`의 절반.
- `--no-cap-bottom`: 열린 바닥 경계 루프를 채우지 않습니다. 기본은 자동으로 채웁니다.
- `--json`: 요약 JSON 출력.

## UV 아틀라스 경계 검사

LOD 후보를 만들 때 main의 UV 범위(`u/v` 최소·최대)를 기준으로 LOD1/LOD2의 UV가 그
범위를 벗어났는지(`outside_source`)와 UV 면적이 0이 된 삼각형 수(`degenerate`)를 같이
기록합니다. `outside_source > 0`이면 `FAIL`입니다. 이 검사는 **아틀라스 경계를 벗어나
다른 면의 텍스처를 끌어오는 사고**를 막는 범위 검사이고, UV seam이 그대로 유지되는지까지
보증하지는 않습니다. 최종 LOD는 생성기에서 만들고 `check.py`의 UV 검사와 게임 내
확인을 거치세요.

## 열린 바닥

킷의 main 메시는 바닥면이 없는 경우가 많아 Decimate가 큰 구멍을 만들 수 있습니다. `lod_auto`는 기본적으로 **z 최솟값의 열린 경계 루프를 채운 뒤** LOD를 만듭니다(`capped_edges`에 채운 변 수 기록). 그래도 창·얇은 난간처럼 별도 메시인 부품은 후보에 포함되지 않으므로, 최종 LOD는 생성기에서 만들어야 합니다.

## 한계

- Decimate는 **창틀·UV·재질 경계를 왜곡**할 수 있습니다. 이 후보는 "삼각형 수와 실루엣을 줄일 수 있는지" 보는 용도이고, 최종 LOD는 생성기에서 창·UV를 유지하며 다시 만드는 편이 좋습니다. UV 범위를 벗어난 LOD는 `uv.lod1/lod2.outside_source`로 `FAIL` 처리되지만, seam·텍셀 밀도 변화는 잡지 못합니다.
- 후보에는 LOD1/LOD2용 텍스처 맵을 만들지 않습니다. 최종 FBX로 쓸 때는 생성기의 `export_asset` 경로를 사용하세요.
- `lod_check --quick`은 16시점이라 얇은 구멍을 놓칠 수 있습니다. 보고 전에는 `--check-full` 또는 `tools/qa/lod_check.py` 전체 검사를 실행하세요.
- 닫힌 합성 메시에서는 잘 동작하지만, 실제 건물의 얇은 난간·루버·차양은 Decimate 후 구멍이 생길 수 있습니다. `previews/lod_check/<후보>/`를 눈으로 확인하세요.

## 검증 예

합성 11,532 tris 메시로 기본값을 실행했습니다.

- LOD1: 4,036 tris (main의 35%)
- LOD2: 474 tris (500 이하)
- `lod_check --quick`: main/LOD1/LOD2 모두 0.000% 구멍, 16/16 뷰 통과

실제 101동 blend에서는 바닥 캡으로 95% 구멍 문제는 사라졌지만, Decimate 후보가 main 0.83%, LOD2 29% 구멍으로 **WARN**이었습니다. 이 후보는 사용하지 않았고 생성기 LOD를 사용했습니다. 실제 건물에서는 이 결과를 그대로 PASS로 보지 말고 전체 LOD 검사와 게임 내 확인을 거쳐야 합니다.
