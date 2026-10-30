// PDF to Word engine, shared by the web app and the iOS app (which runs it in a
// hidden WKWebView). It takes positioned text and images extracted from each
// page, rebuilds lines, paragraphs, headings and columns, and writes a .docx.
//
// Input: pages = [{ width, height, items: [{ t, x, y, w, s, b, i, f }], images: [{ x, y, w, h, data, mime }] }]
//   t text, x/y top-left-origin position of the baseline start (points), w width,
//   s font size, b bold, i italic, f font name; image data is a Uint8Array or base64.
//
// Classic script so WKWebView can load it from file:// URLs; it exposes
// globalThis.RBx9Docx = { build(pages) -> Promise<Uint8Array> }.
(function (root) {
  'use strict';

  // ---------- zip (stored, no compression; Word accepts it) ----------

  const CRC = new Uint32Array(256).map((_, n) => {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
  });

  function crc32(bytes) {
    let c = 0xffffffff;
    for (let i = 0; i < bytes.length; i++) c = CRC[(c ^ bytes[i]) & 255] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  }

  function zip(files) {
    const enc = new TextEncoder();
    const parts = [];
    const central = [];
    let offset = 0;
    for (const { name, data } of files) {
      const nameBytes = enc.encode(name);
      const crc = crc32(data);
      const local = new DataView(new ArrayBuffer(30));
      local.setUint32(0, 0x04034b50, true);
      local.setUint16(4, 20, true);
      local.setUint32(14, crc, true);
      local.setUint32(18, data.length, true);
      local.setUint32(22, data.length, true);
      local.setUint16(26, nameBytes.length, true);
      parts.push(new Uint8Array(local.buffer), nameBytes, data);
      const dir = new DataView(new ArrayBuffer(46));
      dir.setUint32(0, 0x02014b50, true);
      dir.setUint16(4, 20, true);
      dir.setUint16(6, 20, true);
      dir.setUint32(16, crc, true);
      dir.setUint32(20, data.length, true);
      dir.setUint32(24, data.length, true);
      dir.setUint16(28, nameBytes.length, true);
      dir.setUint32(42, offset, true);
      central.push(new Uint8Array(dir.buffer), nameBytes);
      offset += 30 + nameBytes.length + data.length;
    }
    const dirSize = central.reduce((n, p) => n + p.length, 0);
    const end = new DataView(new ArrayBuffer(22));
    end.setUint32(0, 0x06054b50, true);
    end.setUint16(8, files.length, true);
    end.setUint16(10, files.length, true);
    end.setUint32(12, dirSize, true);
    end.setUint32(16, offset, true);
    const all = parts.concat(central, [new Uint8Array(end.buffer)]);
    const out = new Uint8Array(all.reduce((n, p) => n + p.length, 0));
    let at = 0;
    for (const p of all) { out.set(p, at); at += p.length; }
    return out;
  }

  // ---------- layout analysis ----------

  const BULLET = /^\s*([•◦▪●○■□►▸‣⁃–—*-]|\(?\d{1,3}[.)]|\(?[a-zA-Z][.)])\s+/;

  /** Two-column pages: find an empty vertical gutter and read each column in turn. */
  function splitColumns(items, width) {
    if (items.length < 12) return [items];
    let best = null;
    for (let gx = width * 0.3; gx <= width * 0.7; gx += 2) {
      let cross = 0;
      for (const it of items) if (it.x < gx - 1 && it.x + it.w > gx + 1) cross++;
      if (!best || cross < best.cross) best = { gx, cross };
    }
    const left = items.filter((it) => it.x + it.w <= best.gx + 1);
    const right = items.filter((it) => it.x >= best.gx - 1);
    if (best.cross > items.length * 0.04 || left.length < items.length * 0.2 || right.length < items.length * 0.2) return [items];
    const span = items.filter((it) => it.x < best.gx - 1 && it.x + it.w > best.gx + 1);
    const top = Math.min(...left.concat(right).map((it) => it.y));
    return [span.filter((it) => it.y <= top), left, right, span.filter((it) => it.y > top)].filter((g) => g.length);
  }

  function toLines(items) {
    const sorted = items.slice().sort((a, b) => a.y - b.y || a.x - b.x);
    const lines = [];
    for (const it of sorted) {
      const line = lines[lines.length - 1];
      if (line && Math.abs(it.y - line.y) < Math.max(it.s, line.s) * 0.45) {
        line.items.push(it);
        line.s = Math.max(line.s, it.s);
      } else {
        lines.push({ y: it.y, s: it.s, items: [it] });
      }
    }
    for (const line of lines) {
      line.items.sort((a, b) => a.x - b.x);
      const runs = [];
      let end = null;
      for (const it of line.items) {
        let text = it.t;
        const last = runs[runs.length - 1];
        if (end !== null && last && it.x - end > it.s * 0.18 && !/\s$/.test(last.t) && !/^\s/.test(text)) text = ' ' + text;
        const style = { b: !!it.b, i: !!it.i, s: Math.round(it.s * 2) / 2, f: it.f || '' };
        if (last && last.b === style.b && last.i === style.i && last.s === style.s && last.f === style.f) last.t += text;
        else runs.push({ t: text, ...style });
        end = Math.max(end ?? -Infinity, it.x + it.w);
      }
      line.runs = runs;
      line.x = line.items[0].x;
      line.right = end;
      line.text = runs.map((r) => r.t).join('');
    }
    return lines.filter((l) => l.text.trim());
  }

  function bodySize(lines) {
    const weight = new Map();
    for (const l of lines) for (const r of l.runs) weight.set(r.s, (weight.get(r.s) || 0) + r.t.length);
    let best = 11, max = 0;
    for (const [s, w] of weight) if (w > max) { max = w; best = s; }
    return best;
  }

  function toParagraphs(lines, body) {
    if (!lines.length) return [];
    const left = Math.min(...lines.map((l) => l.x));
    const right = Math.max(...lines.map((l) => l.right));
    const width = right - left;
    const paras = [];
    let prev = null;
    for (const line of lines) {
      const p = paras[paras.length - 1];
      const gap = prev ? line.y - prev.y : Infinity;
      const endsShort = prev && prev.right < right - prev.s * 5 && /[.:!?;]["')\]]?$/.test(prev.text.trim());
      const indented = line.x > left + line.s * 1.5 && p && line.x > p.x + line.s;
      const join = p && prev && Math.abs(line.s - prev.s) < 1 && gap > 0 && gap < prev.s * 1.75
        && !BULLET.test(line.text) && !endsShort && !indented;
      if (join) {
        const last = p.runs[p.runs.length - 1];
        const first = { ...line.runs[0] };
        // Re-join words hyphenated across lines; otherwise lines meet with a space.
        if (/\p{L}-$/u.test(last.t) && /^\p{Ll}/u.test(first.t)) last.t = last.t.slice(0, -1);
        else if (!/\s$/.test(last.t)) first.t = ' ' + first.t.replace(/^\s+/, '');
        const runs = [first, ...line.runs.slice(1)];
        for (const r of runs) {
          const tail = p.runs[p.runs.length - 1];
          if (tail.b === r.b && tail.i === r.i && tail.s === r.s && tail.f === r.f) tail.t += r.t;
          else p.runs.push(r);
        }
        p.lines.push(line);
      } else {
        paras.push({ type: 'p', y: line.y - line.s, x: line.x, runs: line.runs.map((r) => ({ ...r })), lines: [line], bullet: BULLET.test(line.text) });
      }
      prev = line;
    }
    for (const p of paras) {
      const chars = p.runs.reduce((n, r) => n + r.t.length, 0);
      const size = p.runs.reduce((n, r) => n + r.s * r.t.length, 0) / Math.max(chars, 1);
      const ratio = size / body;
      // Bigger-than-body text is a heading, even when numbered ("1. Introduction").
      if (chars < 160) p.heading = ratio >= 1.6 ? 1 : ratio >= 1.3 ? 2 : ratio >= 1.12 ? 3 : 0;
      if (p.heading) p.bullet = false;
      const centered = p.lines.every((l) => Math.abs((l.x + l.right) / 2 - (left + right) / 2) < l.s * 0.8 && l.right - l.x < width * 0.85);
      p.align = centered && width > 0 ? 'center' : null;
      p.runs[0].t = p.runs[0].t.replace(/^\s+/, '');
    }
    return paras;
  }

  function analyzePage(page) {
    const items = (page.items || []).filter((it) => it.t && it.t.trim() && it.s > 0);
    const groups = splitColumns(items, page.width);
    const body = bodySize(toLines(items));
    let blocks = [];
    const ranges = [];
    for (const g of groups) {
      const paras = toParagraphs(toLines(g), body);
      ranges.push({ left: Math.min(...g.map((i) => i.x)), right: Math.max(...g.map((i) => i.x + i.w)), blocks: paras });
    }
    // Place each image in the column it sits in, ordered by height on the page.
    for (const img of page.images || []) {
      const cx = img.x + img.w / 2;
      const target = ranges.length > 1 ? (ranges.find((r) => cx >= r.left && cx <= r.right) || ranges[0]) : ranges[0];
      const block = { type: 'img', y: img.y, img, align: Math.abs(cx - page.width / 2) < page.width * 0.08 ? 'center' : null };
      if (target) target.blocks.push(block);
      else ranges.push({ blocks: [block] });
    }
    for (const r of ranges) blocks = blocks.concat(r.blocks.sort((a, b) => a.y - b.y));
    return { blocks, body, left: Math.min(...items.map((i) => i.x), Infinity), right: Math.max(...items.map((i) => i.x + i.w), -Infinity) };
  }

  // ---------- docx writing ----------

  const esc = (s) => s.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F￾￿]/g, '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  function fontFamily(name) {
    const n = (name || '').replace(/^[A-Z]{6}\+/, '');
    if (/times|serif(?!.*sans)|georgia|garamond|cambria|minion/i.test(n)) return /georgia/i.test(n) ? 'Georgia' : /cambria/i.test(n) ? 'Cambria' : 'Times New Roman';
    if (/courier|mono|consol/i.test(n)) return 'Courier New';
    if (/arial|helvetica/i.test(n)) return 'Arial';
    if (/verdana/i.test(n)) return 'Verdana';
    if (/calibri/i.test(n)) return 'Calibri';
    return null;
  }

  function runXml(r) {
    const family = fontFamily(r.f);
    const props = (family ? `<w:rFonts w:ascii="${family}" w:hAnsi="${family}" w:cs="${family}"/>` : '')
      + (r.b ? '<w:b/><w:bCs/>' : '') + (r.i ? '<w:i/><w:iCs/>' : '')
      + `<w:sz w:val="${Math.round(r.s * 2)}"/><w:szCs w:val="${Math.round(r.s * 2)}"/>`;
    return `<w:r><w:rPr>${props}</w:rPr><w:t xml:space="preserve">${esc(r.t)}</w:t></w:r>`;
  }

  function base64ToBytes(b64) {
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  async function build(pages) {
    const enc = new TextEncoder();
    const media = [];
    let body = '';
    let docPr = 1;
    const first = pages[0] || { width: 612, height: 792 };
    const analyzed = pages.map(analyzePage);
    const lefts = analyzed.map((a) => a.left).filter(Number.isFinite);
    const rights = analyzed.map((a, i) => pages[i].width - a.right).filter(Number.isFinite);
    const clampMargin = (v) => Math.round(Math.min(Math.max(v, 36), 90) * 20);
    const marginL = clampMargin(lefts.length ? Math.min(...lefts) : 72);
    const marginR = clampMargin(rights.length ? Math.min(...rights) : 72);
    const contentWidth = first.width - (marginL + marginR) / 20;

    analyzed.forEach((page, index) => {
      if (index > 0) body += '<w:p><w:r><w:br w:type="page"/></w:r></w:p>';
      if (!page.blocks.length) body += '<w:p/>';
      for (const block of page.blocks) {
        const jc = block.align ? `<w:jc w:val="${block.align}"/>` : '';
        if (block.type === 'img') {
          const { img } = block;
          const data = typeof img.data === 'string' ? base64ToBytes(img.data) : img.data;
          const ext = /png/.test(img.mime) ? 'png' : 'jpeg';
          const id = `rIdImg${media.length + 1}`;
          media.push({ name: `word/media/image${media.length + 1}.${ext}`, data, id });
          const scale = Math.min(1, contentWidth / img.w);
          const cx = Math.round(img.w * scale * 12700), cy = Math.round(img.h * scale * 12700);
          const n = docPr++;
          body += `<w:p><w:pPr>${jc}</w:pPr><w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="${cx}" cy="${cy}"/><wp:docPr id="${n}" name="Picture ${n}"/>`
            + '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            + `<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="${n}" name="Picture ${n}"/><pic:cNvPicPr/></pic:nvPicPr>`
            + `<pic:blipFill><a:blip r:embed="${id}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>`
            + `<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="${cx}" cy="${cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>`
            + '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>';
          continue;
        }
        const style = block.heading ? `<w:pStyle w:val="Heading${block.heading}"/>` : '';
        const ind = block.bullet ? '<w:ind w:left="360" w:hanging="360"/>' : '';
        body += `<w:p><w:pPr>${style}${ind}${jc}</w:pPr>${block.runs.map(runXml).join('')}</w:p>`;
      }
    });

    const sect = `<w:sectPr><w:pgSz w:w="${Math.round(first.width * 20)}" w:h="${Math.round(first.height * 20)}"/>`
      + `<w:pgMar w:top="1080" w:right="${marginR}" w:bottom="1080" w:left="${marginL}" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>`;
    const documentXml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
      + '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      + 'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      + `xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><w:body>${body}${sect}</w:body></w:document>`;

    const heading = (n, size) => `<w:style w:type="paragraph" w:styleId="Heading${n}"><w:name w:val="heading ${n}"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:uiPriority w:val="9"/><w:qFormat/>`
      + `<w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/><w:outlineLvl w:val="${n - 1}"/></w:pPr><w:rPr><w:b/><w:sz w:val="${size}"/></w:rPr></w:style>`;
    const stylesXml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
      + '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
      + '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Calibri" w:cs="Calibri"/><w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="en-US"/></w:rPr></w:rPrDefault>'
      + '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
      + '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
      + heading(1, 36) + heading(2, 28) + heading(3, 24) + '</w:styles>';

    const rels = media.map((m) => `<Relationship Id="${m.id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="${m.name.slice(5)}"/>`).join('');
    const files = [
      { name: '[Content_Types].xml', data: enc.encode('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        + '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
        + '<Default Extension="png" ContentType="image/png"/><Default Extension="jpeg" ContentType="image/jpeg"/>'
        + '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        + '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        + '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>') },
      { name: '_rels/.rels', data: enc.encode('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        + '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>') },
      { name: 'docProps/core.xml', data: enc.encode('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        + 'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        + `<dc:creator>RBx9 PDF</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">${new Date().toISOString().replace(/\.\d+Z$/, 'Z')}</dcterms:created></cp:coreProperties>`) },
      { name: 'word/document.xml', data: enc.encode(documentXml) },
      { name: 'word/styles.xml', data: enc.encode(stylesXml) },
      { name: 'word/_rels/document.xml.rels', data: enc.encode('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + `<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>${rels}</Relationships>`) },
      ...media.map((m) => ({ name: m.name, data: m.data })),
    ];
    return zip(files);
  }

  root.RBx9Docx = { build, analyzePage };
})(globalThis);
