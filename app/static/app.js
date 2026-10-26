/* Progressive enhancement: the Flask forms also work without JavaScript. */
(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const root = document.documentElement;
  const themeButton = byId('theme-toggle');
  const applyTheme = theme => {
    root.dataset.theme = theme;
    const dark = theme === 'dark';
    byId('theme-icon').setAttribute('href', dark ? '#icon-sun' : '#icon-moon');
    themeButton.setAttribute('aria-label', dark ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối');
    themeButton.setAttribute('aria-pressed', String(dark));
  };
  let theme = 'light';
  try { if (localStorage.getItem('todo-clean-theme') === 'dark') theme = 'dark'; } catch (_) {}
  applyTheme(theme);
  themeButton.hidden = false;
  themeButton.addEventListener('click', () => {
    const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    try { localStorage.setItem('todo-clean-theme', next); } catch (_) {}
  });

  const list = byId('task-list');
  const tasks = Array.from(list.querySelectorAll('.task'));
  const search = byId('search');
  const sort = byId('sort');
  const normalize = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[đĐ]/g, 'd').toLocaleLowerCase('vi');
  const refresh = () => {
    const query = normalize(search.value.trim());
    let visible = 0;
    [...tasks].sort((a, b) => {
      if (sort.value === 'name') return a.querySelector('.task-title').textContent.localeCompare(b.querySelector('.task-title').textContent, 'vi');
      return sort.value === 'newest' ? Number(b.dataset.id) - Number(a.dataset.id) : Number(a.dataset.id) - Number(b.dataset.id);
    }).forEach(task => {
      task.hidden = !normalize(task.querySelector('.task-title').textContent).includes(query);
      if (!task.hidden) visible += 1;
      list.append(task);
    });
    byId('no-results').hidden = !tasks.length || visible > 0;
    byId('result-count').textContent = query ? `${visible} / ${tasks.length} công việc` : `${tasks.length} công việc trong danh sách`;
  };
  if (tasks.length) {
    byId('toolbar').hidden = false;
    byId('keyboard-hint').hidden = false;
  }
  search.addEventListener('input', refresh);
  sort.addEventListener('change', refresh);
  byId('clear-search').addEventListener('click', () => { search.value = ''; refresh(); search.focus(); });
  document.addEventListener('keydown', event => {
    const editing = event.target.closest('input, textarea, select, [contenteditable]');
    if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey && !editing && tasks.length && !byId('delete-dialog').open) {
      event.preventDefault();
      search.focus();
    }
  });

  const title = byId('title');
  const counter = byId('character-count');
  const error = byId('add-error');
  const addButton = byId('add-button');
  title.addEventListener('input', () => {
    counter.hidden = !title.value.length;
    counter.textContent = `${title.value.length} / 200`;
    title.removeAttribute('aria-invalid');
    error.hidden = true;
    error.textContent = '';
  });
  byId('add-form').addEventListener('submit', event => {
    if (!title.value.trim()) {
      event.preventDefault();
      title.setAttribute('aria-invalid', 'true');
      error.textContent = 'Nhập tên công việc trước khi thêm.';
      error.hidden = false;
      title.focus();
      return;
    }
    // Delay until other submit handlers have had a chance to cancel navigation.
    queueMicrotask(() => {
      if (!event.defaultPrevented) {
        addButton.disabled = true;
        addButton.querySelector('span').textContent = 'Đang thêm…';
      }
    });
  });
  window.addEventListener('pageshow', () => {
    addButton.disabled = false;
    addButton.querySelector('span').textContent = 'Thêm việc';
  });

  const dialog = byId('delete-dialog');
  const approvedForms = new WeakSet();
  let pendingForm = null;
  document.querySelectorAll('.delete-form').forEach(form => {
    form.addEventListener('submit', event => {
      if (approvedForms.has(form)) { approvedForms.delete(form); return; }
      if (typeof dialog.showModal !== 'function') {
        if (!window.confirm('Xoá công việc này? Thao tác không thể hoàn tác.')) event.preventDefault();
        return;
      }
      event.preventDefault();
      pendingForm = form;
      byId('delete-title').textContent = form.closest('.task').querySelector('.task-title').textContent;
      dialog.returnValue = '';
      if (!dialog.open) dialog.showModal();
    });
  });
  dialog.addEventListener('close', () => {
    const form = pendingForm;
    pendingForm = null;
    if (dialog.returnValue === 'delete' && form) {
      approvedForms.add(form);
      form.requestSubmit();
    }
  });
})();
