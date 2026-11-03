// GLB (KHR_texture_basisu) -> .gltf + .bin + raw RGBA textures (tex<i>.rgba + tex<i>.json size). PNG via raw2png.py
// usage: node ktx2raw.js <in.glb> <out_dir>   (transcoder: tools/scan/basis/basis_transcoder.cjs + .wasm - 배포본에는 없음: three.js examples/jsm/libs/basis 에서 두 파일을 받아 이 폴더의 basis/ 에 둔다)
const fs = require("fs"), path = require("path");
const bdir = path.join(__dirname, "basis");
const BASIS = require(path.join(bdir, "basis_transcoder.cjs"));
const [inp, out] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const b = fs.readFileSync(inp);
const jlen = b.readUInt32LE(12);
const js = JSON.parse(b.slice(20, 20 + jlen).toString());
const binStart = 20 + jlen + 8, binLen = b.readUInt32LE(20 + jlen);
const bin = b.slice(binStart, binStart + binLen);
(typeof BASIS === "function" ? BASIS : BASIS.default || BASIS.BASIS)({ wasmBinary: fs.readFileSync(path.join(bdir, "basis_transcoder.wasm")) }).then((M) => {
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
    fs.writeFileSync(path.join(out, "tex" + i + ".rgba"), Buffer.from(dst));
    fs.writeFileSync(path.join(out, "tex" + i + ".json"), JSON.stringify({ w, h }));
    delete im.bufferView; delete im.mimeType; im.uri = "tex" + i + ".png";
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
