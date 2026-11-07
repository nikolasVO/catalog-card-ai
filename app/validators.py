"""Conservative checks of numbers, units and explicitly supplied product facts.

These rules reject known classes of hallucinations; they are not a semantic
proof of arbitrary prose. Every accepted draft still needs editorial review.
"""
import re

from app.schemas import MISSING_MARKERS, ProductInput

# Keep numbers written with thousands separators as single tokens.
_NUMBER = re.compile(r"(?<!\d)(?:\d{1,3}(?:[\u00a0\u202f ]\d{3})+|\d+(?:[.,]\d+)?)(?!\d)")


def number_tokens(text: str) -> set[str]:
    output = set()
    for match in _NUMBER.finditer(text):
        number = match.group().replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
        number = number.replace(",", ".")
        output.add(number)
    return output


def unsupported_numbers(product: ProductInput, generated_fields: list[str]) -> set[str]:
    """Reject newly introduced numerical claims; cannot catch all semantic hallucinations."""
    facts = [product.name, product.manufacturer or "", product.product_type or "", product.description or ""]
    for key, value in product.specs.items():
        if _present(value):
            facts.extend([key, value])
    allowed = number_tokens("\n".join(facts))
    actual = number_tokens("\n".join(generated_fields))
    return actual - allowed

# High-risk identifiers or claims that must have an explicit anchor in the supplied
# product data. This is deliberately conservative: it is NOT a semantic fact-checker.
# These checks complement, but cannot replace, editorial review.
_GUARDED_TERMS = {
    "Wi-Fi": r"(?<![\w])wi[\s\-‐‑–—]?fi(?:\s*\d+(?:[.,]\d+)?)?(?![a-zа-яё_])",
    "Bluetooth": r"(?<![\w])bluetooth(?:\s*\d+(?:[.,]\d+)?)?(?![a-zа-яё_])",
    "Ethernet": r"(?<![\w])ethernet(?![\w])",
    "USB": r"(?<![\w])usb(?:\s*\d+(?:[.,]\d+)?)?(?![a-zа-яё_])",
    "NFC": r"(?<![\w])nfc(?![\w])",
    "HART": r"(?<![\w])hart(?![\w])",
    "Modbus": r"(?<![\w])modbus(?![\w])",
    "RS-485": r"(?<![\w])rs[\s\-‐‑–—]?485(?![\w])",
    "RS-232": r"(?<![\w])rs[\s\-‐‑–—]?232(?![\w])",
    "гарантия": r"\bгаранти[а-яё]*\b",
    "сертификация": r"\bсертифи[а-яё]*\b",
    "Госреестр": r"\bгосреестр[а-яё]*\b",
    "материал корпуса": r"\b(?:нержавеющ[а-яё]*|алюминиев[а-яё]*|пластиков[а-яё]*|стальн[а-яё]*)\b",
    "защита IP": r"\bi[pр][\s\-]?[0-9xх]{2,3}\b",
}
_GUARDED_PATTERNS = {label: re.compile(pattern, re.IGNORECASE) for label, pattern in _GUARDED_TERMS.items()}

_UNAVAILABLE = re.compile(
    r"данных\s+нет|не\s+указ\w*|неизвест\w*|требу\w*\s+уточн\w*|"
    r"уточн\w*|нет\s+данных|не\s+подтвержд\w*|"
    r"(?:нужно|необходимо|следует)\s+(?:подтверд\w*|свер\w*)", re.IGNORECASE,
)
_NEGATIVE = re.compile(
    r"\bнет\b|\bбез\b|отсутств\w*|не\s+(?:поддерж\w*|предусмотр\w*|оснащ\w*|име\w*)|"
    + _UNAVAILABLE.pattern, re.IGNORECASE,
)
_SENTENCE = re.compile(r"[;\n!?]+|\.(?=\s|$)|,\s*(?:но|однако|зато)\s+", re.IGNORECASE)
_AFFIRMATIVE = re.compile(r"поддерж\w*|оснащ\w*|имеет|имеются|предусмотр\w*|\bесть\b", re.IGNORECASE)


def _present(value: str | None) -> bool:
    return bool(value and value.strip().casefold() not in MISSING_MARKERS)


def _clauses(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE.split(text) if part.strip()]


def _records(product: ProductInput) -> list[str]:
    # A bare key such as {"Wi-Fi": ""} is never evidence of support.
    facts = [product.name, product.manufacturer or "", product.product_type or ""]
    facts += [f"{key}: {value}" for key, value in product.specs.items() if _present(value)]
    facts += _clauses(product.description or "")
    return [fact for fact in facts if fact]


def _evidence(product: ProductInput) -> list[str]:
    return [fact for fact in _records(product) if not _NEGATIVE.search(fact)]


def _canonical_identifier(value: str) -> str:
    return re.sub(r"[\s\-‐‑–—]", "", value.casefold()).translate(str.maketrans({"р": "p", "х": "x"}))


def _guarded_identity(label: str, value: str) -> str:
    if label == "материал корпуса":
        for stem in ("нержавеющ", "алюмини", "пластик", "стальн"):
            if stem in value.casefold():
                return stem
    return _canonical_identifier(value)


# Compare complete quantities, preserving signs, range endpoints and units.
# Unit conversions are deliberately not inferred from outside the input.
_SCALAR = r"[+−-]?\d+(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d+)?"
_QUANTITY = re.compile(
    rf"(?<![\w.,])(?P<value>±?{_SCALAR}(?:\s*(?:…|\.{{2,3}}|[–—−-]|до|[×xх])\s*{_SCALAR})*)"
    r"\s*(?P<unit>об\s*/\s*мин|об\s*/\s*с|кГц|Гц|МПа|кПа|Па|мА|мВ|ВА|Вт|мм|см|"
    r"°\s*[CС]|%|В|А|сек(?:унд\w*)?|с)(?![\w/])", re.IGNORECASE,
)
_UNITS = {"сек": "с", "секунд": "с", "секунды": "с", "секунду": "с", "°с": "°c"}


def _quantities(text: str) -> set[tuple[tuple[str, ...], str, bool]]:
    result = set()
    for match in _QUANTITY.finditer(text):
        value = match["value"]
        # Normalize range separators before extracting signed endpoints. A minus
        # between two endpoints is a separator; a minus after it remains a sign.
        value = re.sub(r"(?<=\d)\s*[–—−-]\s*(?=[+−-]?\d)", " to ", value)
        numbers = tuple(
            number.replace("−", "-").lstrip("+").replace(",", ".")
            .replace(" ", "").replace("\u00a0", "").replace("\u202f", "")
            for number in re.findall(_SCALAR, value)
        )
        unit = re.sub(r"\s", "", match["unit"].casefold())
        result.add((numbers, _UNITS.get(unit, unit), "±" in value))
    return result


# Attribute-specific checks keep a relay voltage from becoming a supply voltage,
# and an operating temperature from becoming a measurement range.
_ATTRIBUTES = (
    ("питание", r"питани\w*|напряжени\w*\s+питани\w*", {"в", "мв"}),
    ("температура эксплуатации", r"температур\w*\s+(?:эксплуатац\w*|работ\w*)|рабоч\w*\s+температур\w*", {"°c"}),
    ("диапазон температур", r"диапазон\w*\s+(?:измерени\w*\s+)?температур\w*|измерени\w*\s+температур\w*", {"°c"}),
    ("частота вращения", r"частот\w*\s+вращени\w*|скорост\w*\s+вращени\w*", {"об/мин", "об/с"}),
    ("входная частота", r"частот\w*\s+входн\w*|частот\w*\s+сигнал\w*|входн\w*\s+сигнал\w*", {"гц", "кгц"}),
    ("потребляемая мощность", r"мощност\w*", {"ва", "вт"}),
    ("габариты", r"габарит\w*|размер\w*|корпус\w*", {"мм", "см"}),
    ("цикл опроса", r"цикл\w*\s+опрос\w*|опрос\w*\s+датчик\w*", {"с"}),
)


def unsupported_quantities(product: ProductInput, generated_fields: list[str]) -> set[str]:
    """Reject swapped units/ranges/signs and quantities assigned to another field."""
    facts = _evidence(product)
    allowed = set().union(*(_quantities(fact) for fact in facts)) if facts else set()
    issues: set[str] = set()
    for field in generated_fields:
        for clause in _clauses(field):
            actual = _quantities(clause)
            if actual - allowed:
                issues.add("значение, диапазон или единица измерения")
            for label, expression, units in _ATTRIBUTES:
                if not re.search(expression, clause, re.IGNORECASE):
                    continue
                anchors = [fact for fact in facts if re.search(expression, fact, re.IGNORECASE)]
                anchored = set().union(*(_quantities(fact) for fact in anchors)) if anchors else set()
                if {q for q in actual if q[1] in units} - anchored:
                    issues.add(label)
    return issues


def unsupported_claims(product: ProductInput, generated_fields: list[str]) -> set[str]:
    """Catch a defined set of unsupported non-numeric technical assertions.

    Only product input counts as evidence, never the model's system prompt or
    URLs. A keyword match is not a comprehensive semantic entailment check.
    """
    facts = _evidence(product)
    all_records = _records(product)
    issues: set[str] = set()
    for field in generated_fields:
        for clause in _clauses(field):
            # Explicit statements of missing data are allowed, but cannot smuggle
            # in a number ("класс точности 0,5 требует уточнения").
            for label, pattern in _GUARDED_PATTERNS.items():
                matches = list(pattern.finditer(clause))
                if not matches:
                    continue
                if _UNAVAILABLE.search(clause) and not _AFFIRMATIVE.search(clause) and not number_tokens(clause):
                    continue
                evidence = [fact for fact in facts if pattern.search(fact)]
                if _NEGATIVE.search(clause) and not _UNAVAILABLE.search(clause):
                    if any(pattern.search(fact) and _NEGATIVE.search(fact) for fact in all_records):
                        continue
                    issues.add(label)
                    continue
                if not evidence:
                    issues.add(label)
                elif label in {"защита IP", "материал корпуса"} or (
                    label in {"Wi-Fi", "Bluetooth", "USB"}
                    and any(number_tokens(match.group()) for match in matches)
                ):
                    # A category match (IP54 exists) cannot authorize IP96 or a
                    # different material that happens to have the same category.
                    allowed = {
                        _guarded_identity(label, m.group())
                        for fact in evidence for m in pattern.finditer(fact)
                    }
                    if any(_guarded_identity(label, m.group()) not in allowed for m in matches):
                        issues.add(label)
                elif _NEGATIVE.search(clause):
                    # Positive evidence must not be silently inverted either.
                    issues.add(label)

            missing = [key for key, value in product.specs.items() if not _present(value)]
            supplied = {key.casefold() for key, value in product.specs.items() if _present(value)}
            missing += [key for key in product.expected_specs if key.casefold() not in supplied]
            # Class of accuracy is distinct from measurement error even if it
            # was not explicitly included in expected_specs by the caller.
            accuracy = r"класс\w*\s+точност\w*"
            class_values = [value for key, value in product.specs.items()
                            if re.search(accuracy, key, re.IGNORECASE) and _present(value)
                            and not _NEGATIVE.search(value)]
            if not class_values:
                missing.append("Класс точности")
            else:
                match = re.search(accuracy, clause, re.IGNORECASE)
                if match:
                    tail = re.sub(r"^\s*(?:прибора\s*)?[:=—–-]?\s*", "", clause[match.end():])
                    value = re.match(r"\d+(?:[.,]\d+)?", tail)
                    if value and not number_tokens(value.group()).issubset(number_tokens(" ".join(class_values))):
                        issues.add("Класс точности")
            for key in missing:
                expression = accuracy if re.search(accuracy, key, re.IGNORECASE) else re.escape(key)
                match = re.search(expression, clause, re.IGNORECASE)
                without_identity = clause.replace(product.name, "")
                if match and (not _UNAVAILABLE.search(clause) or number_tokens(without_identity)):
                    issues.add(key)
    return issues
