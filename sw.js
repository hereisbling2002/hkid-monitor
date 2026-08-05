// ============================================================
// Service Worker for HKID Quota Monitor PWA
// 策略：Stale-while-revalidate + 关键资源预缓存
// ============================================================

const CACHE_NAME = 'hkid-monitor-v2';
const DATA_CACHE = 'hkid-data-v1';

// ---- 安装时预缓存的静态资源 ----
const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/config.json',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js'
];

// ---- Install: 预缓存核心静态资源 ----
self.addEventListener('install', (event) => {
  console.log('[SW] Installing...');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[SW] Precaching static assets');
        return cache.addAll(PRECACHE_URLS);
      })
      .then(() => self.skipWaiting())
  );
});

// ---- Activate: 清理旧缓存 ----
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating...');
  const validCaches = [CACHE_NAME, DATA_CACHE];
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => !validCaches.includes(key))
          .map((key) => {
            console.log('[SW] Deleting old cache:', key);
            return caches.delete(key);
          })
      )
    ).then(() => self.clients.claim())
  );
});

// ---- Fetch: Stale-while-revalidate ----
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // 跳过非 GET 请求和 chrome-extension
  if (request.method !== 'GET') return;
  if (url.protocol === 'chrome-extension:') return;

  // ---- 策略 1: 数据 API / JSON 文件 → Network First ----
  if (url.pathname.includes('/data/') || url.pathname.endsWith('.json')) {
    event.respondWith(networkFirst(request));
    return;
  }

  // ---- 策略 2: 导航请求 (HTML) → Network First ----
  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request));
    return;
  }

  // ---- 策略 3: 静态资源 (CSS/JS/图片/字体) → Cache First ----
  if (
    url.pathname.match(/\.(css|js|png|jpg|jpeg|gif|svg|ico|woff2?|ttf|eot)$/) ||
    url.hostname === 'cdn.jsdelivr.net'
  ) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // ---- 默认: Stale-while-revalidate ----
  event.respondWith(staleWhileRevalidate(request));
});

// ========================
// 缓存策略实现
// ========================

/**
 * Cache First: 优先从缓存读取，缓存未命中才走网络。
 * 适用：版本化的静态资源（CSS/JS/图片）。
 */
async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    console.warn('[SW] CacheFirst fetch failed:', request.url, err);
    // 返回离线占位 SVG（针对图片请求）
    if (request.destination === 'image') {
      return new Response(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
        + '<rect fill="#1e293b" width="200" height="200"/>'
        + '<text fill="#94a3b8" x="50%" y="50%" text-anchor="middle" dy=".3em" font-size="14">离线</text>'
        + '</svg>',
        { headers: { 'Content-Type': 'image/svg+xml' } }
      );
    }
    throw err;
  }
}

/**
 * Network First: 优先走网络，失败时回退缓存。
 * 适用：HTML 页面、API 数据。
 */
async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(
        request.url.includes('/data/') ? DATA_CACHE : CACHE_NAME
      );
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    console.warn('[SW] NetworkFirst fallback to cache:', request.url);
    const cached = await caches.match(request);
    if (cached) return cached;
    // 最终回退：返回首页
    if (request.mode === 'navigate') {
      const offlinePage = await caches.match('/');
      if (offlinePage) return offlinePage;
    }
    throw err;
  }
}

/**
 * Stale-while-revalidate: 立即返回缓存，同时后台更新缓存。
 * 适用：非关键资源。
 */
async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);

  const fetchPromise = fetch(request)
    .then((response) => {
      if (response.ok) {
        cache.put(request, response.clone());
      }
      return response;
    })
    .catch((err) => console.warn('[SW] SWR update failed:', request.url, err));

  return cached || fetchPromise;
}

// ========================
// 消息处理
// ========================

self.addEventListener('message', (event) => {
  if (event.data === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  if (event.data === 'CLEAR_DATA_CACHE') {
    caches.delete(DATA_CACHE).then(() => {
      console.log('[SW] Data cache cleared');
      self.clients.matchAll().then((clients) => {
        clients.forEach((client) => client.postMessage('DATA_CACHE_CLEARED'));
      });
    });
  }
});
