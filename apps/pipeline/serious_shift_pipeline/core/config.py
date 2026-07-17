"""Pipeline config — model + pricing, from env. No heavy imports so logging and
cost tracking don't pull in the Anthropic SDK."""
import os

# Extraction model + pricing (USD per token). Haiku 4.5 is the current default;
# override via env when switching models so cost accounting stays correct.
EXTRACTION_MODEL = os.environ.get("EXTRACTION_MODEL", "claude-haiku-4-5-20251001")
EXTRACTION_INPUT_RATE = float(os.environ.get("EXTRACTION_INPUT_PRICE_PER_M", "1.0")) / 1_000_000
EXTRACTION_OUTPUT_RATE = float(os.environ.get("EXTRACTION_OUTPUT_PRICE_PER_M", "5.0")) / 1_000_000
