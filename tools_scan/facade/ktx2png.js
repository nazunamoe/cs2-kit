// GLB with KHR_texture_basisu -> .gltf + .bin + PNG textures (reference rendering only)
// usage: node ktx2png.js <in.glb> <out_dir>
const fs = require("fs"), path = require("path");
const base = path.join(__dirname, "gt", "node_modules");
const { PNG } = require(path.join(base, "pngjs"));
const src = fs.readFileSync(path.join(base, "three/examples/jsm/libs/basis/basis_transcoder.js"), "utf8");
const BASIS = new Function("module", "exports", "require", "__dirname", src + "\nreturn BASIS;")(
  { exports: {} }, {}, require, path.join(base, "three/examples/jsm/libs/basis"));
const [inp, out] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const b = fs.readFileSync(inp);
const jlen = b.readUInt32LE(12);
const js = JSON.parse(b.slice(20, 20 + jlen).toString());
const binStart = 20 + jlen + 8, binLen = b.readUInt32LE(20 + jlen);
const bin = b.slice(binStart, binStart + binLen);
BASIS({ wasmBinary: fs.readFileSync(path.join(base, "three/examples/jsm/libs/basis/basis_transcoder.wasm")) }).then((M) => {
  M.initializeBasis();
  js.images.forEach((im, i) => {
    const bv = js.bufferViews[im.bufferView];
    const data = bin.slice(bv.byteOffset || 0, (bv.byteOffset || 0) + bv.byteLength);
    const k = new M.KTX2File(new Uint8Array(data));
    const w = k.getWidth(), h = k.getHeight();
    k.startTranscoding();
    const size = k.getImageTranscodedSizeInBytes(0, 0, 0, 13);   // 13 = cTFRGBA32
    const dst = new Uint8Array(size);
    k.transcodeImage(dst, 0, 0, 0, 13, 0, -1, -1);
    k.close(); k.delete();
    const png = new PNG({ width: w, height: h });
    png.data = Buffer.from(dst);
    const name = "tex" + i + ".png";
    fs.writeFileSync(path.join(out, name), PNG.sync.write(png));
    delete im.bufferView; delete im.mimeType; im.uri = name;
  });
  (js.textures || []).forEach((t) => {
    if (t.extensions && t.extensions.KHR_texture_basisu) { t.source = t.extensions.KHR_texture_basisu.source; delete t.extensions.KHR_texture_basisu; }
  });
  for (const k of ["extensionsUsed", "extensionsRequired"]) if (js[k]) { js[k] = js[k].filter((e) => e !== "KHR_texture_basisu"); if (!js[k].length) delete js[k]; }
  js.buffers = [{ byteLength: bin.length, uri: "scan.bin" }];
  fs.writeFileSync(path.join(out, "scan.bin"), bin);
  fs.writeFileSync(path.join(out, "scan.gltf"), JSON.stringify(js));
  console.log("images", js.images.length);
});
