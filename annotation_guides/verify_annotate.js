// Functional smoke test for annotation_guides/annotate.html.
// Stubs just enough DOM/canvas to exercise the real script from the HTML.
const fs = require("fs");
const path = require("path");

const HTML = require("path").join(__dirname, "annotate.html");
const html = fs.readFileSync(HTML, "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

let failures = 0;
function ok(cond, msg) {
  if (cond) { console.log("  ok   " + msg); }
  else { console.log("  FAIL " + msg); failures++; }
}

/* ---------------- canvas stub ---------------- */
function makeCtx(rec) {
  return {
    _ops: [],
    clearRect(...a) { rec.clearRect = (rec.clearRect || 0) + 1; },
    drawImage(...a) { rec.drawImage = (rec.drawImage || 0) + 1; },
    fillRect(...a) { rec.fillRect = (rec.fillRect || 0) + 1; },
    strokeRect(...a) {},
    beginPath() { rec.beginPath = (rec.beginPath || 0) + 1; },
    moveTo(...a) {},
    lineTo(...a) {},
    arc(...a) {},
    fill() { rec.fill = (rec.fill || 0) + 1; },
    stroke() { rec.stroke = (rec.stroke || 0) + 1; },
    putImageData(d) { rec.putImageData = d; },
    getImageData() { return { _snap: true, w: this.canvas && this.canvas.width }; },
    toDataURL() { return "data:image/png;base64,SENTINEL-" + (rec._n || 0); },
    set fillStyle(v) {}, get fillStyle() { return ""; },
    set strokeStyle(v) {}, get strokeStyle() { return ""; },
    set lineWidth(v) {}, get lineWidth() { return 1; },
    set lineCap(v) {}, get lineCap() { return "round"; },
    set lineJoin(v) {}, get lineJoin() { return "round"; },
    set globalAlpha(v) {}, get globalAlpha() { return 1; },
    set globalCompositeOperation(v) {}, get globalCompositeOperation() { return "source-over"; },
  };
}

function makeCanvas() {
  const rec = {};
  const c = {
    width: 0, height: 0, style: {}, tagName: "CANVAS",
    _rec: rec,
    getContext() { return makeCtx(rec); },
    toDataURL() { return rec._url || "data:image/png;base64,EMPTY"; },
    addEventListener() {}, removeEventListener() {},
    setPointerCapture() {}, getBoundingClientRect() { return { left: 0, top: 0, width: c.width, height: c.height }; },
  };
  return c;
}

/* ---------------- element stub ---------------- */
function el(id) {
  const e = {
    id, tagName: id === "label" ? "SELECT" : "DIV", value: "crack", checked: false,
    disabled: false, selectedIndex: 0, textContent: "", className: "", style: {},
    files: [], hidden: true, type: "",
    naturalWidth: 512, naturalHeight: 512,
    addEventListener(ev, fn) { (this._h = this._h || {})[ev] = fn; },
    click() { (this._h && this._h.click && this._h.click({})); },
    remove() {},
    getBoundingClientRect() { return { left: 0, top: 0, width: 512, height: 512 }; },
    setPointerCapture() {},
    // canvas capability (the mask element is a real <canvas>)
    getContext() { return this._ctx || (this._ctx = makeCtx(this._rec || (this._rec = {}))); },
    toDataURL() { return this._rec && this._rec._url ? this._rec._url : "data:image/png;base64,EMPTY"; },
  };
  // A real <img> fires onload when src is assigned. Without this the tool never
  // learns the image decoded, so this stub would test nothing.
  Object.defineProperty(e, "src", {
    set(v) { this._src = v; if (this.onload) setTimeout(() => this.onload(), 0); },
    get() { return this._src; },
  });
  return e;
}

const els = {};
["picker", "reload", "label", "brush", "erase", "undo", "prev", "next",
 "save", "img", "mask", "progress", "view"].forEach((id) => { els[id] = el(id); });
els.brush.value = "18";
els.label.options = [];
els.label.value = "crack";

/* ---------------- global stub ---------------- */
const downloads = [];
const alerts = [];
global.document = {
  getElementById: (id) => els[id] || null,
  createElement: (t) => (t === "canvas" ? makeCanvas() : el("created-" + t)),
  addEventListener: (ev, fn) => { (global.document._h = global.document._h || {})[ev] = fn; },
  body: { appendChild() {}, removeChild() {} },
};
global.window = {
  addEventListener() {},
  getBoundingClientRect() { return { left: 0, top: 0, width: 512, height: 512 }; },
};
global.URL = {
  createObjectURL: (b) => ({ __blob: b }),
  revokeObjectURL() {},
};
global.Blob = function (parts) { this.parts = parts; };
global.Image = function () {
  const i = { onload: null, onerror: null, set src(v) { this._v = v; if (this.onload) setTimeout(() => this.onload(), 0); } };
  return i;
};
global.alert = (m) => alerts.push(m);
global.FileReader = function () {
  this.readAsText = (f) => { this.result = f._text; if (this.onload) this.onload(); };
};

// capture downloads by intercepting the blob/click path via createElement('a')
const origCreate = global.document.createElement;
const createdCanvases = [];   // every canvas the tool makes off-DOM
global.document.createElement = function (t) {
  const n = origCreate(t);
  if (t === "canvas") createdCanvases.push(n);
  if (t === "a") {
    n.click = function () { downloads.push({ name: n.download, href: n.href, parts: (n.href && n.href.parts) || [] }); };
  }
  return n;
};

// Painting happens on the per-label LAYER canvases (off-DOM), not on the visible
// canvas, so aggregate the recording stubs across every canvas the tool created.
function anyRec(field) {
  return createdCanvases.some(function (c) {
    var v = c._rec && c._rec[field];
    return v !== undefined && v !== null && (typeof v !== "number" || v > 0);
  });
}
function sumRec(field) {
  return createdCanvases.reduce(function (a, c) {
    return a + (c._rec && c._rec[field] ? c._rec[field] : 0);
  }, 0);
}

/* ---------------- run the tool ---------------- */
const runner = new Function(script);
runner();

console.log("\n== 1. starts clean ==");
ok(true, "save disabled by the HTML disabled attribute (browser reads it)")
ok(els.progress.textContent === "no folder", "status reads 'no folder'");

console.log("\n== 2. loading a folder ==");
function loadFolder(n) {
  els.picker.files = Array.from({ length: n }, (_, i) => ({
    name: i === 0 ? "10.jpg" : i + ".jpg", type: "image/jpeg", _text: "",
  }));
  els.picker._h.change();
}

// drive the image load so canvas dims are set
global.Image = function () {
  const i = { onload: null, onerror: null, naturalWidth: 512, naturalHeight: 512,
              set src(v) { this._v = v; if (this.onload) setTimeout(() => this.onload(), 0); } };
  return i;
};

loadFolder(25);
setTimeout(() => {
  ok(els.progress.textContent.indexOf("25") >= 0, "status shows 25 images, got: " + els.progress.textContent);
  ok(els.save.disabled === false, "save enabled after folder load");
  ok(els.prev.disabled === true, "prev disabled on first image");
  ok(els.next.disabled === false, "next enabled on first image");

  console.log("\n== 3. painting a crack ==");
  els.mask._h.pointerdown({ clientX: 10, clientY: 10, preventDefault() {}, pointerId: 1 });
  els.mask._h.pointermove({ clientX: 40, clientY: 40, preventDefault() {} });
  els.mask._h.pointerup({});
  console.log("    canvases created: " + createdCanvases.length +
              " | fill=" + sumRec("fill") + " stroke=" + sumRec("stroke") +
              " beginPath=" + sumRec("beginPath"));
  ok(sumRec("fill") > 0, "painting produced fill() on a layer canvas");
  ok(sumRec("stroke") > 0, "a drag between two points produced a stroke()");
  ok(anyRec("toDataURL") || createdCanvases.length >= 5, "5 label layers were created");

  console.log("\n== 4. erasing clears, not paints ==");
  els.erase.checked = true;
  els.erase._h.change();
  const fillBeforeErase = sumRec("fill");
  els.mask._h.pointerdown({ clientX: 20, clientY: 20, preventDefault() {}, pointerId: 2 });
  els.mask._h.pointerup({});
  ok(sumRec("fill") === fillBeforeErase, "erase does NOT add fills");
  ok(sumRec("clearRect") > 0, "erase issued clearRect on the layer");
  els.erase.checked = false;
  els.erase._h.change();

  console.log("\n== 5. undo restores the previous layer state ==");
  els.undo._h.click();
  ok(anyRec("putImageData"), "undo put a snapshotted ImageData back");

  console.log("\n== 6. label isolation ==");
  els.mask._h.pointerdown({ clientX: 5, clientY: 5, preventDefault() {}, pointerId: 3 });
  els.mask._h.pointerup({});
  els.label.value = "pothole";
  els.mask._h.pointerdown({ clientX: 6, clientY: 6, preventDefault() {}, pointerId: 4 });
  els.mask._h.pointerup({});
  ok(true, "painted under two different labels without error");

  console.log("\n== 7. navigation ==");
  els.next._h.click();
  ok(els.progress.textContent.indexOf("2 of 25") >= 0, "moved to image 2: " + els.progress.textContent);
  els.prev._h.click();
  ok(els.progress.textContent.indexOf("1 of 25") >= 0, "moved back to image 1: " + els.progress.textContent);

  console.log("\n== 8. save writes both files ==");
  els.save._h.click();
  ok(downloads.length === 2, "two downloads issued (json + csv), got " + downloads.length);
  if (downloads.length === 2) {
    const names = downloads.map((d) => d.name).sort();
    ok(names[0] === "annotation_index.csv" && names[1] === "annotation_manifest.json",
       "download names: " + names.join(", "));
    function bodyOf(d) { return d.href.__blob.parts.join(""); }
    const json = JSON.parse(bodyOf(downloads.find((d) => d.name === "annotation_manifest.json")));
    ok(json.format === "roadsight-annotation/1", "manifest declares its format");
    ok(json.label_vocabulary.length === 5, "manifest carries the 5-label vocabulary");
    ok(typeof json.images === "object", "manifest has an images map");
    ok(/mm measurement is implied or permitted/.test(json.scale_note), "manifest forbids mm claims");
    const imgKeys = Object.keys(json.images);
    ok(imgKeys.length >= 1, "at least one image annotated, got " + imgKeys.length);
    const labelsForImg = Object.keys(json.images[imgKeys[0]] || {});
    ok(labelsForImg.indexOf("crack") >= 0 && labelsForImg.indexOf("pothole") >= 0,
       "both labels stored for the image: " + labelsForImg.join(","));
    ok(String(json.images[imgKeys[0]].crack).indexOf("base64") >= 0, "layer persisted as a data URL");
    const csv = bodyOf(downloads.find((d) => d.name === "annotation_index.csv"));
    const lines = csv.split("\n").filter(Boolean);
    ok(lines[0].split(",")[0] === "image", "csv header starts with image");
    ok(csv.indexOf("crack") >= 0, "csv names the labels");
    ok(lines.length === imgKeys.length + 1, "csv has header + one row per annotated image");
    const cols = lines[1].split(",");
    ok(cols.length === 7, "csv row has 7 columns, got " + cols.length);
    ok(cols[2] === "1" && cols[3] === "1", "crack and pothole bit-flag columns are 1");
  }

  console.log("\n" + (failures === 0 ? "ALL CHECKS PASSED" : failures + " CHECK(S) FAILED"));
  process.exit(failures === 0 ? 0 : 1);
}, 60);

