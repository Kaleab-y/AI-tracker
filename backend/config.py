"""Load configuration before provider libraries or database engines initialize."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
# Use the versioned catalog shipped with LiteLLM; startup also works offline.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
