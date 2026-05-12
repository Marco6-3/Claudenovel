# AGENTS.md

## Global Writing Preference

- When writing any `README` or `README.md`, use Simplified Chinese by default.
- Only write a README in English if the user explicitly requests English in that conversation.
- If the user does not specify a language, keep the README in Chinese.

## Collaboration Preferences

- Stay calm and pragmatic on difficult tasks.
- Do not fabricate results, progress, evidence, test outcomes, or capabilities.
- If something is uncertain, blocked, or unverified, say so directly.
- Inspect real files and actual generated artifacts before making claims about behavior.

## Chinese Encoding Rules

Chinese mojibake is a known risk on this Windows + PowerShell workflow. Treat encoding as a first-class correctness issue.

- All project text files that contain Chinese must be written and read as UTF-8.
- Use `python -X utf8` for Python scripts that read/write Chinese text.
- Prefer file-based Chinese input over shell-inline Chinese strings.
- Do not pass long Chinese prompts, author settings, chapter briefs, or novel prose through PowerShell here-strings, command arguments, or ad hoc inline scripts unless they are encoded via Unicode escapes or already stored in UTF-8 files.
- For author intent, use UTF-8 files such as `设定集/author_bible.md` and `大纲/chapter_{NNNN}_brief.md`.
- For generated prompts, always save the exact prompt to a `.md` file before or during the run.
- When verifying whether a file is corrupted, read it with Python using `Path.read_text(encoding="utf-8")`; do not rely on PowerShell display output alone.
- If Chinese text appears as repeated question marks, replacement diamonds, or visibly corrupted Chinese, treat the artifact as invalid and regenerate it from clean UTF-8 sources.

## Webnovel Writing Flow Rules

- Do not assume the model has read future chapters.
- Continuation prompts must use only prior chapters, author-supplied settings, and the current chapter brief.
- Hidden/reference chapters may be used only for evaluation after generation, never in generation or rewrite prompts.
- For non-trivial continuation work, prepare or load:
  - `设定集/author_bible.md`
  - `大纲/chapter_{NNNN}_brief.md`
- Run a local post-generation gate before rewrite or polish:

```powershell
python -X utf8 webnovel-writer\scripts\webnovel.py --project-root <PROJECT_ROOT> post-rewrite validate --file <DRAFT_FILE>
```

- If validation blocks, regenerate the draft with the failure reason. Do not send a blocked draft into rewrite.
- Use rewrite only for expression, compression, and style calibration. Do not use rewrite to rescue a broken plot event, coercive relationship beat, or unauthorized new power system.

## Current Hard Validators

The draft gate should block:

- Main relationship character initiating unsupported help/dependency too early.
- Protagonist using coercion, threats, public shaming, forced blocking, or crowd pressure as romance.
- Unauthorized new task/stat/passive-skill systems.
- Missing required chapter payoff.

Warnings such as excessive softening language should be reviewed before acceptance.
