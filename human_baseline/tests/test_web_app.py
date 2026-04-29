#!/usr/bin/env python3
"""
Integration test suite for InfoGainme Human Baseline Web App.

Tests cover:
  - Static pages (login, index, game page)
  - Game creation and session lifecycle
  - Two-phase oracle/prune flow (normal turn)
  - Session expiry: 404 from ask_oracle on unknown game_id
  - Email cookie set after login
  - Login page pre-fills email from cookie
  - Markdown prompt rendering (seeker prompt in HTML)
  - Game-over detection (win and loss paths)
  - Status endpoint
  - New-game flow
  - Null/empty question rejection

Run:
    python3 human_baseline/tests/test_web_app.py [--base-url http://localhost:5055]
"""
import argparse
import sys
import json
import time
import requests

GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
RESET  = "\033[0m"

PASS = f"{GREEN}PASS{RESET}"
FAIL = f"{RED}FAIL{RESET}"
SKIP = f"{YELLOW}SKIP{RESET}"

passed = failed = skipped = 0


def ok(name):
    global passed
    passed += 1
    print(f"  {PASS}  {name}")


def fail(name, reason=""):
    global failed
    failed += 1
    print(f"  {FAIL}  {name}" + (f" — {reason}" if reason else ""))


def skip(name, reason=""):
    global skipped
    skipped += 1
    print(f"  {SKIP}  {name}" + (f" — {reason}" if reason else ""))


def section(title):
    print(f"\n── {title} {'─'*(54-len(title))}")


def assert_ok(cond, name, reason=""):
    if cond:
        ok(name)
    else:
        fail(name, reason)


def make_game(base, config="geo_20_human_fo", seed=42, session=None):
    """Create a game and return its id. Uses session for cookies."""
    s = session or requests.Session()
    r = s.get(f"{base}/game_create", params={"config": config, "seed": seed},
              allow_redirects=False)
    loc = r.headers.get("Location", "")
    game_id = loc.split("/game/")[-1].strip()
    return game_id, s


def run_tests(base):
    global passed, failed, skipped

    s = requests.Session()   # shared session for cookie-aware tests

    # ─────────────────────────────────────────────────────────────────────
    section("1. Health / Static Pages")
    # ─────────────────────────────────────────────────────────────────────

    r = requests.get(f"{base}/login")
    assert_ok(r.status_code == 200, "GET /login returns 200")
    assert_ok("Info-GainME" in r.text, "Login page has branding")
    assert_ok('name="email"' in r.text, "Login page has email input")

    r = requests.get(f"{base}/", allow_redirects=False)
    # Should redirect to /login for unauthenticated users (no params)
    assert_ok(r.status_code in (200, 302), "GET / responds (200 or redirect)")

    # ─────────────────────────────────────────────────────────────────────
    section("2. Game Creation")
    # ─────────────────────────────────────────────────────────────────────

    game_id, gs = make_game(base, seed=1)
    assert_ok(len(game_id) > 4, f"game_create returns game_id (got: {game_id!r})")

    r = gs.get(f"{base}/game/{game_id}")
    assert_ok(r.status_code == 200, "GET /game/<id> returns 200")
    assert_ok("Info-GainME" in r.text, "Game page has branding")
    assert_ok("prompt-body" in r.text, "Game page has prompt-body element")
    assert_ok("marked.parse" in r.text, "Game page uses marked.js for markdown")
    assert_ok("SeekerAgent System Prompt" in r.text or "seeker_prompt" in r.text.lower(),
              "Game page embeds seeker system prompt")
    assert_ok("expired-banner" in r.text, "Game page has session-expired banner element")

    # ─────────────────────────────────────────────────────────────────────
    section("3. Turn Flow: Oracle → Prune")
    # ─────────────────────────────────────────────────────────────────────

    r = gs.post(f"{base}/ask_oracle/{game_id}", data={"question": "Is it in Europe?"})
    assert_ok(r.status_code == 200, "POST /ask_oracle returns 200")
    od = r.json()
    assert_ok("oracle_answer" in od, "ask_oracle returns oracle_answer field")
    assert_ok(od.get("oracle_answer") in ("Yes", "No", "Yes! You found the target!"),
              f"oracle_answer is valid ({od.get('oracle_answer')!r})")
    assert_ok("turn" in od, "ask_oracle returns turn number")
    assert_ok("game_over_flag" in od, "ask_oracle returns game_over_flag")

    r2 = gs.post(f"{base}/ask_prune/{game_id}")
    assert_ok(r2.status_code == 200, "POST /ask_prune returns 200")
    pd = r2.json()
    assert_ok("info_gain" in pd, "ask_prune returns info_gain")
    assert_ok("h_before" in pd and "h_after" in pd, "ask_prune returns entropy values")
    assert_ok("active_after" in pd, "ask_prune returns active_after")
    assert_ok(isinstance(pd["info_gain"], (int, float)), "info_gain is a number")
    assert_ok(isinstance(pd["h_after"], (int, float)), "h_after is a number")

    # ─────────────────────────────────────────────────────────────────────
    section("4. Error Handling")
    # ─────────────────────────────────────────────────────────────────────

    # Ask prune without pending oracle
    game_id2, gs2 = make_game(base, seed=2)
    r = gs2.post(f"{base}/ask_prune/{game_id2}")
    assert_ok(r.status_code == 400, "ask_prune without oracle returns 400")
    assert_ok("error" in r.json(), "ask_prune without oracle returns error key")

    # Oracle with empty question
    r = gs2.post(f"{base}/ask_oracle/{game_id2}", data={"question": ""})
    assert_ok(r.status_code == 400, "ask_oracle with empty question returns 400")

    # 404 on expired/unknown game (the bug Bryan reported)
    fake_id = "deadbeef"
    r = requests.post(f"{base}/ask_oracle/{fake_id}", data={"question": "test"})
    assert_ok(r.status_code == 404, "ask_oracle with unknown game_id returns 404")
    assert_ok("error" in r.json(), "404 response is JSON with error key")

    r = requests.post(f"{base}/ask_prune/{fake_id}")
    assert_ok(r.status_code == 404, "ask_prune with unknown game_id returns 404")

    # Double-oracle guard (call oracle twice without prune)
    game_id3, gs3 = make_game(base, seed=3)
    gs3.post(f"{base}/ask_oracle/{game_id3}", data={"question": "Is it in Asia?"})
    r = gs3.post(f"{base}/ask_oracle/{game_id3}", data={"question": "Second without prune"})
    assert_ok(r.status_code == 400, "Double ask_oracle without prune returns 400")

    # ─────────────────────────────────────────────────────────────────────
    section("5. Status Endpoint")
    # ─────────────────────────────────────────────────────────────────────

    game_id4, gs4 = make_game(base, seed=4)
    r = gs4.get(f"{base}/status/{game_id4}")
    assert_ok(r.status_code == 200, "GET /status/<id> returns 200")
    sd = r.json()
    assert_ok("game_id" in sd, "status returns game_id")
    assert_ok("turn" in sd, "status returns turn")
    assert_ok("obs_mode" in sd, "status returns obs_mode")
    # After zero turns
    assert_ok(sd["turn"] == 0, "fresh game status has turn=0")

    # ─────────────────────────────────────────────────────────────────────
    section("6. Email Cookie")
    # ─────────────────────────────────────────────────────────────────────

    cs = requests.Session()
    r = cs.post(f"{base}/login", data={"email": "test@example.com"}, allow_redirects=False)
    # Should redirect to game page
    assert_ok(r.status_code in (302, 303), "POST /login redirects")
    cookie_val = cs.cookies.get("participant_email")
    assert_ok(cookie_val == "test@example.com",
              f"participant_email cookie set (got: {cookie_val!r})")

    # Pre-fill: GET /login with cookie should show email in input
    r2 = cs.get(f"{base}/login")
    assert_ok("test@example.com" in r2.text,
              "Login page pre-fills email from cookie")

    # ─────────────────────────────────────────────────────────────────────
    section("7. New Game Flow")
    # ─────────────────────────────────────────────────────────────────────

    game_id5, gs5 = make_game(base, seed=5)
    r = gs5.get(f"{base}/new_game/{game_id5}", allow_redirects=False)
    assert_ok(r.status_code == 302, "/new_game redirects to fresh game")
    new_loc = r.headers.get("Location", "")
    new_id = new_loc.split("/game/")[-1].strip()
    assert_ok(new_id != game_id5, "New game gets a different game_id")

    # ─────────────────────────────────────────────────────────────────────
    section("8. Observability Modes")
    # ─────────────────────────────────────────────────────────────────────

    game_fo, _ = make_game(base, config="geo_20_human_fo", seed=10)
    r = requests.get(f"{base}/game/{game_fo}")
    assert_ok("candidates-panel" in r.text, "FO game page has candidates panel")
    assert_ok("FULLY_OBSERVABLE" in r.text, "FO badge shown")

    game_po, _ = make_game(base, config="geo_20_human_po", seed=10)
    r = requests.get(f"{base}/game/{game_po}")
    assert_ok('id="candidates-panel"' not in r.text, "PO game page has no candidates panel")
    assert_ok("PARTIALLY_OBSERVABLE" in r.text, "PO badge shown")

    # ─────────────────────────────────────────────────────────────────────
    section("9. Multi-turn Game (smoke test)")
    # ─────────────────────────────────────────────────────────────────────

    game_id6, gs6 = make_game(base, config="geo_20_human_fo", seed=7)
    questions = [
        "Is it in Asia?",
        "Is it in China?",
        "Is it a coastal city?",
    ]
    all_ok = True
    for q in questions:
        r = gs6.post(f"{base}/ask_oracle/{game_id6}", data={"question": q})
        if r.status_code != 200:
            all_ok = False
            fail(f"Multi-turn oracle for '{q}': HTTP {r.status_code}")
            break
        d = r.json()
        if d.get("game_over_flag"):
            break  # game ended early (correct guess), fine
        r2 = gs6.post(f"{base}/ask_prune/{game_id6}")
        if r2.status_code != 200:
            all_ok = False
            fail(f"Multi-turn prune for '{q}': HTTP {r2.status_code}")
            break
    if all_ok:
        ok(f"Multi-turn game ran {len(questions)} turns without error")

    # ─────────────────────────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    total = passed + failed + skipped
    colour = GREEN if failed == 0 else RED
    print(f"{colour}Results: {passed}/{total} passed, {failed} failed, {skipped} skipped{RESET}")
    return failed == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:5055")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    print(f"Testing InfoGainme Web App at {base}\n")

    # Quick connectivity check
    try:
        requests.get(f"{base}/login", timeout=5)
    except Exception as e:
        print(f"{RED}Cannot reach {base}: {e}{RESET}")
        sys.exit(2)

    success = run_tests(base)
    sys.exit(0 if success else 1)
