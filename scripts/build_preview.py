"""Create an offline, self-contained UI preview using the supplied sample cards."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def build_preview(destination: Path) -> None:
    text = (ROOT / 'app/templates/index.html').read_text(encoding='utf-8')
    fixtures = {
        'products': json.loads((ROOT / 'examples/products.json').read_text(encoding='utf-8')),
        'cards': {slug: json.loads((ROOT / f'examples/outputs/{slug}.json').read_text(encoding='utf-8'))
                  for slug in ('tachometer', 'temperature-monitor')},
    }
    # Avoid closing the inline script if data ever contains literal HTML.
    data = json.dumps(fixtures, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    text = text.replace('<link rel="stylesheet" href="/static/style.css">', '<style>\n' + (ROOT / 'app/static/style.css').read_text(encoding='utf-8') + '\n</style>')
    text = text.replace('<script src="/static/vendor/thinking-orbs.js" defer></script>', '<script>\n' + (ROOT / 'app/static/vendor/thinking-orbs.js').read_text(encoding='utf-8') + '\n</script>')
    text = text.replace('<script src="/static/app.js" defer></script>', '<script>window.DRAFTLY_PREVIEW = ' + data + ';</script>\n<script>\n' + (ROOT / 'app/static/app.js').read_text(encoding='utf-8') + '\n</script>')
    text = text.replace('href="/" aria-label="Draftly', 'href="#" aria-label="Draftly')
    text = text.replace('Локальное рабочее место', 'Автономный предпросмотр')
    destination.write_text(text, encoding='utf-8')

if __name__ == '__main__':
    destination = ROOT / 'preview.html'
    build_preview(destination)
    print(destination)
