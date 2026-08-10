import fs from 'node:fs';

const src = fs.readFileSync(process.env.LEGACY_HTML, 'utf8');
const start = src.indexOf('const PRODUCTS = [');
const end = src.indexOf('];', start);
const arr = new Function('return ' + src.slice(start + 'const PRODUCTS = '.length, end + 1))();

console.log('count:', arr.length);

const keys = [...new Set(arr.flatMap(Object.keys))];
console.log('unionKeys:', keys.length, keys.join(','));
console.log('inconsistentObjs:', JSON.stringify(arr.filter(p => Object.keys(p).length !== keys.length).map(p => p.id)));

const ids = arr.map(p => p.id);
console.log('idsUnique:', new Set(ids).size === ids.length);
console.log('idsUniqueLower:', new Set(ids.map(s => s.toLowerCase())).size === ids.length);
console.log('idsUnsafe:', JSON.stringify(ids.filter(s => !/^[a-zA-Z0-9._-]+$/.test(s))));

const mimes = {};
let withImg = 0, maxBytes = 0, totalBytes = 0;
for (const p of arr) {
  const m = /^data:image\/([a-z]+);base64,/.exec(p.img || '');
  if (!m) continue;
  withImg++;
  mimes[m[1]] = (mimes[m[1]] || 0) + 1;
  const bytes = Buffer.from(p.img.slice(m[0].length), 'base64').length;
  totalBytes += bytes;
  maxBytes = Math.max(maxBytes, bytes);
}
console.log('withImg:', withImg, 'mimes:', JSON.stringify(mimes));
console.log('totalKB:', Math.round(totalBytes / 1024), 'maxKB:', Math.round(maxBytes / 1024));
console.log('noImgIds:', JSON.stringify(arr.filter(p => !p.img).map(p => p.id)));

const types = {};
for (const k of keys) types[k] = [...new Set(arr.map(p => Array.isArray(p[k]) ? 'array' : typeof p[k]))].join('|');
console.log('fieldTypes:', JSON.stringify(types));
console.log('tiers:', JSON.stringify([...new Set(arr.map(p => p.tier))]));
