// BusQuiz 서비스워커 — 앱 껍데기만 캐시한다. 문제팩은 IndexedDB에 있으므로 네트워크가 전혀 필요 없다.
const VERSION = "busquiz-v6";
const SHELL = [
  "./", "./index.html", "./manifest.webmanifest",
  "./css/app.css",
  "./js/main.js", "./js/db.js", "./js/pack.js", "./js/md.js", "./js/quiz.js", "./js/exam.js", "./js/stats.js", "./js/ui.js",
  "./icons/icon-192.png", "./icons/icon-512.png", "./icons/apple-touch-icon.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

// 캐시에 있으면 바로 주고, 뒤에서 네트워크로 새 사본을 받아 캐시를 갱신한다(stale-while-revalidate).
// 오프라인이면 캐시만 쓴다. 다음 실행 때 새 파일이 적용된다. 배포 때 VERSION을 바꾸면 옛 캐시를 지운다.
self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET" || new URL(e.request.url).origin !== location.origin) return;
  e.respondWith(
    caches.open(VERSION).then(async (c) => {
      const hit = await c.match(e.request, { ignoreSearch: true });
      const net = fetch(e.request).then((res) => { if (res.ok) c.put(e.request, res.clone()); return res; }).catch(() => null);
      if (hit) { e.waitUntil(net); return hit; }
      const res = await net;
      return res || (await c.match("./index.html"));
    }),
  );
});
