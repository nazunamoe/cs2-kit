---
name: mod-desc
description: Write a Paradox Mods description (Korean + English) for a finished CS2 building project
---

Project: the argument, else the current folder under `projects/`, else `python tools/project.py where`.

1. Read only what exists: the newest worklog or `shape_notes.md`, the household table, `building_spec_*.yaml` (one file per distinct layout), and the folder names in `output/`. Do not read tools, photos, or the web.
2. Write `projects/<project>/mod_description.md`:
   - `# Short description`: one line, Korean / English.
   - `# Long description`: Korean block, then the same content in English. Order: one-sentence intro, layouts with lot size and homes per floor, floors and heights, features, notes.
3. Rules:
   - Describe what players see and use. No file names, presets, work history, or internal tool names.
   - Use only facts from step 1. Never claim in-game settings or tests (level, signature, households entered in the editor) that the files do not confirm.
   - No real brand, complex, or logo names (AGENTS.md rule 3), even if the project folder name has one.
   - Markdown headings, bold, and bullets only. No tables or images.
   - Notes: mention anything that surprises a user (no building numbers, high triangle count, required mods).
4. If `mod_description.md` already exists, read it first and keep the user's edits.
5. Show both texts in the reply in Korean conversation, and list the facts the user should confirm before posting.
