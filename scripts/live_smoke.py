"""Perform REAL API generation for the two example products and save its outputs.

Uses LLM_PROVIDER from environment or .env. Ollama requires no API key;
OpenAI-compatible mode requires OPENAI_API_KEY and may incur API charges.
This script does not silently reuse the manually prepared sample outputs.

    python scripts/live_smoke.py
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings  # noqa: E402
from app.errors import ServiceError  # noqa: E402
from app.llm import LLMClient  # noqa: E402
from app.markdown import as_markdown  # noqa: E402
from app.prompts import PROMPT_VERSION  # noqa: E402
from app.schemas import ProductInput  # noqa: E402
from app.service import CardService  # noqa: E402
from scripts.verify_examples import CHECK_NAMES, verify_product  # noqa: E402


class RecordedClient(LLMClient):
    """Keep local diagnostic attempts; never confuse a rejected answer with a card."""

    def __init__(self, settings: Settings, output_dir: Path):
        super().__init__(settings)
        self.audit_path = output_dir / "attempts.jsonl"

    async def generate(self, product: ProductInput, correction: str = "") -> dict:
        response = await super().generate(product, correction)
        with self.audit_path.open("a", encoding="utf-8") as audit:
            audit.write(json.dumps({
                "product_name": product.name, "correction": correction, "response": response,
            }, ensure_ascii=False) + "\n")
        return response


async def generate_all(output_dir: Path) -> int:
    try:
        cfg = Settings.from_env()
    except ServiceError as exc:
        print(f"LIVE FAILED: {exc.code}: {exc.message}", file=sys.stderr)
        return 1
    if cfg.provider == "openai" and (not cfg.api_key or cfg.api_key == "replace-with-your-api-key"):
        print("LIVE API NOT RUN: set OPENAI_API_KEY in .env (see .env.example).", file=sys.stderr)
        return 2
    source = json.loads((ROOT / "examples" / "products.json").read_text(encoding="utf-8"))
    products = [ProductInput.model_validate(item) for item in source]
    # A separate directory ensures the editorial samples cannot be mistaken for LLM output.
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").unlink(missing_ok=True)
    service = CardService(RecordedClient(cfg, output_dir))
    records = []
    for slug, product in zip(CHECK_NAMES, products, strict=True):
        print(f"Calling {cfg.provider}/{cfg.active_model}: {product.name} ...", flush=True)
        try:
            draft = await service.generate(product)
            verify_product(product, draft)
        except ServiceError as exc:
            print(f"LIVE FAILED [{slug}]: {exc.code}: {exc.message}", file=sys.stderr)
            if exc.code == "LLM_OUTPUT_INVALID" and exc.__cause__:
                print(f"VALIDATION: {exc.__cause__}", file=sys.stderr)
            return 1
        except AssertionError as exc:
            print(f"LIVE FAILED [{slug}]: {exc}", file=sys.stderr)
            return 1
        (output_dir / f"{slug}.json").write_text(
            draft.model_dump_json(indent=2), encoding="utf-8"
        )
        (output_dir / f"{slug}.md").write_text(as_markdown(draft), encoding="utf-8")
        records.append({
            "slug": slug,
            "input_sha256": hashlib.sha256(product.model_dump_json().encode()).hexdigest(),
            "output_sha256": hashlib.sha256((output_dir / f"{slug}.json").read_bytes()).hexdigest(),
            "seo_title_length": len(draft.seo_title),
            "seo_description_length": len(draft.seo_description),
            "search_queries_count": len(draft.search_queries),
        })
        print(f"  PASS: {len(draft.seo_description)} chars; {len(draft.search_queries)} queries")
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": cfg.provider,
        "model": cfg.active_model,
        "prompt_version": PROMPT_VERSION,
        "origin": "real API responses validated by CardService; no editorial fixtures reused",
        "postprocessing": "An unfinished final sentence may be removed if at least 800 complete characters remain; card warnings disclose this.",
        "records": records,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"LIVE VERIFIED: 2 real API responses saved at {output_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output" / "live")
    args = parser.parse_args()
    return asyncio.run(generate_all(args.output_dir))


if __name__ == "__main__":
    raise SystemExit(main())
