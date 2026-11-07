"""FastAPI HTTP API + intentionally simple local UI."""
import json
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import ROOT, Settings
from app.errors import ServiceError
from app.llm import LLMClient
from app.markdown import as_markdown
from app.schemas import CardOutput, ProductInput
from app.service import CardService

app = FastAPI(
    title="B2B Product Card AI",
    description="LLM SEO copy with deterministic technical specs and validation.",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


def get_service() -> CardService:
    return CardService(LLMClient(Settings.from_env()))


@app.exception_handler(ServiceError)
async def service_error_handler(_request, exc: ServiceError):
    return JSONResponse(status_code=exc.http_status, content={"error": exc.code, "message": exc.message})


@app.exception_handler(RequestValidationError)
async def input_error_handler(_request, exc: RequestValidationError):
    # Pydantic errors can contain the complete input, exception objects, and
    # non-finite floats. Return only useful, JSON-safe validation metadata.
    public_fields = {"body", *ProductInput.model_fields}
    details = []
    for error in exc.errors():
        location = [
            part for part in error.get("loc", ())
            if isinstance(part, int) or (isinstance(part, str) and part in public_fields)
        ]
        details.append({
            "loc": location,
            "msg": error.get("msg", "Некорректное значение"),
            "type": error.get("type", "validation_error"),
        })
    return JSONResponse(status_code=422, content={"detail": details})


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(Path(__file__).parent / "templates" / "index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/examples")
async def examples() -> list[ProductInput]:
    with (ROOT / "examples" / "products.json").open(encoding="utf-8") as f:
        return [ProductInput.model_validate(item) for item in json.load(f)]


@app.get("/api/examples/{slug}/draft", response_model=CardOutput)
async def example_draft(slug: str):
    known = {"tachometer", "temperature-monitor"}
    if slug not in known:
        return JSONResponse(status_code=404, content={"message": "Пример не найден"})
    path = ROOT / "examples" / "outputs" / f"{slug}.json"
    with path.open(encoding="utf-8") as f:
        return CardOutput.model_validate(json.load(f))


@app.post("/api/generate", response_model=CardOutput)
async def generate(product: ProductInput, service: CardService = Depends(get_service)) -> CardOutput:
    return await service.generate(product)


@app.post("/api/generate/markdown")
async def generate_markdown(product: ProductInput, service: CardService = Depends(get_service)):
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(as_markdown(await service.generate(product)), media_type="text/markdown")
