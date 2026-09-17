(function () {
var i18n = JSON.parse(document.getElementById('book-ui').textContent);
// Learner workspace: synchronous, per-activity local records. No server account.
var study = (function () {
  'use strict';
  var prefix = 'cardano-booklet.study.v1:' + document.documentElement.lang + ':';
  var sequence = 0;
  var printing = false;
  window.addEventListener('beforeprint', function () { printing = true; });
  window.addEventListener('afterprint', function () { printing = false; });

  function fingerprint(text) {
    // Identity checksum, not a cryptographic proof. Full signatures are checked on read.
    var a = 2166136261, b = 5381;
    for (var i = 0; i < text.length; i += 1) {
      a = Math.imul(a ^ text.charCodeAt(i), 16777619);
      b = Math.imul(b, 33) ^ text.charCodeAt(i);
    }
    return (a >>> 0).toString(36) + '-' + (b >>> 0).toString(36);
  }

  function glyph(kind) {
    var paths = {
      copy: ['M9 9h11v11H9z', 'M15 5V3H3v12h2'],
      edit: ['M16 3a2.1 2.1 0 0 1 3 3L7 18l-4 1 1-4L16 3Z', 'm14.5 4.5 3 3'],
      reset: ['M3 10a9 9 0 1 1 2.7 8.1', 'M3 4v6h6'],
      run: ['m8 5 11 7-11 7V5Z'],
      stop: ['M6 6h12v12H6z'],
      close: ['m6 6 12 12', 'M6 18 18 6'],
      check: ['m5 12 4 4L19 6'],
      clear: ['M21 21H9a2 2 0 0 1-1.414-.586L2.586 15.414a2 2 0 0 1 0-2.828l10-10a2 2 0 0 1 2.828 0l6 6a2 2 0 0 1 0 2.828L12.828 21', 'm5 11 9 9'],
      sun: ['M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z', 'M12 2v2m0 16v2M2 12h2m16 0h2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42'],
      moon: ['M21 12.79A9 9 0 1 1 11.21 3a7 7 0 0 0 9.79 9.79Z'],
      alert: ['M12 4 2 21h20L12 4Z', 'M12 10v5', 'M12 18h.01']
    };
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('width', '20'); svg.setAttribute('height', '20');
    svg.setAttribute('fill', 'none'); svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.7');
    svg.setAttribute('stroke-linecap', 'round'); svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('focusable', 'false');
    paths[kind].forEach(function (d) {
      var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', d); svg.appendChild(path);
    });
    return svg;
  }

  function icon(el, kind, label) {
    el.replaceChildren(glyph(kind));
    el.classList.add('code-icon');
    el.dataset.icon = kind;
    el.setAttribute('aria-label', label);
    var tooltip = document.createElement('span');
    tooltip.className = 'code-tooltip';
    tooltip.setAttribute('aria-hidden', 'true');
    tooltip.textContent = label;
    el.appendChild(tooltip);
  }

  function button(text, className, action) {
    var el = document.createElement('button');
    el.type = 'button';
    el.className = className || 'study-button';
    el.textContent = text;
    var kind = { 'edit-code-btn': 'edit', 'reset-code-btn': 'reset', 'run-btn': 'run', 'stop-code-btn': 'stop', 'clear-output-btn': 'clear' };
    Object.keys(kind).forEach(function (name) { if (el.classList.contains(name)) icon(el, kind[name], text); });
    el.addEventListener('click', action);
    return el;
  }

  function signature(el) {
    var clone = el.cloneNode(true);
    [clone].concat(Array.from(clone.querySelectorAll('*'))).forEach(function (node) {
      ['id', 'name', 'data-answer', 'data-question', 'aria-labelledby', 'aria-describedby'].forEach(function (attr) {
        node.removeAttribute(attr);
      });
    });
    return clone.outerHTML;
  }

  function record(kind, owner, revision, valid) {
    var id = owner.getAttribute('data-progress-id') || owner.getAttribute('data-exercise-id') || fingerprint(revision);
    var key = prefix + kind + ':' + encodeURIComponent(id) + ':' + fingerprint(revision);
    var raw = null, current = null, conflict = false, broken = false, apply = function () {};
    var panel = document.createElement('div');
    panel.className = 'study-storage';
    var status = document.createElement('p');
    status.className = 'study-save-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    status.id = 'study-save-' + (++sequence);
    panel.appendChild(status);
    var choices = document.createElement('div');
    choices.className = 'study-conflict';
    choices.hidden = true;
    panel.appendChild(choices);

    function message(text, error) {
      status.textContent = error ? text : '';
      status.dataset.state = error ? 'warning' : '';
    }
    function decode(value) {
      if (value === null) return null;
      var entry = JSON.parse(value);
      if (!entry || entry.schema !== 1 || entry.revision !== revision || !valid(entry.data)) throw new Error('invalid-record');
      return entry.data;
    }
    function unavailable() {
      message(i18n.storeUnavailable, true);
    }
    function conflictMessage() {
      conflict = true;
      choices.hidden = false;
      message(broken
        ? i18n.storeCorrupt
        : i18n.storeConflict, true);
    }
    function save(data, force) {
      if (!valid(data)) { message(i18n.storeInvalid, true); return false; }
      current = data;
      try {
        var latest = localStorage.getItem(key);
        if (!force && (conflict || broken || latest !== raw)) { conflictMessage(); return false; }
        var next = JSON.stringify({ schema: 1, revision: revision, updatedAt: new Date().toISOString(), data: data });
        localStorage.setItem(key, next);
        if (localStorage.getItem(key) !== next) { conflictMessage(); return false; }
        raw = next;
        conflict = false; broken = false; choices.hidden = true;
        message('', false);
        return true;
      } catch (e) { unavailable(); return false; }
    }
    choices.appendChild(button(i18n.loadSaved, '', function () {
      try {
        var latest = localStorage.getItem(key);
        var data = decode(latest);
        raw = latest; current = data; conflict = false; broken = false; choices.hidden = true;
        apply(data);
        message('', false);
      } catch (e) { broken = true; conflictMessage(); }
    }));
    choices.appendChild(button(i18n.keepTab, '', function () {
      if (current !== null) save(current, true);
      else message(i18n.editBeforeReplace, true);
    }));
    try {
      raw = localStorage.getItem(key);
      current = decode(raw);
      if (current !== null) message('', false);
    } catch (e) {
      if (raw !== null) { broken = true; conflictMessage(); }
      else unavailable();
    }
    window.addEventListener('storage', function (event) {
      if (event.key !== key && event.key !== null) return;
      // Never replace focused input or a draft silently, even across tabs.
      conflictMessage();
    });
    return { key: key, panel: panel, status: status, load: function () { return current; }, save: save,
      onRestore: function (callback) { apply = callback; }, warn: function (text) { message(text, true); } };
  }

  function fields(form) { return Array.from(form.querySelectorAll('input:not([type="button"]):not([type="submit"]), select, textarea')); }
  function capture(form) {
    return fields(form).map(function (field) {
      return { value: field.value, checked: !!field.checked };
    });
  }
  function restore(form, values) {
    fields(form).forEach(function (field, i) {
      if (!values || !values[i]) { field.checked = false; if (field.type !== 'radio' && field.type !== 'checkbox') field.value = ''; return; }
      if (field.type === 'radio' || field.type === 'checkbox') field.checked = values[i].checked;
      else field.value = values[i].value;
    });
  }
  function formRecord(form) {
    var count = fields(form).length;
    return record('answers', form, signature(form), function (data) {
      return !!data && Array.isArray(data.fields) && data.fields.length === count &&
        typeof data.graded === 'boolean' && data.fields.every(function (field) {
          return field && typeof field.value === 'string' && field.value.length <= 10000 && typeof field.checked === 'boolean';
        });
    });
  }
  return { record: record, signature: signature, fingerprint: fingerprint, button: button, icon: icon, glyph: glyph,
    formRecord: formRecord, capture: capture, restore: restore, isPrinting: function () { return printing; } };
})();

function addEditingHighlight(input, numbers, language) {
  var surface = document.createElement('div');
  surface.className = 'code-editor-surface';
  var view = document.createElement('div');
  view.className = 'code-highlight';
  view.setAttribute('aria-hidden', 'true');
  var content = document.createElement('div');
  content.className = 'code-highlight-content';
  view.appendChild(content);
  input.parentNode.insertBefore(surface, input);
  surface.appendChild(view); surface.appendChild(input);
  var painted = null, paintedGrammar = null, composing = false;

  function syncScroll() {
    view.style.width = input.clientWidth + 'px';
    view.style.height = input.clientHeight + 'px';
    numbers.style.height = input.clientHeight + 'px';
    view.scrollTop = input.scrollTop; view.scrollLeft = input.scrollLeft;
    numbers.scrollTop = input.scrollTop;
  }
  function paint() {
    var prism = window.Prism, grammar = prism && prism.languages[language];
    if (composing || input.closest('.code-editor').hidden || !grammar) {
      surface.classList.remove('is-highlighted'); syncScroll(); return;
    }
    try {
      if (painted !== input.value || paintedGrammar !== grammar) {
        // Prism escapes the source. Never interpolate raw learner code into HTML.
        content.innerHTML = prism.highlight(input.value, grammar, language);
        // A final empty line must still occupy a line box, like the textarea caret.
        if (!input.value || input.value.endsWith('\n')) content.appendChild(document.createTextNode('\u200b'));
        painted = input.value; paintedGrammar = grammar;
      }
      surface.classList.add('is-highlighted');
    } catch (error) {
      surface.classList.remove('is-highlighted');
      painted = null; paintedGrammar = null;
    }
    syncScroll();
  }
  input.addEventListener('scroll', syncScroll);
  input.addEventListener('compositionstart', function () { composing = true; paint(); });
  input.addEventListener('compositionend', function () { composing = false; paint(); });
  if (window.ResizeObserver) new ResizeObserver(syncScroll).observe(input);
  else window.addEventListener('resize', syncScroll);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', paint, { once: true });
  return paint;
}

function addCodeEditor(pre, wrap, code) {
  if (!code) return;
  var original = code.textContent;
  var validatorId = pre.getAttribute('data-validator');
  var validatorNode = validatorId ? document.getElementById(validatorId) : null;
  var revisionParts = [original, pre.getAttribute('data-exercise-version') || '1', validatorId,
    validatorNode ? validatorNode.textContent : null];
  if (pre.hasAttribute('data-python-packages')) revisionParts.push(pre.getAttribute('data-python-packages'));
  var revision = JSON.stringify(revisionParts);
  var packageName = pre.getAttribute('data-python-package');
  if (packageName) revision = JSON.stringify([revision, packageName]);
  var state = { code: original, editing: false, result: null };
  var saved = study.record('code', pre, revision, function (data) {
    return !!data && typeof data.code === 'string' && data.code.length <= 100000 && typeof data.editing === 'boolean' &&
      (data.result === null || (data.result && typeof data.result.status === 'string' &&
        ['success', 'validated', 'mismatch', 'error', 'timeout', 'cancelled'].indexOf(data.result.status) !== -1 &&
        typeof data.result.output === 'string' && data.result.output.length <= 34000));
  });
  if (saved.load()) state = saved.load();
  var tools = document.createElement('div');
  tools.className = 'code-tools';
  var copy = wrap.querySelector('.copy-btn');
  if (copy) tools.appendChild(copy);
  wrap.insertBefore(tools, pre);
  var editor = document.createElement('div');
  editor.className = 'code-editor';
  editor.id = saved.status.id + '-editor';
  var grid = document.createElement('div');
  grid.className = 'code-editor-grid';
  var numbers = document.createElement('pre');
  numbers.className = 'code-line-numbers';
  numbers.setAttribute('aria-hidden', 'true');
  var input = document.createElement('textarea');
  input.className = 'code-input';
  input.setAttribute('aria-label', i18n.editorLabel);
  input.setAttribute('spellcheck', 'false');
  input.setAttribute('autocapitalize', 'off');
  input.setAttribute('autocomplete', 'off');
  input.setAttribute('autocorrect', 'off');
  input.setAttribute('wrap', 'off');
  input.maxLength = 100000;
  input.rows = Math.max(8, Math.min(24, original.split('\n').length));
  input.value = state.code;
  grid.appendChild(numbers); grid.appendChild(input); editor.appendChild(grid);
  var language = (code.className.match(/language-([\w-]+)/) || [null, ''])[1];
  var paintEditor = addEditingHighlight(input, numbers, language);
  input.setAttribute('aria-describedby', saved.status.id);
  wrap.appendChild(editor); wrap.appendChild(saved.panel);
  var onChange = function () {}, onRestore = function () {};
  var edit = study.button(i18n.editCode, 'study-button edit-code-btn', function () {
    state.editing = !state.editing;
    render(); save();
    if (state.editing) input.focus();
  });
  edit.setAttribute('aria-controls', editor.id);
  var reset = study.button(i18n.restoreOriginal, 'study-button reset-code-btn', function () {
    if (input.value === original || !window.confirm(i18n.confirmRestore)) return;
    input.value = original;
    changed();
  });
  tools.appendChild(edit); tools.appendChild(reset);

  function save() { saved.save({ code: input.value, editing: state.editing, result: state.result }); }
  function render() {
    pre.hidden = state.editing;
    editor.hidden = !state.editing;
    study.icon(edit, state.editing ? 'close' : 'edit', state.editing ? i18n.closeEditor : i18n.editCode);
    edit.setAttribute('aria-expanded', String(state.editing));
    code.textContent = input.value;
    if (!state.editing && window.Prism) window.Prism.highlightElement(code);
    numbers.textContent = input.value.split('\n').map(function (_, i) { return i + 1; }).join('\n');
    reset.disabled = input.value === original;
    paintEditor();
  }
  function changed() {
    state.code = input.value;
    state.result = null;
    render(); save(); onChange();
  }
  input.addEventListener('input', changed);
  input.addEventListener('keydown', function (event) {
    if (event.isComposing) return;
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      var run = wrap.querySelector('.run-btn');
      if (run && !run.disabled) { event.preventDefault(); run.click(); }
    }
  });
  saved.onRestore(function (data) {
    state = data || { code: original, editing: false, result: null };
    input.value = state.code;
    render(); onRestore(state.result);
  });
  render();
  pre._studyEditor = {
    value: function () { return input.value; }, tools: tools, storage: saved,
    result: function () { return state.result; },
    setResult: function (result) { state.result = result; save(); },
    onChange: function (callback) { onChange = callback; },
    onRestore: function (callback) { onRestore = callback; }
  };
}

  // alternador de tema
  var themeBtn = document.getElementById('theme-toggle');
  function syncThemeLabel() {
    var atual = document.documentElement.getAttribute('data-theme');
    study.icon(themeBtn, atual === 'dark' ? 'sun' : 'moon', atual === 'dark' ? i18n.lightTheme : i18n.darkTheme);
  }
  themeBtn.addEventListener('click', function () {
    var proximo = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', proximo);
    try { localStorage.setItem('book-theme', proximo); } catch (e) {}
    syncThemeLabel();
  });
  syncThemeLabel();

  // botões de copiar nos blocos de código
  document.querySelectorAll('pre').forEach(function (pre) {
    var code = pre.querySelector('code');
    var lang = '';
    if (code && code.className) {
      var m = code.className.match(/language-(\w+)/);
      if (m) lang = m[1];
    }
    var wrap = document.createElement('div');
    wrap.className = 'codewrap';
    wrap.setAttribute('data-lang', lang || 'code');
    pre.parentNode.insertBefore(wrap, pre);
    wrap.appendChild(pre);
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'copy-btn';
    study.icon(btn, 'copy', i18n.copy);
    var copyFeedback = document.createElement('span');
    copyFeedback.className = 'code-sr-only';
    copyFeedback.setAttribute('role', 'status');
    wrap.appendChild(copyFeedback);
    btn.addEventListener('click', function () {
      var texto = pre._studyEditor ? pre._studyEditor.value() : (code ? code.textContent : pre.textContent);
      function ok() {
        study.icon(btn, 'check', i18n.copied);
        copyFeedback.textContent = i18n.copied;
        setTimeout(function () { study.icon(btn, 'copy', i18n.copy); copyFeedback.textContent = ''; }, 1600);
      }
      function copiarComTextarea() {
        var ta = document.createElement('textarea');
        ta.value = texto;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        var copiado = false;
        try { copiado = document.execCommand('copy'); } catch (e) {}
        document.body.removeChild(ta);
        if (copiado) {
          ok();
        } else {
          study.icon(btn, 'alert', i18n.copyFailed);
          copyFeedback.textContent = i18n.copyFailed;
          setTimeout(function () { study.icon(btn, 'copy', i18n.copy); copyFeedback.textContent = ''; }, 2000);
        }
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(texto).then(ok).catch(copiarComTextarea);
      } else {
        copiarComTextarea();
      }
    });
    wrap.appendChild(btn);
    addCodeEditor(pre, wrap, code);
  });

  // atividades compactadas por padrão
  document.querySelectorAll('div.activity').forEach(function (activity) {
    var label = activity.querySelector(':scope > .box-label');
    if (!label) return;

    var details = document.createElement('details');
    Array.prototype.forEach.call(activity.attributes, function (attribute) {
      details.setAttribute(attribute.name, attribute.value);
    });

    var summary = document.createElement('summary');
    summary.className = 'box-label activity-summary';
    while (label.firstChild) summary.appendChild(label.firstChild);
    details.appendChild(summary);

    var content = document.createElement('div');
    content.className = 'activity-content';
    Array.prototype.slice.call(activity.childNodes).forEach(function (node) {
      if (node !== label) content.appendChild(node);
    });
    details.appendChild(content);
    activity.parentNode.replaceChild(details, activity);
    var activityRevision = JSON.stringify([
      summary.textContent,
      Array.from(content.querySelectorAll(':scope > p')).map(function (p) { return p.textContent; }),
      Array.from(content.querySelectorAll('form')).map(study.signature)
    ]);
    var activityRecord = study.record('activity', details, activityRevision, function (data) { return !!data && typeof data.open === 'boolean'; });
    content.appendChild(activityRecord.panel);
    if (activityRecord.load()) details.open = activityRecord.load().open;
    var lastOpen = details.open;
    activityRecord.onRestore(function (data) { details.open = !!(data && data.open); lastOpen = details.open; });
    details.addEventListener('toggle', function () {
      if (study.isPrinting() || details.open === lastOpen) return;
      lastOpen = details.open;
      activityRecord.save({ open: details.open });
    });
  });

  // respostas aparecem dentro da atividade depois que a pergunta é conferida
  function attachContextualAnswer(form) {
    var activity = form.closest('details.activity');
    if (!activity) return null;

    var answerId = form.getAttribute('data-answer');
    var source = answerId ? document.getElementById(answerId) : null;
    if (!source) source = activity.querySelector(':scope > .activity-content > details.answer');
    if (!source) return null;

    var response = document.createElement('div');
    response.className = 'quiz-response';
    response.hidden = true;
    response.setAttribute('role', 'region');
    response.setAttribute('aria-label', i18n.answer);

    var label = document.createElement('p');
    label.className = 'quiz-response-label';
    label.textContent = i18n.answer;
    response.appendChild(label);

    var body = source.querySelector(':scope > .answer-body');
    if (body) response.appendChild(body);
    source.parentNode.removeChild(source);
    if (answerId) response.id = answerId;

    var content = activity.querySelector(':scope > .activity-content');
    if (content) content.appendChild(response);
    return response;
  }

  // módulos recolhíveis na navegação lateral
  var toc = document.getElementById('toc');
  var tocToggle = document.getElementById('toc-toggle');
  var tocBackdrop = document.getElementById('toc-backdrop');
  var mobileTocQuery = window.matchMedia('(max-width: 1000px)');
  var navModules = [];
  if (toc) {
    Array.prototype.slice.call(toc.querySelectorAll(':scope > .nav-mod')).forEach(function (header) {
      var group = document.createElement('details');
      group.className = 'nav-module';
      var moduleLink = header.querySelector('.nav-mod-link');
      var moduleHref = moduleLink ? moduleLink.getAttribute('href') : null;
      if (moduleHref) group.setAttribute('data-module-target', moduleHref.slice(1));
      if (moduleLink) {
        var moduleLabel = document.createElement('span');
        moduleLabel.className = moduleLink.className;
        moduleLabel.innerHTML = moduleLink.innerHTML;
        moduleLink.parentNode.replaceChild(moduleLabel, moduleLink);
      }
      toc.insertBefore(group, header);

      var summary = document.createElement('summary');
      summary.className = 'nav-module-summary';
      summary.appendChild(header);
      group.appendChild(summary);

      var lessons = document.createElement('div');
      lessons.className = 'nav-module-lessons';
      if (moduleHref) {
        var overviewLink = document.createElement('a');
        overviewLink.className = 'nav-lesson nav-module-overview';
        overviewLink.href = moduleHref;
        overviewLink.textContent = i18n.moduleOverview;
        lessons.appendChild(overviewLink);
      }
      var next = group.nextSibling;
      while (next && !(next.nodeType === 1 && (next.classList.contains('nav-mod') || next.classList.contains('toc-language')))) {
        var following = next.nextSibling;
        lessons.appendChild(next);
        next = following;
      }
      group.appendChild(lessons);
      group.addEventListener('toggle', function () {
        if (!group.open || isMobileToc()) return;
        navModules.forEach(function (other) {
          if (other !== group) other.open = false;
        });
      });
      navModules.push(group);
    });
  }

  var languageSelector = document.getElementById('book-language');
  if (languageSelector) {
    languageSelector.addEventListener('change', function () {
      var option = languageSelector.selectedOptions[0];
      if (!option || option.disabled || !option.getAttribute('data-output')) {
        languageSelector.value = document.documentElement.lang;
        return;
      }
      if (option.value === document.documentElement.lang) return;
      var active = toc && toc.querySelector('a.active[href]');
      var anchor = (active ? active.getAttribute('href') : location.hash).slice(1);
      var anchors = (option.getAttribute('data-anchors') || '').split(' ');
      var destination = new URL(option.getAttribute('data-output'), location.href);
      destination.hash = anchors.indexOf(anchor) >= 0 ? anchor : 'sumario';
      location.assign(destination.href);
    });
    window.addEventListener('pageshow', function () {
      languageSelector.value = document.documentElement.lang;
    });
  }

  var horizontalScrollRegions = Array.prototype.slice.call(document.querySelectorAll('.table-scroll, .deck-scene-shell'));
  function updateHorizontalScrollFocus() {
    horizontalScrollRegions.forEach(function (region) {
      if (region.scrollWidth > region.clientWidth + 1) region.setAttribute('tabindex', '0');
      else region.removeAttribute('tabindex');
    });
  }
  updateHorizontalScrollFocus();
  window.addEventListener('resize', updateHorizontalScrollFocus);

  function isMobileToc() {
    return mobileTocQuery.matches;
  }

  function setTocOpen(open, restoreFocus) {
    if (!toc || !tocToggle || !tocBackdrop) return;
    open = !!open && isMobileToc();
    toc.classList.toggle('is-open', open);
    tocToggle.classList.toggle('is-open', open);
    tocBackdrop.classList.toggle('is-open', open);
    tocToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    tocToggle.setAttribute('aria-label', open ? i18n.closeContents : i18n.openContents);

    if (isMobileToc()) {
      toc.setAttribute('aria-hidden', open ? 'false' : 'true');
      toc.inert = !open;
    } else {
      toc.removeAttribute('aria-hidden');
      toc.inert = false;
    }

    if (!open && restoreFocus) {
      try { tocToggle.focus({ preventScroll: true }); } catch (e) { tocToggle.focus(); }
    }
  }

  function syncTocViewport() {
    if (isMobileToc()) {
      setTocOpen(toc.classList.contains('is-open'), false);
      return;
    }
    setTocOpen(false, false);
  }

  if (tocToggle && tocBackdrop) {
    tocToggle.addEventListener('click', function () {
      setTocOpen(!toc.classList.contains('is-open'), false);
    });
    tocBackdrop.addEventListener('click', function () { setTocOpen(false, true); });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && toc.classList.contains('is-open')) setTocOpen(false, true);
    });
  }

  function openNavModule(group) {
    if (isMobileToc()) return;
    navModules.forEach(function (candidate) {
      candidate.open = !!group && candidate === group;
    });
  }

  function syncNavModuleMode() {
    if (isMobileToc()) {
      navModules.forEach(function (group) { group.open = true; });
      return;
    }
    var activeLink = toc ? toc.querySelector('.nav-lesson.active') : null;
    if (!activeLink && toc && location.hash) {
      activeLink = Array.prototype.find.call(toc.querySelectorAll('a[href]'), function (link) {
        return link.getAttribute('href') === location.hash;
      });
    }
    openNavModule(activeLink ? activeLink.closest('.nav-module') : null);
  }

  function handleViewportChange() {
    syncNavModuleMode();
    syncTocViewport();
  }
  window.addEventListener('resize', handleViewportChange);
  handleViewportChange();

  // barra de progresso de leitura
  var readbar = document.getElementById('readbar');
  function onScroll() {
    var h = document.documentElement;
    var max = h.scrollHeight - h.clientHeight;
    readbar.style.width = (max > 0 ? (h.scrollTop / max) * 100 : 0) + '%';
    updateModuleBars();
  }

  // progresso por módulo na navegação lateral
  var moduleRanges = {};
  document.querySelectorAll('.module-divider[id^="modulo-"]').forEach(function (section) {
    var mod = section.id.slice('modulo-'.length);
    var parts = Array.prototype.slice.call(
      document.querySelectorAll('#modulo-' + mod + ', .lesson[data-module="' + mod + '"]')
    );
    if (parts.length) moduleRanges[mod] = parts;
  });
  function updateModuleBars() {
    var vp = window.innerHeight;
    Object.keys(moduleRanges).forEach(function (mod) {
      var parts = moduleRanges[mod];
      var first = parts[0].getBoundingClientRect();
      var last = parts[parts.length - 1].getBoundingClientRect();
      var top = first.top;
      var bottom = last.bottom;
      var total = bottom - top;
      var lido = Math.min(Math.max(vp * 0.35 - top, 0), total);
      var bar = document.getElementById('modbar-' + mod);
      if (bar) bar.style.width = (total > 0 ? (lido / total) * 100 : 0) + '%';
    });
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll);
  onScroll();

  // scroll spy da navegação
  var links = toc.querySelectorAll('a.nav-lesson, a.nav-top, a.nav-mod-link');
  var byId = {};
  links.forEach(function (link) {
    byId[link.getAttribute('href').slice(1)] = link;
  });
  var targets = [];
  Object.keys(byId).forEach(function (id) {
    var el = document.getElementById(id);
    if (el) targets.push(el);
  });
  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        links.forEach(function (l) { l.classList.remove('active'); });
        var link = byId[entry.target.id];
        if (link) {
          link.classList.add('active');
          openNavModule(link.closest('.nav-module'));
        }
      }
    });
  }, { rootMargin: '-8% 0px -82% 0px' });
  targets.forEach(function (t) { observer.observe(t); });

  links.forEach(function (link) {
    link.addEventListener('click', function (e) {
      e.preventDefault();
      openNavModule(link.closest('.nav-module'));
      var el = document.getElementById(link.getAttribute('href').slice(1));
      if (el) {
        if (isMobileToc()) setTocOpen(false, e.detail === 0);
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        history.replaceState(null, '', '#' + el.id);
      }
    });
  });

  // perguntas interativas com resposta contextual
  // tipos de pergunta (data-kind no fieldset): single (padrão, radio),
  // multi (checkbox, marque todas), classify (select por item), input (resposta curta)
  document.querySelectorAll('form.activity-quiz').forEach(function (quiz) {
    var quizRecord = study.formRecord(quiz);
    var questions = Array.prototype.slice.call(quiz.querySelectorAll('.quiz-question'));
    var bottomActions = quiz.querySelector('.quiz-actions');
    if (bottomActions && questions.length > 4 && questions[0]) {
      var topActions = bottomActions.cloneNode(true);
      topActions.classList.add('quiz-actions-top');
      var topStatus = topActions.querySelector('.quiz-status');
      if (topStatus) {
        topStatus.classList.add('quiz-status-mirror');
        topStatus.setAttribute('aria-hidden', 'true');
        topStatus.removeAttribute('aria-live');
        topStatus.removeAttribute('tabindex');
      }
      quiz.insertBefore(topActions, questions[0]);
    }
    var checkButtons = Array.prototype.slice.call(quiz.querySelectorAll('.quiz-check'));
    var statuses = Array.prototype.slice.call(quiz.querySelectorAll('.quiz-status'));
    var status = bottomActions ? bottomActions.querySelector('.quiz-status') : statuses[statuses.length - 1];
    var response = attachContextualAnswer(quiz);

    function kindOf(question) {
      return question.getAttribute('data-kind') || 'single';
    }

    function normalizeInput(value) {
      return value.trim().toLowerCase().replace(/,/g, '.').replace(/\s+/g, ' ');
    }

    function isAnswered(question) {
      var kind = kindOf(question);
      if (kind === 'classify') {
        return Array.prototype.every.call(
          question.querySelectorAll('select.quiz-select'),
          function (select) { return select.value !== ''; }
        );
      }
      if (kind === 'input') {
        return Array.prototype.every.call(
          question.querySelectorAll('input.quiz-input'),
          function (input) { return input.value.trim() !== ''; }
        );
      }
      return !!question.querySelector('input:checked');
    }

    function clearGrade() {
      quiz.classList.remove('is-graded');
      questions.forEach(function (question) {
        question.classList.remove('is-correct', 'is-incorrect');
        question.querySelectorAll('.quiz-option, .quiz-item').forEach(function (row) {
          row.classList.remove('is-correct', 'is-selected-wrong');
          var verdict = row.querySelector('.quiz-verdict');
          if (verdict) verdict.textContent = '';
          row.querySelectorAll('input, select').forEach(function (field) {
            field.removeAttribute('aria-invalid');
          });
        });
        var feedback = question.querySelector('.quiz-question-feedback');
        if (feedback) feedback.textContent = '';
      });
      checkButtons.forEach(function (button) { button.textContent = i18n.checkAnswers; });
      if (response) response.hidden = true;
    }

    function updateProgress() {
      var answered = questions.filter(isAnswered).length;
      checkButtons.forEach(function (button) {
        button.disabled = answered !== questions.length;
      });
      var progressLabel = questions.length === 1 ? i18n.answeredOne : i18n.answeredMany;
      statuses.forEach(function (label) {
        label.textContent = answered + i18n.of + questions.length + ' ' + progressLabel + '.';
      });
    }

    function gradeChoice(question, multi) {
      var correct = true;
      question.querySelectorAll('.quiz-option').forEach(function (option) {
        var input = option.querySelector('input');
        var verdict = option.querySelector('.quiz-verdict');
        var isKey = input.getAttribute('data-correct') === 'true';
        if (isKey && input.checked) {
          option.classList.add('is-correct');
          verdict.textContent = multi ? i18n.correctOption : i18n.correctAnswer;
        } else if (isKey && !input.checked) {
          option.classList.add('is-correct');
          verdict.textContent = multi ? i18n.missedOption : i18n.correctAnswer;
          correct = false;
        } else if (!isKey && input.checked) {
          option.classList.add('is-selected-wrong');
          verdict.textContent = multi ? i18n.extraOption : i18n.yourChoice;
          input.setAttribute('aria-invalid', 'true');
          correct = false;
        }
      });
      return correct;
    }

    function gradeClassify(question) {
      var correct = true;
      question.querySelectorAll('.quiz-item').forEach(function (item) {
        var select = item.querySelector('select.quiz-select');
        var verdict = item.querySelector('.quiz-verdict');
        var expected = select.getAttribute('data-correct');
        if (select.value === expected) {
          item.classList.add('is-correct');
          verdict.textContent = i18n.correct;
        } else {
          var option = select.querySelector('option[value="' + expected + '"]');
          item.classList.add('is-selected-wrong');
          verdict.textContent = i18n.expectedPrefix + (option ? option.textContent : expected);
          select.setAttribute('aria-invalid', 'true');
          correct = false;
        }
      });
      return correct;
    }

    function gradeInput(question) {
      var correct = true;
      question.querySelectorAll('.quiz-item').forEach(function (item) {
        var input = item.querySelector('input.quiz-input');
        var verdict = item.querySelector('.quiz-verdict');
        var accepted = input.getAttribute('data-accept').split('|').map(normalizeInput);
        if (accepted.indexOf(normalizeInput(input.value)) !== -1) {
          item.classList.add('is-correct');
          verdict.textContent = i18n.correct;
        } else {
          item.classList.add('is-selected-wrong');
          verdict.textContent = i18n.expectedPrefix + (input.getAttribute('data-display') || input.getAttribute('data-accept').split('|')[0]);
          input.setAttribute('aria-invalid', 'true');
          correct = false;
        }
      });
      return correct;
    }

    function refresh() {
      if (quiz.classList.contains('is-graded')) clearGrade();
      updateProgress();
      saveQuizState();
    }

    function saveQuizState() { quizRecord.save({ fields: study.capture(quiz), graded: quiz.classList.contains('is-graded') }); }

    quiz.addEventListener('change', refresh);
    quiz.addEventListener('input', refresh);

    function gradeQuiz(focus) {
      if (!questions.every(isAnswered)) return;
      clearGrade();
      var score = 0;
      questions.forEach(function (question) {
        var kind = kindOf(question);
        var isCorrect;
        if (kind === 'classify') isCorrect = gradeClassify(question);
        else if (kind === 'input') isCorrect = gradeInput(question);
        else isCorrect = gradeChoice(question, kind === 'multi');

        question.classList.add(isCorrect ? 'is-correct' : 'is-incorrect');
        if (isCorrect) score += 1;

        var feedback = question.querySelector('.quiz-question-feedback');
        if (feedback) {
          feedback.textContent = isCorrect
            ? i18n.correctFeedback
            : i18n.incorrectFeedback;
        }
      });

      quiz.classList.add('is-graded');
      checkButtons.forEach(function (button) { button.textContent = i18n.checkAgain; });
      var scoreLabel = questions.length === 1 ? i18n.correctOne : i18n.correctMany;
      statuses.forEach(function (label) {
        label.textContent = score + i18n.of + questions.length + ' ' + scoreLabel + i18n.answerBelowSuffix;
      });
      if (response) response.hidden = false;
      if (focus && status) status.focus();
    }
    quiz.addEventListener('submit', function (event) {
      event.preventDefault();
      gradeQuiz(true);
      saveQuizState();
    });
    function restoreQuiz(data) {
      clearGrade();
      study.restore(quiz, data ? data.fields : null);
      updateProgress();
      if (data && data.graded && questions.every(isAnswered)) gradeQuiz(false);
    }
    quiz.appendChild(quizRecord.panel);
    quizRecord.onRestore(restoreQuiz);
    restoreQuiz(quizRecord.load());
  });

  // perguntas conceituais vinculadas aos blocos executáveis:
  // travadas até a execução bem-sucedida do bloco associado
  var cqForms = {};
  document.querySelectorAll('form.code-question').forEach(function (form) {
    var questionRecord = study.formRecord(form);
    var pendingGrade = false;
    var options = Array.prototype.slice.call(form.querySelectorAll('input[type="radio"]'));
    var check = form.querySelector('.cq-check');
    var status = form.querySelector('.cq-status');
    var feedback = form.querySelector('.cq-feedback');
    var response = attachContextualAnswer(form);
    var unlocked = false;

    function clearGrade() {
      form.classList.remove('is-graded', 'is-correct', 'is-incorrect');
      options.forEach(function (input) {
        var row = input.closest('.cq-option');
        if (row) row.classList.remove('is-correct', 'is-selected-wrong');
        input.removeAttribute('aria-invalid');
      });
      feedback.textContent = '';
      if (response) response.hidden = true;
      if (check) check.textContent = i18n.checkAnswer;
    }

    form.classList.add('is-locked');
    options.forEach(function (input) { input.disabled = true; });
    if (check) check.disabled = true;
    status.textContent = i18n.runAboveToUnlock;

    form.addEventListener('change', function () {
      if (unlocked && check) check.disabled = false;
      if (form.classList.contains('is-graded')) clearGrade();
      pendingGrade = false;
      saveQuestionState();
    });

    function saveQuestionState() { questionRecord.save({ fields: study.capture(form), graded: form.classList.contains('is-graded') }); }
    function gradeCodeQuestion() {
      if (!unlocked) return;
      var chosen = null;
      options.forEach(function (input) { if (input.checked) chosen = input; });
      if (!chosen) {
        status.textContent = i18n.chooseFirst;
        return;
      }
      clearGrade();
      form.classList.add('is-graded');
      var row = chosen.closest('.cq-option');
      var acertou = chosen.getAttribute('data-correct') === 'true';
      if (acertou) {
        form.classList.add('is-correct');
        if (row) row.classList.add('is-correct');
      } else {
        form.classList.add('is-incorrect');
        if (row) row.classList.add('is-selected-wrong');
        chosen.setAttribute('aria-invalid', 'true');
      }
      feedback.textContent = chosen.getAttribute('data-feedback') || '';
      if (response) response.hidden = false;
      if (check) check.textContent = i18n.checkAgain;
      status.textContent = acertou
        ? i18n.answerCorrectInfo
        : i18n.answerIncorrectInfo;
    }
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      gradeCodeQuestion();
      saveQuestionState();
    });

    cqForms[form.id] = function (mode, preserveSavedGrade) {
      if (mode === 'lock') {
        unlocked = false;
        clearGrade();
        form.classList.add('is-locked');
        options.forEach(function (input) { input.disabled = true; });
        if (check) check.disabled = true;
        status.textContent = i18n.runCurrentToUnlock;
        status.removeAttribute('data-state');
        if (!preserveSavedGrade) { pendingGrade = false; saveQuestionState(); }
        return;
      }
      unlocked = true;
      form.classList.remove('is-locked');
      options.forEach(function (input) { input.disabled = false; });
      var algumaMarcada = false;
      options.forEach(function (input) { if (input.checked) algumaMarcada = true; });
      if (check) check.disabled = !algumaMarcada;
      if (mode === 'fallback') {
        status.textContent = i18n.runUnavailable;
        status.setAttribute('data-state', 'fallback');
      } else {
        status.textContent = i18n.questionUnlocked;
        status.setAttribute('data-state', 'unlocked');
      }
      if (pendingGrade) { gradeCodeQuestion(); pendingGrade = false; }
    };
    function restoreCodeQuestion(data) {
      clearGrade();
      study.restore(form, data ? data.fields : null);
      pendingGrade = !!(data && data.graded);
      if (unlocked && pendingGrade) { gradeCodeQuestion(); pendingGrade = false; }
    }
    form.appendChild(questionRecord.panel);
    questionRecord.onRestore(restoreCodeQuestion);
    restoreCodeQuestion(questionRecord.load());
  });

  function unlockCodeQuestion(id, mode) {
    if (id && cqForms[id]) cqForms[id](mode);
  }

  function unlockAllCodeQuestionsFallback() {
    Object.keys(cqForms).forEach(function (id) {
      var form = document.getElementById(id);
      if (form && form.classList.contains('is-locked')) cqForms[id]('fallback');
    });
  }

  // Fresh worker per run: user code and tests never block the document or leak globals to another run.
  var PY_CDN_BASE = 'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/';
  // Loading precedent: linconvidal/flask-pyodide-htmx-pycardano, adapted to fresh Workers.
  // Changing this pinned environment requires a new preset ID and exercise revision.
  var PY_CARDANO_PRESET = {
    id: 'pycardano-workshop-0.19.2-pyodide-314.0.7-v1',
    preload: ["micropip", "packaging", "pynacl", "frozenlist", "cryptography", "orjson", "pydantic"],
    requirements: [
      "annotated-types==0.7.0", "asn1crypto==1.5.1", "attrs==26.1.0",
      "base58==2.1.1", "blockfrost-python==0.7.0", "cachetools==7.1.4",
      "cardano-tools==2.1.0", "cbor2==5.9.0", "cbor2pure==5.8.0",
      "certifi==2026.5.20", "certvalidator==0.11.1", "cffi==2.0.0",
      "charset-normalizer==3.4.7", "coloredlogs==15.0.1", "cose==0.9.dev8",
      "cryptography==47.0.0", "docker==7.1.0", "ecdsa==0.19.2", "ecpy==1.2.5",
      "frozendict==2.4.7", "frozenlist==1.8.0", "humanfriendly==10.0",
      "idna==3.16", "micropip==0.11.1", "mnemonic==0.21", "ogmios==1.4.3",
      "orjson==3.11.8", "oscrypto==1.3.0", "packaging==26.1", "pexpect==4.9.0",
      "pprintpp==0.4.0", "ptyprocess==0.7.0", "pycardano==0.19.2", "pycparser==3.0",
      "pydantic==2.12.5", "pydantic-core==2.41.5", "pynacl==1.6.2", "pyparsing==3.3.2",
      "requests==2.34.2", "setuptools==82.0.1", "six==1.17.0", "typeguard==4.5.2",
      "typing-extensions==4.15.0", "typing-inspection==0.4.2", "urllib3==2.7.0",
      "websocket-client==1.9.0", "websockets==16.0"
    ]
  };
  var PY_RUN_TIMEOUT_MS = 10000;
  var PY_LOAD_TIMEOUT_MS = 60000;
  var pyActiveRun = null;
  var pyRunSeq = 0;

  async function pythonWorkerMain() {
    var py = null;
    function errorText(error) {
      return String(error && error.message ? error.message : error).split('\n').slice(-15).join('\n').slice(0, 5000);
    }
    self.onmessage = async function (event) {
      var msg = event.data;
      if (msg.type === 'init') {
        try {
          var module = await import(msg.base + 'pyodide.mjs');
          py = await module.loadPyodide({ indexURL: msg.base });
          if (msg.packages) {
            await py.loadPackage(msg.packages.preload);
            await py.runPythonAsync('import micropip\nawait micropip.install(' + JSON.stringify(msg.packages.requirements) + ')\nimport pycardano');
          }
          if (msg.packageName) {
            if (!/^[a-z0-9_-]+$/.test(msg.packageName)) throw new Error('Invalid Pyodide package name');
            await py.loadPackage(msg.packageName);
            if (!Object.prototype.hasOwnProperty.call(py.loadedPackages, msg.packageName)) throw new Error('Pyodide package was not loaded');
          }
          // This is a learning environment, not a security boundary for hostile code.
          self.fetch = undefined;
          self.XMLHttpRequest = undefined;
          self.postMessage({ type: 'ready' });
        } catch (error) { self.postMessage({ type: 'load-error', error: errorText(error) }); }
        return;
      }
      if (msg.type !== 'run' || !py) return;
      var budget = 30000, chunks = 0;
      function output(text) {
        if (budget <= 0 || chunks >= 200) return;
        text = String(text).slice(0, budget);
        budget -= text.length; chunks += 1;
        self.postMessage({ type: 'output', text: text });
        if (budget <= 0 || chunks === 200) self.postMessage({ type: 'output', text: msg.outputTruncated });
      }
      py.setStdout({ batched: output });
      py.setStderr({ batched: output });
      var dictionary = py.globals.get('dict');
      var namespace = dictionary();
      var value;
      try {
        value = await py.runPythonAsync(msg.code, { globals: namespace });
        if (value && typeof value.destroy === 'function') value.destroy();
        var checks = [];
        for (var test of msg.tests) {
          try {
            value = await py.runPythonAsync(test.code, { globals: namespace });
            if (value && typeof value.destroy === 'function') value.destroy();
            checks.push({ name: test.name, passed: true });
          } catch (error) { checks.push({ name: test.name, passed: false, error: errorText(error) }); }
        }
        self.postMessage({ type: 'done', checks: checks });
      } catch (error) { self.postMessage({ type: 'error', error: errorText(error) }); }
      finally { namespace.destroy(); dictionary.destroy(); }
    };
    self.postMessage({ type: 'boot' });
  }

  function validatorFor(pre) {
    var id = pre.getAttribute('data-validator');
    if (!id) return { tests: [], configured: false };
    try {
      var nodes = document.querySelectorAll('script[type="application/json"]');
      var matches = Array.from(nodes).filter(function (node) { return node.id === id; });
      if (matches.length !== 1) throw new Error('missing-validator');
      var config = JSON.parse(matches[0].textContent);
      if (!config || config.version !== 1 || !Array.isArray(config.tests) || !config.tests.length || config.tests.length > 50) throw new Error('invalid-tests');
      var names = new Set();
      config.tests.forEach(function (test) {
        if (!test || typeof test.name !== 'string' || !test.name.trim() || test.name.length > 200 || names.has(test.name) ||
            typeof test.code !== 'string' || !test.code.trim() || test.code.length > 20000) throw new Error('invalid-test');
        names.add(test.name);
      });
      return { tests: config.tests, configured: true };
    } catch (error) { return { tests: [], configured: true, error: i18n.validatorError }; }
  }

  function showPyStatus(ui, text, state) {
    ui.status.textContent = text;
    if (state === 'success' || state === 'validated') ui.status.prepend(study.glyph('check'));
    ui.status.dataset.state = state || '';
  }
  function appendPyOutput(ui, text) {
    var remaining = 33000 - ui.outPre.textContent.length;
    if (remaining <= 0) return;
    ui.outWrap.hidden = false;
    ui.outPre.textContent += ((ui.outPre.textContent ? '\n' : '') + String(text)).slice(0, remaining);
  }
  function pyMessage(status) {
    return {
      success: i18n.pySuccess,
      validated: i18n.pyValidated,
      mismatch: i18n.pyMismatch,
      error: i18n.pyError,
      timeout: i18n.pyTimeout,
      cancelled: i18n.pyCancelled
    }[status];
  }
  function finishPyRun(run, status, persist) {
    if (pyActiveRun !== run) return;
    clearTimeout(run.timer);
    if (run.worker) run.worker.terminate();
    if (run.url) URL.revokeObjectURL(run.url);
    pyActiveRun = null;
    run.ui.btn.disabled = false;
    run.ui.validate.disabled = !!run.ui.validator.error;
    run.ui.stop.hidden = true;
    if (persist === false) return;
    if (run.ui.editor.value() !== run.code) return;
    if (!run.ui.outPre.textContent) appendPyOutput(run.ui, i18n.noOutput);
    showPyStatus(run.ui, pyMessage(status), status);
    run.ui.editor.setResult({ status: status, output: run.ui.outPre.textContent });
    run.ui.clear.hidden = false;
    if (status === 'success' || status === 'validated') unlockCodeQuestion(run.ui.questionId, 'run');
  }
  function startPyRun(ui, validate) {
    if (pyActiveRun) { showPyStatus(ui, i18n.busy, ''); return; }
    if (validate && ui.validator.error) { showPyStatus(ui, ui.validator.error, 'error'); return; }
    var run = { id: ++pyRunSeq, ui: ui, code: ui.editor.value(), worker: null, timer: null, url: null };
    pyActiveRun = run;
    ui.editor.setResult(null);
    if (cqForms[ui.questionId]) cqForms[ui.questionId]('lock');
    ui.btn.disabled = true; ui.validate.disabled = true; ui.stop.hidden = false;
    ui.outPre.textContent = ''; ui.outWrap.hidden = true; ui.clear.hidden = true;
    showPyStatus(ui, i18n.preparing, '');
    function failedLoad() {
      appendPyOutput(ui, i18n.loadError);
      finishPyRun(run, 'error');
      unlockAllCodeQuestionsFallback();
    }
    try {
      if (ui.packageId !== null && ui.packageId !== PY_CARDANO_PRESET.id) throw new Error('unknown-python-package-preset');
      run.packages = ui.packageId ? PY_CARDANO_PRESET : null;
      run.url = URL.createObjectURL(new Blob(['(' + pythonWorkerMain.toString() + ')();'], { type: 'text/javascript' }));
      run.worker = new Worker(run.url, { type: 'module' });
      run.timer = setTimeout(function () { if (pyActiveRun === run) failedLoad(); }, PY_LOAD_TIMEOUT_MS);
      run.worker.onerror = function () {
        if (pyActiveRun !== run) return;
        if (!run.executing) { failedLoad(); return; }
        appendPyOutput(ui, i18n.workerError);
        finishPyRun(run, 'error');
      };
      run.worker.onmessage = function (event) {
        if (pyActiveRun !== run) return;
        var msg = event.data || {};
        if (msg.type === 'boot') {
          URL.revokeObjectURL(run.url); run.url = null;
          run.worker.postMessage({ type: 'init', base: PY_CDN_BASE, packageName: ui.packageName, packages: run.packages });
        } else if (msg.type === 'ready') {
          clearTimeout(run.timer); run.executing = true;
          showPyStatus(ui, validate ? i18n.validating : i18n.running, '');
          run.timer = setTimeout(function () { finishPyRun(run, 'timeout'); }, PY_RUN_TIMEOUT_MS);
          run.worker.postMessage({ type: 'run', code: run.code, tests: validate ? ui.validator.tests : [], outputTruncated: i18n.outputTruncated });
        } else if (msg.type === 'output') {
          appendPyOutput(ui, msg.text);
        } else if (msg.type === 'load-error') {
          failedLoad();
        } else if (msg.type === 'error') {
          appendPyOutput(ui, msg.error); finishPyRun(run, 'error');
        } else if (msg.type === 'done') {
          if (validate) {
            var checks = Array.isArray(msg.checks) ? msg.checks : [];
            checks.forEach(function (test) { appendPyOutput(ui, (test.passed ? i18n.testPassed : i18n.testFailed) + test.name + (test.error ? '\n' + test.error : '')); });
            var passed = checks.length === ui.validator.tests.length && checks.length > 0 && checks.every(function (test) { return test.passed === true; });
            finishPyRun(run, passed ? 'validated' : 'mismatch');
          } else finishPyRun(run, 'success');
        }
      };
    } catch (error) { failedLoad(); }
  }

  document.querySelectorAll('pre').forEach(function (pre) {
    if (pre.getAttribute('data-python-runner') === 'false') return;
    if (pre.getAttribute('data-python-runner') !== 'true' && !pre.querySelector('code.language-python')) return;
    pre.setAttribute('data-python-runner', 'true');
    var editor = pre._studyEditor;
    if (!editor) return;
    var wrap = pre.parentElement;
    var ui = { editor: editor, questionId: pre.getAttribute('data-question'), validator: validatorFor(pre),
      packageName: pre.getAttribute('data-python-package') || '', packageId: pre.getAttribute('data-python-packages') };
    ui.status = document.createElement('p');
    ui.status.className = 'run-status'; ui.status.setAttribute('role', 'status');
    ui.outWrap = document.createElement('div'); ui.outWrap.className = 'run-out'; ui.outWrap.hidden = true;
    var label = document.createElement('div'); label.className = 'run-output-label'; label.textContent = ui.validator.configured ? i18n.outputTests : i18n.output;
    ui.outPre = document.createElement('pre'); ui.outPre.className = 'run-output'; ui.outPre.setAttribute('aria-label', i18n.outputLabel);
    ui.outPre.id = editor.storage.status.id + '-output';
    ui.clear = study.button(i18n.clearOutput, 'study-button clear-output-btn', function () {
      if (pyActiveRun && pyActiveRun.ui === ui) return;
      var result = editor.result();
      if (!result || !result.output) return;
      ui.outPre.textContent = ''; ui.outWrap.hidden = true; ui.clear.hidden = true;
      editor.setResult({ status: result.status, output: '' });
      showPyStatus(ui, '', '');
      ui.btn.focus({ preventScroll: true });
    });
    ui.clear.hidden = true;
    ui.clear.setAttribute('aria-controls', ui.outPre.id);
    var outputHeader = document.createElement('div'); outputHeader.className = 'run-output-header';
    outputHeader.appendChild(label); outputHeader.appendChild(ui.clear);
    ui.outWrap.appendChild(outputHeader); ui.outWrap.appendChild(ui.outPre);
    ui.btn = study.button(i18n.run, 'run-btn', function () { startPyRun(ui, false); });
    ui.validate = study.button(i18n.validate, 'study-button validate-code-btn', function () { startPyRun(ui, true); });
    ui.validate.hidden = !ui.validator.configured; ui.validate.disabled = !!ui.validator.error;
    ui.stop = study.button(i18n.stop, 'study-button stop-code-btn', function () { if (pyActiveRun && pyActiveRun.ui === ui) finishPyRun(pyActiveRun, 'cancelled'); });
    ui.stop.hidden = true;
    editor.tools.appendChild(ui.btn); editor.tools.appendChild(ui.validate); editor.tools.appendChild(ui.stop);
    wrap.appendChild(ui.status); wrap.appendChild(ui.outWrap);
    function restoreResult(result) {
      if (pyActiveRun && pyActiveRun.ui === ui) finishPyRun(pyActiveRun, 'cancelled', false);
      ui.outPre.textContent = ''; ui.outWrap.hidden = true; ui.clear.hidden = true;
      if (cqForms[ui.questionId]) cqForms[ui.questionId]('lock', true);
      if (!result) { showPyStatus(ui, '', ''); return; }
      if (result.output) {
        appendPyOutput(ui, result.output);
        ui.clear.hidden = false;
        showPyStatus(ui, i18n.previousResult + pyMessage(result.status), result.status);
      } else showPyStatus(ui, '', '');
      if (result.status === 'success' || result.status === 'validated') unlockCodeQuestion(ui.questionId, 'run');
    }
    editor.onChange(function () {
      if (pyActiveRun && pyActiveRun.ui === ui) finishPyRun(pyActiveRun, 'cancelled', false);
      ui.outPre.textContent = ''; ui.outWrap.hidden = true; ui.clear.hidden = true;
      showPyStatus(ui, i18n.codeChanged, '');
      if (cqForms[ui.questionId]) cqForms[ui.questionId]('lock');
    });
    editor.onRestore(restoreResult);
    restoreResult(editor.result());
    if (ui.validator.error) showPyStatus(ui, ui.validator.error, 'error');
  });

  // impressão: abre respostas, inclusive as ainda bloqueadas, e restaura depois
  var opened = [];
  var unhidden = [];
  window.addEventListener('beforeprint', function () {
    opened = [];
    unhidden = [];
    document.querySelectorAll('details[hidden]').forEach(function (d) {
      d.hidden = false;
      unhidden.push(d);
    });
    document.querySelectorAll('details:not([open])').forEach(function (d) {
      d.setAttribute('open', '');
      opened.push(d);
    });
  });
  window.addEventListener('afterprint', function () {
    opened.forEach(function (d) { d.removeAttribute('open'); });
    unhidden.forEach(function (d) { d.hidden = true; });
    opened = [];
    unhidden = [];
  });
})();
