# IFC·CAD에서 GLB로 변환한 뒤 매스 만들기

킷은 IFC·DWG를 직접 읽지 않습니다. IFC를 **GLB로 한 번 변환**한 뒤 `glb-mass`로 단순화된 매스를 만듭니다. 이 문서는 변환 경로를 고르고, 변환 후 무엇을 확인해야 하는지 정리합니다.

```bash
python tools/ifc_to_glb.py --check --json
python tools/ifc_to_glb.py --plan
```

`--check`는 이 컴퓨터에서 쓸 수 있는 변환기(BlenderBIM/Bonsai, IfcConvert, FreeCAD)를 찾습니다. `--plan`은 경로별 명령을 출력합니다.

## 1. Blender + BlenderBIM/Bonsai

IFC의 층·부재·재질 구조를 가장 잘 보존합니다.

1. Blender에 BlenderBIM(현재 이름 Bonsai) 애드온을 설치합니다.
2. `python tools/ifc_to_glb.py --check --json`에서 `blenderbim`이 잡히는지 확인합니다.
3. 변환합니다.

```bash
python tools/ifc_to_glb.py --run --ifc photos/model.ifc --glb photos/model.glb
```

또는 스크립트를 직접 실행합니다.

```bash
python tools/ifc_to_glb.py --emit-script ifc_to_glb_blender.py
blender --background --python ifc_to_glb_blender.py -- photos/model.ifc photos/model.glb
```

## 2. IfcConvert (IfcOpenShell CLI)

IfcConvert가 PATH에 있으면 가장 짧습니다.

```bash
IfcConvert photos/model.ifc photos/model.glb
```

`tools/ifc_to_glb.py --run`도 IfcConvert를 먼저 사용합니다.

## 3. FreeCAD

FreeCAD에서 IFC를 열고 메시로 내보낸 뒤 GLB로 저장합니다. 층·부재 이름이 단순해질 수 있으므로 매스 확인은 필수입니다.

## 변환 후 매스

```bash
python tools/agent.py glb-mass --project my-building --json -- photos/model.glb --list
python tools/agent.py glb-mass --project my-building --json -- photos/model.glb --mesh-index 3 --out generic_spec.json --force
```

확인할 것:

- 단위: IFC가 mm 단위면 GLB가 1000배로 들어올 수 있습니다. `--scale`로 보정합니다.
- 원점과 지면: 지면 z=0, 앞면은 -Y가 되도록 `--front-deg`를 조정합니다.
- 숨은 메시: 가구·설비·주변 대지가 섞이면 `--list`에서 건물 메시만 고릅니다.
- 재질·텍스처는 복사하지 않습니다. GLB는 매스 근거로만 쓰고, 입면은 사진·스타일로 채웁니다.

## 한계

- IFC/DWG 파서를 키트에 내장하지 않습니다. 변환기는 사용자가 설치해야 합니다.
- BlenderBIM/IfcConvert/FreeCAD가 없는 환경에서는 `--check`가 `MISSING`을 반환하고, `--run`은 설치 안내와 함께 중단합니다.
- 실제 IFC 파일 변환은 변환기 설치 후 사용자가 한 번 확인해야 합니다. 검출·스크립트 생성·오류 경로만으로 변환 품질을 보증하지 않습니다.
