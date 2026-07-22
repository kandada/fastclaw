# skill_creator

## Description
Meta-skill: how to create, update and optimize skills. Follow this guide whenever the user asks to add a new skill or improve an existing one.

## Parameters
- name: skill name — lowercase letters, digits and underscores only (e.g. api_tester)
- action: "create" or "update"

## Example
run_skills("skill_creator")

## Skill storage locations

FastClaw has two tiers of skills, both under `workspace/skills/`:

1. **Bundled skills** (read-only): `workspace/skills/bundled/<skill_name>/SKILL.md`
   — Shipped with the framework. Do NOT modify them.
2. **User skills**: `workspace/skills/user/<skill_name>/SKILL.md`
   — Created by the user. This is where new skills go by default.

There is a reference template at `workspace/skills/user/_template/` (SKILL.md + main.py).

## Two kinds of skills

- **Document skill**: the directory contains only SKILL.md. Both `__info__` and execution return the instructional content; the model reads it and follows the steps itself using `run_shell` and other tools. Start here — it's always safe.
- **Script skill**: SKILL.md plus `main.py`. The file must define `async def execute(**kwargs) -> str`. The framework imports it dynamically via importlib on each run, so code changes take effect immediately. Only create one when the logic genuinely needs code (external API calls, heavy computation, etc.).

Document skills can also be created via the WebUI Skills tab (no restart required).

## Required SKILL.md structure

```markdown
## Description
One sentence describing what this skill does.

## Parameters
- param1: description of param1
- param2: description of param2

## Example
run_skills("<skill_name>", {"param1": "value1", "param2": "value2"})
```

Optional sections (append AFTER the three required ones when the skill connects to a remote service):

```markdown
## Remote Endpoint
https://example.com/api

## Secret
<the secret or API key required by the endpoint>
```

## main.py template (script skills only)

```python
async def execute(**kwargs) -> str:
    param1 = kwargs.get("param1", "")
    param2 = kwargs.get("param2", "")
    # implement your skill logic here
    return "result"
```

## How to create a skill

1. Check for name conflicts: `run_skills("__list__")` — if the name already exists (either bundled or user), DO NOT overwrite it unless the user explicitly asked to modify that exact skill. Otherwise pick a different name.
2. Write the files using heredoc (keeps formatting intact):

```
mkdir -p workspace/skills/user/my_skill

cat > workspace/skills/user/my_skill/SKILL.md <<'EOF'
## Description
...

## Parameters
- ...

## Example
run_skills("my_skill", {...})
EOF
```

For script skills also write main.py:

```
cat > workspace/skills/user/my_skill/main.py <<'EOF'
async def execute(**kwargs) -> str:
    ...
    return "result"
EOF
```

3. Verify: `run_skills("__info__", {"skill_name": "my_skill"})` — confirm the content is complete and well-formed. Changes take effect immediately, no restart needed.

## How to update / optimize a skill

1. Read the current version: `run_skills("__info__", {"skill_name": "x"})`.
2. Rewrite the full SKILL.md (same heredoc pattern). Keep the required section structure; preserve existing `## Remote Endpoint` and `## Secret` sections unless the user asked to change them.
3. For script skills, update `main.py` alongside SKILL.md and keep the two consistent.

## Rules

- Skill names: `^[a-z][a-z0-9_]*$` — no spaces, no dashes, no uppercase.
- Never copy a `## Secret` value into any other file, command output, or message; it may only exist inside its own SKILL.md.
- Keep Description to one line — it appears in every system prompt; details belong in the body (progressive disclosure keeps context small).
- Use `<<'EOF'` (quoted) with heredocs to prevent shell variable expansion.
- The script entry point is always named `main.py`. The framework discovers and loads skills through it automatically.
- ALL skill files (SKILL.md, main.py, resources, etc.) must be written inside the skill's own directory (`workspace/skills/user/<skill_name>/`). Never write code outside the skill directory.
