/* ============================================================
   留白 · 图集
   换图 / 加分类：只改下面的 CATS 和 PHOTOS 两个数组。
   src 指向 images/ 里的本地文件，w / h 是图片原始像素宽高
   （用来占位，避免加载时跳动），cat 对应分类的 id。
   ============================================================ */

const CATS = [
  { id: 'R18', name: 'R18' },
  { id: 'foot', name: '脚' },
  { id: 'big', name: '巨入' },
  { id: 'small', name: '贫入' },
  { id: 'beauty', name: '唯美' }
];

const PHOTOS = [
  { src: 'images/01.jpg', w: 1200, h: 1500, cat: 'R18' },
  { src: 'images/02.jpg', w: 1400, h: 933, cat: 'R18' },
  { src: 'images/03.jpg', w: 1200, h: 1200, cat: 'R18' },
  { src: 'images/04.jpg', w: 1200, h: 1600, cat: 'R18' },
  { src: 'images/05.jpg', w: 1200, h: 1500, cat: 'foot' },
  { src: 'images/06.jpg', w: 1400, h: 933, cat: 'foot' },
  { src: 'images/07.jpg', w: 1200, h: 1600, cat: 'foot' },
  { src: 'images/08.jpg', w: 1200, h: 1200, cat: 'big' },
  { src: 'images/09.jpg', w: 1400, h: 933, cat: 'big' },
  { src: 'images/10.jpg', w: 1200, h: 1500, cat: 'big' },
  { src: 'images/11.jpg', w: 1200, h: 1200, cat: 'big' },
  { src: 'images/12.jpg', w: 1400, h: 933, cat: 'big' },
  { src: 'images/13.jpg', w: 1200, h: 1500, cat: 'small' },
  { src: 'images/14.jpg', w: 1200, h: 1200, cat: 'small' },
  { src: 'images/15.jpg', w: 1200, h: 1500, cat: 'beauty' },
  { src: 'images/16.jpg', w: 1400, h: 933, cat: 'beauty' },
  { src: 'images/17.jpg', w: 1200, h: 1500, cat: 'beauty' },
  { src: 'images/18.jpg', w: 1400, h: 933, cat: 'beauty' },
  { src: 'images/19.jpg', w: 1200, h: 1500, cat: 'beauty' },
  { src: 'images/20.jpg', w: 1400, h: 933, cat: 'beauty' }

];

/* ---------------- 元素 ---------------- */

const indexEl = document.getElementById('index');
const galleryEl = document.getElementById('gallery');
const titleEl = document.getElementById('catTitle');
const viewHome = document.getElementById('viewHome');
const viewGalb = document.getElementById('viewGallery');

const lb = document.getElementById('lb');
const lbImg = document.getElementById('lbImg');
const lbNo = document.getElementById('lbNo');
const lbPrev = document.getElementById('lbPrev');
const lbNext = document.getElementById('lbNext');
const lbClose = document.getElementById('lbClose');

let current = [];   // 当前分类的照片
let cursor = 0;

/* ---------------- 首屏 ---------------- */

function renderIndex() {
  indexEl.innerHTML = CATS.map(c => `
    <a class="cat" href="#/${c.id}">
      <span class="cat-name">${c.name}</span>
      <span class="cat-go" aria-hidden="true">→</span>
    </a>`).join('');
}

/* ---------------- 图墙 ---------------- */

const colCount = () => {
  const w = window.innerWidth;
  return w <= 620 ? 1 : w <= 1080 ? 2 : 3;
};

/* 把图片分到各列：多试几遍「放进最矮的列」，取底部最齐的那一版。
   随机种子固定 —— 每次打开排版都一样。                        */

function mulberry32(a) {
  return function () {
    a = a + 0x6D2B79F5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

function distribute(items, n) {
  if (n === 1) return [items];

  const rnd = mulberry32(20261108);
  let best = null;
  let bestScore = Infinity;

  for (let t = 0; t < 120; t++) {
    const arr = items.slice();
    if (t) {
      for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(rnd() * (i + 1));
        [arr[i], arr[j]] = [arr[j], arr[i]];
      }
    }
    const cols = Array.from({ length: n }, () => []);
    const h = new Array(n).fill(0);
    arr.forEach(it => {
      const k = h.indexOf(Math.min(...h));
      cols[k].push(it);
      h[k] += it.r;
    });
    const score = Math.max(...h) - Math.min(...h);
    if (score < bestScore - 1e-6) { bestScore = score; best = cols; }
  }

  // 每列内部按原顺序排，读起来更顺
  best.forEach(c => c.sort((a, b) => a.i - b.i));
  return best;
}

function masonry() {
  const n = colCount();
  const items = [...galleryEl.querySelectorAll('.shot')].map(el => {
    const i = Number(el.dataset.i);
    const p = current[i];
    return { el, i, r: p.h / p.w };
  });

  const cols = distribute(items, n).map(group => {
    const d = document.createElement('div');
    d.className = 'gcol';
    group.forEach(it => d.appendChild(it.el));
    return d;
  });

  galleryEl.replaceChildren(...cols);
}

function bindFade() {
  galleryEl.querySelectorAll('img').forEach(img => {
    const done = () => img.classList.add('loaded');
    if (img.complete && img.naturalWidth) done();
    else { img.addEventListener('load', done); img.addEventListener('error', done); }
  });
}

function openCat(id) {
  const cat = CATS.find(c => c.id === id);
  if (!cat) return goHome();

  closeLB();
  current = PHOTOS.filter(p => p.cat === id);
  titleEl.textContent = cat.name;

  galleryEl.innerHTML = current.map((p, i) => `
    <button class="shot" type="button" data-i="${i}"
            style="animation-delay:${Math.min(i * 35, 420)}ms"
            aria-label="第 ${i + 1} 张，共 ${current.length} 张">
      <img src="${p.src}" width="${p.w}" height="${p.h}" alt=""
           loading="${i < 4 ? 'eager' : 'lazy'}" decoding="async">
    </button>`).join('');

  masonry();
  bindFade();

  document.body.classList.remove('is-home');
  document.body.classList.add('is-gallery');
  viewHome.classList.remove('is-on');
  viewGalb.classList.add('is-on');
  window.scrollTo(0, 0);
}

function goHome() {
  closeLB();
  renderIndex();
  document.body.classList.remove('is-gallery');
  document.body.classList.add('is-home');
  viewGalb.classList.remove('is-on');
  viewHome.classList.add('is-on');
  window.scrollTo(0, 0);
}

/* ---------------- 灯箱 ---------------- */

function paint() {
  const p = current[cursor];
  lbImg.src = p.src;
  lbNo.textContent = `${String(cursor + 1).padStart(2, '0')} / ${String(current.length).padStart(2, '0')}`;
}

function openLB(i) {
  if (!current.length) return;
  cursor = i;
  paint();
  lb.classList.add('open');
  document.body.classList.add('lb-open');
  lbClose.focus({ preventScroll: true });
}

function closeLB() {
  if (!lb.classList.contains('open')) return;
  lb.classList.remove('open');
  document.body.classList.remove('lb-open');
  lbImg.removeAttribute('src');
}

function step(dir) {
  if (!current.length) return;
  cursor = (cursor + dir + current.length) % current.length;
  paint();
}

galleryEl.addEventListener('click', e => {
  const shot = e.target.closest('.shot');
  if (shot) openLB(Number(shot.dataset.i));
});

lbClose.addEventListener('click', closeLB);
lbPrev.addEventListener('click', () => step(-1));
lbNext.addEventListener('click', () => step(1));

lb.addEventListener('click', e => {
  if (e.target === lb || e.target.classList.contains('lb-stage')) closeLB();
});

document.addEventListener('keydown', e => {
  if (lb.classList.contains('open')) {
    if (e.key === 'Escape') closeLB();
    if (e.key === 'ArrowLeft') step(-1);
    if (e.key === 'ArrowRight') step(1);
    return;
  }
  if (e.key === 'Escape' && location.hash) location.hash = '#/';
});

/* 手机滑动 */
let touchX = null;
lb.addEventListener('touchstart', e => { touchX = e.touches[0].clientX; }, { passive: true });
lb.addEventListener('touchend', e => {
  if (touchX === null) return;
  const dx = e.changedTouches[0].clientX - touchX;
  if (Math.abs(dx) > 50) step(dx > 0 ? -1 : 1);
  touchX = null;
}, { passive: true });

/* ---------------- 路由 ---------------- */

function route() {
  const id = (location.hash || '').replace(/^#\/?/, '');
  if (id) openCat(id);
  else goHome();
}

window.addEventListener('hashchange', route);

let rzTimer = null;
window.addEventListener('resize', () => {
  if (!document.body.classList.contains('is-gallery')) return;
  clearTimeout(rzTimer);
  rzTimer = setTimeout(masonry, 140);
});

route();
