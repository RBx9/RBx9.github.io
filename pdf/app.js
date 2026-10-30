// RBx9 PDF: client-side PDF tools. Every operation runs in the browser;
// files are never uploaded anywhere.
import { PDFDocument, StandardFonts, degrees, rgb } from './vendor/pdf-lib.esm.min.js';
import * as pdfjsLib from './vendor/pdf.min.mjs';

pdfjsLib.GlobalWorkerOptions.workerSrc = './vendor/pdf.worker.min.mjs';

const $ = (id) => document.getElementById(id);

// ---------- helpers ----------

const fmtSize = (n) => n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(2)} MB`;
const baseName = (name) => name.replace(/\.[^.]+$/, '');
const pdfBlob = (bytes) => new Blob([bytes], { type: 'application/pdf' });

async function loadPdf(entry) {
  try {
    return await PDFDocument.load(entry.bytes);
  } catch (err) {
    if (/encrypt/i.test(err.message)) throw new Error(`${entry.file.name} is password-protected. Unlock it first.`);
    throw new Error(`${entry.file.name} could not be read as a PDF.`);
  }
}

// pdf.js takes ownership of the buffer it is given, so always hand it a copy.
const openPdfJs = (bytes) => pdfjsLib.getDocument({ data: bytes.slice() }).promise;

// "1-3, 5, 8-" -> [[0,1,2],[4],[7..count-1]] (zero-based, one array per range)
function parseRanges(text, count) {
  const groups = [];
  for (const part of text.split(',').map((s) => s.trim()).filter(Boolean)) {
    const m = part.match(/^(\d+)?\s*(-)?\s*(\d+)?$/);
    if (!m || (!m[1] && !m[3])) throw new Error(`“${part}” is not a valid page range.`);
    const start = m[1] ? +m[1] : 1;
    const end = m[2] ? (m[3] ? +m[3] : count) : start;
    if (start < 1 || end > count || start > end) throw new Error(`Range “${part}” is outside 1–${count}.`);
    groups.push(Array.from({ length: end - start + 1 }, (_, i) => start - 1 + i));
  }
  if (!groups.length) throw new Error('Enter at least one page or range.');
  return groups;
}

function canvasToBlob(canvas, type, quality) {
  return new Promise((resolve) => canvas.toBlob(resolve, type, quality));
}

async function renderPage(page, scale) {
  const viewport = page.getViewport({ scale });
  const canvas = document.createElement('canvas');
  canvas.width = Math.ceil(viewport.width);
  canvas.height = Math.ceil(viewport.height);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  await page.render({ canvasContext: ctx, viewport }).promise;
  return canvas;
}

// Draw any browser-decodable image to a JPEG so pdf-lib can embed it.
async function imageToJpeg(file) {
  const bitmap = await createImageBitmap(file);
  const canvas = document.createElement('canvas');
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(bitmap, 0, 0);
  return new Uint8Array(await (await canvasToBlob(canvas, 'image/jpeg', 0.92)).arrayBuffer());
}

function setStatus(text, isError = false) {
  const el = $('status');
  el.textContent = text;
  el.classList.toggle('error', isError);
}

// ---------- tools ----------

const PAGE_SIZES = { a4: [595.28, 841.89], letter: [612, 792] };

const TOOLS = [
  {
    id: 'merge', title: 'Merge PDF', icon: '⊕', color: '#e5484d', accept: 'pdf', multiple: true, minFiles: 2,
    desc: 'Combine several PDFs into one, in the order you choose.',
    async run({ files }) {
      const out = await PDFDocument.create();
      for (const entry of files) {
        const src = await loadPdf(entry);
        const pages = await out.copyPages(src, src.getPageIndices());
        pages.forEach((p) => out.addPage(p));
      }
      return [{ name: 'merged.pdf', blob: pdfBlob(await out.save()) }];
    },
  },
  {
    id: 'split', title: 'Split PDF', icon: '✂', color: '#f76b15', accept: 'pdf',
    desc: 'Turn page ranges, or every page, into separate PDFs.',
    options: [
      { id: 'mode', label: 'Split by', type: 'select', value: 'ranges', choices: [['ranges', 'Custom ranges'], ['every', 'Every page'], ['chunks', 'Fixed number of pages']] },
      { id: 'ranges', label: 'Ranges', type: 'text', value: '1-2, 3-', hint: 'Each range becomes its own file, e.g. 1-3, 4, 5-' },
      { id: 'chunk', label: 'Pages per file', type: 'number', value: 2, min: 1 },
    ],
    async run({ files, opts }) {
      const entry = files[0];
      const src = await loadPdf(entry);
      const count = src.getPageCount();
      let groups;
      if (opts.mode === 'every') groups = src.getPageIndices().map((i) => [i]);
      else if (opts.mode === 'chunks') {
        const n = Math.max(1, +opts.chunk || 1);
        groups = [];
        for (let i = 0; i < count; i += n) groups.push(src.getPageIndices().slice(i, i + n));
      } else groups = parseRanges(opts.ranges, count);
      const results = [];
      for (const g of groups) {
        const out = await PDFDocument.create();
        (await out.copyPages(src, g)).forEach((p) => out.addPage(p));
        const label = g.length === 1 ? `${g[0] + 1}` : `${g[0] + 1}-${g[g.length - 1] + 1}`;
        results.push({ name: `${baseName(entry.file.name)}_pages_${label}.pdf`, blob: pdfBlob(await out.save()) });
      }
      return results;
    },
  },
  {
    id: 'organize', title: 'Organize pages', icon: '▦', color: '#8e4ec6', accept: 'pdf', pageGrid: true,
    desc: 'Reorder, rotate and delete pages visually.',
    async run({ files, pageState }) {
      const src = await loadPdf(files[0]);
      const keep = pageState.filter((p) => !p.removed);
      if (!keep.length) throw new Error('Every page is marked for deletion.');
      const out = await PDFDocument.create();
      const copied = await out.copyPages(src, keep.map((p) => p.index));
      copied.forEach((page, i) => {
        page.setRotation(degrees((page.getRotation().angle + keep[i].rotation) % 360));
        out.addPage(page);
      });
      return [{ name: `${baseName(files[0].file.name)}_organized.pdf`, blob: pdfBlob(await out.save()) }];
    },
  },
  {
    id: 'remove', title: 'Remove pages', icon: '⌫', color: '#d6409f', accept: 'pdf',
    desc: 'Delete the pages you don’t need.',
    options: [{ id: 'ranges', label: 'Pages to remove', type: 'text', value: '1', hint: 'e.g. 2, 5-7' }],
    async run({ files, opts }) {
      const src = await loadPdf(files[0]);
      const drop = new Set(parseRanges(opts.ranges, src.getPageCount()).flat());
      [...drop].sort((a, b) => b - a).forEach((i) => src.removePage(i));
      if (!src.getPageCount()) throw new Error('That would remove every page.');
      return [{ name: `${baseName(files[0].file.name)}_edited.pdf`, blob: pdfBlob(await src.save()) }];
    },
  },
  {
    id: 'extract', title: 'Extract pages', icon: '⇱', color: '#0d74ce', accept: 'pdf',
    desc: 'Pull selected pages out into a new PDF.',
    options: [{ id: 'ranges', label: 'Pages to extract', type: 'text', value: '1-3', hint: 'e.g. 1, 4-6, 9-' }],
    async run({ files, opts }) {
      const src = await loadPdf(files[0]);
      const out = await PDFDocument.create();
      (await out.copyPages(src, parseRanges(opts.ranges, src.getPageCount()).flat())).forEach((p) => out.addPage(p));
      return [{ name: `${baseName(files[0].file.name)}_extracted.pdf`, blob: pdfBlob(await out.save()) }];
    },
  },
  {
    id: 'rotate', title: 'Rotate PDF', icon: '↻', color: '#12a594', accept: 'pdf',
    desc: 'Rotate all pages or just some of them.',
    options: [
      { id: 'angle', label: 'Rotation', type: 'select', value: '90', choices: [['90', '90° clockwise'], ['180', '180°'], ['270', '90° counter-clockwise']] },
      { id: 'ranges', label: 'Pages', type: 'text', value: '', hint: 'Leave empty for all pages' },
    ],
    async run({ files, opts }) {
      const src = await loadPdf(files[0]);
      const targets = opts.ranges.trim() ? new Set(parseRanges(opts.ranges, src.getPageCount()).flat()) : null;
      src.getPages().forEach((page, i) => {
        if (!targets || targets.has(i)) page.setRotation(degrees((page.getRotation().angle + +opts.angle) % 360));
      });
      return [{ name: `${baseName(files[0].file.name)}_rotated.pdf`, blob: pdfBlob(await src.save()) }];
    },
  },
  {
    id: 'compress', title: 'Compress PDF', icon: '⇲', color: '#30a46c', accept: 'pdf',
    desc: 'Shrink file size. Stronger levels turn pages into images.',
    options: [{
      id: 'level', label: 'Compression', type: 'select', value: 'recommended',
      choices: [['lossless', 'Lossless (keeps text selectable)'], ['less', 'Less (high quality)'], ['recommended', 'Recommended'], ['extreme', 'Extreme (smallest)']],
      hint: 'Less, Recommended and Extreme re-draw each page as an image.',
    }],
    async run({ files, opts, progress }) {
      const entry = files[0];
      const src = await loadPdf(entry);
      const lossless = await src.save({ useObjectStreams: true });
      let best = lossless;
      if (opts.level !== 'lossless') {
        const { scale, quality } = { less: { scale: 2, quality: 0.8 }, recommended: { scale: 1.5, quality: 0.65 }, extreme: { scale: 1, quality: 0.45 } }[opts.level];
        const doc = await openPdfJs(entry.bytes);
        const out = await PDFDocument.create();
        for (let n = 1; n <= doc.numPages; n++) {
          progress(`Compressing page ${n} of ${doc.numPages}…`);
          const page = await doc.getPage(n);
          const { width, height } = page.getViewport({ scale: 1 });
          const canvas = await renderPage(page, scale);
          const jpg = await out.embedJpg(await (await canvasToBlob(canvas, 'image/jpeg', quality)).arrayBuffer());
          out.addPage([width, height]).drawImage(jpg, { x: 0, y: 0, width, height });
          page.cleanup();
        }
        await doc.destroy();
        const raster = await out.save({ useObjectStreams: true });
        if (raster.length < best.length) best = raster;
      }
      const before = entry.bytes.length;
      const saved = before - best.length;
      const note = saved > 0 ? `${fmtSize(before)} → ${fmtSize(best.length)} (−${Math.round((saved / before) * 100)}%)` : 'This file is already well compressed.';
      return [{ name: `${baseName(entry.file.name)}_compressed.pdf`, blob: pdfBlob(saved > 0 ? best : entry.bytes), note }];
    },
  },
  {
    id: 'img2pdf', title: 'Images to PDF', icon: '🖼', color: '#ffb224', accept: 'image', multiple: true,
    desc: 'Convert JPG, PNG and other images into one PDF.',
    options: [
      { id: 'size', label: 'Page size', type: 'select', value: 'fit', choices: [['fit', 'Same as image'], ['a4', 'A4'], ['letter', 'US Letter']] },
      { id: 'margin', label: 'Margin', type: 'select', value: '0', choices: [['0', 'None'], ['18', 'Small'], ['36', 'Large']] },
    ],
    async run({ files, opts }) {
      const out = await PDFDocument.create();
      const margin = +opts.margin;
      for (const entry of files) {
        const type = entry.file.type;
        const img = type === 'image/png' ? await out.embedPng(entry.bytes)
          : type === 'image/jpeg' ? await out.embedJpg(entry.bytes)
          : await out.embedJpg(await imageToJpeg(entry.file));
        let pw, ph;
        if (opts.size === 'fit') { pw = img.width + margin * 2; ph = img.height + margin * 2; }
        else {
          [pw, ph] = PAGE_SIZES[opts.size];
          if (img.width > img.height) [pw, ph] = [ph, pw];
        }
        const s = Math.min((pw - margin * 2) / img.width, (ph - margin * 2) / img.height);
        const w = img.width * s, h = img.height * s;
        out.addPage([pw, ph]).drawImage(img, { x: (pw - w) / 2, y: (ph - h) / 2, width: w, height: h });
      }
      return [{ name: files.length === 1 ? `${baseName(files[0].file.name)}.pdf` : 'images.pdf', blob: pdfBlob(await out.save()) }];
    },
  },
  {
    id: 'pdf2img', title: 'PDF to images', icon: '⇄', color: '#00a2c7', accept: 'pdf',
    desc: 'Save every page as a JPG or PNG image.',
    options: [
      { id: 'format', label: 'Format', type: 'select', value: 'jpeg', choices: [['jpeg', 'JPG'], ['png', 'PNG']] },
      { id: 'dpi', label: 'Resolution', type: 'select', value: '150', choices: [['72', 'Screen (72 dpi)'], ['150', 'Standard (150 dpi)'], ['300', 'Print (300 dpi)']] },
    ],
    async run({ files, opts, progress }) {
      const doc = await openPdfJs(files[0].bytes);
      const ext = opts.format === 'png' ? 'png' : 'jpg';
      const results = [];
      for (let n = 1; n <= doc.numPages; n++) {
        progress(`Rendering page ${n} of ${doc.numPages}…`);
        const page = await doc.getPage(n);
        const canvas = await renderPage(page, +opts.dpi / 72);
        results.push({ name: `${baseName(files[0].file.name)}_page_${n}.${ext}`, blob: await canvasToBlob(canvas, `image/${opts.format}`, 0.9) });
        page.cleanup();
      }
      await doc.destroy();
      return results;
    },
  },
  {
    id: 'numbers', title: 'Add page numbers', icon: '#', color: '#5b5bd6', accept: 'pdf',
    desc: 'Stamp page numbers in the position and style you want.',
    options: [
      { id: 'position', label: 'Position', type: 'select', value: 'bc', choices: [['bc', 'Bottom center'], ['br', 'Bottom right'], ['bl', 'Bottom left'], ['tc', 'Top center'], ['tr', 'Top right'], ['tl', 'Top left']] },
      { id: 'format', label: 'Format', type: 'select', value: '{n}', choices: [['{n}', '1'], ['Page {n}', 'Page 1'], ['{n} / {total}', '1 / 10'], ['Page {n} of {total}', 'Page 1 of 10']] },
      { id: 'start', label: 'First number', type: 'number', value: 1, min: 0 },
      { id: 'fontSize', label: 'Font size', type: 'number', value: 11, min: 6, max: 48 },
    ],
    async run({ files, opts }) {
      const src = await loadPdf(files[0]);
      const font = await src.embedFont(StandardFonts.Helvetica);
      const size = +opts.fontSize || 11;
      const pages = src.getPages();
      const total = pages.length + (+opts.start || 1) - 1;
      pages.forEach((page, i) => {
        const text = opts.format.replace('{n}', i + (+opts.start || 1)).replace('{total}', total);
        const { width, height } = page.getSize();
        const w = font.widthOfTextAtSize(text, size);
        const pad = 28;
        const x = opts.position[1] === 'l' ? pad : opts.position[1] === 'r' ? width - pad - w : (width - w) / 2;
        const y = opts.position[0] === 'b' ? pad - size / 2 : height - pad - size / 2;
        page.drawText(text, { x, y, size, font, color: rgb(0.2, 0.2, 0.2) });
      });
      return [{ name: `${baseName(files[0].file.name)}_numbered.pdf`, blob: pdfBlob(await src.save()) }];
    },
  },
  {
    id: 'watermark', title: 'Watermark', icon: '💧', color: '#3e63dd', accept: 'pdf',
    desc: 'Stamp text diagonally across every page.',
    options: [
      { id: 'text', label: 'Text', type: 'text', value: 'CONFIDENTIAL' },
      { id: 'fontSize', label: 'Font size', type: 'number', value: 60, min: 8, max: 200 },
      { id: 'opacity', label: 'Opacity', type: 'range', value: 0.2, min: 0.05, max: 1, step: 0.05 },
      { id: 'angle', label: 'Angle', type: 'select', value: '45', choices: [['45', 'Diagonal'], ['0', 'Horizontal']] },
    ],
    async run({ files, opts }) {
      if (!opts.text.trim()) throw new Error('Enter watermark text.');
      const src = await loadPdf(files[0]);
      const font = await src.embedFont(StandardFonts.HelveticaBold);
      const size = +opts.fontSize || 60;
      let w;
      try { w = font.widthOfTextAtSize(opts.text, size); } catch {
        throw new Error('The web version only supports Latin characters in watermarks.');
      }
      const h = font.heightAtSize(size);
      const theta = (+opts.angle * Math.PI) / 180;
      for (const page of src.getPages()) {
        const { width, height } = page.getSize();
        // Offset the anchor so the rotated text is centred on the page.
        const x = width / 2 - (w / 2) * Math.cos(theta) + (h / 2) * Math.sin(theta);
        const y = height / 2 - (w / 2) * Math.sin(theta) - (h / 2) * Math.cos(theta);
        page.drawText(opts.text, { x, y, size, font, color: rgb(0.85, 0.1, 0.1), opacity: +opts.opacity, rotate: degrees(+opts.angle) });
      }
      return [{ name: `${baseName(files[0].file.name)}_watermarked.pdf`, blob: pdfBlob(await src.save()) }];
    },
  },
];

// ---------- UI ----------

let tool = null;
let files = [];
let pageState = [];
let resultUrls = [];

function buildGrid() {
  const grid = $('tool-grid');
  for (const t of TOOLS) {
    const btn = document.createElement('button');
    btn.className = 'tile';
    btn.innerHTML = `<div class="ic" style="background:${t.color}">${t.icon}</div><strong>${t.title}</strong><span>${t.desc}</span>`;
    btn.addEventListener('click', () => { location.hash = t.id; });
    grid.append(btn);
  }
}

function clearResults() {
  resultUrls.forEach(URL.revokeObjectURL);
  resultUrls = [];
  $('results').hidden = true;
  $('result-list').replaceChildren();
}

function openTool(t) {
  tool = t;
  files = [];
  pageState = [];
  clearResults();
  setStatus('');
  $('home').hidden = true;
  $('tool').hidden = false;
  $('tool-icon').textContent = t.icon;
  $('tool-icon').style.background = t.color;
  $('tool-title').textContent = t.title;
  $('tool-desc').textContent = t.desc;
  document.title = `${t.title} · RBx9 PDF`;
  const input = $('file-input');
  input.accept = t.accept === 'pdf' ? 'application/pdf,.pdf' : 'image/*';
  input.multiple = !!t.multiple;
  $('drop-label').textContent = t.multiple ? `Choose ${t.accept === 'pdf' ? 'PDFs' : 'images'}` : 'Choose a PDF';
  buildOptions(t);
  renderFiles();
  window.scrollTo(0, 0);
}

function goHome() {
  tool = null;
  clearResults();
  $('tool').hidden = true;
  $('home').hidden = false;
  document.title = 'RBx9 PDF';
}

function buildOptions(t) {
  const form = $('options');
  form.replaceChildren();
  for (const o of t.options || []) {
    const field = document.createElement('div');
    field.className = 'field';
    field.dataset.id = o.id;
    const label = document.createElement('label');
    label.textContent = o.label;
    label.htmlFor = `opt-${o.id}`;
    let input;
    if (o.type === 'select') {
      input = document.createElement('select');
      for (const [value, text] of o.choices) input.append(new Option(text, value, false, value === o.value));
    } else {
      input = document.createElement('input');
      input.type = o.type;
      input.value = o.value;
      for (const k of ['min', 'max', 'step']) if (o[k] !== undefined) input[k] = o[k];
    }
    input.id = `opt-${o.id}`;
    input.name = o.id;
    field.append(label, input);
    if (o.hint) {
      const hint = document.createElement('small');
      hint.textContent = o.hint;
      field.append(hint);
    }
    form.append(field);
  }
  form.onchange = form.oninput = syncOptionVisibility;
  syncOptionVisibility();
}

// Split shows the field that matches the chosen mode only.
function syncOptionVisibility() {
  if (tool?.id !== 'split') return;
  const mode = $('opt-mode').value;
  document.querySelector('[data-id=ranges]').hidden = mode !== 'ranges';
  document.querySelector('[data-id=chunk]').hidden = mode !== 'chunks';
}

function readOptions() {
  return Object.fromEntries(new FormData($('options')).entries());
}

async function addFiles(list) {
  const wanted = [...list].filter((f) => tool.accept === 'pdf' ? (f.type === 'application/pdf' || /\.pdf$/i.test(f.name)) : f.type.startsWith('image/'));
  if (!wanted.length) { setStatus(`Please choose ${tool.accept === 'pdf' ? 'PDF files' : 'image files'}.`, true); return; }
  const entries = await Promise.all(wanted.map(async (file) => ({ file, bytes: new Uint8Array(await file.arrayBuffer()) })));
  files = tool.multiple ? files.concat(entries) : entries.slice(0, 1);
  clearResults();
  setStatus('');
  renderFiles();
  if (tool.pageGrid) await buildPageGrid();
}

function renderFiles() {
  const list = $('file-list');
  list.replaceChildren();
  files.forEach((entry, i) => {
    const li = document.createElement('li');
    const name = document.createElement('span');
    name.className = 'name';
    name.textContent = entry.file.name;
    const meta = document.createElement('span');
    meta.className = 'meta';
    meta.textContent = fmtSize(entry.file.size);
    li.append(name, meta);
    const mk = (label, title, fn, disabled) => {
      const b = document.createElement('button');
      b.className = 'icon-btn';
      b.textContent = label;
      b.title = title;
      b.disabled = disabled;
      b.onclick = fn;
      li.append(b);
    };
    if (tool.multiple) {
      mk('↑', 'Move up', () => { [files[i - 1], files[i]] = [files[i], files[i - 1]]; renderFiles(); }, i === 0);
      mk('↓', 'Move down', () => { [files[i + 1], files[i]] = [files[i], files[i + 1]]; renderFiles(); }, i === files.length - 1);
    }
    mk('✕', 'Remove', () => { files.splice(i, 1); pageState = []; $('page-grid').hidden = true; renderFiles(); }, false);
    list.append(li);
  });
  $('run').disabled = files.length < (tool.minFiles || 1);
  $('run').textContent = tool.title;
}

async function buildPageGrid() {
  const grid = $('page-grid');
  grid.replaceChildren();
  grid.hidden = false;
  setStatus('Loading pages…');
  const doc = await openPdfJs(files[0].bytes);
  pageState = [];
  for (let n = 1; n <= doc.numPages; n++) {
    const page = await doc.getPage(n);
    const scale = 160 / page.getViewport({ scale: 1 }).width;
    pageState.push({ index: n - 1, rotation: 0, removed: false, canvas: await renderPage(page, scale) });
    page.cleanup();
  }
  await doc.destroy();
  setStatus('');
  drawPageGrid();
}

function drawPageGrid() {
  const grid = $('page-grid');
  grid.replaceChildren();
  pageState.forEach((p, i) => {
    const card = document.createElement('div');
    card.className = 'page' + (p.removed ? ' removed' : '');
    const thumb = document.createElement('div');
    thumb.className = 'thumb';
    // Sideways pages are shrunk so they still fit the portrait thumbnail box.
    p.canvas.style.transform = `rotate(${p.rotation}deg)` + (p.rotation % 180 ? ' scale(.75)' : '');
    thumb.append(p.canvas);
    const ctrl = document.createElement('div');
    ctrl.className = 'ctrl';
    const mk = (label, title, fn, disabled = false) => {
      const b = document.createElement('button');
      b.className = 'icon-btn';
      b.textContent = label;
      b.title = title;
      b.disabled = disabled;
      b.onclick = () => { fn(); drawPageGrid(); };
      ctrl.append(b);
    };
    mk('←', 'Move left', () => { [pageState[i - 1], pageState[i]] = [p, pageState[i - 1]]; }, i === 0);
    mk('↻', 'Rotate', () => { p.rotation = (p.rotation + 90) % 360; });
    mk(p.removed ? '↺' : '🗑', p.removed ? 'Restore' : 'Delete', () => { p.removed = !p.removed; });
    mk('→', 'Move right', () => { [pageState[i + 1], pageState[i]] = [p, pageState[i + 1]]; }, i === pageState.length - 1);
    const label = document.createElement('small');
    label.textContent = `Page ${p.index + 1}`;
    card.append(thumb, label, ctrl);
    grid.append(card);
  });
}

async function run() {
  const btn = $('run');
  btn.disabled = true;
  clearResults();
  setStatus('Working…');
  try {
    const results = await tool.run({ files, opts: readOptions(), pageState, progress: (m) => setStatus(m) });
    const list = $('result-list');
    for (const r of results) {
      const url = URL.createObjectURL(r.blob);
      resultUrls.push(url);
      const a = document.createElement('a');
      a.href = url;
      a.download = r.name;
      a.innerHTML = '<span></span><span></span>';
      a.firstChild.textContent = `⬇ ${r.name}`;
      a.lastChild.textContent = r.note || fmtSize(r.blob.size);
      list.append(a);
    }
    $('results').hidden = false;
    setStatus(results.length > 1 ? `${results.length} files ready.` : '');
    if (results.length === 1) list.firstChild.click();
  } catch (err) {
    console.error(err);
    setStatus(err.message || String(err), true);
  } finally {
    btn.disabled = files.length < (tool.minFiles || 1);
  }
}

function route() {
  const t = TOOLS.find((x) => x.id === location.hash.slice(1));
  t ? openTool(t) : goHome();
}

buildGrid();
$('file-input').addEventListener('change', (e) => { addFiles(e.target.files); e.target.value = ''; });
$('run').addEventListener('click', run);
document.querySelectorAll('[data-home]').forEach((el) => el.addEventListener('click', (e) => { e.preventDefault(); history.pushState(null, '', './'); goHome(); }));
const drop = $('drop');
drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
drop.addEventListener('dragleave', () => drop.classList.remove('over'));
drop.addEventListener('drop', (e) => { e.preventDefault(); drop.classList.remove('over'); addFiles(e.dataTransfer.files); });
window.addEventListener('hashchange', route);
route();

if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
