"""Browser smoke checks for the standalone preview and mocked generation UI.

Optional: pip install playwright; playwright install chromium
Run: python scripts/build_preview.py && python scripts/check_ui.py
The network boundary is mocked explicitly; no paid LLM requests are made.
"""
import json
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def run() -> None:
    html = (ROOT / 'preview.html').read_text(encoding='utf-8')
    cards = {slug: json.loads((ROOT / f'examples/outputs/{slug}.json').read_text(encoding='utf-8'))
             for slug in ('tachometer', 'temperature-monitor')}
    products = json.loads((ROOT / 'examples/products.json').read_text(encoding='utf-8'))
    checks = []
    with sync_playwright() as p:
        options = {'headless': True}
        if shutil.which('chromium'):
            options['executable_path'] = shutil.which('chromium')
        browser = p.chromium.launch(**options)
        page = browser.new_page(viewport={'width': 1440, 'height': 1040})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.set_content(html, wait_until='load')
        expect(page.locator('.description-block')).to_be_visible()
        expect(page.locator('#status')).to_have_text('Образец')
        checks.append('initial_sample')

        page.locator('[data-product="1"]').click()
        expect(page.locator('.title-block')).to_contain_text('УКТ38')
        page.locator('#tab-specs').click()
        expect(page.locator('.facts-table')).to_contain_text('IP54')
        expect(page.locator('.facts-table')).to_contain_text('данных нет')
        checks.append('product_switch_and_specs')

        page.locator('#review-open').click()
        expect(page.locator('#result')).to_contain_text('Интерфейс связи')
        checks.append('missing_fields')

        page.locator('#tab-json').click()
        assert json.loads(page.locator('#result pre').inner_text())['product_name'] == cards['temperature-monitor']['product_name']
        page.locator('#tab-json').press('ArrowRight')
        expect(page.locator('#tab-markdown')).to_have_attribute('aria-selected', 'true')
        expect(page.locator('#result')).to_contain_text('## SEO-заголовок')
        checks.append('json_markdown_and_keyboard_tabs')

        page.locator('#export-menu-toggle').click()
        with page.expect_download() as event:
            page.locator('[data-export="json"]').click()
        assert json.loads(Path(event.value.path()).read_text(encoding='utf-8')) == cards['temperature-monitor']
        checks.append('json_export')
        page.locator('#export-menu-toggle').click()
        with page.expect_download() as event:
            page.locator('[data-export="markdown"]').click()
        assert '## Характеристики' in Path(event.value.path()).read_text(encoding='utf-8')
        checks.append('markdown_export')

        page.evaluate("Object.defineProperty(navigator, 'clipboard', {configurable:true,value:{writeText:async text=>{window.copiedText=text;}}})")
        page.locator('#copy').click()
        assert '## SEO-заголовок' in page.evaluate('window.copiedText')
        checks.append('clipboard')
        page.evaluate("() => { navigator.clipboard.writeText=async()=>{throw new Error('Denied')}; }")
        page.locator('#copy').click()
        expect(page.locator('#result')).to_contain_text('## SEO-заголовок')
        checks.append('clipboard_failure_preserves_result')

        page.locator('#field-name').fill('Изменённый прибор')
        expect(page.locator('#stale-notice')).to_be_visible()
        page.locator('#input-tab-json').click()
        assert json.loads(page.locator('#json-input').input_value())['name'] == 'Изменённый прибор'
        checks.append('form_json_sync_and_stale')

        page.locator('#json-input').fill('{broken')
        page.locator('#generate').click()
        expect(page.locator('#input-error')).to_contain_text('Некорректный JSON')
        expect(page.locator('#result')).to_contain_text('УКТ38')
        checks.append('bad_json_preserves_previous_result')

        page.locator('[data-product="0"]').click()
        page.locator('#input-tab-fields').click()
        page.locator('#toggle-specs').click()
        assert page.locator('.spec-row:visible').count() == len(products[0]['specs'])
        page.locator('#add-spec').click()
        page.locator('.spec-key').last.fill('Проверка')
        page.locator('.spec-value').last.fill('123')
        page.locator('#input-tab-json').click()
        assert json.loads(page.locator('#json-input').input_value())['specs']['Проверка'] == '123'
        checks.append('edit_and_add_specs')
        page.locator('#input-tab-fields').click()
        page.locator('.spec-key').last.fill('Назначение')
        page.locator('#generate').click()
        expect(page.locator('#input-error')).to_contain_text('Повторяется характеристика')
        page.locator('.remove-spec').last.click()
        checks.append('duplicate_spec_validation')

        page.locator('#file-input').set_input_files({'name':'product.json','mimeType':'application/json','buffer':json.dumps({'name':'Импорт','specs':{'Диапазон':'10 В'}},ensure_ascii=False).encode()})
        expect(page.locator('#field-name')).to_have_value('Импорт')
        expect(page.locator('#show-demo')).to_be_disabled()
        checks.append('json_import')
        page.locator('#new-product').click()
        expect(page.locator('#field-name')).to_have_value('')
        page.locator('#generate').click()
        expect(page.locator('#input-error')).to_contain_text('Укажите название')
        checks.append('new_product_and_empty_validation')

        page.locator('[data-product="0"]').click()
        page.locator('#generate').click()
        expect(page.locator('#result-error')).to_contain_text('автономный предпросмотр')
        expect(page.locator('#result')).to_contain_text('ТХ01')
        checks.append('preview_does_not_fake_generation')

        page.locator('#tab-description').click()
        # Simulate a slow network response explicitly to test the real loading and cancellation UI.
        page.evaluate("""() => {
          window.DRAFTLY_PREVIEW = null;
          window.fetch = (url, options={}) => new Promise((resolve, reject) => {
            window.pendingResponse = resolve;
            options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted','AbortError')));
          });
        }""")
        page.locator('#generate').click()
        expect(page.locator('#loading')).to_be_visible()
        expect(page.locator('#field-name')).to_be_disabled()
        expect(page.locator('#generate')).to_be_disabled()
        first_frame = page.locator('#loading-orb').evaluate('(canvas)=>canvas.toDataURL()')
        page.wait_for_timeout(150)
        assert first_frame != page.locator('#loading-orb').evaluate('(canvas)=>canvas.toDataURL()')
        page.screenshot(path=str(ROOT / 'docs/screenshot-loading.png'), full_page=True)
        checks.append('real_orb_animation_and_busy_state')
        page.locator('#cancel').click()
        expect(page.locator('#loading')).to_be_hidden()
        expect(page.locator('#generate')).to_be_enabled()
        expect(page.locator('#result')).to_contain_text('ТХ01')
        checks.append('cancel_preserves_previous_result')

        page.locator('#generate').click()
        page.evaluate("card => window.pendingResponse(new Response(JSON.stringify(card), {status:200,headers:{'Content-Type':'application/json'}}))", cards['tachometer'])
        expect(page.locator('#status')).to_have_text('Черновик')
        expect(page.locator('#output-origin')).to_have_text('Сформировано через API')
        checks.append('successful_mocked_api_response')

        page.locator('#generate').click()
        page.evaluate("window.pendingResponse(new Response(JSON.stringify({message:'API-ключ не задан'}),{status:503}))")
        expect(page.locator('#result-error')).to_contain_text('API-ключ не задан')
        expect(page.locator('#result')).to_contain_text('ТХ01')
        checks.append('api_failure_preserves_result')

        malicious = dict(cards['tachometer'])
        malicious['seo_title'] = '<img src=x onerror="window.xss=true">'
        page.locator('#generate').click()
        page.evaluate("card => window.pendingResponse(new Response(JSON.stringify(card), {status:200}))", malicious)
        expect(page.locator('.title-block')).to_contain_text('<img')
        assert page.locator('#result img').count() == 0
        assert not page.evaluate('window.xss || false')
        checks.append('escaped_model_output')

        page.locator('.help-trigger').click()
        expect(page.locator('#help-dialog')).to_be_visible()
        page.keyboard.press('Escape')
        expect(page.locator('#help-dialog')).to_be_hidden()
        checks.append('help_dialog')

        for width in (320, 390, 768, 1024, 1440):
            view = browser.new_page(viewport={'width':width,'height':900})
            view.set_content(html, wait_until='load')
            expect(view.locator('.description-block')).to_be_visible()
            assert view.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), f'Overflow at {width}'
            if width <= 960:
                expect(view.locator('.source-pane')).to_be_hidden()
                view.locator('[data-mobile-view="source"]').click()
                expect(view.locator('#field-name')).to_be_visible()
                assert view.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), f'Source overflow at {width}'
            view.close()
        checks.append('responsive_320_390_768_1024_1440')

        reduced = browser.new_page(viewport={'width':800,'height':900}, reduced_motion='reduce')
        reduced.set_content(html, wait_until='load')
        reduced.locator('.help-trigger').click()
        first = reduced.locator('#help-orb').evaluate('(canvas)=>canvas.toDataURL()')
        reduced.wait_for_timeout(150)
        assert first == reduced.locator('#help-orb').evaluate('(canvas)=>canvas.toDataURL()')
        checks.append('prefers_reduced_motion')
        assert not errors, errors
        browser.close()
    print(f'{len(checks)} browser checks passed')
    for check in checks: print('  OK', check)
    (ROOT / 'docs/ui-checks.json').write_text(json.dumps({'checks':checks,'total':len(checks),'api_calls':'mocked; no paid LLM requests'},ensure_ascii=False,indent=2),encoding='utf-8')

if __name__ == '__main__':
    run()
