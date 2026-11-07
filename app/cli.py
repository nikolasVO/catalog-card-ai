"""Batch CLI: python -m app.cli --input examples/products.json --output-dir output."""
import argparse
import asyncio
import json
from pathlib import Path
import re

from app.config import Settings
from app.errors import ServiceError
from app.llm import LLMClient
from app.markdown import as_markdown
from app.schemas import ProductInput
from app.service import CardService


def slugify(name: str) -> str:
    latin = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-")
    return latin.lower()[:45] or "product"


async def run(input_path: Path, output_dir: Path) -> int:
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Ошибка входного файла: {exc}")
        return 2
    if not isinstance(data, (dict, list)):
        print("Ошибка: JSON должен содержать объект товара или массив объектов")
        return 2
    products = data if isinstance(data, list) else [data]
    output_dir.mkdir(parents=True, exist_ok=True)
    service = CardService(LLMClient(Settings.from_env()))
    failed = False
    for i, source in enumerate(products, 1):
        try:
            product = ProductInput.model_validate(source)
            card = await service.generate(product)
        except (ServiceError, ValueError) as exc:
            print(f"[{i}] Ошибка: {exc}")
            failed = True
            continue
        filename = f"{i:02d}-{slugify(product.name)}"
        (output_dir / f"{filename}.json").write_text(
            card.model_dump_json(indent=2), encoding="utf-8"
        )
        (output_dir / f"{filename}.md").write_text(as_markdown(card), encoding="utf-8")
        print(f"[{i}] {product.name}: {card.status}, сохранено в {output_dir}")
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Генератор B2B-карточек товара")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.input, args.output_dir)))


if __name__ == "__main__":
    main()
