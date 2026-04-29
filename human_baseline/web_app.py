#!/usr/bin/env python3
"""Flask web app for human baseline data collection.

Uses the exact same game logic as human_benchmark_runner.py and the Orchestrator,
with the human providing questions via a web browser instead of CLI stdin.

Oracle and Pruner are LLM-powered (same agents as the automated benchmark).
Results are saved in the standard outputs/ structure for the analysis pipeline.

Participant flow:
  /login          — enter email, auto-assigned a config (balanced distribution)
  /               — config picker (for researchers/debug; login-aware)
  /game_create?config=<key>&seed=N  — skip form (debug)
  /new_game/<game_id>               — restart with same config (+ optional &seed=N)

URL params (debug / direct linking):
  /?config=<key>&seed=<int>         — pre-fill the start form
  /game_create?config=<key>&seed=N  — create + redirect directly (skip form)
"""

import copy
import csv
import json
import logging
import os
import random
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.middleware.proxy_fix import ProxyFix

# ── Project imports (resolve from repo root) ──────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_types import ObservabilityMode, Question, Answer, TurnState
from src.candidates import Candidate, CandidatePool
from src.entropy import Entropy
from src.agents.oracle import OracleAgent
from src.agents.pruner import PrunerAgent
from src.agents.llm_adapter import LLMAdapter
from src.agents.llm_config import LLMConfig
from src.domain.types import DomainConfig, GEO_DOMAIN, OBJECTS_DOMAIN, DISEASES_DOMAIN
from src.domain.geo.loader import load_geo_candidates
from src.domain.objects import load_flat_object_candidates
from src.domain.diseases import load_flat_disease_candidates
from src.prompts import get_seeker_system_prompt
from src.utils.config_loader import load_benchmark_config

# ── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/infogainme_web.log"),
    ],
)
logger = logging.getLogger(__name__)

# ── Flask app ─────────────────────────────────────────────────────────────
app = Flask(__name__)
# Honor X-Forwarded-Prefix from Caddy so url_for() generates correct paths
# under /infogainme/ when accessed through the Tailscale Funnel.
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)
app.secret_key = os.urandom(24)

# ── Configuration ─────────────────────────────────────────────────────────
# Local Ollama endpoint (Qwen3-8B on jarbas)
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
API_KEY = "ollama"

# Available human baseline configs (must exist in configs/human/)
AVAILABLE_CONFIGS = {}
configs_dir = PROJECT_ROOT / "configs" / "human"
if configs_dir.exists():
    for f in sorted(configs_dir.glob("*.yaml")):
        AVAILABLE_CONFIGS[f.stem] = str(f.relative_to(PROJECT_ROOT))

# ── Participant tracking ─────────────────────────────────────────────────
# Persisted to disk so participants survive server restarts.
PARTICIPANTS_FILE = PROJECT_ROOT / "human_baseline" / "participants.json"
PARTICIPANTS_LOCK = threading.Lock()

# Configs eligible for auto-assignment (all human configs, sorted for determinism)
AUTO_ASSIGN_CONFIGS = sorted(AVAILABLE_CONFIGS.keys())


def _load_participants() -> dict:
    """Load participant registry from disk. Returns {} on first run."""
    if PARTICIPANTS_FILE.exists():
        try:
            return json.loads(PARTICIPANTS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_participants(data: dict) -> None:
    """Persist participant registry to disk (atomic-ish write)."""
    PARTICIPANTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PARTICIPANTS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(PARTICIPANTS_FILE)


def assign_config_for_participant(email: str) -> str:
    """Assign a config key to a participant, balancing across all auto-assign configs.

    - If this email was seen before: return the same config they got last time.
    - Otherwise: pick the config with fewest assignments so far (round-robin).
    """
    with PARTICIPANTS_LOCK:
        data = _load_participants()
        participants = data.get("participants", {})

        email_lower = email.strip().lower()
        if email_lower in participants:
            # Returning participant — give them the same config
            return participants[email_lower]["config"]

        # New participant — pick least-assigned config
        counts = data.get("config_counts", {k: 0 for k in AUTO_ASSIGN_CONFIGS})
        # Make sure all keys exist (handles new configs added later)
        for k in AUTO_ASSIGN_CONFIGS:
            counts.setdefault(k, 0)

        # Pick config with lowest count; break ties by sorted order (deterministic)
        assigned = min(AUTO_ASSIGN_CONFIGS, key=lambda k: (counts.get(k, 0), k))

        # Record participant
        counts[assigned] = counts.get(assigned, 0) + 1
        participants[email_lower] = {
            "email": email.strip(),
            "config": assigned,
            "assigned_at": datetime.now().isoformat(),
            "games": 0,
        }
        data["participants"] = participants
        data["config_counts"] = counts
        _save_participants(data)

        logger.info("New participant: %s → config=%s", email_lower, assigned)
        return assigned


def record_game_for_participant(email: str) -> None:
    """Increment the games counter for a returning participant."""
    if not email:
        return
    with PARTICIPANTS_LOCK:
        data = _load_participants()
        participants = data.get("participants", {})
        email_lower = email.strip().lower()
        if email_lower in participants:
            participants[email_lower]["games"] = participants[email_lower].get("games", 0) + 1
            data["participants"] = participants
            _save_participants(data)


# ── In-memory game storage ────────────────────────────────────────────────
GAMES: dict[str, "GameSession"] = {}
GAMES_LOCK = threading.Lock()


def _safe_name(text: str) -> str:
    return text.replace("/", "-").replace("\\", "-").replace(":", "-").replace(" ", "_")


class GameSession:
    """Tracks state for one human game — mirrors Orchestrator internals."""

    def __init__(
        self,
        *,
        pool: CandidatePool,
        oracle: OracleAgent,
        pruner: PrunerAgent,
        entropy: Entropy,
        target: Candidate,
        max_turns: int,
        obs_mode: ObservabilityMode,
        domain_config: DomainConfig,
        config_key: str,
        benchmark_config,
        dataset_type: str,
        participant_email: str = "",
    ):
        self.id = str(uuid.uuid4())[:8]
        self.pool = pool
        self.oracle = oracle
        self.pruner = pruner
        self.entropy = entropy
        self.target = target
        self.max_turns = max_turns
        self.obs_mode = obs_mode
        self.domain_config = domain_config
        self.config_key = config_key
        self.benchmark_config = benchmark_config
        self.dataset_type = dataset_type
        self.participant_email = participant_email
        self.turns: list[TurnState] = []
        self.current_turn = 0
        self.game_over = False
        self.win = False
        self.created_at = datetime.now()
        self.n_candidates = len(pool.candidates)

        # Two-phase ask: stores oracle result between /ask_oracle and /ask_prune
        self.pending_question: Question | None = None
        self.pending_oracle_answer: Answer | None = None
        self.pending_turn_num: int | None = None
        self.pending_h_before: float | None = None
        self.pending_active_before: int | None = None
        self.pending_turn_start: datetime | None = None


def _load_dataset(config: dict) -> tuple[CandidatePool, str]:
    """Load dataset — same logic as human_benchmark_runner.py."""
    dataset_cfg = config.get("dataset", {})
    dataset_type = dataset_cfg.get("type", "geo")
    csv_path = PROJECT_ROOT / dataset_cfg["csv_path"]

    if dataset_type == "objects":
        pool, _ = load_flat_object_candidates(csv_path=csv_path)
    elif dataset_type == "diseases":
        pool, _ = load_flat_disease_candidates(csv_path=csv_path)
    else:
        pool, _ = load_geo_candidates(csv_path=csv_path)

    return pool, dataset_type


def create_game(config_key: str, seed: int | None = None, participant_email: str = "") -> GameSession:
    """Create a new game session using the project's standard config pipeline.

    Only the LLM endpoint is changed to local Ollama. Everything else
    (prompts, temperature, max_tokens, timeout) comes from the YAML config.
    """
    config_path = PROJECT_ROOT / AVAILABLE_CONFIGS[config_key]

    benchmark_config, config = load_benchmark_config(config_path, API_KEY)

    # Redirect oracle/pruner to local Ollama — the ONLY change from default flow
    for cfg in [benchmark_config.oracle_config, benchmark_config.pruner_config]:
        cfg.base_url = OLLAMA_BASE_URL
        cfg.model = OLLAMA_MODEL
        cfg.api_key = API_KEY

    # Load dataset
    pool, dataset_type = _load_dataset(config)

    # Pick random target (same as human_benchmark_runner.py)
    rng = random.Random(seed)
    all_candidates = list(pool.candidates)
    target = rng.choice(all_candidates)

    # Deep copy pool for this game
    game_pool = copy.deepcopy(pool)

    # Create agents — mirrors Orchestrator.from_target() exactly
    domain_config = benchmark_config.domain_config or GEO_DOMAIN

    oracle_adapter = LLMAdapter(benchmark_config.oracle_config, save_reasoning=True)
    pruner_adapter = LLMAdapter(benchmark_config.pruner_config, save_reasoning=True)

    oracle = OracleAgent(
        llm_adapter=oracle_adapter,
        target=target,
        domain_config=domain_config,
    )

    pruner = PrunerAgent(
        llm_adapter=pruner_adapter,
        domain_config=domain_config,
    )

    entropy = Entropy()

    game = GameSession(
        pool=game_pool,
        oracle=oracle,
        pruner=pruner,
        entropy=entropy,
        target=target,
        max_turns=benchmark_config.max_turns,
        obs_mode=benchmark_config.observability_mode,
        domain_config=domain_config,
        config_key=config_key,
        benchmark_config=benchmark_config,
        dataset_type=dataset_type,
        participant_email=participant_email,
    )

    logger.info(
        "Game %s created | config=%s | target=%s | pool=%d | mode=%s",
        game.id, config_key, target.label, len(all_candidates),
        benchmark_config.observability_mode.name,
    )

    return game


def export_game(game: GameSession) -> Path:
    """Export game results in the standard benchmark format.

    Writes to outputs/ in the same structure as BenchmarkRunner so the
    standard analysis pipeline (analyze_results.sh etc.) can process them.
    """
    output_base = PROJECT_ROOT / "outputs"
    bc = game.benchmark_config

    seeker_name = _safe_name("human")
    oracle_name = _safe_name(bc.oracle_config.model)
    pruner_name = _safe_name(bc.pruner_config.model)
    exp_name = _safe_name(bc.experiment_name or "default")

    exp_dir = output_base / f"models/s_{seeker_name}__o_{oracle_name}__p_{pruner_name}" / exp_name
    conv_dir = exp_dir / "conversations" / _safe_name(game.target.id)
    conv_dir.mkdir(parents=True, exist_ok=True)

    # 1. turns.jsonl
    with (conv_dir / "turns.jsonl").open("w", encoding="utf-8") as f:
        for ts in game.turns:
            f.write(json.dumps(ts.to_export_dict(), ensure_ascii=False) + "\n")

    # 2. metadata.json
    summary = _game_summary(game)
    win = game.win
    compliance_rate = (
        sum(1 for t in game.turns if t.answer.compliant) / len(game.turns)
    ) if game.turns else 0.0

    total_pruned = sum(t.pruned_count for t in game.turns)
    initial_count = len(game.pool.candidates)
    final_active = len(game.pool.get_active())

    metadata = {
        "game_id": game.id,
        "timestamp": game.created_at.isoformat(),
        "participant_email": game.participant_email or None,
        "target": {
            "id": game.target.id,
            "label": game.target.label,
            "attrs": dict(game.target.attrs),
        },
        "config": {
            "experiment_name": bc.experiment_name,
            "observability_mode": game.obs_mode.name,
            "max_turns": game.max_turns,
            "models": {
                "seeker": "human",
                "oracle": bc.oracle_config.model,
                "pruner": bc.pruner_config.model,
            },
        },
        "results": {
            "turns_played": len(game.turns),
            "win": win,
            "h_start": summary["h_start"],
            "h_end": summary["h_end"],
            "total_info_gain": summary["total_info_gain"],
            "avg_info_gain_per_turn": summary["avg_info_gain_per_turn"],
            "compliance_rate": round(compliance_rate, 4),
            "final_active_candidates": final_active,
        },
        "pool_stats": {
            "initial_candidates": initial_count,
            "final_candidates": final_active,
            "total_pruned": total_pruned,
            "pruning_efficiency": round(total_pruned / initial_count, 4) if initial_count > 0 else 0,
        },
    }

    with (conv_dir / "metadata.json").open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # 3. oracle.json (conversation history)
    oracle_data = {
        "agent_type": "oracle",
        "config": {
            "model": bc.oracle_config.model,
            "temperature": bc.oracle_config.temperature,
            "max_tokens": bc.oracle_config.max_tokens,
            "base_url": bc.oracle_config.base_url,
        },
        "target": {
            "id": game.oracle._target.id,
            "label": game.oracle._target.label,
            "attrs": dict(game.oracle._target.attrs),
        },
        "total_messages": len(game.oracle._llm_adapter.history),
        "history": game.oracle._llm_adapter.history,
        "reasoning_history": game.oracle._llm_adapter.reasoning_history,
    }
    with (conv_dir / "oracle.json").open("w", encoding="utf-8") as f:
        json.dump(oracle_data, f, indent=2, ensure_ascii=False)

    # 4. pruner.json
    pruner_data = {
        "agent_type": "pruner",
        "config": {
            "model": bc.pruner_config.model,
            "temperature": bc.pruner_config.temperature,
            "max_tokens": bc.pruner_config.max_tokens,
            "base_url": bc.pruner_config.base_url,
        },
        "save_history": game.pruner.llm_adapter._save_history,
        "total_calls": len(game.turns),
    }
    if game.pruner.llm_adapter._save_history:
        pruner_data["total_messages"] = len(game.pruner.llm_adapter.history)
        pruner_data["history"] = game.pruner.llm_adapter.history
        pruner_data["reasoning_history"] = game.pruner.llm_adapter.reasoning_history
    with (conv_dir / "pruner.json").open("w", encoding="utf-8") as f:
        json.dump(pruner_data, f, indent=2, ensure_ascii=False)

    # 5. seeker.json (human — record Q&A pairs)
    seeker_history = []
    for ts in game.turns:
        seeker_history.append({"role": "assistant", "content": ts.question.text})
        seeker_history.append({
            "role": "user",
            "content": f"[Turn {ts.turn_index}/{game.max_turns}] [Oracle] {ts.answer.text}",
        })
    seeker_data = {
        "agent_type": "seeker",
        "config": {"model": "human", "temperature": None, "max_tokens": None, "base_url": None},
        "observability_mode": game.obs_mode.name,
        "total_messages": len(seeker_history),
        "history": seeker_history,
        "reasoning_history": [],
    }
    with (conv_dir / "seeker.json").open("w", encoding="utf-8") as f:
        json.dump(seeker_data, f, indent=2, ensure_ascii=False)

    # 6. Append to runs.csv (same as BenchmarkRunner)
    csv_path = exp_dir / "runs.csv"
    write_header = not csv_path.exists()
    with csv_path.open("a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow([
                "experiment_name", "seeker_model", "oracle_model", "pruner_model",
                "observability", "max_turns", "target_id", "target_label",
                "run_index", "turns", "h_start", "h_end", "total_info_gain",
                "avg_info_gain_per_turn", "win", "compliance_rate", "conversation_path",
            ])
        writer.writerow([
            bc.experiment_name or "default",
            "human",
            bc.oracle_config.model,
            bc.pruner_config.model,
            game.obs_mode.name,
            game.max_turns,
            game.target.id,
            game.target.label,
            1,
            summary["turns"],
            summary["h_start"],
            summary["h_end"],
            summary["total_info_gain"],
            summary["avg_info_gain_per_turn"],
            int(win),
            round(compliance_rate, 4),
            str(conv_dir.relative_to(output_base)),
        ])

    logger.info("Game %s exported to %s", game.id, conv_dir)
    return conv_dir


def _game_summary(game: GameSession) -> dict:
    """Compute game summary — same as Orchestrator.get_summary()."""
    total_ig = sum(t.info_gain for t in game.turns)
    n = len(game.turns)
    return {
        "turns": n,
        "h_start": game.turns[0].h_before if game.turns else None,
        "h_end": game.turns[-1].h_after if game.turns else None,
        "total_info_gain": total_ig,
        "avg_info_gain_per_turn": total_ig / n if n > 0 else 0.0,
    }


# ── Routes ────────────────────────────────────────────────────────────────


@app.route("/login", methods=["GET", "POST"])
def login():
    """Participant login page — accept email, auto-assign config, start game.

    GET:  Show login form.
    POST: Validate email, assign config (balanced), create game, redirect to game.
    """
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        if not email or "@" not in email:
            return render_template("login.html", error="Please enter a valid email address.")

        # Assign config (balanced) — same config returned for returning participants
        config_key = assign_config_for_participant(email)
        if config_key not in AVAILABLE_CONFIGS:
            # Fallback if config was removed since participant registered
            config_key = next(iter(AVAILABLE_CONFIGS))

        # Store email in Flask session
        session["participant_email"] = email
        session["participant_config"] = config_key

        # Create game directly (no form step for participants)
        try:
            game = create_game(config_key, participant_email=email)
        except Exception as e:
            logger.error("Failed to create game for %s (config=%s): %s", email, config_key, e)
            return render_template("login.html", error=f"Failed to start game: {e}")

        with GAMES_LOCK:
            GAMES[game.id] = game

        record_game_for_participant(email)
        logger.info("Participant %s assigned config=%s, game=%s", email, config_key, game.id)
        return redirect(url_for("game_page", game_id=game.id))

    # GET — show login form
    return render_template("login.html", error=None)


@app.route("/")
def index():
    """Landing page — pick a config and start a game.

    Participants (no explicit config param) are redirected to /login for
    auto-assignment.  Researchers with explicit ?config= or ?seed= params
    go directly to the form (debug / researcher mode).

    Optional URL params to pre-fill form:
      ?config=geo_160_human_fo   — pre-select a config (researcher mode)
      ?seed=42                   — pre-fill seed
    """
    preselect_config = request.args.get("config", "")
    preselect_seed = request.args.get("seed", "")

    # If no explicit config override — redirect participants to login
    if not preselect_config and not preselect_seed:
        return redirect(url_for("login"))

    return render_template(
        "index.html",
        configs=AVAILABLE_CONFIGS,
        preselect_config=preselect_config,
        preselect_seed=preselect_seed,
    )


@app.route("/game_create")
def game_create():
    """Create a new game directly from URL parameters and redirect to game page.

    Useful for debugging or deep-linking to a specific config/seed without
    going through the form.

    URL params:
      ?config=geo_160_human_fo   — required: config key
      ?seed=42                   — optional: random seed (omit for random)

    Returns 400 JSON with available configs if config is invalid.
    """
    config_key = request.args.get("config", "")
    if config_key not in AVAILABLE_CONFIGS:
        return jsonify({
            "error": "Invalid or missing config parameter.",
            "available_configs": sorted(AVAILABLE_CONFIGS.keys()),
            "example": f"?config={next(iter(AVAILABLE_CONFIGS), 'geo_160_human_fo')}&seed=42",
        }), 400

    seed = request.args.get("seed")
    seed = int(seed) if seed and seed.strip().lstrip("-").isdigit() else None

    game = create_game(config_key, seed=seed, participant_email=session.get("participant_email", ""))
    with GAMES_LOCK:
        GAMES[game.id] = game

    return redirect(url_for("game_page", game_id=game.id))


@app.route("/start", methods=["POST"])
def start():
    """Create a new game and redirect to the game page (researcher/form flow)."""
    config_key = request.form.get("config")
    if config_key not in AVAILABLE_CONFIGS:
        return "Invalid config", 400

    seed = request.form.get("seed")
    seed = int(seed) if seed and seed.strip() else None

    # Carry participant email from session if present
    email = session.get("participant_email", "")
    game = create_game(config_key, seed=seed, participant_email=email)

    with GAMES_LOCK:
        GAMES[game.id] = game

    if email:
        record_game_for_participant(email)

    return redirect(url_for("game_page", game_id=game.id))


@app.route("/new_game/<game_id>")
def new_game(game_id):
    """Start a new game reusing the config from an existing game.

    Optional URL params:
      ?seed=42   — override seed (default: random)
    """
    old_game = GAMES.get(game_id)
    config_key = old_game.config_key if old_game else request.args.get("config", "")

    if config_key not in AVAILABLE_CONFIGS:
        return redirect(url_for("index"))

    seed = request.args.get("seed")
    seed = int(seed) if seed and seed.strip().lstrip("-").isdigit() else None

    # Carry participant email from session or from old game
    email = session.get("participant_email", "") or (old_game.participant_email if old_game else "")
    game = create_game(config_key, seed=seed, participant_email=email)
    with GAMES_LOCK:
        GAMES[game.id] = game

    if email:
        record_game_for_participant(email)

    return redirect(url_for("game_page", game_id=game.id))


@app.route("/game/<game_id>")
def game_page(game_id):
    """Render the game interface."""
    game = GAMES.get(game_id)
    if not game:
        # Redirect to index with a gentle error message instead of bare 404
        return redirect(url_for("index", _anchor="session-expired"))

    active = game.pool.get_active()
    candidates_text = ", ".join(c.label for c in sorted(active, key=lambda c: c.label))

    seeker_prompt = get_seeker_system_prompt(
        target_noun=game.domain_config.target_noun,
        domain_description=game.domain_config.domain_description,
        max_turns=game.max_turns,
        observability_mode=game.obs_mode.value,
        pool_description=game.domain_config.seeker_pool_description,
    )

    return render_template(
        "game.html",
        game=game,
        candidates_text=candidates_text,
        active_count=len(active),
        seeker_prompt=seeker_prompt,
    )


@app.route("/ask_oracle/<game_id>", methods=["POST"])
def ask_oracle(game_id):
    """Phase 1 of a two-phase ask: run the Oracle and return its answer.

    The client should display "Oracle answered: <X>. Pruner is analyzing..."
    and then immediately call /ask_prune/<game_id> to complete the turn.

    This split gives the player real-time feedback even when the Pruner
    takes a long time with many candidates.
    """
    game = GAMES.get(game_id)
    if not game:
        return jsonify({"error": "Game not found (session may have expired — start a new game)"}), 404
    if game.game_over:
        return jsonify({"error": "Game is already over"}), 400
    if game.pending_oracle_answer is not None:
        return jsonify({"error": "Pruner step still pending — call /ask_prune first"}), 400

    question_text = request.form.get("question", "").strip()
    if not question_text:
        return jsonify({"error": "Question cannot be empty"}), 400

    turn = game.current_turn + 1
    active_candidates = game.pool.get_active()
    active_count_before = len(active_candidates)
    h_before = game.entropy.compute(active_count_before)

    question = Question(text=question_text)

    try:
        game.oracle.add_seeker_question(question)
        answer = game.oracle.answer_seeker()
    except Exception as e:
        logger.error("Oracle error (game %s, turn %d): %s", game_id, turn, e)
        return jsonify({"error": f"Oracle error: {e}"}), 500

    # Store pending state for the prune step
    game.pending_question = question
    game.pending_oracle_answer = answer
    game.pending_turn_num = turn
    game.pending_h_before = h_before
    game.pending_active_before = active_count_before
    game.pending_turn_start = datetime.now()

    logger.info(
        "Game %s | turn %d | oracle answered: %s (game_over=%s)",
        game_id, turn, answer.text, answer.game_over,
    )

    return jsonify({
        "turn": turn,
        "max_turns": game.max_turns,
        "question": question_text,
        "oracle_answer": answer.text,
        # oracle_rationale intentionally omitted — it reveals the target
        "game_over_flag": answer.game_over,
        "compliant": answer.compliant,
    })


@app.route("/ask_prune/<game_id>", methods=["POST"])
def ask_prune(game_id):
    """Phase 2 of a two-phase ask: run the Pruner and complete the turn.

    Must be called after /ask_oracle/<game_id>. Returns the full turn result
    including pruner stats, entropy update, and game-over status.
    """
    game = GAMES.get(game_id)
    if not game:
        return jsonify({"error": "Game not found (session may have expired — start a new game)"}), 404
    if game.pending_oracle_answer is None:
        return jsonify({"error": "No oracle result pending — call /ask_oracle first"}), 400

    # Retrieve and clear pending state atomically
    question = game.pending_question
    answer = game.pending_oracle_answer
    turn = game.pending_turn_num
    h_before = game.pending_h_before
    active_count_before = game.pending_active_before
    turn_start = game.pending_turn_start

    game.pending_question = None
    game.pending_oracle_answer = None
    game.pending_turn_num = None
    game.pending_h_before = None
    game.pending_active_before = None
    game.pending_turn_start = None

    # Now commit the turn counter
    game.current_turn = turn

    # ── Pruner ────────────────────────────────────────────────────────────
    try:
        pruning_result = game.pruner.analyze_and_prune(
            candidate_pool=game.pool,
            turn_index=turn,
            question=question,
            answer=answer,
            target_label=game.target.label,
        )
        pruned_count = 0
        if pruning_result.pruned_labels:
            pruned_count = game.pool.prune(pruning_result.pruned_labels)
    except Exception as e:
        logger.error("Pruner error (game %s, turn %d): %s", game_id, turn, e)
        from src.data_types import PruningResult
        pruning_result = PruningResult(pruned_labels=set(), rationale=f"error: {e}")
        pruned_count = 0

    # ── Entropy ───────────────────────────────────────────────────────────
    active_count_after = len(game.pool.get_active())
    if answer.game_over:
        h_after = 0.0
    else:
        h_after = game.entropy.compute(active_count_after)

    info_gain = game.entropy.info_gain(h_before, h_after)

    turn_end = datetime.now()
    duration = (turn_end - turn_start).total_seconds()

    # ── Record turn ───────────────────────────────────────────────────────
    active_candidates = game.pool.get_active()  # snapshot before this turn started
    turn_state = TurnState(
        turn_index=turn,
        h_before=h_before,
        h_after=h_after,
        info_gain=info_gain,
        pruned_count=pruned_count,
        question=question,
        answer=answer,
        pruning_result=pruning_result,
        active_candidates_before=active_count_before,
        active_candidates_after=active_count_after,
        timestamp_start=turn_start.isoformat(),
        timestamp_end=turn_end.isoformat(),
        duration_seconds=round(duration, 6),
        candidates_snapshot=[c.label for c in game.pool.get_active()],
    )
    game.turns.append(turn_state)

    # ── Game end conditions ───────────────────────────────────────────────
    if answer.game_over:
        game.game_over = True
        game.win = True
        logger.info("Game %s WON in %d turns (target: %s)", game_id, turn, game.target.label)
    elif turn >= game.max_turns:
        game.game_over = True
        game.win = False
        logger.info("Game %s LOST — max turns reached (target: %s)", game_id, game.target.label)

    # ── Auto-export on game end ───────────────────────────────────────────
    export_path = None
    if game.game_over:
        try:
            export_path = str(export_game(game))
        except Exception as e:
            logger.error("Export failed for game %s: %s", game_id, e)

    # ── Build response ────────────────────────────────────────────────────
    active_after = game.pool.get_active()
    candidates_text = ", ".join(c.label for c in sorted(active_after, key=lambda c: c.label))

    return jsonify({
        "turn": turn,
        "max_turns": game.max_turns,
        "question": question.text,
        "oracle_answer": answer.text,
        # oracle_rationale intentionally omitted — it reveals the target
        "game_over_flag": answer.game_over,
        "compliant": answer.compliant,
        "h_before": round(h_before, 4),
        "h_after": round(h_after, 4),
        "info_gain": round(info_gain, 4),
        "active_before": active_count_before,
        "active_after": active_count_after,
        "pruned_count": pruned_count,
        # pruner_rationale intentionally omitted — may reference the target
        "candidates_text": candidates_text,
        "game_over": game.game_over,
        "win": game.win,
        "target_label": game.target.label if game.game_over else None,
        "export_path": export_path,
    })


@app.route("/ask/<game_id>", methods=["POST"])
def ask(game_id):
    """Single-phase ask (legacy): runs Oracle + Pruner in one blocking request.

    Prefer the two-phase /ask_oracle → /ask_prune flow for better UX.
    This endpoint is kept for backward compatibility and API clients.
    """
    game = GAMES.get(game_id)
    if not game:
        return jsonify({"error": "Game not found (session may have expired — start a new game)"}), 404
    if game.game_over:
        return jsonify({"error": "Game is already over"}), 400

    question_text = request.form.get("question", "").strip()
    if not question_text:
        return jsonify({"error": "Question cannot be empty"}), 400

    game.current_turn += 1
    turn = game.current_turn
    turn_start = datetime.now()

    # ── Exactly mirrors Orchestrator.run() ────────────────────────────

    active_candidates = game.pool.get_active()
    active_count_before = len(active_candidates)
    h_before = game.entropy.compute(active_count_before)

    # Seeker's question
    question = Question(text=question_text)

    # Oracle answers
    try:
        game.oracle.add_seeker_question(question)
        answer = game.oracle.answer_seeker()
    except Exception as e:
        logger.error("Oracle error (game %s, turn %d): %s", game_id, turn, e)
        game.current_turn -= 1
        return jsonify({"error": f"Oracle error: {e}"}), 500

    # Pruner prunes
    try:
        pruning_result = game.pruner.analyze_and_prune(
            candidate_pool=game.pool,
            turn_index=turn,
            question=question,
            answer=answer,
            target_label=game.target.label,
        )
        pruned_count = 0
        if pruning_result.pruned_labels:
            pruned_count = game.pool.prune(pruning_result.pruned_labels)
    except Exception as e:
        logger.error("Pruner error (game %s, turn %d): %s", game_id, turn, e)
        from src.data_types import PruningResult
        pruning_result = PruningResult(pruned_labels=set(), rationale=f"error: {e}")
        pruned_count = 0

    # Entropy after pruning
    active_count_after = len(game.pool.get_active())
    if answer.game_over:
        h_after = 0.0
    else:
        h_after = game.entropy.compute(active_count_after)

    info_gain = game.entropy.info_gain(h_before, h_after)

    turn_end = datetime.now()
    duration = (turn_end - turn_start).total_seconds()

    # Record turn state — same as Orchestrator
    turn_state = TurnState(
        turn_index=turn,
        h_before=h_before,
        h_after=h_after,
        info_gain=info_gain,
        pruned_count=pruned_count,
        question=question,
        answer=answer,
        pruning_result=pruning_result,
        active_candidates_before=active_count_before,
        active_candidates_after=active_count_after,
        timestamp_start=turn_start.isoformat(),
        timestamp_end=turn_end.isoformat(),
        duration_seconds=round(duration, 6),
        candidates_snapshot=[c.label for c in active_candidates],
    )
    game.turns.append(turn_state)

    # ── End of Orchestrator.run() mirror ──────────────────────────────

    # Check game end conditions
    if answer.game_over:
        game.game_over = True
        game.win = True
        logger.info("Game %s WON in %d turns (target: %s)", game_id, turn, game.target.label)
    elif turn >= game.max_turns:
        game.game_over = True
        game.win = False
        logger.info("Game %s LOST — max turns reached (target: %s)", game_id, game.target.label)

    # Auto-export on game end
    export_path = None
    if game.game_over:
        try:
            export_path = str(export_game(game))
        except Exception as e:
            logger.error("Export failed for game %s: %s", game_id, e)

    # Updated candidates for FO mode
    active_after = game.pool.get_active()
    candidates_text = ", ".join(c.label for c in sorted(active_after, key=lambda c: c.label))

    return jsonify({
        "turn": turn,
        "max_turns": game.max_turns,
        "question": question_text,
        "oracle_answer": answer.text,
        # oracle_rationale intentionally omitted — it reveals the target
        "game_over_flag": answer.game_over,
        "compliant": answer.compliant,
        "h_before": round(h_before, 4),
        "h_after": round(h_after, 4),
        "info_gain": round(info_gain, 4),
        "active_before": active_count_before,
        "active_after": active_count_after,
        "pruned_count": pruned_count,
        # pruner_rationale intentionally omitted — may reference the target
        "candidates_text": candidates_text,
        "game_over": game.game_over,
        "win": game.win,
        "target_label": game.target.label if game.game_over else None,
        "export_path": export_path,
    })


@app.route("/status/<game_id>")
def status(game_id):
    """Return current game state as JSON."""
    game = GAMES.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    active = game.pool.get_active()
    return jsonify({
        "game_id": game.id,
        "config": game.config_key,
        "participant_email": game.participant_email or None,
        "turn": game.current_turn,
        "max_turns": game.max_turns,
        "active_candidates": len(active),
        "total_candidates": game.n_candidates,
        "game_over": game.game_over,
        "win": game.win,
        "obs_mode": game.obs_mode.name,
        "turns_history": [
            {
                "turn": t.turn_index,
                "question": t.question.text,
                "answer": t.answer.text,
                "info_gain": round(t.info_gain, 4),
                "active_after": t.active_candidates_after,
            }
            for t in game.turns
        ],
    })


@app.route("/participants")
def participants_admin():
    """Admin view: list all registered participants and their config assignments.

    Returns JSON with participant list, config counts, and assignment balance.
    For researcher use only — not linked from participant UI.
    """
    with PARTICIPANTS_LOCK:
        data = _load_participants()
    participants = data.get("participants", {})
    counts = data.get("config_counts", {})
    return jsonify({
        "total_participants": len(participants),
        "config_counts": counts,
        "participants": [
            {
                "email": v["email"],
                "config": v["config"],
                "assigned_at": v["assigned_at"],
                "games": v.get("games", 0),
            }
            for v in sorted(participants.values(), key=lambda x: x["assigned_at"], reverse=True)
        ],
    })


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="InfoGainme Human Baseline Web App")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=5050, help="Port")
    parser.add_argument("--debug", action="store_true", help="Flask debug mode")
    parser.add_argument(
        "--ollama-url", default=None,
        help="Override Ollama base URL (default: http://localhost:11434/v1)",
    )
    parser.add_argument(
        "--ollama-model", default=None,
        help="Override Ollama model name (default: qwen3:8b)",
    )
    args = parser.parse_args()

    if args.ollama_url:
        OLLAMA_BASE_URL = args.ollama_url
    if args.ollama_model:
        OLLAMA_MODEL = args.ollama_model

    logger.info("Starting InfoGainme Human Baseline Web App")
    logger.info("  Ollama: %s (model: %s)", OLLAMA_BASE_URL, OLLAMA_MODEL)
    logger.info("  Configs: %s", list(AVAILABLE_CONFIGS.keys()))

    app.run(host=args.host, port=args.port, debug=args.debug)
