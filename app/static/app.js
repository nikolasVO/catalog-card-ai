/* Draftly workspace. All product/model strings are escaped; no HTML from data is executed. */
(() => {
  'use strict';
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const icons = {
    folder: '<path d="M3 5h5l2 2h11v12H3z"/>',
    help: '<circle cx="12" cy="12" r="9"/><path d="M9.4 9a2.7 2.7 0 0 1 5.2 1c0 2-2.6 2-2.6 4m0 3v.01"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    file: '<path d="M14 3H5v18h14V8z"/><path d="M14 3v5h5M8 12h8M8 16h6"/>',
    external: '<path d="M14 3h7v7M21 3l-11 11"/><path d="M10 5H4v15h15v-6"/>',
    upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/>',
    download: '<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
    copy: '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
    'chevron-down': '<path d="m6 9 6 6 6-6"/>',
    'arrow-right': '<path d="M4 12h16m-6-6 6 6-6 6"/>',
    lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4M12 14v3"/>',
    code: '<path d="m8 6-6 6 6 6m8-12 6 6-6 6M14 3l-4 18"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.01"/>',
    close: '<path d="m6 6 12 12M6 18 18 6"/>',
    gauge: '<path d="M4 17a9 9 0 1 1 16 0"/><path d="m12 12 4-5M7 17h10M12 4v1M5 8l1 1M19 8l-1 1"/><circle cx="12" cy="12" r="1"/>',
    thermometer: '<path d="M10 14V5a2 2 0 0 1 4 0v9a4 4 0 1 1-4 0Z"/><path d="M12 9v8M17 5h3M17 9h2"/>'
  };
  function icon(name) {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.file}</svg>`;
  }
  function hydrateIcons(root = document) {
    $$('[data-icon]', root).forEach(el => { el.innerHTML = icon(el.dataset.icon); });
  }
  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }
  function urlSafe(value) {
    try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : ''; }
    catch { return ''; }
  }
  const clone = value => JSON.parse(JSON.stringify(value));
  const state = {
    examples: [], selected: 0, inputTab: 'fields', outputTab: 'description',
    raw: '', base: {}, current: null, kind: 'sample', snapshot: '', busy: false,
    expandedSpecs: false, controller: null, requestId: 0, demoVersion: 0
  };
  const slugs = ['tachometer', 'temperature-monitor'];
  let toastTimer;
  const motion = {};
  function showToast(text) {
    clearTimeout(toastTimer);
    $('#toast').textContent = text; $('#toast').hidden = false;
    toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 3200);
  }
  function showInputError(text = '') {
    $('#input-error').textContent = text;
    $('#input-error').hidden = !text;
  }
  function showResultError(text = '') {
    $('#result-error').textContent = text;
    $('#result-error').hidden = !text;
  }
  function mobilePane(view) {
    document.body.dataset.mobilePane = view;
    $$('[data-mobile-view]').forEach(el => {
      el.classList.toggle('active', el.dataset.mobileView === view);
      el.setAttribute('aria-pressed', String(el.dataset.mobileView === view));
    });
  }
  function fingerprint(value) {
    const canonical = obj => Array.isArray(obj) ? obj.map(canonical) :
      obj && typeof obj === 'object' ? Object.fromEntries(Object.keys(obj).sort().map(k => [k, canonical(obj[k])])) : obj;
    return JSON.stringify(canonical(value));
  }
  function inputObject(raw) {
    let obj;
    try { obj = JSON.parse(raw); }
    catch { throw new Error('Некорректный JSON. Проверьте кавычки, запятые и закрывающие скобки.'); }
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) throw new Error('Нужен один JSON-объект с данными товара, не массив.');
    if (obj.specs != null && (typeof obj.specs !== 'object' || Array.isArray(obj.specs))) throw new Error('Поле specs должно быть объектом: название характеристики и её значение.');
    if (obj.expected_specs != null && (!Array.isArray(obj.expected_specs) || obj.expected_specs.some(x => typeof x !== 'string'))) throw new Error('expected_specs должен содержать массив названий характеристик.');
    for (const k of ['name', 'manufacturer', 'product_type', 'description', 'source_url']) {
      if (obj[k] != null && typeof obj[k] !== 'string') throw new Error(`Поле ${k} должно быть строкой.`);
    }
    for (const [key, val] of Object.entries(obj.specs || {})) {
      if (val !== null && !['string', 'number', 'boolean'].includes(typeof val)) throw new Error(`Характеристика «${key}» должна содержать строку, число или пустое значение.`);
    }
    return obj;
  }
  function renderProducts() {
    $('#product-count').textContent = state.examples.length;
    $('#product-list').innerHTML = state.examples.map((product, i) => `
      <button type="button" class="product-button ${state.selected === i ? 'selected' : ''}" data-product="${i}" aria-pressed="${state.selected === i}" ${state.busy ? 'disabled' : ''}>
        <span class="product-icon">${icon(i === 0 ? 'gauge' : 'thermometer')}</span>
        <span class="product-name"><strong>${i === 0 ? 'ОВЕН ТХ01' : 'ОВЕН УКТ38'}</strong><small>${i === 0 ? 'Тахометр' : 'Контроль температуры'}</small></span>
      </button>`).join('');
  }
  function specRow(key, value, index) {
    return `<div class="spec-row" data-index="${index}" ${!state.expandedSpecs && index >= 4 ? 'hidden' : ''}>
      <input class="spec-key" value="${esc(key)}" title="${esc(key)}" aria-label="Название характеристики ${index + 1}" placeholder="Параметр" spellcheck="false">
      <input class="spec-value" value="${esc(value)}" title="${esc(value)}" aria-label="Значение характеристики ${index + 1}" placeholder="данных нет" spellcheck="false">
      <button type="button" class="remove-spec" aria-label="Удалить характеристику ${index + 1}" title="Удалить характеристику">${icon('close')}</button>
    </div>`;
  }
  function updateSpecVisibility() {
    const rows = $$('.spec-row');
    rows.forEach((row, i) => { row.hidden = !state.expandedSpecs && i >= 4; });
    $('#spec-count').textContent = `${rows.length} параметров`;
    $('#toggle-specs').hidden = rows.length <= 4;
    $('#toggle-specs').innerHTML = (state.expandedSpecs ? 'Свернуть' : `Все характеристики (${rows.length})`) + icon('chevron-down');
    $('#toggle-specs').setAttribute('aria-expanded', String(state.expandedSpecs));
  }
  function populateFields(product) {
    state.base = clone(product);
    $('#field-name').value = product.name ?? '';
    $('#field-manufacturer').value = product.manufacturer ?? '';
    $('#field-type').value = product.product_type ?? '';
    $('#field-description').value = product.description ?? '';
    $('#field-source').value = product.source_url ?? '';
    $('#field-expected').value = (product.expected_specs || []).join('\n');
    $('#spec-rows').innerHTML = Object.entries(product.specs || {}).map(([key, value], i) => specRow(key, value, i)).join('');
    updateSpecVisibility();
  }
  function collectFields() {
    const product = clone(state.base);
    product.name = $('#field-name').value;
    for (const [key, id] of [['manufacturer', 'field-manufacturer'], ['product_type', 'field-type'], ['description', 'field-description']]) product[key] = $('#' + id).value;
    const source = $('#field-source').value.trim();
    if (source) product.source_url = source; else delete product.source_url;
    const specs = Object.create(null);
    for (const row of $$('.spec-row')) {
      const key = $('.spec-key', row).value.trim(), value = $('.spec-value', row).value.trim();
      if (!key && value) throw new Error('Укажите название для характеристики со значением «' + value + '».');
      if (!key) continue;
      if (Object.hasOwn(specs, key)) throw new Error('Повторяется характеристика «' + key + '». Названия должны быть уникальными.');
      // Retain the original JSON scalar type until the value is actually edited.
      const original = state.base.specs?.[key];
      specs[key] = original != null && String(original) === value ? original : value || null;
    }
    product.specs = specs;
    product.expected_specs = [...new Set($('#field-expected').value.split('\n').map(x => x.trim()).filter(Boolean))];
    return product;
  }
  function updateStale() {
    let stale = false;
    if (state.current) {
      try { stale = fingerprint(inputObject(state.raw)) !== state.snapshot; }
      catch { stale = true; }
      if (!$('#input-error').hidden) stale = true;
    }
    $('#stale-notice').hidden = !stale;
  }
  function changed() {
    $('#input-state').textContent = 'Изменено';
    showInputError();
    if (state.inputTab === 'fields') {
      try { state.raw = JSON.stringify(collectFields(), null, 2); $('#json-input').value = state.raw; }
      catch (error) { showInputError(error.message); }
    } else state.raw = $('#json-input').value;
    updateStale();
  }
  function switchInput(tab) {
    if (state.busy || tab === state.inputTab) return;
    try {
      if (tab === 'fields') populateFields(inputObject(state.raw));
      else { state.raw = JSON.stringify(collectFields(), null, 2); $('#json-input').value = state.raw; }
      showInputError();
    } catch (error) { showInputError(error.message); return; }
    state.inputTab = tab;
    $('#fields-panel').hidden = tab !== 'fields'; $('#raw-panel').hidden = tab !== 'json';
    $$('[data-input-tab]').forEach(el => {
      const active = el.dataset.inputTab === tab;
      el.classList.toggle('active', active); el.setAttribute('aria-selected', String(active)); el.tabIndex = active ? 0 : -1;
    });
  }
  function setInput(product, label = 'Пример') {
    state.raw = JSON.stringify(product, null, 2); $('#json-input').value = state.raw;
    state.expandedSpecs = false; populateFields(product); showInputError();
    $('#input-state').textContent = label; updateStale();
  }
  function formatMarkdown(card) {
    const cell = x => String(x ?? '').replaceAll('|', '\\|').replaceAll('\n', ' ');
    const lines = [`# ${card.product_name}`, ''];
    if (card.status === 'needs_data') lines.push('**Недостаточно данных для генерации.**', '');
    else lines.push('## SEO-заголовок', card.seo_title || '', '', '## SEO-описание', card.seo_description || '', '');
    lines.push('## Характеристики', '| Параметр | Значение |', '| --- | --- |');
    (card.key_characteristics || []).forEach(f => lines.push(`| ${cell(f.name)} | ${cell(f.value)} |`));
    if (card.search_queries?.length) lines.push('', '## Поисковые запросы', ...card.search_queries.map(x => '- ' + x));
    if (card.commercial_block) lines.push('', '## Для менеджера', card.commercial_block);
    if (card.missing_fields?.length) lines.push('', '## Нужно уточнить', ...card.missing_fields.map(x => '- ' + x + ': данных нет'));
    if (card.warnings?.length) lines.push('', '## Примечания', ...card.warnings.map(x => '- ' + x));
    if (card.source_url) lines.push('', `Источник: ${card.source_url}`);
    lines.push('', 'Черновик. Требуется проверка редактором.');
    return lines.join('\n') + '\n';
  }
  function outputText(format) {
    if (!state.current) return '';
    return format === 'json' ? JSON.stringify(state.current, null, 2) : formatMarkdown(state.current);
  }
  function updateTools() {
    const enabled = !!state.current && !state.busy;
    $('#copy').disabled = !enabled; $('#export-menu-toggle').disabled = !enabled;
    $('#show-demo').disabled = state.busy || state.selected === null;
  }
  function render() {
    updateTools();
    if (!state.current) {
      $('#result').innerHTML = `<div class="empty-state"><div class="empty-icon">${icon('file')}</div><h3>Здесь будет карточка товара</h3><p>Добавьте исходные данные и подготовьте черновик.<br>Для примеров доступен результат без обращения к модели.</p></div>`;
      $('#review-strip').hidden = true;
      $('#status').textContent = 'Не создана'; $('#status').className = 'status-badge';
      $('#output-origin').textContent = 'Без автоматической публикации';
      return;
    }
    const card = state.current;
    $('#status').textContent = card.status === 'needs_data' ? 'Нужны данные' : state.kind === 'sample' ? 'Образец' : 'Черновик';
    $('#status').className = 'status-badge' + (card.status === 'needs_data' ? ' needs-data' : '');
    $('#output-origin').textContent = state.kind === 'sample' ? 'Готовый пример · без вызова API' : card.status === 'needs_data' ? 'Недостаточно данных · без вызова API' : 'Сформировано через API';
    const missing = card.missing_fields || [];
    $('#review-strip').hidden = !missing.length;
    $('#review-title').textContent = 'Нужно уточнить перед публикацией';
    $('#review-text').textContent = missing.join(' · ');
    if (state.outputTab === 'json' || state.outputTab === 'markdown') {
      $('#result').innerHTML = `<pre>${esc(outputText(state.outputTab))}</pre>`;
    } else if (state.outputTab === 'specs') {
      $('#result').innerHTML = `<p class="table-intro">Значения перенесены из исходных данных. Отсутствующие параметры отмечены отдельно.</p><table class="facts-table"><thead><tr><th>Характеристика</th><th>Значение</th></tr></thead><tbody>${(card.key_characteristics || []).map(f => `<tr><td>${esc(f.name)}</td><td class="${f.verified ? '' : 'missing-value'}">${esc(f.value)}</td></tr>`).join('')}</tbody></table>`;
    } else if (state.outputTab === 'manager') {
      const url = urlSafe(card.source_url);
      $('#result').innerHTML = `<section class="manager-section"><h3>Кому подходит и какие задачи решает</h3><p>${esc(card.commercial_block || 'Для этого блока пока недостаточно данных.')}</p></section>
        ${missing.length ? `<section class="manager-section"><h3>Что запросить у поставщика</h3><ul class="missing-list">${missing.map(x => `<li>${esc(x)}<span>данных нет</span></li>`).join('')}</ul></section>` : ''}
        ${card.warnings?.length ? `<section class="manager-section"><h3>Примечания к черновику</h3><ul class="warning-list">${card.warnings.map(x => `<li>${esc(x)}</li>`).join('')}</ul></section>` : ''}
        <section class="manager-section"><h3>Источник</h3>${url ? `<a class="source-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Открыть страницу товара ${icon('external')}</a>` : '<p>Ссылка на источник не указана.</p>'}</section>`;
    } else {
      const title = card.seo_title || '', description = card.seo_description || '';
      const n = x => Array.from(x).length.toLocaleString('ru-RU');
      $('#result').innerHTML = description ? `<div class="title-block"><div class="content-label"><span>SEO-заголовок</span><span class="counter ${Array.from(title).length > 70 ? 'invalid' : ''}">${n(title)} / 70</span></div><h3>${esc(title)}</h3></div>
        <div class="description-block"><div class="content-label"><span>SEO-описание</span><span class="counter ${Array.from(description).length < 800 || Array.from(description).length > 1200 ? 'invalid' : ''}">${n(description)} / 1 200</span></div>${description.split(/\n\s*\n/).map(p => `<p>${esc(p)}</p>`).join('')}</div>
        ${card.search_queries?.length ? `<div class="query-block"><div class="content-label"><span>Поисковые запросы</span><span class="counter">${card.search_queries.length} запроса</span></div><div class="queries">${card.search_queries.map(q => `<span class="query">${esc(q)}</span>`).join('')}</div></div>` : ''}` : `<div class="empty-state"><div class="empty-icon">${icon('info')}</div><h3>Недостаточно исходных данных</h3><p>Дополните характеристики и описание товара. Список недостающих полей — во вкладке «Для менеджера».</p><button class="quiet-btn" id="see-missing" type="button">Посмотреть недостающие поля</button></div>`;
    }
    updateStale();
  }
  function switchOutput(tab) {
    state.outputTab = tab;
    $$('[data-tab]').forEach(el => {
      const active = el.dataset.tab === tab;
      el.classList.toggle('active', active); el.setAttribute('aria-selected', String(active)); el.tabIndex = active ? 0 : -1;
    });
    $('#result').setAttribute('aria-labelledby', 'tab-' + tab);
    render();
  }
  function setCard(card, kind, source) {
    state.current = card; state.kind = kind; state.snapshot = fingerprint(source);
    showResultError(); render();
  }
  async function api(path, options = {}) {
    // Standalone preview uses explicit, supplied fixtures; live generation is never simulated.
    if (window.DRAFTLY_PREVIEW) {
      if (path === '/api/examples') return clone(window.DRAFTLY_PREVIEW.products);
      const match = path.match(/^\/api\/examples\/([^/]+)\/draft$/);
      if (match && window.DRAFTLY_PREVIEW.cards[match[1]]) return clone(window.DRAFTLY_PREVIEW.cards[match[1]]);
      throw new Error('Это автономный предпросмотр. Для настоящей генерации запустите Python-проект и подключите модель через Ollama или настройте облачный API в .env.');
    }
    const response = await fetch(path, options);
    let body;
    try { body = await response.json(); }
    catch { throw new Error('Сервер вернул ответ, который не удалось прочитать. Повторите запрос.'); }
    if (!response.ok) {
      const detail = Array.isArray(body.detail) ? body.detail.map(x => `${(x.loc || []).filter(k => k !== 'body').join('.')}: ${x.msg}`).join('; ') : '';
      throw new Error(body.message || detail || `Не удалось выполнить запрос (HTTP ${response.status}).`);
    }
    return body;
  }
  async function showSample() {
    if (state.busy || state.selected === null) return;
    const selected = state.selected, version = ++state.demoVersion;
    try {
      const card = await api(`/api/examples/${slugs[selected]}/draft`);
      if (version !== state.demoVersion || state.selected !== selected) return;
      setCard(card, 'sample', state.examples[selected]);
      mobilePane('result');
    } catch (error) { showResultError(error.message); }
  }
  async function selectProduct(index) {
    if (state.busy || !state.examples[index]) return;
    state.selected = index; state.current = null; state.snapshot = '';
    setInput(state.examples[index]); renderProducts(); showResultError(); render();
    await showSample();
  }
  function setBusy(value) {
    state.busy = value;
    $('#source-fields').disabled = value;
    $('#json-input').disabled = value;
    for (const id of ['generate', 'new-product', 'import-json', 'format-json']) $('#' + id).disabled = value;
    $$('[data-product], [data-input-tab], [data-tab]').forEach(el => { el.disabled = value; });
    $('#loading').hidden = !value; $('#result').hidden = value;
    $('.output-pane').setAttribute('aria-busy', String(value));
    $('#generate').innerHTML = value ? '<span>Подготавливаем…</span>' : '<span>Подготовить карточку</span>' + icon('arrow-right');
    if (value) { $('#review-strip').hidden = true; $('#output-origin').textContent = 'Запрос к модели · ожидание ответа'; $('#status').textContent = 'В работе'; $('#export-menu').hidden = true; $('#export-menu-toggle').setAttribute('aria-expanded', 'false'); }
    motion.loading?.setPaused(!value);
    updateTools();
  }
  async function generate() {
    if (state.busy) return;
    let product;
    try {
      product = state.inputTab === 'fields' ? collectFields() : inputObject(state.raw);
      if (!product.name?.trim()) throw new Error('Укажите название товара. Остальные отсутствующие поля можно оставить пустыми.');
      if (product.source_url && !urlSafe(product.source_url)) throw new Error('Укажите корректный URL источника, начинающийся с http:// или https://.');
      state.raw = JSON.stringify(product, null, 2); $('#json-input').value = state.raw;
      showInputError();
    } catch (error) { showInputError(error.message); mobilePane('source'); return; }
    showResultError(); ++state.demoVersion;
    const controller = new AbortController(); state.controller = controller;
    const requestId = ++state.requestId;
    setBusy(true); mobilePane('result');
    try {
      const card = await api('/api/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(product), signal: controller.signal });
      if (requestId !== state.requestId || controller.signal.aborted) return;
      setCard(card, 'live', product);
    } catch (error) {
      if (error.name === 'AbortError') showToast('Ожидание отменено. Провайдер мог уже получить запрос.');
      else showResultError(error instanceof TypeError ? 'Не удалось связаться с сервером. Проверьте, запущен ли сервис.' : error.message);
    } finally {
      if (requestId === state.requestId) { state.controller = null; setBusy(false); render(); }
    }
  }
  async function copy() {
    if (!state.current || state.busy) return;
    const text = outputText(state.outputTab === 'json' ? 'json' : 'markdown');
    try {
      await navigator.clipboard.writeText(text);
      showToast(state.outputTab === 'json' ? 'JSON скопирован' : 'Карточка скопирована в Markdown');
    } catch {
      // A clipboard failure must not erase the result.
      switchOutput(state.outputTab === 'json' ? 'json' : 'markdown');
      showToast('Буфер обмена недоступен. Скопируйте текст из открытой вкладки.');
    }
  }
  function download(format) {
    if (!state.current || state.busy) return;
    const json = format === 'json';
    const blob = new Blob([outputText(format)], { type: (json ? 'application/json' : 'text/markdown') + ';charset=utf-8' });
    const url = URL.createObjectURL(blob), a = document.createElement('a');
    const name = String(state.current.product_name || 'product').replace(/[^\p{L}\p{N}._-]/gu, '-').slice(0, 100);
    a.href = url; a.download = `${name}-card.${json ? 'json' : 'md'}`; document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
    $('#export-menu').hidden = true; $('#export-menu-toggle').setAttribute('aria-expanded', 'false');
  }
  function resetCustom(product, label) {
    ++state.demoVersion; state.selected = null; state.current = null; state.snapshot = '';
    setInput(product, label); renderProducts(); showResultError(); render(); mobilePane('source');
  }
  async function importFile(file) {
    if (!file || state.busy) return;
    try {
      if (file.size > 200000) throw new Error('Для прототипа выберите JSON-файл размером не более 200 КБ.');
      const product = inputObject((await file.text()).replace(/^\uFEFF/, ''));
      resetCustom(product, 'Импортировано'); showToast('Данные товара импортированы');
    } catch (error) { mobilePane('source'); showInputError(error.message); }
  }
  function bindTabKeyboard(selector) {
    $$(selector).forEach(tab => tab.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const tabs = $$(selector).filter(el => !el.disabled), index = tabs.indexOf(tab);
      const target = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
      tabs[target].focus(); tabs[target].click();
    }));
  }
  hydrateIcons();
  motion.brand = window.ThinkingOrbs?.mount($('#brand-orb'), { size: 32, paused: true });
  motion.loading = window.ThinkingOrbs?.mount($('#loading-orb'), { size: 64, paused: true });
  motion.help = window.ThinkingOrbs?.mount($('#help-orb'), { size: 64, paused: true });
  $('#product-list').addEventListener('click', event => {
    const button = event.target.closest('[data-product]');
    if (button) selectProduct(Number(button.dataset.product));
  });
  $('#fields-panel').addEventListener('submit', event => event.preventDefault());
  $('#fields-panel').addEventListener('input', changed);
  $('#json-input').addEventListener('input', changed);
  $('#spec-rows').addEventListener('click', event => {
    const button = event.target.closest('.remove-spec');
    if (button && !state.busy) { button.closest('.spec-row').remove(); updateSpecVisibility(); changed(); }
  });
  $('#add-spec').addEventListener('click', () => {
    state.expandedSpecs = true;
    $('#spec-rows').insertAdjacentHTML('beforeend', specRow('', '', $$('.spec-row').length));
    updateSpecVisibility(); $$('.spec-key').at(-1).focus();
  });
  $('#toggle-specs').addEventListener('click', () => { state.expandedSpecs = !state.expandedSpecs; updateSpecVisibility(); });
  $$('[data-input-tab]').forEach(el => el.addEventListener('click', () => switchInput(el.dataset.inputTab)));
  $$('[data-tab]').forEach(el => el.addEventListener('click', () => switchOutput(el.dataset.tab)));
  $$('[data-mobile-view]').forEach(el => el.addEventListener('click', () => mobilePane(el.dataset.mobileView)));
  bindTabKeyboard('[data-tab]'); bindTabKeyboard('[data-input-tab]');
  $('#format-json').addEventListener('click', () => {
    try { state.raw = JSON.stringify(inputObject($('#json-input').value), null, 2); $('#json-input').value = state.raw; showInputError(); updateStale(); }
    catch (error) { showInputError(error.message); }
  });
  $('#generate').addEventListener('click', generate);
  $('#show-demo').addEventListener('click', showSample);
  $('#cancel').addEventListener('click', () => state.controller?.abort());
  $('#copy').addEventListener('click', copy);
  $('#export-menu-toggle').addEventListener('click', () => {
    const open = $('#export-menu').hidden; $('#export-menu').hidden = !open;
    $('#export-menu-toggle').setAttribute('aria-expanded', String(open));
    if (open) $('[data-export]').focus();
  });
  $$('[data-export]').forEach(el => el.addEventListener('click', () => download(el.dataset.export)));
  document.addEventListener('click', event => {
    if (!event.target.closest('.export-wrap')) { $('#export-menu').hidden = true; $('#export-menu-toggle').setAttribute('aria-expanded', 'false'); }
    if (event.target.closest('#see-missing')) switchOutput('manager');
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !$('#export-menu').hidden) { $('#export-menu').hidden = true; $('#export-menu-toggle').setAttribute('aria-expanded', 'false'); $('#export-menu-toggle').focus(); }
  });
  $('#review-open').addEventListener('click', () => { switchOutput('manager'); $('#result').focus(); });
  $('#new-product').addEventListener('click', () => {
    resetCustom({ name: '', manufacturer: '', specs: {}, description: '' }, 'Новый товар');
    if (state.inputTab === 'fields') $('#field-name').focus(); else $('#json-input').focus();
  });
  $('#import-json').addEventListener('click', () => $('#file-input').click());
  $('.api-link').addEventListener('click', event => {
    if (window.DRAFTLY_PREVIEW) {
      event.preventDefault();
      showToast('API-документация доступна по /docs после запуска Python-сервера.');
    }
  });
  $('#file-input').addEventListener('change', async event => { await importFile(event.target.files[0]); event.target.value = ''; });
  const dialog = $('#help-dialog');
  $$('.help-trigger').forEach(el => el.addEventListener('click', () => { dialog.showModal(); motion.help?.setPaused(false); }));
  $('#close-help').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => motion.help?.setPaused(true));
  dialog.addEventListener('click', event => {
    const rect = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
  });
  window.addEventListener('pagehide', () => { Object.values(motion).forEach(orb => orb?.destroy()); state.controller?.abort(); });
  mobilePane('result'); render();
  (async () => {
    try {
      state.examples = await api('/api/examples');
      if (!Array.isArray(state.examples) || state.examples.length < 2) throw new Error('Не удалось загрузить два примера товаров.');
      await selectProduct(0);
    } catch (error) { showResultError(error.message); }
  })();
})();
