// RBx9 PDF editor: change existing text, add text, images, signatures,
// drawings, highlights and shapes. Everything runs in the browser.
//
// Objects live in page coordinates (points, top-left origin, unrotated
// viewport at scale 1) and are drawn into the original PDF with pdf-lib on save.
import { BlendMode, LineCapStyle, PDFDocument, StandardFonts, degrees, rgb } from './vendor/pdf-lib.esm.min.js';
import * as pdfjsLib from './vendor/pdf.min.mjs';

pdfjsLib.GlobalWorkerOptions.workerSrc = './vendor/pdf.worker.min.mjs';

const $ = (id) => document.getElementById(id);
const host = window.webkit?.messageHandlers?.rbx9 || null;

const ICONS = {
  select: '<path d="m4 4 7.07 17 2.51-7.39L21 11.07z"/>',
  edittext: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
  text: '<path d="M4 7V4h16v3"/><path d="M9 20h6"/><path d="M12 4v16"/>',
  draw: '<path d="M3 17c3-3 4-8 7-8s2 7 5 7 3-4 6-5"/>',
  highlight: '<path d="m9 11-6 6v3h9l3-3"/><path d="m22 12-4.6 4.6a2 2 0 0 1-2.8 0l-5.2-5.2a2 2 0 0 1 0-2.8L14 4"/>',
  whiteout: '<path d="m7 21-4.3-4.3c-1-1-1-2.5 0-3.4l9.6-9.6c1-1 2.5-1 3.4 0l5.6 5.6c1 1 1 2.5 0 3.4L13 21"/><path d="M22 21H7"/><path d="m5 11 9 9"/>',
  rect: '<rect width="18" height="14" x="3" y="5" rx="2"/>',
  image: '<rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.09-3.09a2 2 0 0 0-2.82 0L6 21"/>',
  sign: '<path d="M20 19H4"/><path d="M5 15c2-4 3-9 5-9 3 0-1 9 2 9 1.5 0 2-2 3-2s1 2 3 2"/>',
  undo: '<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>',
  redo: '<path d="M21 7v6h-6"/><path d="M3 17a9 9 0 0 1 9-9 9 9 0 0 1 6 2.3L21 13"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
  minus: '<path d="M5 12h14"/>',
  upload: '<path d="M4 14.9A7 7 0 1 1 15.7 8h1.8a4.5 4.5 0 0 1 2.5 8.2"/><path d="M12 12v9"/><path d="m16 16-4-4-4 4"/>',
  edit: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="m10.5 17.5 6-6-2-2-6 6-.5 2.5z"/>',
};
const svg = (name) => `<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`;

const TOOLS = [
  ['select', 'Select', 'Click an item to move, resize or delete it. Double-click text to edit it.'],
  ['edittext', 'Edit text', 'Click any existing text in the PDF to change it.'],
  ['text', 'Add text', 'Click where you want to add text.'],
  ['draw', 'Draw', 'Drag to draw freehand.'],
  ['highlight', 'Highlight', 'Drag over text to highlight it.'],
  ['whiteout', 'White-out', 'Drag to cover content with white.'],
  ['rect', 'Shape', 'Drag to draw a rectangle.'],
  ['image', 'Image', 'Pick an image to place on the page.'],
  ['sign', 'Sign', 'Draw or type your signature.'],
];
const COLORS = ['#111827', '#ef4444', '#2563eb', '#16a34a', '#f59e0b', '#ffffff'];
const HIGHLIGHT = '#fde047';
const FONT_CSS = { sans: 'Helvetica, Arial, sans-serif', serif: '"Times New Roman", Times, serif', mono: '"Courier New", Courier, monospace' };
// Where the baseline sits in a 1.2 line box for each family, as a fraction of the font size.
const BASELINE = { sans: 0.947, serif: 0.937, mono: 0.866 };

const state = {
  file: null, bytes: null, doc: null,
  pages: [], objects: [], images: new Map(),
  tool: 'select', selected: null, editing: null,
  color: COLORS[0], size: 16, stroke: 3, font: 'sans', bold: false, italic: false,
  zoom: 1, undo: [], redo: [], currentPage: 0, nextId: 1,
};

// ---------- setup ----------

$('start-icon').innerHTML = svg('edit');
$('start-icon').style.background = 'linear-gradient(135deg,#8b5cf6,#ec4899)';
$('drop-ic').innerHTML = svg('upload');
$('undo').innerHTML = svg('undo');
$('redo').innerHTML = svg('redo');
$('delete').innerHTML = svg('trash');
$('zoom-in').innerHTML = svg('plus');
$('zoom-out').innerHTML = svg('minus');

for (const [id, label] of TOOLS) {
  const b = document.createElement('button');
  b.className = 'tool-btn';
  b.dataset.tool = id;
  b.innerHTML = `${svg(id)}<span>${label}</span>`;
  b.addEventListener('click', () => chooseTool(id));
  $('tools').append(b);
}
for (const c of COLORS) {
  const b = document.createElement('button');
  b.className = 'swatch';
  b.style.background = c;
  b.dataset.color = c;
  b.title = c;
  b.addEventListener('click', () => setColor(c));
  $('swatches').append(b);
}
const custom = document.createElement('label');
custom.className = 'swatch custom';
custom.title = 'Custom colour';
custom.innerHTML = '<input type="color" value="#7c3aed">';
custom.querySelector('input').addEventListener('input', (e) => setColor(e.target.value));
$('swatches').append(custom);

$('file-input').addEventListener('change', (e) => { if (e.target.files[0]) openFile(e.target.files[0]); e.target.value = ''; });
const drop = $('drop');
drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
drop.addEventListener('dragleave', () => drop.classList.remove('over'));
drop.addEventListener('drop', (e) => { e.preventDefault(); drop.classList.remove('over'); if (e.dataTransfer.files[0]) openFile(e.dataTransfer.files[0]); });

$('size').addEventListener('input', (e) => { state.size = +e.target.value; $('size-out').textContent = e.target.value; applyToSelected({ size: state.size }); });
$('stroke').addEventListener('input', (e) => { state.stroke = +e.target.value; $('stroke-out').textContent = e.target.value; applyToSelected({ strokeWidth: state.stroke }); });
$('font').addEventListener('change', (e) => { state.font = e.target.value; applyToSelected({ font: state.font }); });
$('bold').addEventListener('click', () => { state.bold = !state.bold; syncProps(); applyToSelected({ bold: state.bold }); });
$('italic').addEventListener('click', () => { state.italic = !state.italic; syncProps(); applyToSelected({ italic: state.italic }); });
$('delete').addEventListener('click', deleteSelected);
$('undo').addEventListener('click', undo);
$('redo').addEventListener('click', redo);
$('save').addEventListener('click', save);
$('zoom-in').addEventListener('click', () => setZoom(state.zoom * 1.2));
$('zoom-out').addEventListener('click', () => setZoom(state.zoom / 1.2));
$('image-input').addEventListener('change', (e) => { if (e.target.files[0]) addImageFile(e.target.files[0]); e.target.value = ''; });

document.addEventListener('keydown', (e) => {
  if (state.editing || /INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName)) return;
  const mod = e.ctrlKey || e.metaKey;
  if (mod && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo(); }
  else if (mod && e.key.toLowerCase() === 'y') { e.preventDefault(); redo(); }
  else if ((e.key === 'Delete' || e.key === 'Backspace') && state.selected) { e.preventDefault(); deleteSelected(); }
  else if (e.key === 'Escape') select(null);
});
window.addEventListener('beforeunload', (e) => { if (state.undo.length && state.undo.length !== state.savedAt) e.preventDefault(); });
window.addEventListener('resize', () => { if (state.doc) layoutPages(); });

// ---------- loading & rendering ----------

async function openFile(file) {
  $('start-status').textContent = 'Opening…';
  $('start-status').classList.remove('error');
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    const doc = await pdfjsLib.getDocument({ data: bytes.slice() }).promise;
    Object.assign(state, { file, bytes, doc, objects: [], undo: [], redo: [], selected: null, pages: [] });
    $('doc-name').textContent = file.name;
    $('start').hidden = true;
    $('workspace').hidden = false;
    $('save').disabled = false;
    await buildPages();
    chooseTool('edittext');
  } catch (err) {
    console.error(err);
    const locked = /password/i.test(err?.message || '') || err?.name === 'PasswordException';
    $('start-status').textContent = locked ? 'This PDF is password-protected. Unlock it first.' : 'That file could not be opened as a PDF.';
    $('start-status').classList.add('error');
  }
}

async function buildPages() {
  const wrap = $('pages');
  wrap.replaceChildren();
  const observer = new IntersectionObserver((entries) => {
    for (const en of entries) {
      const info = state.pages[+en.target.dataset.index];
      if (en.isIntersecting) {
        if (!info.rendered) renderPage(info);
        if (en.intersectionRatio > 0.3) state.currentPage = info.index;
      }
    }
  }, { rootMargin: '600px 0px', threshold: [0, 0.3] });
  for (let n = 1; n <= state.doc.numPages; n++) {
    const page = await state.doc.getPage(n);
    const viewport = page.getViewport({ scale: 1 });
    const box = document.createElement('div');
    box.className = 'page-box';
    box.dataset.index = n - 1;
    const canvas = document.createElement('canvas');
    const layer = document.createElement('div');
    layer.className = 'layer';
    layer.style.width = `${viewport.width}px`;
    layer.style.height = `${viewport.height}px`;
    const num = document.createElement('div');
    num.className = 'page-num';
    num.textContent = `${n} / ${state.doc.numPages}`;
    box.append(canvas, layer, num);
    wrap.append(box);
    const info = { index: n - 1, page, viewport, box, canvas, layer, lines: [], rendered: false, renderTask: null };
    state.pages.push(info);
    attachLayer(info);
    observer.observe(box);
  }
  layoutPages();
}

function pageScale(info) {
  const avail = Math.min(980, document.documentElement.clientWidth - 32);
  return (avail / info.viewport.width) * state.zoom;
}

function layoutPages() {
  for (const info of state.pages) {
    const k = pageScale(info);
    info.scale = k;
    info.box.style.width = `${info.viewport.width * k}px`;
    info.box.style.height = `${info.viewport.height * k}px`;
    info.layer.style.transform = `scale(${k})`;
    if (info.rendered) { info.rendered = false; renderPage(info); }
  }
  $('zoom-out-label').textContent = `${Math.round(state.zoom * 100)}%`;
}

function setZoom(z) {
  state.zoom = Math.min(3, Math.max(0.4, z));
  layoutPages();
}

async function renderPage(info) {
  info.rendered = true;
  const k = info.scale * (window.devicePixelRatio || 1);
  const vp = info.page.getViewport({ scale: k });
  const canvas = document.createElement('canvas');
  canvas.width = Math.ceil(vp.width);
  canvas.height = Math.ceil(vp.height);
  info.renderTask?.cancel();
  info.renderTask = info.page.render({ canvasContext: canvas.getContext('2d'), viewport: vp });
  try { await info.renderTask.promise; } catch { return; }
  info.box.replaceChild(canvas, info.canvas);
  info.canvas = canvas;
  if (!info.lines.length) info.lines = await textLines(info);
  drawLayer(info);
}

// Groups the page's text into editable line segments with their font details.
async function textLines(info) {
  const content = await info.page.getTextContent();
  const segs = [];
  for (const it of content.items) {
    if (!it.str || !it.str.trim()) continue;
    const tx = pdfjsLib.Util.transform(info.viewport.transform, it.transform);
    const size = Math.hypot(tx[2], tx[3]);
    if (size < 2 || Math.abs(tx[1]) > Math.abs(tx[0]) * 0.1) continue; // skip rotated text
    let name = content.styles[it.fontName]?.fontFamily || '';
    let font = null;
    try { if (info.page.commonObjs.has(it.fontName)) { font = info.page.commonObjs.get(it.fontName); name = font.name || name; } } catch { /* not loaded */ }
    const seg = {
      text: it.str, x: tx[4], base: tx[5], w: it.width, size,
      bold: !!font?.bold || /bold|black|heavy|semibold|demi/i.test(name),
      italic: !!font?.italic || /italic|oblique/i.test(name),
      font: /courier|mono|consol/i.test(name) || font?.isMonospace ? 'mono' : /times|serif|georgia|garamond|cambria|minion|roman/i.test(name) && !/sans/i.test(name) || font?.isSerifFont ? 'serif' : 'sans',
    };
    const last = segs[segs.length - 1];
    if (last && Math.abs(last.base - seg.base) < size * 0.3 && seg.x - (last.x + last.w) < size * 1.2 && seg.x >= last.x
        && Math.abs(last.size - seg.size) < 1 && last.font === seg.font && last.bold === seg.bold && last.italic === seg.italic) {
      const gap = seg.x - (last.x + last.w);
      last.text += (gap > size * 0.15 && !/\s$/.test(last.text) ? ' ' : '') + seg.text;
      last.w = seg.x + seg.w - last.x;
    } else segs.push(seg);
  }
  return segs.map((s, i) => ({ ...s, id: `L${info.index}_${i}`, y: s.base - s.size * 0.92, h: s.size * 1.18 }));
}

// ---------- Apple Pencil ----------

const DRAWING_TOOLS = ['draw', 'highlight', 'whiteout', 'rect'];

// Stroke width multiplier from Pencil pressure (about 0.35–1.65; 1 for mouse and touch).
const pressureWidth = (e) => (e.pointerType === 'pen' && e.pressure > 0 ? 0.35 + e.pressure * 1.3 : 1);

function segmentSvg(a, b, color, width, ox, oy) {
  return `<line x1="${(a[0] - ox).toFixed(1)}" y1="${(a[1] - oy).toFixed(1)}" x2="${(b[0] - ox).toFixed(1)}" y2="${(b[1] - oy).toFixed(1)}" stroke="${color}" stroke-width="${(width * ((a[2] ?? 1) + (b[2] ?? 1)) / 2).toFixed(2)}" stroke-linecap="round"/>`;
}

// The first time an Apple Pencil touches the page, drawing switches to
// Pencil-only so fingers and palms scroll instead of leaving marks.
function notePencil(e) {
  if (e.pointerType !== 'pen' || state.penSeen) return;
  state.penSeen = true;
  setPencilOnly(true);
}

function setPencilOnly(on) {
  state.pencilOnly = on;
  document.body.classList.toggle('pencil-only', on);
  $('pencil-only').hidden = !state.penSeen;
  $('pencil-only').classList.toggle('on', on);
}

$('pencil-only').addEventListener('click', () => setPencilOnly(!state.pencilOnly));

// ---------- objects ----------

const uid = () => `o${state.nextId++}`;
const findObj = (id) => state.objects.find((o) => o.id === id);

function snapshot() {
  state.undo.push(JSON.stringify(state.objects));
  if (state.undo.length > 150) state.undo.shift();
  state.redo = [];
  syncHistory();
}

function restore(json) {
  state.objects = JSON.parse(json);
  state.selected = null;
  state.editing = null;
  redrawAll();
  syncProps();
}

function undo() {
  if (!state.undo.length) return;
  state.redo.push(JSON.stringify(state.objects));
  restore(state.undo.pop());
  syncHistory();
}

function redo() {
  if (!state.redo.length) return;
  state.undo.push(JSON.stringify(state.objects));
  restore(state.redo.pop());
  syncHistory();
}

function syncHistory() {
  $('undo').disabled = !state.undo.length;
  $('redo').disabled = !state.redo.length;
}

function addObject(obj, { edit = false } = {}) {
  const before = JSON.stringify(state.objects);
  if (!edit) snapshot();
  obj.id = uid();
  state.objects.push(obj);
  select(obj.id);
  if (edit) {
    startEditing(obj.id, true);
    state.editBefore = before; // adding and typing are one undo step
  }
  return obj;
}

function updateObject(id, patch, { record = true } = {}) {
  const obj = findObj(id);
  if (!obj) return;
  if (record) snapshot();
  Object.assign(obj, patch);
  drawLayer(state.pages[obj.page]);
}

function deleteSelected() {
  const obj = findObj(state.selected);
  if (!obj) return;
  snapshot();
  // Deleting replaced text also removes the white cover that hid the original.
  state.objects = state.objects.filter((o) => o.id !== obj.id && !(obj.cover && o.id === obj.cover));
  state.selected = null;
  drawLayer(state.pages[obj.page]);
  syncProps();
}

function applyToSelected(patch) {
  const obj = findObj(state.selected);
  if (!obj) return;
  const allowed = obj.type === 'text' ? ['size', 'font', 'bold', 'italic', 'color']
    : obj.type === 'path' ? ['strokeWidth', 'color']
    : obj.type === 'rect' ? ['strokeWidth', 'color'] : [];
  const p = Object.fromEntries(Object.entries(patch).filter(([k]) => allowed.includes(k)));
  if (Object.keys(p).length) updateObject(obj.id, p);
  if (obj.type === 'text') measureText(obj);
}

function redrawAll() { state.pages.forEach(drawLayer); }

function drawLayer(info) {
  if (!info) return;
  const layer = info.layer;
  const editingEl = state.editing && layer.querySelector(`[data-id="${state.editing}"]`);
  if (editingEl) findObj(state.editing).text = editingEl.innerText.replace(/\n$/, '');
  layer.className = `layer tool-${state.tool}`;
  state.rebuilding = true;
  layer.replaceChildren();
  const replaced = new Set(state.objects.filter((o) => o.replaces).map((o) => o.replaces));
  for (const line of info.lines) {
    if (replaced.has(line.id)) continue;
    const hit = document.createElement('div');
    hit.className = 'hit';
    hit.dataset.line = line.id;
    Object.assign(hit.style, { left: `${line.x - 1}px`, top: `${line.y - 1}px`, width: `${line.w + 2}px`, height: `${line.h + 2}px` });
    layer.append(hit);
  }
  for (const obj of state.objects.filter((o) => o.page === info.index)) layer.append(objectElement(obj));
  state.rebuilding = false;
  if (editingEl) focusEditor(layer.querySelector(`[data-id="${state.editing}"]`), false);
}

function objectElement(o) {
  const el = document.createElement('div');
  el.className = `obj ${o.type}`;
  el.dataset.id = o.id;
  el.style.left = `${o.x}px`;
  el.style.top = `${o.y}px`;
  if (o.type !== 'text') { el.style.width = `${o.w}px`; el.style.height = `${o.h}px`; }
  if (o.type === 'text') {
    Object.assign(el.style, { fontSize: `${o.size}px`, fontFamily: FONT_CSS[o.font], color: o.color, fontWeight: o.bold ? 700 : 400, fontStyle: o.italic ? 'italic' : 'normal' });
    el.textContent = o.text;
    if (state.editing === o.id) el.contentEditable = 'true';
  } else if (o.type === 'image') {
    const img = document.createElement('img');
    img.src = state.images.get(o.image).url;
    img.alt = '';
    el.append(img);
  } else if (o.type === 'rect') {
    el.style.background = o.fill || 'transparent';
    if (o.stroke) el.style.border = `${o.strokeWidth}px solid ${o.color}`;
  } else if (o.type === 'highlight') {
    el.style.background = o.color;
    el.style.opacity = 0.4;
  } else if (o.type === 'path') {
    const shape = o.pressure
      ? o.points.slice(1).map((b, i) => segmentSvg(o.points[i], b, o.color, o.strokeWidth, o.x, o.y)).join('')
      : `<polyline points="${o.points.map(([x, y]) => `${(x - o.x).toFixed(1)},${(y - o.y).toFixed(1)}`).join(' ')}" fill="none" stroke="${o.color}" stroke-width="${o.strokeWidth}" stroke-linecap="round" stroke-linejoin="round"/>`;
    el.innerHTML = `<svg width="${o.w}" height="${o.h}">${shape}</svg>`;
  }
  if (state.selected === o.id && state.editing !== o.id) {
    el.classList.add('selected');
    if (o.type !== 'path') {
      const h = document.createElement('div');
      h.className = 'handle';
      el.append(h);
    }
  }
  return el;
}

function select(id) {
  if (state.editing && state.editing !== id) finishEditing();
  state.selected = id;
  const obj = findObj(id);
  if (obj?.type === 'text') Object.assign(state, { size: Math.round(obj.size), font: obj.font, bold: obj.bold, italic: obj.italic, color: obj.color });
  if (obj?.strokeWidth) state.stroke = obj.strokeWidth;
  redrawAll();
  syncProps();
}

// ---------- text editing ----------

function startEditing(id, selectAll = false) {
  const obj = findObj(id);
  if (!obj || obj.type !== 'text') return;
  state.editing = id;
  state.selected = id;
  state.editBefore = JSON.stringify(state.objects);
  drawLayer(state.pages[obj.page]);
  focusEditor(state.pages[obj.page].layer.querySelector(`[data-id="${id}"]`), selectAll);
  syncProps();
}

function focusEditor(el, selectAll) {
  if (!el) return;
  state.rebuilding = true;
  el.focus();
  state.rebuilding = false;
  const range = document.createRange();
  range.selectNodeContents(el);
  if (!selectAll) range.collapse(false);
  const sel = getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
}

function finishEditing() {
  const id = state.editing;
  if (!id) return;
  const obj = findObj(id);
  state.editing = null;
  if (!obj) return;
  const el = state.pages[obj.page].layer.querySelector(`[data-id="${id}"]`);
  const text = (el?.innerText ?? obj.text).replace(/\n$/, '');
  if (!text.trim()) {
    state.objects = state.objects.filter((o) => o.id !== id && o.id !== obj.cover);
    state.selected = null;
  } else obj.text = text;
  // The whole edit session is one undo step (the snapshot taken when it started).
  if (state.editBefore && state.editBefore !== JSON.stringify(state.objects)) {
    state.undo.push(state.editBefore);
    state.redo = [];
  }
  state.editBefore = null;
  if (findObj(id)) measureText(findObj(id));
  drawLayer(state.pages[obj.page]);
  syncHistory();
  syncProps();
}

// Text boxes size themselves to their content; remember the size for hit-testing.
function measureText(obj) {
  const probe = objectElement({ ...obj, id: '__probe' });
  probe.style.visibility = 'hidden';
  state.pages[obj.page].layer.append(probe);
  obj.w = probe.offsetWidth;
  obj.h = probe.offsetHeight;
  probe.remove();
}

// Replaces a line of the original PDF: a cover in the page's background colour
// hides it, and an editable text box takes its place.
function replaceLine(info, line) {
  const { bg, ink } = sampleColors(info, line);
  const before = JSON.stringify(state.objects);
  const cover = { id: uid(), page: info.index, type: 'rect', x: line.x - 1, y: line.y, w: line.w + 2, h: line.h, fill: bg, auto: true };
  const text = {
    id: uid(), page: info.index, type: 'text', text: line.text, x: line.x, y: line.base - line.size * BASELINE[line.font],
    size: Math.round(line.size * 10) / 10, font: line.font, bold: line.bold, italic: line.italic, color: ink, replaces: line.id, cover: cover.id,
  };
  state.objects.push(cover, text);
  select(text.id);
  startEditing(text.id);
  state.editBefore = before; // replacing and typing are one undo step
}

function sampleColors(info, box) {
  const fallback = { bg: '#ffffff', ink: '#111827' };
  try {
    const k = info.canvas.width / info.viewport.width;
    const sx = Math.max(0, Math.floor((box.x - 2) * k)), sy = Math.max(0, Math.floor(box.y * k));
    const sw = Math.max(1, Math.ceil((box.w + 4) * k)), sh = Math.max(1, Math.ceil(box.h * k));
    const data = info.canvas.getContext('2d').getImageData(sx, sy, sw, sh).data;
    const counts = new Map();
    for (let i = 0; i < data.length; i += 4) {
      const key = ((data[i] >> 3) << 10) | ((data[i + 1] >> 3) << 5) | (data[i + 2] >> 3);
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    const bgKey = [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0];
    // Average the real pixels in the most common colour bucket, so white stays exactly white.
    const sum = [0, 0, 0];
    let n = 0;
    for (let i = 0; i < data.length; i += 4) {
      if ((((data[i] >> 3) << 10) | ((data[i + 1] >> 3) << 5) | (data[i + 2] >> 3)) !== bgKey) continue;
      sum[0] += data[i]; sum[1] += data[i + 1]; sum[2] += data[i + 2]; n++;
    }
    const bg = sum.map((v) => Math.round(v / n));
    let best = 0, ink = [17, 24, 39];
    for (let i = 0; i < data.length; i += 4) {
      const d = Math.abs(data[i] - bg[0]) + Math.abs(data[i + 1] - bg[1]) + Math.abs(data[i + 2] - bg[2]);
      if (d > best) { best = d; ink = [data[i], data[i + 1], data[i + 2]]; }
    }
    const hex = (c) => `#${c.map((v) => Math.min(255, v).toString(16).padStart(2, '0')).join('')}`;
    return { bg: hex(bg), ink: best > 60 ? hex(ink) : fallback.ink };
  } catch { return fallback; }
}

// ---------- pointer interaction ----------

function toPage(info, e) {
  const r = info.layer.getBoundingClientRect();
  return [(e.clientX - r.left) / info.scale, (e.clientY - r.top) / info.scale];
}

function attachLayer(info) {
  const layer = info.layer;
  layer.addEventListener('focusout', (e) => {
    if (!state.rebuilding && e.target.matches?.('[contenteditable=true]')) finishEditing();
  });
  layer.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && e.target.matches?.('[contenteditable=true]')) { e.preventDefault(); e.target.blur(); }
  });
  layer.addEventListener('paste', (e) => {
    if (!e.target.closest?.('[contenteditable=true]')) return;
    e.preventDefault();
    document.execCommand('insertText', false, e.clipboardData.getData('text/plain'));
  });
  layer.addEventListener('dblclick', (e) => {
    const el = e.target.closest('.obj.text');
    if (el) startEditing(el.dataset.id);
  });
  // Stop the page scrolling under the Pencil while drawing; fingers still scroll.
  layer.addEventListener('touchstart', (e) => {
    if (DRAWING_TOOLS.includes(state.tool) && [...e.changedTouches].some((t) => t.touchType === 'stylus')) e.preventDefault();
  }, { passive: false });
  layer.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || e.target.closest('[contenteditable=true]')) return;
    notePencil(e);
    if (state.pencilOnly && e.pointerType === 'touch' && DRAWING_TOOLS.includes(state.tool)) return; // finger scrolls
    const [x, y] = toPage(info, e);
    const objEl = e.target.closest('.obj');
    const tool = state.tool;

    if (tool === 'edittext') {
      const hit = e.target.closest('.hit');
      if (hit) { e.preventDefault(); replaceLine(info, info.lines.find((l) => l.id === hit.dataset.line)); return; }
      if (objEl && findObj(objEl.dataset.id)?.type === 'text') { e.preventDefault(); select(objEl.dataset.id); startEditing(objEl.dataset.id); return; }
    }
    if (tool === 'select' || tool === 'edittext') {
      if (!objEl) { select(null); return; }
      e.preventDefault();
      const obj = findObj(objEl.dataset.id);
      if (state.selected !== obj.id) select(obj.id);
      const resizing = e.target.classList.contains('handle');
      drag(info, e, obj, resizing ? 'resize' : 'move', [x, y]);
      return;
    }
    if (tool === 'text') {
      e.preventDefault();
      chooseTool('select');
      addObject({ page: info.index, type: 'text', text: 'Type here', x, y: y - state.size * 0.6, size: state.size, font: state.font, bold: state.bold, italic: state.italic, color: state.color }, { edit: true });
      return;
    }
    if (tool === 'draw') { e.preventDefault(); drawPath(info, e, [x, y]); return; }
    if (tool === 'highlight' || tool === 'whiteout' || tool === 'rect') { e.preventDefault(); dragRect(info, e, [x, y], tool); }
  });
}

function trackPointer(target, e, onMove, onUp) {
  try { target.setPointerCapture(e.pointerId); } catch { /* pointer already gone */ }
  // Only follow the pointer that started the gesture, so a resting palm or a
  // second finger can't disturb an Apple Pencil stroke.
  const move = (ev) => { if (ev.pointerId === e.pointerId) onMove(ev); };
  const up = (ev) => {
    if (ev.pointerId !== e.pointerId) return;
    target.removeEventListener('pointermove', move);
    target.removeEventListener('pointerup', up);
    target.removeEventListener('pointercancel', up);
    onUp(ev);
  };
  target.addEventListener('pointermove', move);
  target.addEventListener('pointerup', up);
  target.addEventListener('pointercancel', up);
}

function drag(info, e, obj, mode, start) {
  const orig = { ...obj, points: obj.points?.map((p) => [...p]) };
  const before = JSON.stringify(state.objects);
  let moved = false;
  trackPointer(info.layer, e, (ev) => {
    const [x, y] = toPage(info, ev);
    const dx = x - start[0], dy = y - start[1];
    if (Math.abs(dx) + Math.abs(dy) > 1) moved = true;
    if (!moved) return;
    if (mode === 'move') {
      obj.x = orig.x + dx;
      obj.y = orig.y + dy;
      if (obj.points) obj.points = orig.points.map(([px, py, ...rest]) => [px + dx, py + dy, ...rest]);
    } else if (obj.type === 'text') {
      // Resizing text scales its font.
      obj.size = Math.max(4, orig.size * Math.max(0.2, (orig.w + dx) / orig.w));
    } else if (obj.type === 'image') {
      const s = Math.max(0.05, (orig.w + dx) / orig.w);
      obj.w = orig.w * s;
      obj.h = orig.h * s; // keep the picture's proportions
    } else {
      obj.w = Math.max(4, orig.w + dx);
      obj.h = Math.max(4, orig.h + dy);
    }
    info.layer.querySelector(`[data-id="${obj.id}"]`)?.replaceWith(objectElement(obj));
  }, () => {
    if (!moved) return;
    if (obj.type === 'text') measureText(obj);
    state.undo.push(before);
    state.redo = [];
    syncHistory();
    drawLayer(info);
    syncProps();
  });
}

function drawPath(info, e, start) {
  const pen = e.pointerType === 'pen';
  const points = [[start[0], start[1], pressureWidth(e)]];
  const obj = { page: info.index, type: 'path', points, color: state.color, strokeWidth: state.stroke, pressure: pen, x: start[0], y: start[1], w: 1, h: 1 };
  const preview = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  Object.assign(preview.style, { position: 'absolute', left: 0, top: 0, overflow: 'visible', pointerEvents: 'none' });
  preview.setAttribute('width', info.viewport.width);
  preview.setAttribute('height', info.viewport.height);
  const line = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
  Object.entries({ fill: 'none', stroke: state.color, 'stroke-width': state.stroke, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }).forEach(([k, v]) => line.setAttribute(k, v));
  if (!pen) preview.append(line);
  info.layer.append(preview);
  trackPointer(info.layer, e, (ev) => {
    // Coalesced events carry every sample the Pencil reported, for smoother lines.
    const samples = ev.getCoalescedEvents?.().length ? ev.getCoalescedEvents() : [ev];
    for (const sample of samples) {
      const p = toPage(info, sample);
      const last = points[points.length - 1];
      if (Math.hypot(p[0] - last[0], p[1] - last[1]) < 0.6) continue;
      const next = [p[0], p[1], pen ? last[2] * 0.6 + pressureWidth(sample) * 0.4 : 1];
      points.push(next);
      if (pen) preview.insertAdjacentHTML('beforeend', segmentSvg(last, next, state.color, state.stroke, 0, 0));
    }
    if (!pen) line.setAttribute('points', points.map((q) => `${q[0]},${q[1]}`).join(' '));
  }, () => {
    preview.remove();
    if (points.length < 2) return;
    const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
    Object.assign(obj, { x: Math.min(...xs), y: Math.min(...ys), w: Math.max(1, Math.max(...xs) - Math.min(...xs)), h: Math.max(1, Math.max(...ys) - Math.min(...ys)) });
    addObject(obj);
    state.selected = null;
    drawLayer(info);
    syncProps();
  });
}

function dragRect(info, e, start, kind) {
  const ghost = document.createElement('div');
  ghost.className = `obj ${kind === 'highlight' ? 'highlight' : 'rect'}`;
  const style = kind === 'highlight' ? { background: HIGHLIGHT, opacity: 0.4 }
    : kind === 'whiteout' ? { background: '#fff', outline: '1px dashed #94a3b8' } : { border: `${state.stroke}px solid ${state.color}` };
  Object.assign(ghost.style, style);
  info.layer.append(ghost);
  let rect = null;
  trackPointer(info.layer, e, (ev) => {
    const [x, y] = toPage(info, ev);
    rect = { x: Math.min(x, start[0]), y: Math.min(y, start[1]), w: Math.abs(x - start[0]), h: Math.abs(y - start[1]) };
    Object.assign(ghost.style, { left: `${rect.x}px`, top: `${rect.y}px`, width: `${rect.w}px`, height: `${rect.h}px` });
  }, () => {
    ghost.remove();
    if (!rect || rect.w < 3 || rect.h < 3) return;
    const base = { page: info.index, ...rect };
    if (kind === 'highlight') addObject({ ...base, type: 'highlight', color: HIGHLIGHT });
    else if (kind === 'whiteout') addObject({ ...base, type: 'rect', fill: '#ffffff' });
    else addObject({ ...base, type: 'rect', stroke: true, color: state.color, strokeWidth: state.stroke });
    state.selected = null;
    drawLayer(info);
    syncProps();
  });
}

// ---------- images & signatures ----------

async function storeImage(blob) {
  let type = blob.type;
  let bytes = new Uint8Array(await blob.arrayBuffer());
  const bitmap = await createImageBitmap(blob);
  if (type !== 'image/png' && type !== 'image/jpeg') {
    // pdf-lib embeds PNG and JPEG only, so convert everything else.
    const c = document.createElement('canvas');
    c.width = bitmap.width;
    c.height = bitmap.height;
    c.getContext('2d').drawImage(bitmap, 0, 0);
    const png = await new Promise((r) => c.toBlob(r, 'image/png'));
    bytes = new Uint8Array(await png.arrayBuffer());
    type = 'image/png';
  }
  const id = `img${state.images.size + 1}`;
  state.images.set(id, { bytes, type, url: URL.createObjectURL(new Blob([bytes], { type })) });
  return { id, width: bitmap.width, height: bitmap.height };
}

function placeOnCurrentPage(imageId, w, h) {
  const info = state.pages[state.currentPage] || state.pages[0];
  const r = info.box.getBoundingClientRect();
  // Centre of the visible part of the page.
  const top = Math.max(0, -r.top + 140) / info.scale;
  const bottom = Math.min(info.viewport.height, (innerHeight - r.top) / info.scale);
  const cy = (top + bottom) / 2;
  addObject({ page: info.index, type: 'image', image: imageId, x: (info.viewport.width - w) / 2, y: Math.max(8, cy - h / 2), w, h });
  chooseTool('select', { keepSelection: true });
}

async function addImageFile(file) {
  const { id, width, height } = await storeImage(file);
  const info = state.pages[state.currentPage] || state.pages[0];
  const s = Math.min(1, (info.viewport.width * 0.5) / width, (info.viewport.height * 0.5) / height);
  placeOnCurrentPage(id, width * s, height * s);
}

const sign = { mode: 'draw', strokes: [] };
const pad = $('sign-pad');
const padCtx = pad.getContext('2d');

function openSignature() {
  sign.strokes = [];
  clearPad();
  $('sign-text').value = '';
  $('sign-preview').textContent = '';
  $('sign-dialog').showModal();
}

function clearPad() {
  padCtx.clearRect(0, 0, pad.width, pad.height);
  sign.strokes = [];
}

$('sign-clear').addEventListener('click', () => { clearPad(); $('sign-text').value = ''; $('sign-preview').textContent = ''; });
document.querySelectorAll('#sign-dialog .chip').forEach((chip) => chip.addEventListener('click', () => {
  sign.mode = chip.dataset.mode;
  document.querySelectorAll('#sign-dialog .chip').forEach((c) => c.classList.toggle('on', c === chip));
  $('sign-draw').hidden = sign.mode !== 'draw';
  $('sign-type').hidden = sign.mode !== 'type';
}));
const updatePreview = () => {
  $('sign-preview').textContent = $('sign-text').value;
  $('sign-preview').style.fontFamily = `"${$('sign-font').value}", cursive`;
};
$('sign-text').addEventListener('input', updatePreview);
$('sign-font').addEventListener('change', updatePreview);

pad.addEventListener('pointerdown', (e) => {
  e.preventDefault();
  const r = pad.getBoundingClientRect();
  const at = (ev) => [(ev.clientX - r.left) * (pad.width / r.width), (ev.clientY - r.top) * (pad.height / r.height)];
  const stroke = [at(e)];
  sign.strokes.push(stroke);
  Object.assign(padCtx, { strokeStyle: '#111827', lineCap: 'round', lineJoin: 'round' });
  pad.setPointerCapture(e.pointerId);
  let width = pressureWidth(e);
  const move = (ev) => {
    const samples = ev.getCoalescedEvents?.().length ? ev.getCoalescedEvents() : [ev];
    for (const sample of samples) {
      const p = at(sample);
      const last = stroke[stroke.length - 1];
      width = width * 0.6 + pressureWidth(sample) * 0.4;
      padCtx.lineWidth = 5 * width;
      padCtx.beginPath();
      padCtx.moveTo(...last);
      padCtx.lineTo(...p);
      padCtx.stroke();
      stroke.push(p);
    }
  };
  const up = () => { pad.removeEventListener('pointermove', move); pad.removeEventListener('pointerup', up); };
  pad.addEventListener('pointermove', move);
  pad.addEventListener('pointerup', up);
});

$('sign-add').addEventListener('click', async () => {
  let canvas;
  if (sign.mode === 'draw') {
    if (!sign.strokes.length) return;
    canvas = trimCanvas(pad);
  } else {
    const text = $('sign-text').value.trim();
    if (!text) return;
    const family = $('sign-font').value;
    await document.fonts.load(`120px "${family}"`);
    canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    ctx.font = `120px "${family}"`;
    canvas.width = Math.ceil(ctx.measureText(text).width + 40);
    canvas.height = 190;
    ctx.font = `120px "${family}"`;
    ctx.fillStyle = '#111827';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, 20, 95);
    canvas = trimCanvas(canvas);
  }
  const blob = await new Promise((r) => canvas.toBlob(r, 'image/png'));
  $('sign-dialog').close();
  const { id, width, height } = await storeImage(blob);
  const w = 170, h = (height / width) * w;
  placeOnCurrentPage(id, w, h);
});

// Crops a canvas to its drawn pixels plus a small margin.
function trimCanvas(src) {
  const { width, height } = src;
  const data = src.getContext('2d').getImageData(0, 0, width, height).data;
  let minX = width, minY = height, maxX = 0, maxY = 0;
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    if (data[(y * width + x) * 4 + 3] > 10) { minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y); }
  }
  if (maxX < minX) return src;
  const m = 8;
  const out = document.createElement('canvas');
  out.width = maxX - minX + m * 2;
  out.height = maxY - minY + m * 2;
  out.getContext('2d').drawImage(src, minX - m, minY - m, out.width, out.height, 0, 0, out.width, out.height);
  return out;
}

// ---------- toolbar state ----------

function chooseTool(tool, { keepSelection = false } = {}) {
  if (tool === 'image') { $('image-input').click(); return; }
  if (tool === 'sign') { openSignature(); return; }
  state.tool = tool;
  if (!keepSelection) { if (state.editing) finishEditing(); state.selected = null; }
  document.querySelectorAll('.tool-btn').forEach((b) => b.classList.toggle('on', b.dataset.tool === tool));
  $('hint').textContent = TOOLS.find((t) => t[0] === tool)?.[2] || '';
  redrawAll();
  syncProps();
}

function setColor(c) {
  state.color = c;
  syncProps();
  applyToSelected({ color: c });
}

function syncProps() {
  const obj = findObj(state.selected);
  const kind = obj?.type || state.tool;
  const isText = kind === 'text' || kind === 'edittext';
  const isStroke = kind === 'draw' || kind === 'rect' || kind === 'path';
  $('prop-size').hidden = !isText;
  $('prop-font').hidden = !isText;
  $('prop-stroke').hidden = !isStroke;
  $('swatches').hidden = !(isText || isStroke);
  $('delete').hidden = !obj;
  $('size').value = state.size;
  $('size-out').textContent = state.size;
  $('stroke').value = state.stroke;
  $('stroke-out').textContent = state.stroke;
  $('font').value = state.font;
  $('bold').classList.toggle('on', state.bold);
  $('italic').classList.toggle('on', state.italic);
  document.querySelectorAll('.swatch[data-color]').forEach((s) => s.classList.toggle('on', s.dataset.color.toLowerCase() === state.color.toLowerCase()));
}

// ---------- saving ----------

const hexToRgb = (hex) => {
  const n = parseInt(hex.replace('#', '').padEnd(6, '0').slice(0, 6), 16);
  return rgb(((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255);
};

const STANDARD = {
  sans: [StandardFonts.Helvetica, StandardFonts.HelveticaBold, StandardFonts.HelveticaOblique, StandardFonts.HelveticaBoldOblique],
  serif: [StandardFonts.TimesRoman, StandardFonts.TimesRomanBold, StandardFonts.TimesRomanItalic, StandardFonts.TimesRomanBoldItalic],
  mono: [StandardFonts.Courier, StandardFonts.CourierBold, StandardFonts.CourierOblique, StandardFonts.CourierBoldOblique],
};

// Text the standard PDF fonts can't encode (emoji, non-Latin scripts) is drawn as a sharp image instead.
async function textAsPng(o) {
  const scale = 4;
  const c = document.createElement('canvas');
  c.width = Math.ceil(o.w * scale) + 4;
  c.height = Math.ceil(o.h * scale) + 4;
  const ctx = c.getContext('2d');
  ctx.scale(scale, scale);
  ctx.font = `${o.italic ? 'italic ' : ''}${o.bold ? 700 : 400} ${o.size}px ${FONT_CSS[o.font]}`;
  ctx.fillStyle = o.color;
  ctx.textBaseline = 'alphabetic';
  o.text.split('\n').forEach((line, i) => ctx.fillText(line, 0, o.size * BASELINE[o.font] + i * o.size * 1.2));
  return new Uint8Array(await (await new Promise((r) => c.toBlob(r, 'image/png'))).arrayBuffer());
}

async function save() {
  if (state.editing) finishEditing();
  const btn = $('save');
  btn.disabled = true;
  btn.classList.add('busy');
  try {
    const out = await PDFDocument.load(state.bytes);
    const pages = out.getPages();
    const fontCache = new Map();
    const font = async (name) => {
      if (!fontCache.has(name)) fontCache.set(name, await out.embedFont(name));
      return fontCache.get(name);
    };
    const embedded = new Map();
    const image = async (id) => {
      if (!embedded.has(id)) {
        const img = state.images.get(id);
        embedded.set(id, img.type === 'image/png' ? await out.embedPng(img.bytes) : await out.embedJpg(img.bytes));
      }
      return embedded.get(id);
    };
    for (const o of state.objects) {
      const page = pages[o.page];
      const vp = state.pages[o.page].viewport;
      const rot = degrees(page.getRotation().angle);
      const P = (x, y) => vp.convertToPdfPoint(x, y);
      if (o.type === 'rect' || o.type === 'highlight') {
        const [x, y] = P(o.x, o.y + o.h);
        page.drawRectangle({
          x, y, width: o.w, height: o.h, rotate: rot,
          color: o.type === 'highlight' ? hexToRgb(o.color) : o.fill ? hexToRgb(o.fill) : undefined,
          opacity: o.type === 'highlight' ? 0.4 : 1,
          blendMode: o.type === 'highlight' ? BlendMode.Multiply : undefined,
          borderColor: o.stroke ? hexToRgb(o.color) : undefined,
          borderWidth: o.stroke ? o.strokeWidth : 0,
        });
      } else if (o.type === 'image') {
        const [x, y] = P(o.x, o.y + o.h);
        page.drawImage(await image(o.image), { x, y, width: o.w, height: o.h, rotate: rot });
      } else if (o.type === 'path' && o.pressure) {
        for (let i = 1; i < o.points.length; i++) {
          const [a, b] = [o.points[i - 1], o.points[i]];
          const [x1, y1] = P(a[0], a[1]), [x2, y2] = P(b[0], b[1]);
          page.drawLine({ start: { x: x1, y: y1 }, end: { x: x2, y: y2 }, thickness: o.strokeWidth * (a[2] + b[2]) / 2, color: hexToRgb(o.color), lineCap: LineCapStyle.Round });
        }
      } else if (o.type === 'path') {
        const d = o.points.map(([px, py], i) => { const [x, y] = P(px, py); return `${i ? 'L' : 'M'}${x.toFixed(2)} ${(-y).toFixed(2)}`; }).join(' ');
        page.drawSvgPath(d, { x: 0, y: 0, borderColor: hexToRgb(o.color), borderWidth: o.strokeWidth, borderLineCap: LineCapStyle.Round });
      } else if (o.type === 'text') {
        const f = await font(STANDARD[o.font][(o.bold ? 1 : 0) + (o.italic ? 2 : 0)]);
        const lines = o.text.split('\n');
        try {
          lines.forEach((line) => f.encodeText(line));
          lines.forEach((line, i) => {
            const [x, y] = P(o.x, o.y + o.size * BASELINE[o.font] + i * o.size * 1.2);
            page.drawText(line, { x, y, size: o.size, font: f, color: hexToRgb(o.color), rotate: rot });
          });
        } catch {
          const png = await out.embedPng(await textAsPng(o));
          const [x, y] = P(o.x, o.y + o.h);
          page.drawImage(png, { x, y, width: png.width / 4, height: png.height / 4, rotate: rot });
        }
      }
    }
    const bytes = await out.save();
    const name = `${state.file.name.replace(/\.pdf$/i, '')}_edited.pdf`;
    if (host) {
      host.postMessage({ action: 'save', name, data: await toBase64(bytes) });
    } else {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([bytes], { type: 'application/pdf' }));
      a.download = name;
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 30000);
    }
    state.savedAt = state.undo.length;
  } catch (err) {
    console.error(err);
    alert(`Saving failed: ${err.message || err}`);
  } finally {
    btn.disabled = false;
    btn.classList.remove('busy');
  }
}

syncProps();

// ---------- iOS app host ----------
// Inside the RBx9 PDF app the editor runs in a WKWebView: the app hands over
// the PDF, and Save/Done go back to the app instead of downloading.

function toBase64(bytes) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.slice(reader.result.indexOf(',') + 1));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(new Blob([bytes]));
  });
}

if (host) {
  document.body.classList.add('in-app');
  $('save').textContent = 'Save';
  const done = document.createElement('button');
  done.className = 'ghost done';
  done.textContent = 'Done';
  done.addEventListener('click', () => {
    if (state.editing) finishEditing();
    const unsaved = state.undo.length && state.undo.length !== state.savedAt;
    if (!unsaved || confirm('Close without saving your changes?')) host.postMessage({ action: 'close' });
  });
  document.querySelector('header.top .brand').replaceWith(done);
  window.RBx9Editor = {
    open(b64, name) {
      const bin = atob(b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      return openFile(new File([bytes], name, { type: 'application/pdf' }));
    },
  };
  host.postMessage({ action: 'ready' });
}
