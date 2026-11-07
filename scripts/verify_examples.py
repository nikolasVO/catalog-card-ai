"""Verify both bundled product drafts without a paid LLM request.

Usage:
    python scripts/verify_examples.py
    python scripts/verify_examples.py --output-dir output/live
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.schemas import CardOutput, GeneratedText, ProductInput  # noqa: E402
from app.service import factual_characteristics  # noqa: E402
from app.validators import unsupported_claims, unsupported_numbers, unsupported_quantities  # noqa: E402


CHECK_NAMES = ("tachometer", "temperature-monitor")


def verify_product(product: ProductInput, draft: CardOutput) -> None:
    """Check schema/length/card provenance for a draft and its exact input."""
    assert draft.status == "draft", f"Expected draft, got {draft.status}"
    checked = GeneratedText.model_validate({key: getattr(draft, key) for key in (
        "seo_title", "seo_description", "search_queries", "commercial_block",
    )})
    assert checked.seo_description == draft.seo_description, "Stored draft contains an unfinished sentence"
    assert draft.product_name == product.name
    assert draft.manufacturer == (product.manufacturer or "данных нет")
    assert 5 <= len(draft.seo_title) <= 70
    assert product.name.casefold() in draft.seo_title.casefold()
    assert 800 <= len(draft.seo_description) <= 1200
    assert 3 <= len(draft.search_queries) <= 5
    assert 40 <= len(draft.commercial_block) <= 450
    assert draft.requires_editor_review is True
    assert draft.source_url == product.source_url
    assert draft.source_id == product.source_id
    expected_chars, missing_fields = factual_characteristics(product)
    assert draft.key_characteristics == expected_chars, "Technical specs differ from the source JSON"
    assert set(missing_fields).issubset(set(draft.missing_fields))
    fields = [draft.seo_title, draft.seo_description, *draft.search_queries, draft.commercial_block]
    assert not unsupported_numbers(product, fields), "Output contains ungrounded numerical tokens"
    assert not unsupported_quantities(product, fields), "Output changes a quantity, unit or its attribute"
    assert not unsupported_claims(product, fields), "Output contains unsupported guarded claims"


def verify_files(output_dir: Path) -> list[str]:
    source = json.loads((ROOT / "examples" / "products.json").read_text(encoding="utf-8"))
    products = [ProductInput.model_validate(item) for item in source]
    verified = []
    for slug, product in zip(CHECK_NAMES, products, strict=True):
        path = output_dir / f"{slug}.json"
        draft = CardOutput.model_validate_json(path.read_text(encoding="utf-8"))
        verify_product(product, draft)
        verified.append(f"{slug}: OK ({len(draft.seo_title)} / 70, {len(draft.seo_description)} / 1200, {len(draft.search_queries)} queries)")
    return verified


def verify_manifest(output_dir: Path) -> None:
    """Detect accidental edits to published API responses or their exact inputs."""
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["provider"] in {"ollama", "openai"}
    assert manifest["model"] and manifest["generated_at"] and manifest["prompt_version"]
    source = json.loads((ROOT / "examples/products.json").read_text(encoding="utf-8"))
    assert len(manifest["records"]) == len(CHECK_NAMES)
    for slug, product_data, record in zip(CHECK_NAMES, source, manifest["records"], strict=True):
        product = ProductInput.model_validate(product_data)
        assert record["slug"] == slug
        assert record["input_sha256"] == hashlib.sha256(product.model_dump_json().encode()).hexdigest(), "Live input changed since generation"
        path = output_dir / f"{slug}.json"
        assert record["output_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest(), "Live response changed since generation"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "examples" / "outputs")
    parser.add_argument("--require-manifest", action="store_true", help="Require provenance hashes for recorded API responses")
    args = parser.parse_args()
    try:
        verified = verify_files(args.output_dir)
        if args.require_manifest or (args.output_dir / "manifest.json").exists():
            verify_manifest(args.output_dir)
    except (FileNotFoundError, AssertionError, ValueError, KeyError, TypeError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print("Examples validated (bundled outputs are editorial reference drafts, not live LLM responses):")
    for item in verified:
        print(f"  {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
