"""
Seed script - populates the telemetry database with realistic fake data.

Run from the backend/ directory:
    python seed.py

Generates ~250 log entries spread over the last 30 days using a realistic
mix of OpenAI, Anthropic, and Google models with plausible token counts
and latency values.
"""

import argparse
import random
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from sqlalchemy import delete
from sqlmodel import Session, select

from database.connection import create_db_and_tables, engine
from database.models import RequestLog
from utils.pricing import calculate_cost

load_dotenv()

# ── Seed configuration ────────────────────────────────────────────────

SEED_ENTRIES = 280
DAYS_BACK = 30

# Each entry is (model_name, provider, avg_prompt, avg_completion, avg_latency_ms)
MODEL_PROFILES = [
    # OpenAI
    ("gpt-4o", "openai", 800, 400, 2200),
    ("gpt-4o-mini", "openai", 600, 300, 900),
    ("gpt-4.1", "openai", 750, 380, 1900),
    ("gpt-4.1-mini", "openai", 550, 280, 800),
    ("o3-mini", "openai", 1200, 600, 4500),
    # Anthropic
    ("claude-3-5-sonnet-20241022", "anthropic", 900, 450, 2600),
    ("claude-3-5-haiku-20241022", "anthropic", 650, 320, 1100),
    ("claude-3-opus-20240229", "anthropic", 1100, 550, 3800),
    ("claude-3-haiku-20240307", "anthropic", 500, 250, 750),
    # Google
    ("gemini-2.0-flash", "google", 700, 350, 1200),
    ("gemini-2.5-pro", "google", 1000, 500, 2900),
    ("gemini-1.5-flash", "google", 600, 300, 950),
]

# Weights — simulate realistic usage patterns (cheaper/faster models used more)
MODEL_WEIGHTS = [
    10,  # gpt-4o
    25,  # gpt-4o-mini
    8,  # gpt-4.1
    20,  # gpt-4.1-mini
    4,  # o3-mini
    12,  # claude-3-5-sonnet
    15,  # claude-3-5-haiku
    3,  # claude-3-opus
    10,  # claude-3-haiku
    18,  # gemini-2.0-flash
    5,  # gemini-2.5-pro
    14,  # gemini-1.5-flash
]


def jitter(value: int, pct: float = 0.35) -> int:
    """Return value ± pct% random variation, floored at 1."""
    delta = int(value * pct)
    return max(1, value + random.randint(-delta, delta))


def random_timestamp(days_back: int) -> datetime:
    """Pick a random datetime within the last `days_back` days."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    seconds_back = random.randint(0, days_back * 86400)
    return now - timedelta(seconds=seconds_back)


def seed(clear_demo=False):
    print("[seed] Creating database tables if needed...")
    create_db_and_tables()
    with Session(engine) as session:
        if clear_demo:
            result = session.exec(
                delete(RequestLog).where(RequestLog.is_demo.is_(True))
            )
            session.commit()
            print(
                f"[seed] Removed {result.rowcount} sample rows. Real requests were kept."
            )
            return
        if session.exec(
            select(RequestLog).where(RequestLog.is_demo.is_(True)).limit(1)
        ).first():
            print("[seed] Sample data already exists; no duplicate rows added.")
            return

    entries = []
    for _ in range(SEED_ENTRIES):
        profile = random.choices(MODEL_PROFILES, weights=MODEL_WEIGHTS, k=1)[0]
        model_name, provider, avg_prompt, avg_completion, avg_latency = profile

        prompt_tokens = jitter(avg_prompt)
        completion_tokens = jitter(avg_completion)
        latency_ms = jitter(avg_latency, pct=0.45)
        total_cost = calculate_cost(model_name, prompt_tokens, completion_tokens)
        timestamp = random_timestamp(DAYS_BACK)
        failed = random.random() < 0.05

        entries.append(
            RequestLog(
                timestamp=timestamp,
                model_name=model_name,
                provider=provider,
                prompt_tokens=None if failed else prompt_tokens,
                completion_tokens=None if failed else completion_tokens,
                total_cost=None if failed else total_cost,
                latency_ms=latency_ms,
                status="error" if failed else "success",
                usage_available=not failed,
                error_code="rate_limit_error" if failed else None,
                is_demo=True,
            )
        )

    with Session(engine) as session:
        for entry in entries:
            session.add(entry)
        session.commit()

    print(f"[seed] OK - Inserted {len(entries)} log entries across {DAYS_BACK} days.")
    print(f"[seed]   Models: {len(MODEL_PROFILES)} - OpenAI, Anthropic, Google")
    print("[seed]   Now start the server and open http://localhost:3000")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Add or remove labeled sample telemetry"
    )
    parser.add_argument(
        "--clear-demo", action="store_true", help="Remove only labeled demo rows"
    )
    seed(clear_demo=parser.parse_args().clear_demo)
