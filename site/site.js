/* SAP — shared motion + enquiry store. Loaded by every page. */
(function () {
  var E = 'cubic-bezier(.2,.7,.2,1)';
  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var io = null, mounted = false, pending = [], pageOk = false;
  function release() {
    if (!window.__sapHold && !pending.length) return;
    window.__sapHold = false;
    var p = pending; pending = []; p.forEach(show);
    window.dispatchEvent(new Event('sap-ready'));
  }
  function el(tag, css, parent, text) { var e = document.createElement(tag); if (css) e.style.cssText = css; if (text) e.textContent = text; if (parent) parent.appendChild(e); return e; }
  function A(node, frames, opts) { return node.animate ? node.animate(frames, Object.assign({ fill: 'both', easing: E }, opts)) : null; }
  function loader() {
    var L = document.getElementById('sap-loader');
    if (!L || L.dataset.run) return; L.dataset.run = '1';
    window.__sapHold = true;
    var done = function () { L.style.display = 'none'; L.style.pointerEvents = 'none'; L.innerHTML = ''; };
    var safety = setTimeout(function () { if (L.style.display !== 'none') { done(); release(); } }, 5000);
    if (!L.animate) { done(); release(); return; }
    try { history.scrollRestoration = 'manual'; } catch (e) {}
    window.scrollTo(0, 0);
    L.style.display = 'flex'; L.style.alignItems = 'center'; L.style.justifyContent = 'center'; L.style.fontFamily = "'Geist',system-ui,sans-serif";
    var box = el('div', 'width:min(62vw,440px);position:relative', L);
    var foot = el('div', 'position:absolute;left:clamp(20px,4vw,56px);right:clamp(20px,4vw,56px);bottom:clamp(24px,4vw,48px);display:flex;justify-content:space-between;align-items:flex-end;gap:16px;font-size:13px;color:#676868', L);
    el('span', '', foot, 'Architectural Furniture Fitting');
    var num = el('span', 'font-size:clamp(44px,7vw,96px);font-weight:500;letter-spacing:-.05em;line-height:.9;color:#1C1C1C;font-variant-numeric:tabular-nums', foot, '0');
    var bar = el('div', 'position:absolute;left:0;bottom:0;height:3px;width:100%;background:#00A65B;transform:scaleX(0);transform-origin:left', L);
    var DUR = 2100, svgOk = false;
    loader.go = function () {
      if (!svgOk || loader.started) return; loader.started = true;
      var p = box.querySelectorAll('path'), list = [];
      var bA = A(bar, [{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }], { duration: DUR, easing: 'cubic-bezier(.3,.1,.3,1)' }); list.push(bA);
      (function tick() { if (!L.isConnected || !bA) return; var k = Math.min(1, (bA.currentTime || 0) / DUR); num.textContent = Math.round((1 - Math.pow(1 - k, 2)) * 100); if (k < 1) requestAnimationFrame(tick); })();
      list.push(A(p[2], [{ opacity: 0, transform: 'scale(.55) rotate(-8deg)' }, { opacity: 1, transform: 'none' }], { duration: 900, delay: 100, easing: 'cubic-bezier(.2,1.3,.3,1)' }));
      list.push(A(p[3], [{ opacity: 0, transform: 'translateY(45%)' }, { opacity: 1, transform: 'none' }], { duration: 800, delay: 380 }));
      list.push(A(p[0], [{ opacity: 0, transform: 'translateX(-40%)' }, { opacity: 1, transform: 'none' }], { duration: 900, delay: 560 }));
      list.push(A(p[1], [{ opacity: 0, transform: 'translateX(40%)' }, { opacity: 1, transform: 'none' }], { duration: 900, delay: 560 }));
      list.push(A(p[4], [{ opacity: 0, transform: 'scale(0)' }, { opacity: 1, transform: 'none' }], { duration: 600, delay: 1050, easing: 'cubic-bezier(.2,1.4,.3,1)' }));
      list.push(A(p[5], [{ opacity: 0, transform: 'scale(0)' }, { opacity: 1, transform: 'none' }], { duration: 600, delay: 1100, easing: 'cubic-bezier(.2,1.4,.3,1)' }));
      for (var j = 6; j < p.length; j++) list.push(A(p[j], [{ opacity: 0, transform: 'translateY(60%)' }, { opacity: 1, transform: 'none' }], { duration: 600, delay: 1000 + (j - 6) * 45 }));
      Promise.all(list.map(function (a) { return a && a.finished; })).then(function () { setTimeout(fly, 300); });
    };
    fetch('assets/sap-logo.svg').then(function (r) { return r.text(); }).then(function (txt) {
      txt = txt.replace(/<\?xml[^>]*>/, '').replace(/<metadata>[\s\S]*?<\/metadata>/, '');
      box.innerHTML = txt;
      var svg = box.querySelector('svg'); if (!svg) throw 0;
      svg.style.cssText = 'width:100%;height:auto;display:block;overflow:visible';
      var p = svg.querySelectorAll('path');
      for (var i = 0; i < p.length; i++) { p[i].style.transformBox = 'fill-box'; p[i].style.transformOrigin = 'center'; }
      for (var q = 0; q < p.length; q++) p[q].style.opacity = '0';
      svgOk = true; loader.go();
    }).catch(function () { done(); release(); });
    function fly() {
      if (!pageOk || !document.querySelector('[data-hdr] img')) { setTimeout(fly, 80); return; }
      window.scrollTo(0, 0);
      var hdr = document.querySelector('[data-hdr]'), logo = hdr && hdr.querySelector('img'), nav = hdr && hdr.querySelector('nav');
      if (!logo) { A(L, [{ opacity: 1 }, { opacity: 0 }], { duration: 500 }).onfinish = function () { done(); release(); }; return; }
      var s = box.getBoundingClientRect(), t = logo.getBoundingClientRect(), sc = t.width / s.width;
      if (!isFinite(sc) || sc <= 0 || !s.width || !t.width) { A(L, [{ opacity: 1 }, { opacity: 0 }], { duration: 350 }).onfinish = function () { done(); release(); clearTimeout(safety); }; return; }
      logo.style.opacity = '0'; if (nav) nav.style.opacity = '0';
      A(foot, [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(16px)' }], { duration: 450 });
      A(bar, [{ transform: 'scaleX(1)' }, { transform: 'scaleX(1)', opacity: 0 }], { duration: 400 });
      box.style.transformOrigin = '0 0';
      var f = A(box, [{ transform: 'none' }, { transform: 'translate(' + (t.left - s.left) + 'px,' + (t.top - s.top) + 'px) scale(' + sc + ')' }], { duration: 1100, delay: 150, easing: 'cubic-bezier(.75,0,.15,1)' });
      A(L, [{ backgroundColor: 'rgba(239,239,239,1)' }, { backgroundColor: 'rgba(239,239,239,0)' }], { duration: 700, delay: 700, easing: 'ease' });
      setTimeout(release, 950);
      f.onfinish = function () {
        logo.style.opacity = '1'; done(); clearTimeout(safety);
        if (nav) { nav.style.opacity = '1'; Array.prototype.forEach.call(nav.querySelectorAll('a, button'), function (n, i) { A(n, [{ opacity: 0, transform: 'translateY(-14px)' }, { opacity: 1, transform: 'none' }], { duration: 700, delay: i * 70 }); }); }
      };
    }
  }

  function count(el) {
    if (el.dataset.counted) return; el.dataset.counted = '1';
    var to = +el.dataset.count || 0, t0 = performance.now(), dur = 1400;
    (function tick(t) {
      var k = Math.min(1, (t - t0) / dur), v = Math.round(to * (1 - Math.pow(1 - k, 3)));
      el.textContent = v; if (k < 1) requestAnimationFrame(tick);
    })(t0);
  }
  function show(el) {
    var v = el.dataset.rv || '';
    if (v === 'line') el.style.transform = 'none';
    else if (v === 'clip') el.style.clipPath = 'inset(0% 0% 0% 0% round 4px)';
    else { el.style.opacity = 1; el.style.transform = 'none'; }
    if (el.dataset.count !== undefined) count(el);
    el.querySelectorAll('[data-count]').forEach(count);
  }
  function prep(el) {
    var v = el.dataset.rv || '', d = +el.dataset.d || 0;
    if (v === 'line') { el.style.transform = 'translateY(108%)'; el.style.transition = 'transform 1.15s ' + E + ' ' + d + 'ms'; }
    else if (v === 'clip') { el.style.clipPath = 'inset(12% 8% 12% 8% round 4px)'; el.style.transition = 'clip-path 1.5s ' + E + ' ' + d + 'ms'; }
    else { el.style.opacity = 0; el.style.transform = 'translateY(28px)'; el.style.transition = 'opacity 1s ' + E + ' ' + d + 'ms, transform 1.2s ' + E + ' ' + d + 'ms'; }
  }

  function scan() {
    document.querySelectorAll('img[data-gen][data-src]').forEach(function (i) {
      var v = i.getAttribute('data-src');
      if (v && v.indexOf('{{') < 0 && i.getAttribute('src') !== v) i.setAttribute('src', v);
    });
    if (!io) io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { if (window.__sapHold) pending.push(e.target); else show(e.target); io.unobserve(e.target); } });
    }, { threshold: 0.08, rootMargin: '0px 0px -6% 0px' });
    requestAnimationFrame(function () {
      document.querySelectorAll('[data-rv]:not([data-rvd])').forEach(function (el) {
        el.dataset.rvd = '1';
        if (reduce) { show(el); return; }
        prep(el); io.observe(el);
      });
    });
    document.querySelectorAll('[data-hov]:not([data-hovd])').forEach(function (el) {
      el.dataset.hovd = '1';
      el.addEventListener('mouseenter', function () {
        el.querySelectorAll('[data-hx]').forEach(function (c) {
          if (c.dataset.h0 === undefined) c.dataset.h0 = c.style.transform || '';
          c.style.transform = c.dataset.hx;
        });
      });
      el.addEventListener('mouseleave', function () {
        el.querySelectorAll('[data-hx]').forEach(function (c) { c.style.transform = c.dataset.h0 || ''; });
      });
    });
    if (!reduce) document.querySelectorAll('[data-mag]:not([data-magd])').forEach(function (el) {
      el.dataset.magd = '1';
      el.addEventListener('pointermove', function (e) {
        if (e.pointerType !== 'mouse') return;
        var r = el.getBoundingClientRect();
        el.style.transform = 'translate(' + ((e.clientX - r.left - r.width / 2) * 0.28).toFixed(1) + 'px,' + ((e.clientY - r.top - r.height / 2) * 0.4).toFixed(1) + 'px)';
      });
      el.addEventListener('pointerleave', function () { el.style.transform = ''; });
    });
    if (!reduce) document.querySelectorAll('[data-marquee]:not([data-mqd])').forEach(function (el) {
      el.dataset.mqd = '1';
      var x = 0, v = 0, lastY = scrollY, hover = false;
      el.addEventListener('mouseenter', function () { hover = true; });
      el.addEventListener('mouseleave', function () { hover = false; });
      (function loop() {
        var track = el.querySelector('[data-track]');
        if (!document.body.contains(el)) return;
        if (track) {
          var dy = scrollY - lastY; lastY = scrollY;
          v += (Math.abs(dy) * 0.12 - v) * 0.08;
          x -= (hover ? 0.15 : 0.55) + v;
          var half = track.scrollWidth / 2;
          if (half > 0 && -x >= half) x += half;
          track.style.transform = 'translate3d(' + x.toFixed(2) + 'px,0,0)';
        }
        requestAnimationFrame(loop);
      })();
    });
  }

  function smoothTo(id) {
    var t = document.getElementById(id); if (!t) return false;
    window.scrollTo({ top: t.getBoundingClientRect().top + window.scrollY - 80, behavior: 'smooth' });
    return true;
  }
  function curtainReset() {
    var c = document.querySelector('[data-curtain]'); if (!c) return;
    c.style.transition = 'none'; c.style.transform = 'translateY(100%)';
  }
  function leave(href) {
    var c = document.querySelector('[data-curtain]');
    if (!c || reduce) { location.href = href; return; }
    try { sessionStorage.setItem('sapNav', '1'); } catch (e) {}
    c.style.transition = 'transform .6s cubic-bezier(.7,0,.2,1)';
    requestAnimationFrame(function () { c.style.transform = 'translateY(0)'; });
    setTimeout(function () { location.href = href; }, 620);
  }

  function mount() {
    pageOk = true; loader(); if (loader.go) setTimeout(loader.go, 120);
    if (mounted) return; mounted = true;
    // images
    function onImg(e) {
      var t = e.target;
      if (!t || t.tagName !== 'IMG' || !t.hasAttribute('data-gen')) return;
      t.style.opacity = e.type === 'load' ? 1 : 0;
    }
    document.addEventListener('load', onImg, true);
    document.addEventListener('error', onImg, true);
    document.querySelectorAll('img[data-gen]').forEach(function (i) { if (i.complete && i.naturalWidth) i.style.opacity = 1; });
    // arrival cover (created in <helmet> before paint)
    var cover = document.getElementById('sap-cover');
    if (cover) {
      cover.style.transition = 'transform .9s cubic-bezier(.7,0,.2,1) .12s';
      requestAnimationFrame(function () { requestAnimationFrame(function () { cover.style.transform = 'translateY(-100%)'; }); });
      setTimeout(function () { cover.remove(); }, 1200);
    }
    window.addEventListener('pageshow', function (e) { if (e.persisted) curtainReset(); });
    // header hide/show + progress
    var last = scrollY, hidden = false;
    function onScroll() {
      var y = scrollY, h = document.querySelector('[data-hdr]'), p = document.querySelector('[data-progress]');
      if (h) {
        h.style.boxShadow = y > 8 ? '0 1px 0 rgba(28,28,28,.06)' : 'none';
      }
      if (p) { var max = document.documentElement.scrollHeight - innerHeight; p.style.transform = 'scaleX(' + (max > 0 ? Math.min(1, y / max) : 0) + ')'; }
      last = y;
    }
    window.addEventListener('scroll', onScroll, { passive: true }); onScroll();
    // links: smooth anchors + page curtain
    document.addEventListener('click', function (e) {
      var a = e.target.closest && e.target.closest('a[href]');
      if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || a.target === '_blank') return;
      var href = a.getAttribute('href');
      if (href.charAt(0) === '#') { if (smoothTo(href.slice(1))) e.preventDefault(); return; }
      var u; try { u = new URL(href, location.href); } catch (er) { return; }
      if (u.origin !== location.origin) return;
      if (u.pathname === location.pathname && u.search === location.search && u.hash) { if (smoothTo(u.hash.slice(1))) e.preventDefault(); return; }
      e.preventDefault(); leave(u.href);
    });
    if (location.hash) setTimeout(function () { smoothTo(location.hash.slice(1)); }, 350);
  }

  var enq = {
    get: function () { try { return +(localStorage.getItem('sap-enq') || 0); } catch (e) { return 0; } },
    add: function (n) {
      var v = enq.get() + (n || 1);
      try { localStorage.setItem('sap-enq', v); } catch (e) {}
      window.dispatchEvent(new CustomEvent('sap-enq', { detail: v }));
      var b = document.querySelector('[data-badge]');
      if (b && b.animate) b.animate([{ transform: 'scale(1)' }, { transform: 'scale(1.5)', background: '#1C1C1C', color: '#EFEFEF' }, { transform: 'scale(1)' }], { duration: 620, easing: E });
      return v;
    }
  };
  function pulse(sel) {
    var el = document.querySelector(sel);
    if (el && el.animate && !reduce) el.animate([{ opacity: 0.25, transform: 'translateY(10px)' }, { opacity: 1, transform: 'none' }], { duration: 520, easing: E });
  }

  // Safety net: the page renders its markup twice (raw HTML, then React). If the visible
  // loader overlay is a copy the intro never attached to, it would cover the page forever.
  (function guard(n) {
    var L = document.getElementById('sap-loader');
    if (L && L.isConnected && !L.dataset.run && n > 8) {
      L.style.display = 'none'; L.style.pointerEvents = 'none'; L.innerHTML = '';
      window.__sapHold = false; release();
    }
    if (n < 150) setTimeout(function () { guard(n + 1); }, 100);
  })(0);

  window.SAP = { fx: { mount: mount, scan: scan, pulse: pulse, release: release, loader: loader }, enq: enq };
  (function wait(n) { if (document.getElementById('sap-loader')) loader(); else if (n < 200) setTimeout(function () { wait(n + 1); }, 25); })(0);
})();
