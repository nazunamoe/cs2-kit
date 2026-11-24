---
name: mod-desc
description: Write a Paradox Mods description (Korean + English) for a finished CS2 building project
---

Project: the argument, else the current folder under `projects/`, else `python tools/project.py where`.

1. Read only what exists: the newest worklog or `shape_notes.md`, the household table, `building_spec_*.yaml` (one file per distinct layout), and the folder names in `output/`. Do not read tools, photos, or the web.
2. Write `projects/<project>/mod_description.md`:
   - `# Short description`: one line, Korean / English.
   - `# Long description`: Korean block, then the same content in English. Order: one-sentence intro, AI disclosure, layouts with lot size and homes per floor, floors and heights, features, notes.
3. Rules:
   - Describe what players see and use. No file names, presets, work history, or internal tool names (the AI disclosure below is the one exception).
   - Always include an AI disclosure paragraph right after the intro, in both languages (user rule, 2026-11-24). Keep the wording, naming the AI (Claude):
     - KO: `**AI 사용 안내**: 이 에셋은 AI(Claude)의 도움으로 만들었습니다. 참고 사진과 배치도를 바탕으로 AI가 모델과 텍스처를 생성하는 스크립트를 작성했고, 제작자가 방향을 정하고 결과를 확인하며 수정을 요청했습니다.`
     - EN: `**AI disclosure**: This asset pack was made with the help of AI (Claude). Working from reference photos and site plans, the AI wrote the scripts that generate the models and textures; the creator directed the work, checked the results and requested corrections.`
     - Adjust only what differs for the project (e.g. no photos or site plans used, textures taken from photos). Do not drop the paragraph. Keep it in an existing `mod_description.md` too.
   - Use only facts from step 1. Never claim in-game settings or tests (level, signature, households entered in the editor) that the files do not confirm.
   - No real brand, complex, or logo names (AGENTS.md rule 3), even if the project folder name has one.
   - Markdown headings, bold, and bullets only. No tables or images.
   - Notes: mention anything that surprises a user (no building numbers, high triangle count, required mods).
4. If `mod_description.md` already exists, read it first and keep the user's edits.
5. Show both texts in the reply in Korean conversation, and list the facts the user should confirm before posting.
