// Compress PDF engine, shared by the web app and the iOS app (which runs it in
// a hidden WKWebView). Large embedded images are downscaled and re-encoded as
// JPEG in place, leaving text and vector content untouched.
//
// Classic script so WKWebView can load it from file:// URLs; it exposes
// globalThis.RBx9Compress = { LEVELS, create(PDFLib) }.
(function (root) {
  'use strict';

  const LEVELS = {
    less: { maxSide: 2400, quality: 0.8 },
    recommended: { maxSide: 1600, quality: 0.65 },
    extreme: { maxSide: 1100, quality: 0.45, raster: { scale: 1, quality: 0.45 } },
  };

  function create({ PDFArray, PDFDict, PDFName, PDFNumber, PDFRawStream }) {
    const N = (name) => PDFName.of(name);

    const canvasToBlob = (canvas, type, q) => new Promise((resolve) => canvas.toBlob(resolve, type, q));

    async function inflate(bytes) {
      const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate'));
      return new Uint8Array(await new Response(stream).arrayBuffer());
    }

    // Reverses PNG row predictors (FlateDecode /Predictor >= 10) for 8-bit samples.
    function unpredictPng(data, columns, colors) {
      const rowLen = columns * colors;
      const rows = Math.floor(data.length / (rowLen + 1));
      const out = new Uint8Array(rows * rowLen);
      for (let r = 0; r < rows; r++) {
        const type = data[r * (rowLen + 1)];
        const inRow = r * (rowLen + 1) + 1;
        const o = r * rowLen;
        for (let i = 0; i < rowLen; i++) {
          const x = data[inRow + i];
          const a = i >= colors ? out[o + i - colors] : 0;
          const b = r > 0 ? out[o - rowLen + i] : 0;
          const c = r > 0 && i >= colors ? out[o - rowLen + i - colors] : 0;
          let v;
          if (type === 0) v = x;
          else if (type === 1) v = x + a;
          else if (type === 2) v = x + b;
          else if (type === 3) v = x + ((a + b) >> 1);
          else if (type === 4) {
            const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
            v = x + (pa <= pb && pa <= pc ? a : pb <= pc ? b : c);
          } else throw new Error('bad predictor');
          out[o + i] = v & 255;
        }
      }
      return out;
    }

    // Number of colour components for colour spaces we can safely re-encode as RGB JPEG.
    function componentCount(doc, cs) {
      if (cs === N('DeviceRGB')) return 3;
      if (cs === N('DeviceGray')) return 1;
      if (cs instanceof PDFArray && cs.lookup(0) === N('ICCBased')) {
        const n = cs.lookup(1, PDFRawStream).dict.lookup(N('N'));
        return n instanceof PDFNumber && (n.asNumber() === 3 || n.asNumber() === 1) ? n.asNumber() : 0;
      }
      return 0;
    }

    // Decodes one image XObject into something drawable, or null if unsupported.
    async function decodeImage(doc, stream) {
      const d = stream.dict;
      if (d.lookup(N('ImageMask')) || d.lookup(N('Decode')) || d.lookup(N('Mask')) instanceof PDFArray) return null;
      let filter = d.lookup(N('Filter'));
      if (filter instanceof PDFArray) filter = filter.size() === 1 ? filter.lookup(0) : null;
      const comps = componentCount(doc, d.lookup(N('ColorSpace')));
      if (!comps) return null;
      const bytes = stream.getContents();
      if (filter === N('DCTDecode')) return createImageBitmap(new Blob([bytes], { type: 'image/jpeg' }));
      if (filter !== N('FlateDecode')) return null;
      const w = d.lookup(N('Width')).asNumber(), h = d.lookup(N('Height')).asNumber();
      if (d.lookup(N('BitsPerComponent'))?.asNumber() !== 8) return null;
      let raw = await inflate(bytes);
      const parms = d.lookup(N('DecodeParms'));
      const predictor = parms instanceof PDFDict ? parms.lookup(N('Predictor'))?.asNumber() ?? 1 : 1;
      if (predictor >= 10) raw = unpredictPng(raw, w, comps);
      else if (predictor !== 1) return null;
      if (raw.length < w * h * comps) return null;
      const rgba = new Uint8ClampedArray(w * h * 4);
      for (let i = 0, j = 0; i < w * h; i++, j += comps) {
        rgba[i * 4] = raw[j];
        rgba[i * 4 + 1] = raw[j + (comps === 3 ? 1 : 0)];
        rgba[i * 4 + 2] = raw[j + (comps === 3 ? 2 : 0)];
        rgba[i * 4 + 3] = 255;
      }
      return createImageBitmap(new ImageData(rgba, w, h));
    }

    // Downscales and re-encodes every large image in place. Returns how many it found.
    async function shrinkImages(doc, { maxSide, quality }, progress = () => {}) {
      const masks = new Set();
      const images = [];
      for (const [ref, obj] of doc.context.enumerateIndirectObjects()) {
        if (!(obj instanceof PDFRawStream) || obj.dict.lookup(N('Subtype')) !== N('Image')) continue;
        const smask = obj.dict.get(N('SMask'));
        if (smask) masks.add(smask.toString());
        images.push([ref, obj]);
      }
      // Soft masks must stay greyscale and lossless.
      const targets = images.filter(([ref, obj]) => !masks.has(ref.toString())
        && obj.dict.lookup(N('Width')).asNumber() * obj.dict.lookup(N('Height')).asNumber() >= 40000);
      for (const [i, [ref, obj]] of targets.entries()) {
        progress(`Optimizing image ${i + 1} of ${targets.length}…`);
        let bitmap;
        try { bitmap = await decodeImage(doc, obj); } catch { bitmap = null; }
        if (!bitmap) continue;
        const s = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(bitmap.width * s));
        canvas.height = Math.max(1, Math.round(bitmap.height * s));
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#fff';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        bitmap.close();
        const jpg = new Uint8Array(await (await canvasToBlob(canvas, 'image/jpeg', quality)).arrayBuffer());
        if (jpg.length >= obj.getContentsSize()) continue;
        const dict = { Type: 'XObject', Subtype: 'Image', Width: canvas.width, Height: canvas.height, ColorSpace: 'DeviceRGB', BitsPerComponent: 8, Filter: 'DCTDecode' };
        const smask = obj.dict.get(N('SMask'));
        if (smask) dict.SMask = smask;
        doc.context.assign(ref, doc.context.stream(jpg, dict));
      }
      return targets.length;
    }

    return { shrinkImages };
  }

  root.RBx9Compress = { LEVELS, create };
})(globalThis);
