// IndexedDB 래퍼. 저장소:
//  packs      key=book          {book, name, version, count, sets[], importedAt}
//  questions  key=id, idx book  문제팩의 문항 그대로(이미지 제외)
//  images     key=name          data URL 문자열
//  progress   key=qid           {qid, book, attempts, correct, wrong, last, lastAt, streak, inWrong, confused, note}
//  sessions   key=id            풀기/모의고사 세션(이어풀기용)
//  meta       key=k             설정 등
const NAME = "busquiz", VER = 1;
let dbp = null;

export function open() {
  if (dbp) return dbp;
  dbp = new Promise((res, rej) => {
    const r = indexedDB.open(NAME, VER);
    r.onupgradeneeded = () => {
      const d = r.result;
      d.createObjectStore("packs", { keyPath: "book" });
      d.createObjectStore("questions", { keyPath: "id" }).createIndex("book", "book");
      d.createObjectStore("images", { keyPath: "name" });
      d.createObjectStore("progress", { keyPath: "qid" }).createIndex("book", "book");
      d.createObjectStore("sessions", { keyPath: "id" });
      d.createObjectStore("meta", { keyPath: "k" });
    };
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error);
  });
  return dbp;
}

function tx(stores, mode = "readonly") {
  return open().then((d) => d.transaction(stores, mode));
}
const done = (t) => new Promise((res, rej) => { t.oncomplete = () => res(); t.onerror = () => rej(t.error); t.onabort = () => rej(t.error); });
const req = (r) => new Promise((res, rej) => { r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });

export async function get(store, key) { return req((await tx(store)).objectStore(store).get(key)); }
export async function all(store) { return req((await tx(store)).objectStore(store).getAll()); }
export async function allBy(store, index, value) {
  return req((await tx(store)).objectStore(store).index(index).getAll(value));
}
export async function put(store, obj) { const t = await tx(store, "readwrite"); t.objectStore(store).put(obj); return done(t); }
export async function del(store, key) { const t = await tx(store, "readwrite"); t.objectStore(store).delete(key); return done(t); }
export async function putMany(store, objs) {
  const t = await tx(store, "readwrite"); const s = t.objectStore(store);
  for (const o of objs) s.put(o);
  return done(t);
}
export async function count(store) { return req((await tx(store)).objectStore(store).count()); }

export async function getMeta(k, dflt = null) { const r = await get("meta", k); return r ? r.v : dflt; }
export async function setMeta(k, v) { return put("meta", { k, v }); }

// 한 책의 문항·이미지를 통째로 바꾼다(학습 기록 progress는 건드리지 않는다)
export async function replaceBook(pack) {
  const t = await tx(["packs", "questions", "images"], "readwrite");
  const qs = t.objectStore("questions"), im = t.objectStore("images");
  await new Promise((res) => {
    const c = qs.index("book").openKeyCursor(IDBKeyRange.only(pack.book));
    c.onsuccess = () => { const cur = c.result; if (cur) { qs.delete(cur.primaryKey); cur.continue(); } else res(); };
  });
  await new Promise((res) => {
    const c = im.openKeyCursor(IDBKeyRange.bound(pack.book + "-", pack.book + "-￿"));
    c.onsuccess = () => { const cur = c.result; if (cur) { im.delete(cur.primaryKey); cur.continue(); } else res(); };
  });
  for (const q of pack.questions) qs.put(q);
  for (const [name, data] of Object.entries(pack.images || {})) im.put({ name, data });
  t.objectStore("packs").put({ book: pack.book, name: pack.name, version: pack.version, count: pack.questions.length,
    sets: pack.sets, subjects: pack.subjects || null, importedAt: Date.now() });
  return done(t);
}

export async function removeBook(book) {
  const t = await tx(["packs", "questions", "images"], "readwrite");
  const qs = t.objectStore("questions"), im = t.objectStore("images");
  await new Promise((res) => {
    const c = qs.index("book").openKeyCursor(IDBKeyRange.only(book));
    c.onsuccess = () => { const cur = c.result; if (cur) { qs.delete(cur.primaryKey); cur.continue(); } else res(); };
  });
  await new Promise((res) => {
    const c = im.openKeyCursor(IDBKeyRange.bound(book + "-", book + "-￿"));
    c.onsuccess = () => { const cur = c.result; if (cur) { im.delete(cur.primaryKey); cur.continue(); } else res(); };
  });
  t.objectStore("packs").delete(book);
  return done(t);
}
