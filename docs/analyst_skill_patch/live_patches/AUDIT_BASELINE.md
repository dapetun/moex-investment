# Базовая линия аудита live-инструкций (V8)

Источник: Grok Bot RESULT `2026-10-11_analyst-instructions-audit-3303148`  
ref: `cur-20261011-2040`  
Снято: 2026-10-11 20:41:33 МСК  
Репо-контекст: `feature/headless-cli-grok-bot` @ `3303148`  
Границы: read-only; live не менялся.

## Файлы и sha256

| Файл | sha256 |
|------|--------|
| profile.json | `c4d4f8f187a598a9c6210f9afbff04468dd504789c077bf2b21629277eea4e2c` |
| description (поле) | `3dc443b7800e971fc12cc176dd3ff8d9c7edca6a071dab3bcbd586c8a3a1f975` |
| OPT SKILL.md (`skill-1791618014068`) | `f0f5cfd616f3d9602d136e39f09f98cab2efb61b8a85212cd3c1ac0ff7b573d4` |
| POS SKILL.md (`skill-1791618006478`) | `543a05a47a46138cae1a41423e0970630f37d57ae6dd97c565ea65b777ba10bc` |
| optimizer.yaml | `a9f44c2606b95b42bfb70c1c9400d4e5c39c1ce83f564be5ae3ab746e9c09c83` |
| analysis_spec.md | `fa1ee6e4f2ec9dbf63e93d83c22773282e97680e4cf334ea37d5e4e4eb5fc3af` |
| run_optimizer.example.py | `92015189728c1f1ed3c72abe5ec24a1f0a19a321070edb4a9778649e3ce34229` |

## Пути на box

- Профиль: `/home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de/profile.json`
- OPT: `/home/box/agent-data/workflows/skill-1791618014068/SKILL.md`
- POS: `/home/box/agent-data/workflows/skill-1791618006478/SKILL.md`
- YAML: `/workspace/invest/portfolio/optimizer/config/optimizer.yaml` (`enabled: false`)
- SPEC: `/workspace/invest/portfolio/analysis_spec.md`

## Защита от drift

Перед apply Permission A: пересчитать sha256 тех же путей.  
Если любой хеш ≠ таблице выше — **стоп**, повторный аудит, патчи не применять.
