"""Publishable, copy-friendly Markdown rendering."""
from app.schemas import CardOutput


def as_markdown(card: CardOutput) -> str:
    lines = [f"# {card.product_name}", ""]
    if card.status == "needs_data":
        lines += ["**Недостаточно данных для генерации.**", ""]
    else:
        lines += ["## SEO-заголовок", card.seo_title, "", "## SEO-описание", card.seo_description, ""]
    lines += ["## Характеристики", "| Параметр | Значение |", "| --- | --- |"]
    for ch in card.key_characteristics:
        name = ch.name.replace("|", "\\|").replace("\n", " ")
        val = ch.value.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {name} | {val} |")
    if card.search_queries:
        lines += ["", "## Поисковые запросы"]
        lines += [f"- {query}" for query in card.search_queries]
    if card.commercial_block:
        lines += ["", "## Для менеджера", card.commercial_block]
    if card.missing_fields:
        lines += ["", "## Нужно уточнить"]
        lines += [f"- {field}: данных нет" for field in card.missing_fields]
    if card.warnings:
        lines += ["", "## Примечания"]
        lines += [f"- {warning}" for warning in card.warnings]
    if card.source_url:
        lines += ["", f"Источник: {card.source_url}"]
    return "\n".join(lines).strip() + "\n"
