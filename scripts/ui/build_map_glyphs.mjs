#!/usr/bin/env node
/**
 * Build the map's label glyphs from the bundled Inter (clients/web/src/assets/fonts, OFL-1.1),
 * so the bundled basemap draws its labels with no remote glyph server.
 *
 * MapLibre draws text from signed-distance-field glyphs in 256-character ranges
 * (`{fontstack}/{range}.pbf`). This script renders each character of the ranges below with the
 * bundled Inter in a headless Chromium canvas (the same rendering MapLibre's own local glyph path
 * uses: 24 px, a 3 px buffer, an 8 px radius and a 0.25 cutoff), computes the distance field and
 * writes the ranges as MapLibre glyph protobufs under clients/web/public/basemaps/glyphs/.
 * Chinese names are drawn by MapLibre from the device's own fonts (localIdeographFontFamily), so
 * no CJK range is built or fetched.
 *
 *     EUROGAS_UAT_PLAYWRIGHT_PATH=<playwright/index.js> node scripts/ui/build_map_glyphs.mjs
 *
 * The output is data: commit it with the font's licence (THIRD_PARTY_NOTICES.md covers Inter).
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const FONT_DIR = path.join(ROOT, "clients/web/src/assets/fonts/inter");
const OUT_DIR = path.join(ROOT, "clients/web/public/basemaps/glyphs");
export const FONTSTACK = "Inter Regular";
const RANGES = [0, 256, 8192];
// The code points the bundled Inter subsets (latin, latin-ext) cover.
const COVERED = [
  [0x0000, 0x02ff],
  [0x2000, 0x206f],
  [0x20a0, 0x20c0],
  [0x2113, 0x2113],
  [0x2122, 0x2122],
  [0x2191, 0x2191],
  [0x2193, 0x2193],
  [0x2212, 0x2212],
  [0x2215, 0x2215],
];
const SIZE = 24;
const BUFFER = 3;
const RADIUS = 8;
const CUTOFF = 0.25;

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.EUROGAS_UAT_PLAYWRIGHT_PATH || "playwright");

/** Runs in the page: render one character with Inter and return its distance field. */
function renderRange({ start, size, buffer, radius, cutoff, covered }) {
  const canvasSize = size + buffer * 4;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = canvasSize;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.font = `400 ${size}px InterBundled`;
  ctx.textBaseline = "alphabetic";
  ctx.textAlign = "left";
  ctx.fillStyle = "black";
  const INF = 1e20;

  function edt1d(grid, offset, stride, length, f, v, z) {
    v[0] = 0;
    z[0] = -INF;
    z[1] = INF;
    for (let q = 0; q < length; q++) f[q] = grid[offset + q * stride];
    for (let q = 1, k = 0, s = 0; q < length; q++) {
      do {
        const r = v[k];
        s = (f[q] - f[r] + q * q - r * r) / (q - r) / 2;
      } while (s <= z[k] && --k > -1);
      k++;
      v[k] = q;
      z[k] = s;
      z[k + 1] = INF;
    }
    for (let q = 0, k = 0; q < length; q++) {
      while (z[k + 1] < q) k++;
      const r = v[k];
      const qr = q - r;
      grid[offset + q * stride] = f[r] + qr * qr;
    }
  }

  function edt(data, width, height) {
    const f = new Float64Array(Math.max(width, height));
    const v = new Uint16Array(Math.max(width, height));
    const z = new Float64Array(Math.max(width, height) + 1);
    for (let x = 0; x < width; x++) edt1d(data, x, width, height, f, v, z);
    for (let y = 0; y < height; y++) edt1d(data, y * width, 1, width, f, v, z);
  }

  const glyphs = [];
  for (let id = start; id < start + 256; id++) {
    const char = String.fromCodePoint(id);
    if (id < 32 || (id >= 127 && id < 160)) continue;
    // Only what Inter draws: a character outside its ranges would come from a fallback font.
    if (!covered.some(([from, to]) => id >= from && id <= to)) continue;
    const metrics = ctx.measureText(char);
    const advance = Math.round(metrics.width);
    const glyphTop = Math.ceil(metrics.actualBoundingBoxAscent);
    const glyphWidth = Math.max(0, Math.min(size + buffer, Math.ceil(metrics.actualBoundingBoxRight - metrics.actualBoundingBoxLeft)));
    const glyphHeight = Math.max(0, Math.min(size + buffer, glyphTop + Math.ceil(metrics.actualBoundingBoxDescent)));
    const width = glyphWidth + 2 * buffer;
    const height = glyphHeight + 2 * buffer;
    if (glyphWidth === 0 || glyphHeight === 0) {
      // A space or a character Inter does not draw: an advance only.
      if (advance > 0) glyphs.push({ id, width: 0, height: 0, left: 0, top: -27, advance, bitmap: [] });
      continue;
    }
    ctx.clearRect(0, 0, canvasSize, canvasSize);
    // As MapLibre's own local glyphs (TinySDF): drawn at the buffer, left bearing 0.
    ctx.fillText(char, buffer, buffer + glyphTop);
    const image = ctx.getImageData(0, 0, width, height).data;
    const outer = new Float64Array(width * height);
    const inner = new Float64Array(width * height);
    for (let i = 0; i < width * height; i++) {
      const a = image[4 * i + 3] / 255;
      if (a === 1) {
        outer[i] = 0;
        inner[i] = INF;
      } else if (a === 0) {
        outer[i] = INF;
        inner[i] = 0;
      } else {
        const d = 0.5 - a;
        outer[i] = d > 0 ? d * d : 0;
        inner[i] = d < 0 ? d * d : 0;
      }
    }
    edt(outer, width, height);
    edt(inner, width, height);
    const bitmap = new Array(width * height);
    for (let i = 0; i < width * height; i++) {
      const d = Math.sqrt(outer[i]) - Math.sqrt(inner[i]);
      bitmap[i] = Math.max(0, Math.min(255, Math.round(255 - 255 * (d / radius + cutoff))));
    }
    glyphs.push({
      id,
      width: glyphWidth,
      height: glyphHeight,
      left: 0,
      top: glyphTop - 27,
      advance,
      bitmap,
    });
  }
  return glyphs;
}

/* ------------------------------------------------------------------ protobuf (glyphs.proto) */
function varint(value, out) {
  let v = value >>> 0;
  while (v > 127) {
    out.push((v & 127) | 128);
    v >>>= 7;
  }
  out.push(v);
}
const zigzag = (value) => ((value << 1) ^ (value >> 31)) >>> 0;
function field(number, wire, out) {
  varint((number << 3) | wire, out);
}
function bytes(number, payload, out) {
  field(number, 2, out);
  varint(payload.length, out);
  for (const b of payload) out.push(b);
}
function encodeGlyph(glyph) {
  const out = [];
  field(1, 0, out);
  varint(glyph.id, out);
  if (glyph.bitmap.length) bytes(2, glyph.bitmap, out);
  field(3, 0, out);
  varint(glyph.width, out);
  field(4, 0, out);
  varint(glyph.height, out);
  field(5, 0, out);
  varint(zigzag(glyph.left), out);
  field(6, 0, out);
  varint(zigzag(glyph.top), out);
  field(7, 0, out);
  varint(glyph.advance, out);
  return out;
}
function encodeRange(name, start, glyphs) {
  const stack = [];
  bytes(1, Buffer.from(name, "utf8"), stack);
  bytes(2, Buffer.from(`${start}-${start + 255}`, "utf8"), stack);
  for (const glyph of glyphs) bytes(3, encodeGlyph(glyph), stack);
  const out = [];
  bytes(1, stack, out);
  return Buffer.from(out);
}

async function main() {
  const fonts = ["inter-latin-wght-normal.woff2", "inter-latin-ext-wght-normal.woff2"].map((name) =>
    readFileSync(path.join(FONT_DIR, name)).toString("base64"),
  );
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setContent(`<!doctype html><style>
    @font-face { font-family: InterBundled; src: url(data:font/woff2;base64,${fonts[0]}) format("woff2"); font-weight: 100 900; unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD; }
    @font-face { font-family: InterBundled; src: url(data:font/woff2;base64,${fonts[1]}) format("woff2"); font-weight: 100 900; unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF; }
  </style><p style="font-family: InterBundled">Aa Łł</p>`);
  await page.evaluate(async () => {
    await document.fonts.load("400 24px InterBundled", "AaŁł–");
    await document.fonts.ready;
  });
  const dir = path.join(OUT_DIR, FONTSTACK);
  mkdirSync(dir, { recursive: true });
  for (const start of RANGES) {
    const glyphs = await page.evaluate(renderRange, { start, size: SIZE, buffer: BUFFER, radius: RADIUS, cutoff: CUTOFF, covered: COVERED });
    const file = path.join(dir, `${start}-${start + 255}.pbf`);
    writeFileSync(file, encodeRange(FONTSTACK, start, glyphs));
    console.log(`${path.relative(ROOT, file)}: ${glyphs.length} glyphs`);
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
