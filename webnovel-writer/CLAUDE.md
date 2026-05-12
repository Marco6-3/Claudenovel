# CLAUDE.md

## Project Role

This repository is a webnovel writing agent framework. Treat it as a production writing workflow, not only an experiment sandbox.

## Chinese Output And Encoding

Chinese encoding issues have caused real prompt corruption in prior experiments. Follow these rules strictly:

- Read and write Chinese text as UTF-8.
- Prefer `python -X utf8` for scripts that touch Chinese content.
- Do not put long Chinese prose, author settings, chapter briefs, or generated prompts directly inside PowerShell inline commands.
- Store Chinese-heavy input in files first, then pass file paths to scripts.
- Save exact generation/rewrite prompts as UTF-8 `.md` files for audit.
- Verify suspect files with Python:

```powershell
python -X utf8 -c "from pathlib import Path; print(Path(r'<PATH>').read_text(encoding='utf-8')[:1000])"
```

- If a prompt or setting file contains repeated question marks, replacement diamonds, or visibly corrupted Chinese, stop and rebuild that artifact from clean UTF-8 input.

## Author Settings Must Be File-Based

For serious continuation work, do not ask the model to infer everything from previous chapters alone. Real writing needs author intent.

Use these files when available:

- `设定集/author_bible.md`
- `大纲/chapter_{NNNN}_brief.md`

Templates:

- `webnovel-writer/templates/author_bible.template.md`
- `webnovel-writer/templates/chapter_brief.template.md`

The author bible should define:

- character labels and hard boundaries
- relationship stage and allowed next concession
- world-rule boundaries
- forbidden power-system changes
- volume or near-future direction
- style mechanics

The chapter brief should define:

- must-cover beats
- forbidden beats
- current character states
- relationship evidence card
- world/setting guard
- ending strategy

## Generation Boundary

- Never assume the model has read future chapters.
- For chapter continuation, generate only from prior chapters, author bible, chapter brief, and approved memory/RAG evidence.
- Hidden original chapters are evaluation references only. They must not enter generation, rewrite, or style prompts.

## Draft Gate Before Rewrite

After a draft is generated and before any rewrite/polish/reviewer stage, run:

```powershell
python -X utf8 webnovel-writer\scripts\webnovel.py --project-root <PROJECT_ROOT> post-rewrite validate --file <DRAFT_FILE>
```

If the command exits non-zero, do not continue to rewrite. Regenerate the draft with the validator failure reason.

Blocking risks include:

- unsupported Qin-style help/dependency initiation
- protagonist coercion, threats, public shaming, repeated blocking, or crowd pressure
- unauthorized new systems such as charm values, task systems, passive abilities, or stat rewards
- missing required payoff

## Rewrite Scope

`post-rewrite rewrite` is expression-only:

- compress prose
- reduce explanatory psychology
- improve dialogue rhythm
- calibrate style against prior chapters

It must not preserve or normalize a broken story event. If the plot event is wrong, reject and regenerate before rewrite.
