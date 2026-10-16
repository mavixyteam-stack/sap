/* SAP Hardware admin. Vanilla JS, no build step. All text is inserted via textContent (no innerHTML). */
(function () {
  'use strict';
  var app = document.getElementById('app');
  var state = { user: null, view: 'dashboard', cache: {} };

  /* ---------- helpers ---------- */
  function h(tag, attrs) {
    var el = document.createElement(tag);
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v === false || v == null) return;
      if (k === 'class') el.className = v;
      else if (k === 'style') el.style.cssText = v;
      else if (k.slice(0, 2) === 'on') el.addEventListener(k.slice(2), v);
      else if (k === 'value') el.value = v;
      else if (k === 'checked' || k === 'disabled' || k === 'selected') el[k] = !!v;
      else el.setAttribute(k, v === true ? '' : v);
    });
    for (var i = 2; i < arguments.length; i++) add(el, arguments[i]);
    return el;
  }
  function add(el, c) {
    if (c == null || c === false) return;
    if (Array.isArray(c)) c.forEach(function (x) { add(el, x); });
    else el.appendChild(c.nodeType ? c : document.createTextNode(String(c)));
  }
  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }
  var toastT;
  function toast(msg, bad) {
    var t = document.getElementById('toast');
    t.textContent = msg; t.className = 'on' + (bad ? ' bad' : '');
    clearTimeout(toastT); toastT = setTimeout(function () { t.className = ''; }, 3200);
  }
  function api(path, method, body) {
    var opt = { method: method || 'GET', headers: { 'X-Requested-With': 'sap-admin' }, credentials: 'same-origin' };
    if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    return fetch('/admin/api' + path, opt).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (r.status === 401 && path !== '/login') { state.user = null; render(); throw new Error('Please sign in'); }
        if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : (j.detail && j.detail[0] && j.detail[0].msg) || 'Something went wrong');
        return j;
      });
    });
  }
  function fail(e) { toast(e.message || 'Something went wrong', true); }
  function img(src) { return src ? '/' + src.replace(/^\//, '') : ''; }
  function toggle(label, checked, onchange) {
    var i = h('input', { type: 'checkbox', checked: checked });
    if (onchange) i.addEventListener('change', function () { onchange(i.checked); });
    var l = h('label', { class: 'toggle' }, i, label);
    l.input = i; return l;
  }
  function logoBlock() {
    return h('div', { class: 'logoblock' }, h('img', { src: '/assets/sap-logo.svg', alt: 'SAP Hardware' }), h('span', null, 'Architectural & Furniture Fittings'));
  }
  function field(label, input, hint) { return h('label', { class: 'f' }, label, input, hint ? h('span', { class: 'hint' }, hint) : null); }
  function confirmBox(msg) { return window.confirm(msg); }

  /* ---------- drawer ---------- */
  function drawer(title, body, onSave, saveLabel, opts) {
    opts = opts || {};
    var scrim = h('div', { class: 'scrim' });
    var save = h('button', { class: 'btn green' }, saveLabel || 'Save');
    var close = function () { scrim.remove(); box.remove(); document.removeEventListener('keydown', esc); if (opts.onClose) opts.onClose(); };
    var esc = function (e) { if (e.key === 'Escape' && box.parentNode && document.querySelectorAll('.drawer').length && box === document.querySelectorAll('.drawer')[document.querySelectorAll('.drawer').length - 1]) close(); };
    var box = h('aside', { class: 'drawer' + (opts.wide ? ' wide' : ''), role: 'dialog', 'aria-label': title },
      h('header', null, h('h2', null, title), h('button', { class: 'btn ghost icon', onclick: close, 'aria-label': 'Close' }, '\u2715')),
      h('div', { class: 'body' }, body),
      h('footer', null, opts.noCancel ? null : h('button', { class: 'btn ghost', onclick: close }, 'Cancel'), save));
    save.addEventListener('click', function () {
      save.disabled = true;
      Promise.resolve(onSave()).then(function () { close(); }, function (e) { save.disabled = false; fail(e); });
    });
    scrim.addEventListener('click', close);
    document.addEventListener('keydown', esc);
    document.body.appendChild(scrim); document.body.appendChild(box);
    var first = box.querySelector('input[type=text],textarea'); if (first) first.focus();
  }

  /* ---------- image picker ---------- */
  function uploadFile(file) {
    var fd = new FormData(); fd.append('file', file);
    return fetch('/admin/api/upload', { method: 'POST', body: fd, headers: { 'X-Requested-With': 'sap-admin' }, credentials: 'same-origin' })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || 'Upload failed'); return j.path; }); });
  }
  function imagePicker(initial, label, hint) {
    var val = initial || '';
    var pv = h('div', { class: 'pv' });
    var paint = function () { pv.style.backgroundImage = val ? 'url("' + img(val) + '")' : ''; pv.textContent = val ? '' : 'No image'; };
    var file = h('input', { type: 'file', accept: 'image/*', style: 'display:none' });
    var btn = h('button', { class: 'btn ghost sm', type: 'button', onclick: function () { file.click(); } }, 'Upload image');
    var rm = h('button', { class: 'btn ghost sm', type: 'button', onclick: function () { val = ''; paint(); } }, 'Remove');
    file.addEventListener('change', function () {
      if (!file.files[0]) return;
      btn.disabled = true; btn.textContent = 'Uploading…';
      uploadFile(file.files[0]).then(function (p) { val = p; paint(); }, fail).then(function () { btn.disabled = false; btn.textContent = 'Upload image'; file.value = ''; });
    });
    paint();
    var el = field(label, h('div', { class: 'img' }, pv, h('div', { class: 'stack', style: 'gap:8px' }, h('div', { class: 'row' }, btn, rm), file)), hint);
    el.get = function () { return val; };
    return el;
  }
  function galleryPicker(initial) {
    var vals = (initial || []).slice();
    var wrap = h('div', { class: 'gal' });
    var file = h('input', { type: 'file', accept: 'image/*', multiple: true, style: 'display:none' });
    var addBtn = h('button', { class: 'btn ghost sm', type: 'button', onclick: function () { file.click(); } }, '+ Add images');
    var paint = function () {
      clear(wrap);
      vals.forEach(function (v, i) {
        var g = h('div', { class: 'g', style: 'background-image:url("' + img(v) + '")' },
          h('button', { type: 'button', 'aria-label': 'Remove', onclick: function () { vals.splice(i, 1); paint(); } }, '×'));
        wrap.appendChild(g);
      });
    };
    file.addEventListener('change', function () {
      var files = Array.prototype.slice.call(file.files); if (!files.length) return;
      addBtn.disabled = true; addBtn.textContent = 'Uploading…';
      files.reduce(function (p, f) { return p.then(function () { return uploadFile(f).then(function (path) { vals.push(path); paint(); }); }); }, Promise.resolve())
        .catch(fail).then(function () { addBtn.disabled = false; addBtn.textContent = '+ Add images'; file.value = ''; });
    });
    paint();
    var el = field('More photos (optional)', h('div', { class: 'stack', style: 'gap:10px' }, wrap, h('div', null, addBtn, file)),
      'Shown as extra thumbnails on the product page. Leave empty to use the standard layout.');
    el.get = function () { return vals.slice(); };
    return el;
  }

  /* ---------- shell ---------- */
  var NAV = [['dashboard', 'Overview'], ['categories', 'Categories'], ['products', 'Products'], ['home', 'Home page'], ['downloads', 'Downloads'],
    ['enquiries', 'Enquiries'], ['contact', 'Contact details'], ['pages', 'About & legal'], ['settings', 'Settings']];

  function render() {
    clear(app);
    if (!state.user) return renderLogin();
    var main = h('main', { class: 'main' });
    var side = h('nav', { class: 'side' },
      logoBlock(),
      NAV.map(function (n) {
        var a = h('a', { class: 'nav' + (state.view === n[0] ? ' on' : ''), href: '#' + n[0], onclick: function (e) { e.preventDefault(); go(n[0]); } }, n[1]);
        if (n[0] === 'enquiries' && state.newEnq) a.appendChild(h('span', { class: 'count' }, String(state.newEnq)));
        return a;
      }),
      h('div', { class: 'foot' }, state.user.email,
        h('a', { href: '/', target: '_blank', rel: 'noopener' }, 'View website ↗'),
        h('a', { href: '#', onclick: function (e) { e.preventDefault(); api('/logout', 'POST').then(function () { state.user = null; render(); }); } }, 'Sign out')));
    app.appendChild(h('div', { class: 'shell' }, side, main));
    state.main = main;
    var v = views[state.view] || views.dashboard;
    v(main);
  }
  function go(view) { state.view = view; location.hash = view; render(); window.scrollTo(0, 0); }
  function refreshBadge() {
    api('/summary').then(function (s) {
      state.newEnq = s.enquiries_new;
      var a = Array.prototype.find.call(document.querySelectorAll('.side a.nav'), function (x) { return x.textContent.indexOf('Enquiries') === 0; });
      if (!a) return;
      var c = a.querySelector('.count'); if (c) c.remove();
      if (s.enquiries_new) a.appendChild(h('span', { class: 'count' }, String(s.enquiries_new)));
    }).catch(function () {});
  }
  function header(title, sub, actions) {
    return h('div', { class: 'head' }, h('div', null, h('h1', null, title), sub ? h('p', null, sub) : null), h('div', { class: 'row' }, actions));
  }

  function renderLogin() {
    var email = h('input', { type: 'email', required: true, autocomplete: 'username', placeholder: 'you@company.com' });
    var pw = h('input', { type: 'password', required: true, autocomplete: 'current-password' });
    var err = h('div', { class: 'small', style: 'color:var(--red);min-height:18px' });
    var form = h('form', { onsubmit: function (e) {
      e.preventDefault(); err.textContent = '';
      api('/login', 'POST', { email: email.value, password: pw.value }).then(function (u) { state.user = u; render(); refreshBadge(); },
        function (er) { err.textContent = er.message; });
    } },
      logoBlock(),
      h('div', null, h('h1', null, 'Admin sign in'), h('p', { class: 'muted', style: 'margin:8px 0 0' }, 'Manage categories, products and the home page.')),
      field('Email', email), field('Password', pw), err, h('button', { class: 'btn green', type: 'submit', style: 'align-self:flex-start' }, 'Sign in'));
    app.appendChild(h('div', { class: 'login' }, form));
    email.focus();
  }

  /* ---------- data loaders ---------- */
  function load() {
    return Promise.all([api('/collections'), api('/catalogues'), api('/finishes'), api('/products')]).then(function (r) {
      state.cols = r[0]; state.cats = r[1]; state.fins = r[2]; state.prods = r[3];
    });
  }
  function reload(fn) { return load().then(function () { if (fn) fn(); }).catch(fail); }
  function colName(id) { var c = (state.cols || []).find(function (x) { return x.id === id; }); return c ? c.name : id; }

  var views = {};

  /* ---------- dashboard ---------- */
  views.dashboard = function (main) {
    main.appendChild(header('Overview', 'Everything the client needs to keep the website up to date.'));
    var box = h('div'); main.appendChild(box);
    api('/summary').then(function (s) {
      state.newEnq = s.enquiries_new;
      api('/settings/email').then(function (e) {
        if (e.host || e.from_env) return;
        box.insertBefore(h('div', { class: 'card', style: 'margin-bottom:14px;background:#F5E3A8' }, h('h2', null, 'Enquiry emails are not set up yet'),
          h('p', { class: 'small', style: 'margin:8px 0 14px' }, 'Enquiries are saved here, but the team will not get an email until you add the mail settings.'),
          h('a', { class: 'btn sm', href: '#settings', onclick: function (ev) { ev.preventDefault(); go('settings'); } }, 'Set up email')), box.firstChild);
      }).catch(function () {});
      box.appendChild(h('div', { class: 'cards' },
        stat(s.products_live, 'Products live', s.products + ' in total'),
        stat(s.collections_live, 'Categories live', s.collections + ' in total'),
        stat(s.enquiries_new, 'New enquiries', s.enquiries_total + ' received')));
      var tip = function (t, d, v) { return h('div', { class: 'card' }, h('h2', null, t), h('p', { class: 'muted small', style: 'margin:8px 0 14px' }, d), h('a', { class: 'btn ghost sm', href: '#' + v, onclick: function (e) { e.preventDefault(); go(v); } }, 'Open')); };
      box.appendChild(h('div', { class: 'cards' },
        tip('Add or edit a product', 'Name, photos, finishes, category and catalogue pages.', 'products'),
        tip('Change the home page', 'Hero slides and the products featured on the home page.', 'home'),
        tip('Reorder categories', 'Control which categories show and in what order.', 'categories')));
      refreshBadge();
    }).catch(fail);
    function stat(n, label, sub) { return h('div', { class: 'card stat' }, h('b', null, String(n)), h('div', null, label), h('span', null, sub)); }
  };

  /* ---------- categories ---------- */
  views.categories = function (main) {
    var list = h('div', { class: 'list' });
    main.appendChild(header('Categories', 'These appear as “Collections” on the website, in this order.',
      h('button', { class: 'btn green', onclick: function () { editCategory(); } }, '+ New category')));
    main.appendChild(list);
    function paint() {
      clear(list);
      if (!state.cols.length) list.appendChild(h('div', { class: 'empty' }, 'No categories yet.'));
      state.cols.forEach(function (c, i) {
        var move = function (d) {
          var ids = state.cols.map(function (x) { return x.id; }); var j = i + d; if (j < 0 || j >= ids.length) return;
          var t = ids[i]; ids[i] = ids[j]; ids[j] = t;
          api('/collections/reorder', 'POST', { ids: ids }).then(function () { return reload(paint); }).catch(fail);
        };
        list.appendChild(h('div', { class: 'item' + (c.active ? '' : ' off') },
          h('div', { class: 'thumb', style: 'background:var(--line) center/cover' + (c.scene ? ';background-image:url("' + img(c.scene) + '")' : '') }),
          h('div', { style: 'min-width:0' },
            h('div', { class: 't' }, c.name, c.active ? null : h('span', { class: 'pill o' }, 'Hidden')),
            h('div', { class: 's' }, c.product_count + ' product' + (c.product_count === 1 ? '' : 's') + (c.blurb ? ' · ' + c.blurb : ''))),
          h('div', { class: 'acts' },
            h('button', { class: 'btn ghost sm icon', title: 'Move up', disabled: i === 0, onclick: function () { move(-1); } }, '↑'),
            h('button', { class: 'btn ghost sm icon', title: 'Move down', disabled: i === state.cols.length - 1, onclick: function () { move(1); } }, '↓'),
            h('button', { class: 'btn ghost sm', onclick: function () { editCategory(c); } }, 'Edit'),
            h('button', { class: 'btn danger sm', onclick: function () {
              if (!confirmBox('Delete the category “' + c.name + '”?')) return;
              api('/collections/' + encodeURIComponent(c.id), 'DELETE').then(function () { toast('Category deleted'); return reload(paint); }).catch(fail);
            } }, 'Delete'))));
      });
    }
    function editCategory(c) {
      var isNew = !c; c = c || { name: '', blurb: '', q: '', mats: [], scene: '', active: true };
      var name = h('input', { type: 'text', value: c.name, maxlength: 80 });
      var blurb = h('textarea', { maxlength: 300 }, c.blurb);
      var q = h('input', { type: 'text', value: c.q, maxlength: 200, placeholder: 'e.g. polished stainless steel glass fitting' });
      var mats = h('input', { type: 'text', value: (c.mats || []).join(', '), placeholder: 'Aluminium, Steel' });
      var pic = imagePicker(c.scene, 'Category image', 'Shown when hovering the category on the home page. Wide photos (3:2) work best.');
      var vis = toggle('Visible on the website', c.active);
      drawer(isNew ? 'New category' : 'Edit category', [
        field('Name', name), field('Short description', blurb, 'One sentence shown under the category name.'),
        field('Search descriptor (optional)', q, 'Used behind the scenes for search descriptions.'),
        field('Typical materials', mats, 'Comma separated. Used as the default for new products.'), pic, vis
      ], function () {
        var body = { name: name.value, blurb: blurb.value, q: q.value, scene: pic.get(), active: vis.input.checked,
          mats: mats.value.split(',').map(function (s) { return s.trim(); }).filter(Boolean) };
        return api('/collections' + (isNew ? '' : '/' + encodeURIComponent(c.id)), isNew ? 'POST' : 'PUT', body)
          .then(function () { toast('Saved'); return reload(paint); });
      });
    }
    load().then(paint).catch(fail);
  };

  /* ---------- products ---------- */
  views.products = function (main) {
    var f = state.pf = state.pf || { q: '', cat: '', col: '', show: '' };
    var list = h('div', { class: 'stack', style: 'gap:28px' });
    var q = h('input', { type: 'search', placeholder: 'Search by name or code…', value: f.q, oninput: function () { f.q = q.value; paint(); } });
    var catSel = h('select', { onchange: function () { f.cat = catSel.value; paint(); } });
    var colSel = h('select', { onchange: function () { f.col = colSel.value; paint(); } });
    var showSel = h('select', { onchange: function () { f.show = showSel.value; paint(); } },
      [['', 'All'], ['live', 'Visible'], ['hidden', 'Hidden'], ['new', 'Marked New'], ['featured', 'On home page'], ['empty', 'No components yet']].map(function (o) { return h('option', { value: o[0], selected: f.show === o[0] }, o[1]); }));
    main.appendChild(header('Products', 'Every product is a complete system, shown in the same order as the printed catalogue.',
      h('button', { class: 'btn green', onclick: function () { editProduct(); } }, '+ New product')));
    main.appendChild(h('div', { class: 'bar' }, q, catSel, colSel, showSel));
    main.appendChild(list);

    function fillSelects() {
      clear(catSel); catSel.appendChild(h('option', { value: '' }, 'Both catalogues'));
      state.cats.forEach(function (k) { catSel.appendChild(h('option', { value: k.key, selected: f.cat === k.key }, k.name)); });
      clear(colSel); colSel.appendChild(h('option', { value: '' }, 'All categories'));
      state.cols.forEach(function (c) { colSel.appendChild(h('option', { value: c.id, selected: f.col === c.id }, c.name)); });
    }
    function paint() {
      clear(list);
      var qq = f.q.trim().toLowerCase();
      var canMove = !qq && !f.col && !f.show;
      var shown = 0;
      state.cats.forEach(function (k, ki) {
        if (f.cat && f.cat !== k.key) return;
        var all = state.prods.filter(function (p) { return p.catalogue_key === k.key; });
        var rows = all.filter(function (p) {
          if (f.col && p.collection_id !== f.col) return false;
          if (f.show === 'live' && !p.active) return false;
          if (f.show === 'hidden' && p.active) return false;
          if (f.show === 'new' && !p.is_new) return false;
          if (f.show === 'featured' && !p.featured) return false;
          if (f.show === 'empty' && p.component_count) return false;
          return !qq || (p.name + ' ' + p.code + ' ' + p.collection_name).toLowerCase().indexOf(qq) >= 0;
        });
        if (!rows.length) return;
        shown += rows.length;
        var box = h('div', { class: 'list' });
        rows.forEach(function (p, i) {
          var move = function (d) { api('/products/' + encodeURIComponent(p.id) + '/move', 'POST', { dir: d }).then(function () { return reload(paint); }).catch(fail); };
          box.appendChild(h('div', { class: 'item' + (p.active ? '' : ' off') },
            h('img', { class: 'thumb', src: img(p.image) || '/assets/placeholder.svg', alt: '', loading: 'lazy' }),
            h('div', { style: 'min-width:0' },
              h('div', { class: 't' }, h('span', { class: 'muted', style: 'font-weight:400;margin-right:8px;font-variant-numeric:tabular-nums' }, p.code), p.name,
                p.is_new ? h('span', { class: 'pill g' }, 'New') : null, p.featured ? h('span', { class: 'pill' }, 'Home') : null,
                p.active ? null : h('span', { class: 'pill o' }, 'Hidden')),
              h('div', { class: 's' }, p.collection_name + (p.pages ? ' · pp. ' + p.pages : '') + ' · ' + (p.component_count ? p.component_count + ' components' : 'no components yet'))),
            h('div', { class: 'acts' },
              h('button', { class: 'btn ghost sm', onclick: function () { openComponents(p); } }, 'What’s included (' + (p.component_count || 0) + ')'),
              canMove ? [h('button', { class: 'btn ghost sm icon', title: 'Move up', disabled: i === 0, onclick: function () { move(-1); } }, '↑'),
                h('button', { class: 'btn ghost sm icon', title: 'Move down', disabled: i === rows.length - 1, onclick: function () { move(1); } }, '↓')] : null,
              h('button', { class: 'btn ghost sm', onclick: function () { editProduct(p); } }, 'Edit'),
              h('button', { class: 'btn danger sm', onclick: function () {
                if (!confirmBox('Delete “' + p.name + '” and its ' + (p.component_count || 0) + ' components? This cannot be undone. (Tip: switch it to Hidden to keep it.)')) return;
                api('/products/' + encodeURIComponent(p.id), 'DELETE').then(function () { toast('Product deleted'); return reload(paint); }).catch(fail);
              } }, 'Delete'))));
        });
        list.appendChild(h('section', null,
          h('div', { class: 'grp' }, h('span', { class: 'muted small' }, 'Catalogue ' + String(ki + 1).padStart(2, '0')), h('h2', null, k.name),
            h('span', { class: 'muted small' }, all.length + ' series' + (k.pages_label ? ' · pp. ' + k.pages_label : ''))),
          box));
      });
      if (!shown) list.appendChild(h('div', { class: 'empty' }, 'No products match.'));
    }

    function openComponents(p) {
      var comps = [], filter = '';
      var body = h('div', { class: 'stack', style: 'gap:14px' });
      var listEl = h('div', { class: 'stack', style: 'gap:22px' });
      var search = h('input', { type: 'search', placeholder: 'Search components…', oninput: function () { filter = search.value.trim().toLowerCase(); paintC(); } });
      var bulkFile = h('input', { type: 'file', accept: 'image/*', multiple: true, style: 'display:none' });
      var bulkBtn = h('button', { class: 'btn ghost', type: 'button', onclick: function () { bulkFile.click(); } }, 'Add photos in bulk');
      bulkFile.addEventListener('change', function () {
        var files = Array.prototype.slice.call(bulkFile.files); if (!files.length) return;
        bulkBtn.disabled = true; bulkBtn.textContent = 'Uploading ' + files.length + '…';
        var section = comps.length ? comps[comps.length - 1].section : '';
        files.reduce(function (pr, file) {
          return pr.then(function () {
            return uploadFile(file).then(function (path) {
              var nm = file.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').trim();
              return api('/products/' + encodeURIComponent(p.id) + '/components', 'POST', { name: nm, section: section, image: path });
            });
          });
        }, Promise.resolve()).then(function () { toast(files.length + ' components added — rename them below'); return refreshC(); })
          .catch(fail).then(function () { bulkBtn.disabled = false; bulkBtn.textContent = 'Add photos in bulk'; bulkFile.value = ''; });
      });
      body.appendChild(h('div', { class: 'row' }, h('button', { class: 'btn green', onclick: function () { editComp(); } }, '+ Add component'), bulkBtn, bulkFile, search));
      body.appendChild(h('p', { class: 'muted small', style: 'margin:0' }, 'This is the “What’s included” list customers see on the product page. Components are grouped by section, in the order shown here.'));
      body.appendChild(listEl);

      function sections() { var s = []; comps.forEach(function (c) { if (s.indexOf(c.section) < 0) s.push(c.section); }); return s; }
      function paintC() {
        clear(listEl);
        if (!comps.length) { listEl.appendChild(h('div', { class: 'empty' }, 'No components yet. Add the parts that make up this system.')); return; }
        sections().forEach(function (sec) {
          var rows = comps.filter(function (c) { return c.section === sec && (!filter || (c.name + ' ' + c.code).toLowerCase().indexOf(filter) >= 0); });
          if (!rows.length) return;
          var inSec = comps.filter(function (c) { return c.section === sec; });
          var box = h('div', { class: 'list' });
          rows.forEach(function (c) {
            var idx = inSec.indexOf(c);
            var move = function (d) {
              var j = idx + d; if (j < 0 || j >= inSec.length) return;
              var a = comps.indexOf(inSec[idx]), b = comps.indexOf(inSec[j]); var t = comps[a]; comps[a] = comps[b]; comps[b] = t;
              api('/products/' + encodeURIComponent(p.id) + '/components/reorder', 'POST', { ids: comps.map(function (x) { return x.id; }) }).then(refreshC).catch(fail);
            };
            box.appendChild(h('div', { class: 'item comp' + (c.active ? '' : ' off') },
              h('div', { class: 'cthumb', style: c.image ? 'background-image:url("' + img(c.image) + '")' : '' }, c.image ? '' : 'No photo'),
              h('div', { style: 'min-width:0' }, h('div', { class: 't' }, c.name || h('span', { class: 'muted' }, 'Untitled'), c.active ? null : h('span', { class: 'pill o' }, 'Hidden')),
                h('div', { class: 's' }, [c.code, c.material].filter(Boolean).join(' · '))),
              h('div', { class: 'acts' },
                h('button', { class: 'btn ghost sm icon', disabled: idx === 0, onclick: function () { move(-1); } }, '↑'),
                h('button', { class: 'btn ghost sm icon', disabled: idx === inSec.length - 1, onclick: function () { move(1); } }, '↓'),
                h('button', { class: 'btn ghost sm', onclick: function () { editComp(c); } }, 'Edit'),
                h('button', { class: 'btn danger sm', onclick: function () {
                  if (!confirmBox('Remove “' + (c.name || c.code || 'this component') + '”?')) return;
                  api('/components/' + c.id, 'DELETE').then(refreshC).catch(fail);
                } }, 'Remove'))));
          });
          var rn = h('button', { class: 'btn ghost sm', onclick: function () {
            var nv = window.prompt('Rename this section', sec); if (nv === null || nv.trim() === sec) return;
            inSec.reduce(function (pr, c) { return pr.then(function () { return api('/components/' + c.id, 'PUT', compBody(c, { section: nv.trim() })); }); }, Promise.resolve()).then(refreshC).catch(fail);
          } }, 'Rename');
          listEl.appendChild(h('div', null, h('div', { class: 'grp' }, h('h2', { style: 'font-size:16px' }, sec || 'Ungrouped'), h('span', { class: 'row' }, h('span', { class: 'muted small' }, inSec.length + ' items'), rn)), box));
        });
      }
      function compBody(c, over) {
        var b = { section: c.section, code: c.code, name: c.name, material: c.material, image: c.image, num: c.num, active: c.active };
        Object.keys(over || {}).forEach(function (k) { b[k] = over[k]; }); return b;
      }
      function refreshC() { return api('/products/' + encodeURIComponent(p.id) + '/components').then(function (r) { comps = r; paintC(); }).catch(fail); }
      function editComp(c) {
        var isNew = !c;
        c = c || { section: comps.length ? comps[comps.length - 1].section : '', code: '', name: '', material: '', image: '', active: true };
        var name = h('input', { type: 'text', value: c.name, maxlength: 160, placeholder: 'e.g. Concealed floor spring' });
        var code = h('input', { type: 'text', value: c.code, maxlength: 40, placeholder: 'e.g. SSDF 5036' });
        var sec = h('input', { type: 'text', value: c.section, maxlength: 120, list: 'seclist', placeholder: 'e.g. Pivot & Floor Spring' });
        var dl = h('datalist', { id: 'seclist' }, sections().filter(Boolean).map(function (s) { return h('option', { value: s }); }));
        var mat = h('input', { type: 'text', value: c.material, maxlength: 80, placeholder: 'e.g. Aluminium (optional)' });
        var pic = imagePicker(c.image, 'Photo', 'Square or portrait photo on a plain background works best.');
        var vis = toggle('Visible on the website', c.active);
        drawer(isNew ? 'Add component' : 'Edit component', [field('Name', name), h('div', { class: 'grid2' }, field('Item code', code), field('Material', mat)),
          field('Section', sec, 'The group heading it appears under on the product page.'), dl, pic, vis], function () {
          var b = { section: sec.value, code: code.value, name: name.value, material: mat.value, image: pic.get(), num: c.num == null ? null : c.num, active: vis.input.checked };
          if (!b.name.trim() && !b.code.trim()) return Promise.reject(new Error('Add a name or an item code'));
          return api(isNew ? '/products/' + encodeURIComponent(p.id) + '/components' : '/components/' + c.id, isNew ? 'POST' : 'PUT', b).then(function () { toast('Saved'); return refreshC(); });
        });
      }
      drawer(p.name + ' — what’s included', body, function () { return Promise.resolve(); }, 'Done', { wide: true, noCancel: true, onClose: function () { reload(paint); } });
      refreshC();
    }

    function editProduct(p) {
      var isNew = !p;
      p = p || { name: '', collection_id: f.col || (state.cols[0] && state.cols[0].id) || '', catalogue_key: f.cat || (state.cats[0] && state.cats[0].key), code: '',
        pages: '', material: '', finishes: [], description: '', image: '', gallery: [], is_new: false, active: true, featured: false, subs: null };
      var name = h('input', { type: 'text', value: p.name, maxlength: 140 });
      var col = h('select', null, state.cols.map(function (c) { return h('option', { value: c.id, selected: c.id === p.collection_id }, c.name + (c.active ? '' : ' (hidden)')); }));
      var cat = h('select', null, state.cats.map(function (c) { return h('option', { value: c.key, selected: c.key === p.catalogue_key }, c.name); }));
      var code = h('input', { type: 'text', value: p.code, maxlength: 20, placeholder: isNew ? 'Automatic' : '' });
      var pages = h('input', { type: 'text', value: p.pages, maxlength: 40, placeholder: 'e.g. 07–22' });
      var matList = h('datalist', { id: 'matlist' });
      var allMats = {}; state.cols.forEach(function (c) { (c.mats || []).forEach(function (m) { allMats[m] = 1; }); });
      state.prods.forEach(function (x) { if (x.material) allMats[x.material] = 1; });
      Object.keys(allMats).forEach(function (m) { matList.appendChild(h('option', { value: m })); });
      var mat = h('input', { type: 'text', value: p.material, list: 'matlist', maxlength: 60 });
      var chosen = {}; (p.finishes || []).forEach(function (n) { chosen[n] = 1; });
      var sw = h('div', { class: 'sw' }, state.fins.map(function (fi) {
        var b = h('button', { type: 'button', class: chosen[fi.name] ? 'on' : '', onclick: function () { chosen[fi.name] = !chosen[fi.name]; b.className = chosen[fi.name] ? 'on' : ''; } }, h('i', { style: 'background:' + fi.color }), fi.name);
        return b;
      }));
      var desc = h('textarea', { maxlength: 1500, placeholder: 'A short overview of the system and what it is used for.' }, p.description);
      var seoT = h('input', { type: 'text', maxlength: 90, value: p.seo_title || '' }), seoD = h('textarea', { maxlength: 200, style: 'min-height:64px' }, p.seo_desc || '');
      var pic = imagePicker(p.image, 'Main photo', 'Shown on the product list and at the top of the product page.');
      var gal = galleryPicker(p.gallery);
      var subs = (p.subs || []).map(function (s) { return [s[0], s[1]]; });
      var subsBox = h('div', { class: 'stack', style: 'gap:8px' });
      var paintSubs = function () {
        clear(subsBox);
        subs.forEach(function (s, i) {
          subsBox.appendChild(h('div', { class: 'vrow' },
            h('input', { type: 'text', value: s[0], placeholder: 'Sub-system name', oninput: function (e) { s[0] = e.target.value; } }),
            h('input', { type: 'text', value: s[1], placeholder: 'Page', oninput: function (e) { s[1] = e.target.value; } }),
            h('button', { class: 'btn ghost sm icon', type: 'button', onclick: function () { subs.splice(i, 1); paintSubs(); } }, '×')));
        });
        subsBox.appendChild(h('div', null, h('button', { class: 'btn ghost sm', type: 'button', onclick: function () { subs.push(['', '']); paintSubs(); } }, '+ Add sub-system')));
      };
      paintSubs();
      var isNewTog = toggle('Show a “New” badge', p.is_new);
      var feat = toggle('Feature on the home page', p.featured);
      var vis = toggle('Visible on the website', p.active);
      col.addEventListener('change', function () {
        var c = state.cols.find(function (x) { return x.id === col.value; });
        if (c && !mat.value && c.mats && c.mats.length) mat.value = c.mats[0];
      });
      drawer(isNew ? 'New product' : 'Edit product', [
        field('Product name', name),
        h('div', { class: 'grid2' }, field('Category', col), field('Catalogue', cat)),
        h('div', { class: 'grid2' }, field('Series code', code, isNew ? 'Generated from the catalogue if left empty.' : null), field('Catalogue pages', pages)),
        field('Overview', desc), pic, gal,
        field('Sub-systems (optional)', subsBox, 'Named parts of the series with their catalogue page, e.g. “Synchro Sliding — 18”.'),
        h('div', { class: 'stack', style: 'gap:12px' }, isNewTog, feat, vis),
        h('details', null, h('summary', { class: 'muted small', style: 'cursor:pointer' }, 'Search & sharing (optional), material, finishes'),
          h('div', { class: 'stack', style: 'margin-top:14px' },
            field('Search title', seoT, 'What Google shows as the page title. Leave empty to use “Name — Category | SAP Hardware”.'),
            field('Search description', seoD, 'About 150 characters. Leave empty to use the overview above.'),
            field('Material', mat), matList, field('Finishes', sw)))
      ], function () {
        var body = { name: name.value, collection_id: col.value, catalogue_key: cat.value, code: code.value, pages: pages.value,
          material: mat.value, finishes: state.fins.map(function (x) { return x.name; }).filter(function (n) { return chosen[n]; }),
          description: desc.value, image: pic.get(), gallery: gal.get(), is_new: isNewTog.input.checked, active: vis.input.checked,
          subs: subs.filter(function (s) { return s[0].trim(); }), seo_title: seoT.value, seo_desc: seoD.value };
        if (!body.name.trim()) return Promise.reject(new Error('Please enter a product name'));
        return api('/products' + (isNew ? '' : '/' + encodeURIComponent(p.id)), isNew ? 'POST' : 'PUT', body).then(function (r) {
          var pid = isNew ? r.id : p.id, want = feat.input.checked;
          if (want === !!p.featured) return;
          return api('/featured').then(function (ids) {
            ids = ids.filter(function (x) { return x !== pid; });
            if (want) ids.push(pid);
            return api('/featured', 'PUT', { ids: ids });
          });
        }).then(function () { toast('Saved'); return reload(paint); });
      });
    }
    load().then(function () { fillSelects(); paint(); }).catch(fail);
  };

  /* ---------- home page ---------- */
  views.home = function (main) {
    main.appendChild(header('Home page', 'Control the hero slides, the featured products and the catalogue cards.'));
    var slidesBox = h('div', { class: 'list' }), featBox = h('div', { class: 'list' }), catBox = h('div', { class: 'list' });
    var featPick = h('select', { style: 'max-width:340px' });
    main.appendChild(h('div', { class: 'section', style: 'margin-top:0' },
      h('div', { class: 'row' }, h('h2', null, 'Hero slides'), h('button', { class: 'btn green sm', onclick: function () { editSlide(); } }, '+ New slide')),
      h('p', null, 'The large rotating banner at the top of the home page. Use wide photos (about 16:9). At least one slide must stay visible.'),
      slidesBox));
    main.appendChild(h('div', { class: 'section' },
      h('div', { class: 'row' }, h('h2', null, 'Featured products')),
      h('p', null, 'Shown in the “Featured” row on the home page, in this order (up to 8).'),
      featBox,
      h('div', { class: 'row', style: 'margin-top:12px' }, featPick, h('button', { class: 'btn ghost sm', onclick: addFeat }, 'Add to featured'))));
    main.appendChild(h('div', { class: 'section' },
      h('div', { class: 'row' }, h('h2', null, 'Catalogue cards')),
      h('p', null, 'The two catalogue cards near the bottom of the home page.'), catBox));

    var slides = [], feat = [];
    function paintSlides() {
      clear(slidesBox);
      slides.forEach(function (s, i) {
        var move = function (d) {
          var ids = slides.map(function (x) { return x.id; }), j = i + d; if (j < 0 || j >= ids.length) return;
          var t = ids[i]; ids[i] = ids[j]; ids[j] = t;
          api('/slides/reorder', 'POST', { ids: ids }).then(refresh).catch(fail);
        };
        slidesBox.appendChild(h('div', { class: 'item' + (s.active ? '' : ' off') },
          h('img', { class: 'thumb', src: img(s.image), alt: '', style: 'width:96px' }),
          h('div', { style: 'min-width:0' }, h('div', { class: 't' }, s.title, s.active ? null : h('span', { class: 'pill o' }, 'Hidden')),
            h('div', { class: 's' }, s.collection_id ? 'Links to ' + colName(s.collection_id) : 'Links to all products')),
          h('div', { class: 'acts' },
            h('button', { class: 'btn ghost sm icon', disabled: i === 0, onclick: function () { move(-1); } }, '↑'),
            h('button', { class: 'btn ghost sm icon', disabled: i === slides.length - 1, onclick: function () { move(1); } }, '↓'),
            h('button', { class: 'btn ghost sm', onclick: function () { editSlide(s); } }, 'Edit'),
            h('button', { class: 'btn danger sm', onclick: function () {
              if (!confirmBox('Delete this slide?')) return;
              api('/slides/' + s.id, 'DELETE').then(function () { toast('Slide deleted'); return refresh(); }).catch(fail);
            } }, 'Delete'))));
      });
    }
    function editSlide(s) {
      var isNew = !s; s = s || { title: '', image: '', collection_id: '', active: true };
      var title = h('input', { type: 'text', value: s.title, maxlength: 90, placeholder: 'Frameless, by design.' });
      var col = h('select', null, h('option', { value: '' }, 'All products'),
        state.cols.map(function (c) { return h('option', { value: c.id, selected: c.id === s.collection_id }, c.name); }));
      var pic = imagePicker(s.image, 'Slide photo', 'Wide photo, at least 1600px across.');
      var vis = toggle('Visible on the website', s.active);
      drawer(isNew ? 'New slide' : 'Edit slide', [field('Headline', title), field('Button links to', col, 'The “Explore” button opens this category.'), pic, vis], function () {
        var body = { title: title.value, image: pic.get(), collection_id: col.value || null, active: vis.input.checked };
        if (!body.title.trim()) return Promise.reject(new Error('Please enter a headline'));
        if (!body.image) return Promise.reject(new Error('Please upload a slide photo'));
        return api('/slides' + (isNew ? '' : '/' + s.id), isNew ? 'POST' : 'PUT', body).then(function () { toast('Saved'); return refresh(); });
      });
    }
    function paintFeat() {
      clear(featBox);
      if (!feat.length) featBox.appendChild(h('div', { class: 'empty' }, 'Nothing featured yet.'));
      feat.forEach(function (id, i) {
        var p = state.prods.find(function (x) { return x.id === id; }); if (!p) return;
        var save = function (ids) { api('/featured', 'PUT', { ids: ids }).then(function () { feat = ids; return load(); }).then(paintFeat).catch(fail); };
        featBox.appendChild(h('div', { class: 'item' },
          h('img', { class: 'thumb', src: img(p.image) || '/assets/placeholder.svg', alt: '' }),
          h('div', { style: 'min-width:0' }, h('div', { class: 't' }, p.name), h('div', { class: 's' }, p.code + ' · ' + p.collection_name)),
          h('div', { class: 'acts' },
            h('button', { class: 'btn ghost sm icon', disabled: i === 0, onclick: function () { var a = feat.slice(); a.splice(i - 1, 0, a.splice(i, 1)[0]); save(a); } }, '↑'),
            h('button', { class: 'btn ghost sm icon', disabled: i === feat.length - 1, onclick: function () { var a = feat.slice(); a.splice(i + 1, 0, a.splice(i, 1)[0]); save(a); } }, '↓'),
            h('button', { class: 'btn ghost sm', onclick: function () { save(feat.filter(function (x) { return x !== id; })); } }, 'Remove'))));
      });
      clear(featPick);
      featPick.appendChild(h('option', { value: '' }, 'Choose a product…'));
      state.prods.filter(function (p) { return feat.indexOf(p.id) < 0; }).forEach(function (p) { featPick.appendChild(h('option', { value: p.id }, p.code + ' — ' + p.name)); });
    }
    function addFeat() {
      if (!featPick.value) return;
      if (feat.length >= 8) return fail(new Error('Up to 8 featured products'));
      var ids = feat.concat([featPick.value]);
      api('/featured', 'PUT', { ids: ids }).then(function () { feat = ids; return load(); }).then(paintFeat).catch(fail);
    }
    function paintCats() {
      clear(catBox);
      state.cats.forEach(function (k, i) {
        var name = h('input', { type: 'text', value: k.name, maxlength: 100 });
        var pages = h('input', { type: 'text', value: k.pages_label, maxlength: 40, placeholder: '01–94' });
        catBox.appendChild(h('div', { class: 'card' },
          h('div', { class: 'small muted', style: 'margin-bottom:10px' }, 'Catalogue ' + String(i + 1).padStart(2, '0')),
          h('div', { class: 'grid2' }, field('Name', name), field('Page range', pages)),
          h('div', { style: 'margin-top:14px' }, h('button', { class: 'btn ghost sm', onclick: function () {
            api('/catalogues/' + k.key, 'PUT', { name: name.value, pages_label: pages.value }).then(function () { toast('Saved'); return load(); }).catch(fail);
          } }, 'Save'))));
      });
    }
    function refresh() {
      return Promise.all([load(), api('/slides'), api('/featured')]).then(function (r) { slides = r[1]; feat = r[2]; paintSlides(); paintFeat(); paintCats(); }).catch(fail);
    }
    refresh();
  };

  /* ---------- enquiries ---------- */
  views.enquiries = function (main) {
    main.appendChild(header('Enquiries', 'Messages sent through the website contact form.',
      h('a', { class: 'btn ghost', href: '/admin/api/enquiries.csv' }, 'Download CSV')));
    var box = h('div', { class: 'list' }); main.appendChild(box);
    var TOPIC = { product: 'Product enquiry', dist: 'Distributorship', visit: 'Display centre visit' };
    function paint(rows) {
      clear(box);
      if (!rows.length) box.appendChild(h('div', { class: 'empty' }, 'No enquiries yet. They will appear here as soon as someone submits the contact form.'));
      rows.forEach(function (r) {
        var d = new Date(r.created_at);
        box.appendChild(h('div', { class: 'card', style: r.status === 'done' ? 'opacity:.6' : '' },
          h('div', { class: 'row', style: 'justify-content:space-between;align-items:flex-start' },
            h('div', null, h('h2', null, r.name, r.status === 'new' ? h('span', { class: 'pill g' }, 'New') : null),
              h('div', { class: 'small muted', style: 'margin-top:4px' }, (TOPIC[r.topic] || r.topic) + ' · ' + d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })),
              r.product_name ? h('div', { style: 'margin-top:8px;font-weight:500' }, 'About: ', r.page_url ? h('a', { href: r.page_url, target: '_blank', rel: 'noopener' }, r.product_name) : r.product_name) : null),
            h('div', { class: 'row' },
              h('button', { class: 'btn ghost sm', onclick: function () {
                api('/enquiries/' + r.id, 'PUT', { status: r.status === 'new' ? 'done' : 'new' }).then(function () { refresh(); }).catch(fail);
              } }, r.status === 'new' ? 'Mark handled' : 'Reopen'),
              h('button', { class: 'btn danger sm', onclick: function () {
                if (confirmBox('Delete this enquiry?')) api('/enquiries/' + r.id, 'DELETE').then(function () { refresh(); }).catch(fail);
              } }, 'Delete'))),
          h('div', { class: 'row small', style: 'margin-top:12px;gap:18px' },
            h('a', { href: 'tel:' + r.phone.replace(/[^\d+]/g, '') }, r.phone),
            r.email ? h('a', { href: 'mailto:' + r.email }, r.email) : null, r.city ? h('span', null, r.city) : null,
            r.mail_status && r.mail_status !== 'sent' ? h('span', { class: 'muted', title: r.mail_status }, 'Email: ' + (r.mail_status.indexOf('failed') === 0 ? 'could not be sent' : 'not set up')) : null),
          r.message ? h('p', { style: 'margin:12px 0 0;white-space:pre-wrap' }, r.message) : null));
      });
    }
    function refresh() { api('/enquiries').then(function (rows) { state.newEnq = rows.filter(function (x) { return x.status === 'new'; }).length; paint(rows); refreshBadge(); }).catch(fail); }
    refresh();
  };

  /* ---------- contact details ---------- */
  views.contact = function (main) {
    main.appendChild(header('Contact details', 'Display centres and offices shown on the Contact and About pages.'));
    var cBox = h('div', { class: 'stack' }), oBox = h('div', { class: 'stack' });
    var centers = [], offices = [];
    main.appendChild(h('div', { class: 'section', style: 'margin-top:0' }, h('h2', null, 'Display centres'), h('p', { class: 'muted small', style: 'margin:6px 0 14px' }, 'Shown as numbered cards.'), cBox,
      h('div', { style: 'margin-top:12px' }, h('button', { class: 'btn ghost sm', onclick: function () { centers.push({ city: '', addr: '', phone: '', map: '' }); paintC(); } }, '+ Add display centre'))));
    main.appendChild(h('div', { class: 'section' }, h('h2', null, 'Offices'), h('p', { class: 'muted small', style: 'margin:6px 0 14px' }, 'Head office and branches on the Contact page.'), oBox,
      h('div', { style: 'margin-top:12px' }, h('button', { class: 'btn ghost sm', onclick: function () { offices.push({ tag: '', addr: '', phones: [], email: '', map: '' }); paintO(); } }, '+ Add office'))));
    main.appendChild(h('div', { style: 'margin-top:28px' }, h('button', { class: 'btn green', onclick: function () {
      api('/contact-info', 'PUT', { centers: centers.filter(function (c) { return c.city.trim(); }), offices: offices.filter(function (o) { return o.tag.trim(); }) })
        .then(function () { toast('Saved'); }).catch(fail);
    } }, 'Save contact details')));
    function bind(obj, key, input) { input.addEventListener('input', function () { obj[key] = input.value; }); return input; }
    function paintC() {
      clear(cBox);
      centers.forEach(function (c, i) {
        cBox.appendChild(h('div', { class: 'card stack', style: 'gap:12px' },
          h('div', { class: 'grid2' }, field('City', bind(c, 'city', h('input', { type: 'text', value: c.city }))), field('Phone', bind(c, 'phone', h('input', { type: 'text', value: c.phone })))),
          field('Address', bind(c, 'addr', h('input', { type: 'text', value: c.addr }))),
          field('Google Maps link (optional)', bind(c, 'map', h('input', { type: 'text', value: c.map || '', placeholder: 'https://maps.app.goo.gl/…' })), 'Open Google Maps, find the display centre, press Share → Copy link, and paste it here. The “Open in Maps” button will use it.'),
          h('div', null, h('button', { class: 'btn danger sm', onclick: function () { centers.splice(i, 1); paintC(); } }, 'Remove'))));
      });
    }
    function paintO() {
      clear(oBox);
      offices.forEach(function (o, i) {
        var phones = h('input', { type: 'text', value: (o.phones || []).join(', ') });
        phones.addEventListener('input', function () { o.phones = phones.value.split(',').map(function (s) { return s.trim(); }).filter(Boolean); });
        oBox.appendChild(h('div', { class: 'card stack', style: 'gap:12px' },
          h('div', { class: 'grid2' }, field('Label', bind(o, 'tag', h('input', { type: 'text', value: o.tag, placeholder: 'Head office · Bengaluru' }))), field('Email', bind(o, 'email', h('input', { type: 'text', value: o.email })))),
          field('Address', bind(o, 'addr', h('input', { type: 'text', value: o.addr }))),
          field('Phone numbers', phones, 'Separate with commas.'),
          field('Google Maps link (optional)', bind(o, 'map', h('input', { type: 'text', value: o.map || '', placeholder: 'https://maps.app.goo.gl/…' }))),
          h('div', null, h('button', { class: 'btn danger sm', onclick: function () { offices.splice(i, 1); paintO(); } }, 'Remove'))));
      });
    }
    api('/contact-info').then(function (r) { centers = r.centers; offices = r.offices; paintC(); paintO(); }).catch(fail);
  };

  /* ---------- settings ---------- */
  views.settings = function (main) {
    main.appendChild(header('Settings'));
    var cur = h('input', { type: 'password', autocomplete: 'current-password' }), nw = h('input', { type: 'password', autocomplete: 'new-password' });
    main.appendChild(h('div', { class: 'card stack', style: 'max-width:460px' }, h('h2', null, 'Change password'),
      field('Current password', cur), field('New password', nw, 'At least 8 characters.'),
      h('div', null, h('button', { class: 'btn green sm', onclick: function () {
        api('/password', 'POST', { current: cur.value, new: nw.value }).then(function () { toast('Password changed'); cur.value = nw.value = ''; }).catch(fail);
      } }, 'Update password'))));

    var finBox = h('div', { class: 'stack', style: 'gap:10px' }), fins = [];
    main.appendChild(h('div', { class: 'section' }, h('h2', null, 'Finish colours'),
      h('p', null, 'The finishes products can be offered in. Removing a finish also removes it from products using it.'),
      h('div', { class: 'card stack', style: 'max-width:560px' }, finBox,
        h('div', { class: 'row' },
          h('button', { class: 'btn ghost sm', onclick: function () { fins.push({ name: '', color: '#CBCBC7' }); paintF(); } }, '+ Add finish'),
          h('button', { class: 'btn green sm', onclick: function () {
            api('/finishes', 'PUT', fins.filter(function (f) { return f.name.trim(); })).then(function () { toast('Saved'); return load(); }).catch(fail);
          } }, 'Save finishes')))));
    function paintF() {
      clear(finBox);
      fins.forEach(function (f, i) {
        var n = h('input', { type: 'text', value: f.name, placeholder: 'Finish name' }), c = h('input', { type: 'color', value: f.color });
        n.addEventListener('input', function () { f.name = n.value; }); c.addEventListener('input', function () { f.color = c.value; });
        finBox.appendChild(h('div', { class: 'row', style: 'flex-wrap:nowrap' }, c, n, h('button', { class: 'btn ghost sm icon', onclick: function () { fins.splice(i, 1); paintF(); } }, '×')));
      });
    }
    api('/finishes').then(function (r) { fins = r.map(function (x) { return { name: x.name, color: x.color }; }); paintF(); }).catch(fail);

    /* --- enquiry emails --- */
    var emailBox = h('div', { class: 'card stack', style: 'max-width:620px' });
    main.appendChild(h('div', { class: 'section' }, h('h2', null, 'Enquiry emails'),
      h('p', null, 'When someone sends an enquiry, the SAP team gets an email with the product name and a link to its page. Every enquiry is also saved under Enquiries.'), emailBox));
    api('/settings/email').then(function (e) {
      var to = h('input', { type: 'text', value: (e.to || []).join(', '), placeholder: 'sales@yourcompany.com, owner@yourcompany.com' });
      var host = h('input', { type: 'text', value: e.host, placeholder: 'smtp.gmail.com' }), port = h('input', { type: 'text', value: e.port });
      var user = h('input', { type: 'text', value: e.user, placeholder: 'the sending email address', autocomplete: 'off' });
      var pass = h('input', { type: 'password', value: '', placeholder: e.has_password ? '•••••••• (saved; leave blank to keep)' : 'App password', autocomplete: 'new-password' });
      var from = h('input', { type: 'text', value: e.from_addr, placeholder: 'defaults to the sending address' });
      emailBox.appendChild(h('div', { class: 'stack' },
        e.from_env ? h('div', { class: 'small', style: 'color:var(--green)' }, 'Mail server settings are provided by the server configuration and take priority.') : null,
        field('Send enquiry emails to', to, 'Separate several addresses with commas.'),
        h('div', { class: 'grid2' }, field('Mail server (SMTP)', host), field('Port', port, '587 for most providers')),
        h('div', { class: 'grid2' }, field('Login (email address)', user), field('Password', pass, 'For Gmail, create an “App password” in your Google account security settings.')),
        field('Show as sender', from),
        h('div', { class: 'row' },
          h('button', { class: 'btn green sm', onclick: function () {
            api('/settings/email', 'PUT', { to: to.value.split(','), host: host.value, port: parseInt(port.value, 10) || 587, user: user.value, password: pass.value, from_addr: from.value, from_name: '' })
              .then(function () { toast('Saved'); pass.value = ''; }).catch(fail);
          } }, 'Save email settings'),
          h('button', { class: 'btn ghost sm', onclick: function () {
            api('/settings/email/test', 'POST').then(function (r) { toast('Test email sent to ' + r.sent_to.join(', ')); }).catch(fail);
          } }, 'Send a test email'))));
    }).catch(fail);

    /* --- google & search --- */
    var seoBox = h('div', { class: 'card stack', style: 'max-width:620px' });
    main.appendChild(h('div', { class: 'section' }, h('h2', null, 'Google & search'),
      h('p', null, 'Titles, descriptions, share previews and structured data are generated automatically for every page. These settings connect the site to Google tools.'), seoBox));
    api('/settings/site').then(function (s) {
      var desc = h('textarea', { maxlength: 400 }, s.description), ga = h('input', { type: 'text', value: s.ga4, placeholder: 'G-XXXXXXXXXX' });
      var gsc = h('input', { type: 'text', value: s.gsc_verification, placeholder: 'verification code' }), bing = h('input', { type: 'text', value: s.bing_verification, placeholder: 'verification code' });
      var url = h('input', { type: 'text', value: s.site_url, placeholder: 'https://www.yourdomain.com (leave empty to detect automatically)' });
      var pic = imagePicker(s.share_image, 'Default share picture (optional)', 'Used when a page is shared on WhatsApp or social media and has no picture of its own. Leave empty to use the generated one.');
      seoBox.appendChild(h('div', { class: 'stack' },
        field('Default site description', desc, 'Used on the home page and as the fallback everywhere else (about 150 characters is ideal).'),
        field('Website address', url, 'Set this once your real domain is connected.'),
        field('Google Analytics 4 ID', ga, 'Optional. Loads only for visitors who accept cookies.'),
        h('div', { class: 'grid2' }, field('Google Search Console code', gsc, 'Only the code from the “HTML tag” method'), field('Bing Webmaster code', bing)), pic,
        h('div', { class: 'row' }, h('button', { class: 'btn green sm', onclick: function () {
          api('/settings/site', 'PUT', { description: desc.value, share_image: pic.get(), ga4: ga.value, gsc_verification: gsc.value, bing_verification: bing.value, site_url: url.value })
            .then(function () { toast('Saved'); }).catch(fail);
        } }, 'Save'), h('a', { class: 'btn ghost sm', href: '/sitemap.xml', target: '_blank', rel: 'noopener' }, 'View sitemap'))));
    }).catch(fail);

  };

  /* ---------- downloads (PDF links + cover images) ---------- */
  views.downloads = function (main) {
    var list = h('div', { class: 'list' });
    main.appendChild(header('Downloads', 'Catalogues and brochures shown on the home page. Upload each PDF to Google Drive, then paste its link here, so the website stays fast.',
      h('button', { class: 'btn green', onclick: function () { edit(); } }, '+ Add a PDF')));
    main.appendChild(h('div', { class: 'card small', style: 'margin-bottom:18px;line-height:1.6' },
      h('b', null, 'How to add a PDF: '), '1) Upload the file to Google Drive. 2) Right-click it → Share → set “Anyone with the link” → Copy link. 3) Click “Add a PDF” here, paste the link and upload a cover picture.'));
    main.appendChild(list);
    var docs = [];
    function paint() {
      clear(list);
      if (!docs.length) list.appendChild(h('div', { class: 'empty' }, 'No downloads yet.'));
      docs.forEach(function (d, i) {
        var move = function (dir) {
          var ids = docs.map(function (x) { return x.id; }), j = i + dir; if (j < 0 || j >= ids.length) return;
          var t = ids[i]; ids[i] = ids[j]; ids[j] = t;
          api('/documents/reorder', 'POST', { ids: ids }).then(refresh).catch(fail);
        };
        var catName = (state.cats || []).filter(function (k) { return k.key === d.catalogue_key; }).map(function (k) { return k.name; })[0];
        list.appendChild(h('div', { class: 'item' + (d.active ? '' : ' off') },
          h('div', { class: 'thumb', style: 'background:var(--line) center/cover' + (d.cover ? ';background-image:url("' + img(d.cover) + '")' : '') }),
          h('div', { style: 'min-width:0' }, h('div', { class: 't' }, d.title, d.active ? null : h('span', { class: 'pill o' }, 'Hidden'), catName ? h('span', { class: 'pill' }, catName) : null),
            h('div', { class: 's' }, d.note || d.url)),
          h('div', { class: 'acts' },
            h('a', { class: 'btn ghost sm', href: d.url, target: '_blank', rel: 'noopener' }, 'Test link'),
            h('button', { class: 'btn ghost sm icon', disabled: i === 0, onclick: function () { move(-1); } }, '↑'),
            h('button', { class: 'btn ghost sm icon', disabled: i === docs.length - 1, onclick: function () { move(1); } }, '↓'),
            h('button', { class: 'btn ghost sm', onclick: function () { edit(d); } }, 'Edit'),
            h('button', { class: 'btn danger sm', onclick: function () {
              if (!confirmBox('Remove “' + d.title + '” from the website?')) return;
              api('/documents/' + d.id, 'DELETE').then(function () { toast('Removed'); return refresh(); }).catch(fail);
            } }, 'Remove'))));
      });
    }
    function edit(d) {
      var isNew = !d; d = d || { title: '', note: '', url: '', cover: '', catalogue_key: '', active: true };
      var title = h('input', { type: 'text', value: d.title, maxlength: 120, placeholder: 'e.g. Aluminium Profile Catalogue 2026' });
      var note = h('input', { type: 'text', value: d.note, maxlength: 200, placeholder: 'e.g. 94 pages · PDF' });
      var url = h('input', { type: 'text', value: d.url, placeholder: 'https://drive.google.com/file/d/…/view' });
      var pic = imagePicker(d.cover, 'Cover image', 'A picture of the first page works well (portrait, 4:5).');
      var cat = h('select', null, h('option', { value: '' }, 'Only in the Downloads section'),
        (state.cats || []).map(function (k) { return h('option', { value: k.key, selected: k.key === d.catalogue_key }, 'Also link from the “' + k.name + '” card'); }));
      var vis = toggle('Visible on the website', d.active);
      drawer(isNew ? 'Add a PDF' : 'Edit download', [field('Title', title), field('Short note (optional)', note), field('PDF link', url, 'A Google Drive share link works best. People can view it online or download it.'), pic,
        field('Where to show it', cat, 'The catalogue cards on the home page have a “Download PDF” button; choose one to connect it.'), vis], function () {
        var body = { title: title.value, note: note.value, url: url.value, cover: pic.get(), catalogue_key: cat.value, active: vis.input.checked };
        if (!body.title.trim()) return Promise.reject(new Error('Please add a title'));
        if (!/^https?:\/\//i.test(body.url.trim())) return Promise.reject(new Error('Paste the full link, starting with https://'));
        return api('/documents' + (isNew ? '' : '/' + d.id), isNew ? 'POST' : 'PUT', body).then(function () { toast('Saved'); return refresh(); });
      });
    }
    function refresh() { return Promise.all([api('/documents'), state.cats ? Promise.resolve() : load()]).then(function (r) { docs = r[0]; paint(); }).catch(fail); }
    refresh();
  };

  /* ---------- About founder + legal pages ---------- */
  views.pages = function (main) {
    main.appendChild(header('About & legal pages', 'Edit the founder story on the About page, and the Privacy, Cookie and Terms pages.'));
    var tabs = h('div', { class: 'bar' }), body = h('div'); main.appendChild(tabs); main.appendChild(body);
    var cur = state.pgTab || 'founder';
    [['founder', 'Founder (About page)'], ['privacy', 'Privacy Policy'], ['cookies', 'Cookie Policy'], ['terms', 'Terms of Use']].forEach(function (t) {
      tabs.appendChild(h('button', { class: 'btn ' + (cur === t[0] ? '' : 'ghost') + ' sm', onclick: function () { state.pgTab = t[0]; render(); } }, t[1]));
    });
    if (cur === 'founder') founderForm(); else legalForm(cur);

    function founderForm() {
      api('/settings/founder').then(function (f) {
        var name = h('input', { type: 'text', value: f.name }), role = h('input', { type: 'text', value: f.role });
        var headline = h('input', { type: 'text', value: f.headline }), intro = h('textarea', null, f.intro);
        var story = h('textarea', { style: 'min-height:260px' }, (f.story || []).join('\n\n'));
        var vision = h('textarea', null, f.vision);
        var pic = imagePicker(f.photo, 'Photo', 'Portrait photo (4:5) works best.');
        var ms = (f.milestones || []).map(function (m) { return { year: m.year, label: m.label }; }), vals = (f.values || []).map(function (v) { return { title: v.title, text: v.text }; });
        var msBox = h('div', { class: 'stack', style: 'gap:8px' }), vBox = h('div', { class: 'stack', style: 'gap:8px' });
        function paintMs() {
          clear(msBox);
          ms.forEach(function (m, i) {
            msBox.appendChild(h('div', { class: 'vrow', style: 'grid-template-columns:90px 1fr auto' },
              h('input', { type: 'text', value: m.year, placeholder: '2013', oninput: function (e) { m.year = e.target.value; } }),
              h('input', { type: 'text', value: m.label, placeholder: 'What happened', oninput: function (e) { m.label = e.target.value; } }),
              h('button', { class: 'btn ghost sm icon', type: 'button', onclick: function () { ms.splice(i, 1); paintMs(); } }, '×')));
          });
          msBox.appendChild(h('div', null, h('button', { class: 'btn ghost sm', type: 'button', onclick: function () { ms.push({ year: '', label: '' }); paintMs(); } }, '+ Add a milestone')));
        }
        function paintV() {
          clear(vBox);
          vals.forEach(function (v, i) {
            vBox.appendChild(h('div', { class: 'vrow', style: 'grid-template-columns:140px 1fr auto' },
              h('input', { type: 'text', value: v.title, placeholder: 'Honest', oninput: function (e) { v.title = e.target.value; } }),
              h('input', { type: 'text', value: v.text, placeholder: 'One short sentence', oninput: function (e) { v.text = e.target.value; } }),
              h('button', { class: 'btn ghost sm icon', type: 'button', onclick: function () { vals.splice(i, 1); paintV(); } }, '×')));
          });
          vBox.appendChild(h('div', null, h('button', { class: 'btn ghost sm', type: 'button', onclick: function () { vals.push({ title: '', text: '' }); paintV(); } }, '+ Add a value')));
        }
        paintMs(); paintV();
        body.appendChild(h('div', { class: 'card stack', style: 'max-width:760px' },
          h('div', { class: 'grid2' }, field('Name', name), field('Role', role)), pic, field('Headline', headline), field('Opening paragraph', intro),
          field('The story', story, 'Leave a blank line between paragraphs.'), field('Vision', vision),
          field('Milestones', msBox), field('Values', vBox),
          h('div', null, h('button', { class: 'btn green', onclick: function () {
            api('/settings/founder', 'PUT', { name: name.value, role: role.value, photo: pic.get(), headline: headline.value, intro: intro.value,
              story: story.value.split(/\n\s*\n/).map(function (s) { return s.trim(); }).filter(Boolean), vision: vision.value,
              values: vals.filter(function (v) { return v.title.trim(); }), milestones: ms.filter(function (m) { return m.label.trim(); }) })
              .then(function () { toast('Saved. The About page is updated.'); }).catch(fail);
          } }, 'Save founder page'), ' ', h('a', { class: 'btn ghost', href: '/about.html#founder', target: '_blank', rel: 'noopener' }, 'View page'))));
      }).catch(fail);
    }
    function legalForm(key) {
      api('/settings/legal').then(function (all) {
        var d = all[key];
        var title = h('input', { type: 'text', value: d.title }), upd = h('input', { type: 'text', value: d.updated, placeholder: '16 October 2026' });
        var text = h('textarea', { style: 'min-height:480px;font-family:ui-monospace,Menlo,monospace;font-size:13px;line-height:1.6' }, d.body);
        var slug = { privacy: 'privacy-policy', cookies: 'cookie-policy', terms: 'terms' }[key];
        body.appendChild(h('div', { class: 'card stack', style: 'max-width:820px' },
          h('p', { class: 'muted small', style: 'margin:0;line-height:1.6' }, 'Formatting: start a line with ',  h('b', null, '## '), 'for a heading, ', h('b', null, '- '), 'for a bullet point. Plain lines are paragraphs. These texts are a starting draft; please have them reviewed by your legal adviser.'),
          h('div', { class: 'grid2' }, field('Page title', title), field('Last updated', upd)), field('Text', text),
          h('div', null, h('button', { class: 'btn green', onclick: function () {
            all[key] = { title: title.value, updated: upd.value, body: text.value };
            api('/settings/legal', 'PUT', all).then(function () { toast('Saved'); }).catch(fail);
          } }, 'Save'), ' ', h('a', { class: 'btn ghost', href: '/' + slug, target: '_blank', rel: 'noopener' }, 'View page'))));
      }).catch(fail);
    }
  };

  /* ---------- boot ---------- */
  var start = (location.hash || '').slice(1);
  if (views[start]) state.view = start;
  window.addEventListener('hashchange', function () { var v = location.hash.slice(1); if (views[v] && v !== state.view && state.user) { state.view = v; render(); } });
  api('/me').then(function (u) { state.user = u; render(); refreshBadge(); }, function () { state.user = null; render(); });
})();
