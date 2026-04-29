# Human Baseline Web App — Specification

**Status:** Active  
**Path:** `human_baseline/web_app.py`  
**Port:** `5055` (default)  
**Started:** `nohup .venv/bin/python human_baseline/web_app.py --port 5055 --ollama-url http://localhost:11435/v1 &`

---

## Purpose

Collect human-playing data from participants that mirrors the exact conditions of LLM benchmarks. The human acts as the **Seeker** (asking yes/no questions) while an LLM backend runs the **Oracle** and **Pruner** agents with the same prompts and configs as automated benchmarks. Outputs are saved in the standard `outputs/` structure, compatible with all analysis pipelines.

---

## Architecture

### Components

| Role | Agent | Model |
|------|-------|-------|
| Seeker | Human (web browser) | — |
| Oracle | `OracleAgent` + `LLMAdapter` | Qwen3:4b (Ollama, same as benchmark) |
| Pruner | `PrunerAgent` + `LLMAdapter` | Qwen3:4b (Ollama, same as benchmark) |

### Session Storage

Games are held **in-memory** in the global `GAMES` dict. A server restart clears all active sessions. The UI handles this gracefully with an expired-session banner (see § UI Behaviour).

### Config Loading

Configs are loaded at startup from `configs/human/*.yaml`. Keys are derived from filenames (without `.yaml`). Currently available configs cover:

- `geo_20_human_fo` / `po` — 20-city geography, FO/PO
- `geo_160_human_fo` / `po` / `hint` / `prior` — 160-city geography
- `objects_158_human_fo` / `po` / `hint` / `prior` — 158 objects
- `diseases_160_human_fo` / `po` / `hint` / `prior` — 160 diseases

Config files set: dataset type/path, oracle/pruner model + timeout (300s), observability mode, max turns (30), and experiment name.

---

## Routes

### Participant Flow

```
GET  /login                  → show login form (email pre-filled from cookie)
POST /login                  → validate email → assign config → create game → redirect to /game/<id>
                               also sets participant_email cookie (1 year)
GET  /game/<game_id>         → main game interface
GET  /new_game/<game_id>     → fresh game reusing same config → redirect to /game/<new_id>
```

### Researcher / Debug Flow

```
GET  /                       → config picker form (researcher mode; participants redirect to /login)
POST /start                  → create game from form → redirect to /game/<id>
GET  /game_create?config=<key>&seed=<N>  → create game + redirect (URL shortcut)
```

### API (called by game page JS)

```
POST /ask_oracle/<game_id>   → Phase 1: run Oracle on submitted question
                               Body: question (form field)
                               Returns JSON: {turn, max_turns, question, oracle_answer, game_over_flag, compliant}
                               Status: 200 | 400 (empty question / pruner pending) | 404 (session expired)

POST /ask_prune/<game_id>    → Phase 2: run Pruner, complete turn
                               Returns JSON: {turn, max_turns, question, oracle_answer, game_over_flag, compliant,
                                              h_before, h_after, info_gain, active_before, active_after,
                                              pruned_count, candidates_text, game_over, win, target_label,
                                              export_path}
                               Status: 200 | 400 (no pending oracle) | 404 (session expired)
                               Note: oracle_rationale and pruner_rationale intentionally omitted (reveal target)

POST /ask/<game_id>          → Legacy single-phase (Oracle + Pruner in one call). Kept for API clients.
                               Returns same fields as /ask_prune.

GET  /status/<game_id>       → Current game state (turn, obs_mode, turns_history, game_over, etc.)
GET  /participants            → Admin: participant list + config assignment counts (JSON)
```

---

## UI Behaviour

### Login Page (`templates/login.html`)

- Minimal centered card with email input.
- **Email pre-fill:** On GET, the `participant_email` cookie (if present) is read server-side and injected as `value=` on the input. The user can change it; no auto-login.
- On successful POST: email stored in Flask session + `participant_email` cookie (1-year expiry, SameSite=Lax).

### Game Page (`templates/game.html`)

**Layout (top → bottom):**

1. **Session Expired Banner** — hidden by default; shown when `ask_oracle` or `ask_prune` returns HTTP 404 (server restarted mid-game). Displays explanation + links to start a new game.
2. **Header bar** — game ID, observability mode badge (FO=blue / PO=red), dataset · N candidates · max turns, "↺ New Game" button.
3. **Stats bar** — Turn / Active Candidates / Entropy (bits) / Total IG.
4. **Candidates panel** — FO mode only; scrollable list of remaining candidates, updated live.
5. **Game Instructions panel** — collapsible `<details>` with the **seeker system prompt rendered as Markdown** (via [marked.js](https://cdn.jsdelivr.net/npm/marked/marked.min.js)). Styled for dark theme. Shows exact prompt the LLM seeker receives, with domain/max_turns substituted.
6. **Game Over panel** — hidden until game ends; shows 🎉 win or ❌ loss, target label, stats summary.
7. **Status bar** — live feedback during LLM calls (e.g. "Oracle answered: Yes. Pruner is analyzing…"); errors shown inline (no `alert()`).
8. **Input area** — question text field + Ask button + spinner. Enter key submits.
9. **Q&A history** — most recent turn first; each card shows Q/A + IG delta + entropy change.

**Two-phase turn flow:**
1. JS POSTs question to `/ask_oracle/<id>` → shows "Oracle answered: X. Pruner is analyzing…"
2. JS POSTs to `/ask_prune/<id>` → updates all stats and history card.
3. On 404 from either phase: shows expired-session banner, hides input.
4. On non-404 errors: shows inline error in status bar.

**Null/undefined guard:** All `.toFixed()` calls use `?? 0` fallback to prevent TypeError if a field is missing.

---

## Participant Assignment

`assign_config_for_participant(email)`:
- Returning participants always get the same config they were first assigned.
- New participants get the config with the fewest current assignments (round-robin by count).
- State persisted in `human_baseline/participants.json`.

`record_game_for_participant(email)` increments that participant's game count.

---

## Data Export

On game end, `export_game(game)` writes to:
```
outputs/models/s_human__o_<oracle>__p_<pruner>/<experiment_name>/conversations/<target_label>_<run_N>/
  metadata.json   — game summary (config, turns, win/loss, IG stats)
  turns.jsonl     — one JSON line per turn (question, oracle_answer, IG, entropy, pruner rationale)
```

Compatible with all analysis scripts (`src/analysis/`, `scripts/`).

---

## Tests

**Integration test suite:** `human_baseline/tests/test_web_app.py`

Run:
```bash
cd /path/to/infogainme
.venv/bin/python human_baseline/tests/test_web_app.py [--base-url http://localhost:5055]
```

Covers (44 assertions):
1. Health / Static Pages — login renders, branding present, email input present
2. Game Creation — game_create returns valid id, game page renders with prompt/banner elements
3. Turn Flow — oracle returns valid answer, prune returns IG/entropy, all fields present
4. Error Handling — empty question, no-pending-oracle, unknown game_id (404 JSON), double-oracle guard
5. Status Endpoint — returns correct fields, turn=0 on fresh game
6. Email Cookie — POST /login sets cookie, GET /login pre-fills value
7. New Game Flow — returns different game_id
8. Observability Modes — FO has candidates panel, PO does not
9. Multi-turn Smoke — 3-turn game completes without error

---

## Known Limitations

- **In-memory sessions:** Server restart clears all games. The UI shows a clear expired-session banner.
- **No auth:** The login email is trust-based; no password or verification.
- **Single-threaded Flask dev server:** Not suitable for concurrent production load. For real deployment, wrap with gunicorn/uwsgi.
- **No persistence of active games:** A game cannot be resumed after browser close + server restart.

---

## Requirements Summary (from Bryan, 2026-04-29)

- [x] Two-phase oracle → prune flow with live status feedback
- [x] Game system prompt (seeker prompt) visible to participant, rendered as formatted Markdown
- [x] Session expiry handled gracefully (expired-banner, not crash / `alert()`)
- [x] All `.toFixed()` calls null-safe
- [x] Email cookie: pre-fill login field; do not auto-login
- [x] Oracle/pruner timeouts: 300s
- [x] Case-insensitive pruner label matching
- [x] hint/prior configs (with seeker_pool_description)
- [x] Integration test suite (44 assertions, 100% pass)
