export default function(component) {
  const { data, parentElement, setStateValue, setTriggerValue } = component;
  const root = parentElement.querySelector('.sample-app');
  const grid = root.querySelector('[data-role="grid"]');
  const empty = root.querySelector('[data-role="empty"]');
  const toolbar = root.querySelector('[data-role="toolbar"]');
  const menu = root.querySelector('[data-role="context"]');
  const dialog = root.querySelector('[data-role="note-dialog"]');
  const viewer = root.querySelector('[data-role="viewer-dialog"]');
  const viewerCanvas = root.querySelector('[data-role="viewer-canvas"]');
  const viewerImage = root.querySelector('[data-role="viewer-image"]');
  let contextSample = null;
  let viewerScale = 1;
  let viewerX = 0;
  let viewerY = 0;
  let dragging = false;
  let dragStartX = 0;
  let dragStartY = 0;

  const make = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const opId = () => crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;

  function renderBadges(card, sample) {
    card.querySelectorAll('.badges').forEach(node => node.remove());
    if (!data.show_badges || !sample.labels?.length) return;
    const holder = make('div', 'badges');
    holder.title = sample.labels.map(label => label.name).join('、');
    sample.labels.slice(0, 6).forEach(label => {
      const badge = make('span', 'badge');
      badge.style.backgroundColor = label.color;
      badge.title = label.name;
      holder.appendChild(badge);
    });
    if (sample.labels.length > 6) holder.appendChild(make('span', 'badge-more', `+${sample.labels.length - 6}`));
    card.appendChild(holder);
  }

  function openNote(sample) {
    contextSample = sample;
    const note = sample.note || {current: '', updated_at: '', history: []};
    root.querySelector('[data-role="note-filename"]').textContent = sample.name;
    root.querySelector('[data-role="note-text"]').value = note.current || '';
    root.querySelector('[data-role="note-updated"]').textContent = note.updated_at ? `最后更新：${note.updated_at}` : '尚无备注';
    const history = root.querySelector('[data-role="note-history"]');
    history.replaceChildren();
    [...(note.history || [])].reverse().forEach(item => {
      const entry = make('div', 'history-entry');
      entry.appendChild(make('time', '', `${item.updated_at} · ${item.action === 'clear' ? '清空' : '保存'}`));
      entry.appendChild(make('div', '', item.text || '（空）'));
      history.appendChild(entry);
    });
    dialog.showModal();
  }

  function updateViewer() {
    viewerImage.style.transform = `translate(${viewerX}px, ${viewerY}px) scale(${viewerScale})`;
    root.querySelector('[data-role="zoom-value"]').textContent = `${Math.round(viewerScale * 100)}%`;
  }

  function setViewerScale(nextScale) {
    viewerScale = Math.max(0.25, Math.min(8, nextScale));
    if (viewerScale === 1) { viewerX = 0; viewerY = 0; }
    updateViewer();
  }

  function openViewer(sample) {
    if (!sample || sample.kind !== 'image' || !sample.source) return;
    contextSample = sample;
    viewerScale = 1; viewerX = 0; viewerY = 0;
    root.querySelector('[data-role="viewer-filename"]').textContent = sample.name;
    viewerImage.src = sample.source;
    updateViewer();
    viewer.showModal();
  }

  grid.replaceChildren();
  grid.style.gridTemplateColumns = `repeat(${data.cols}, minmax(120px, 1fr))`;
  grid.style.gridAutoRows = `${Math.max(130, Math.min(280, 500 / Math.max(1, data.rows)))}px`;
  empty.hidden = data.samples.length > 0;
  data.samples.forEach(sample => {
    const card = make('article', 'sample-card');
    card.dataset.sample = sample.name;
    const media = make('div', 'media');
    if (sample.error) {
      media.appendChild(make('div', 'error', sample.error));
    } else if (sample.kind === 'image') {
      const image = make('img'); image.src = sample.source; image.alt = sample.name; image.loading = 'eager'; media.appendChild(image);
    } else if (sample.kind === 'video') {
      const video = make('video'); video.src = sample.source; video.controls = true; video.preload = 'metadata'; media.appendChild(video);
    } else {
      media.appendChild(make('pre', '', sample.source));
    }
    card.appendChild(media);
    const filename = make('div', 'filename', sample.name); filename.title = sample.name; card.appendChild(filename);
    if (sample.notice) card.appendChild(make('div', 'notice', sample.notice));
    if (sample.kind === 'image' && sample.source) {
      const viewButton = make('button', 'view-button', '⛶');
      viewButton.type = 'button'; viewButton.title = '单独查看并缩放';
      viewButton.addEventListener('click', event => { event.stopPropagation(); openViewer(sample); });
      card.appendChild(viewButton);
    }
    if (sample.has_note) { const icon = make('span', 'note-indicator', '📝'); icon.title = '已有单样本备注'; card.appendChild(icon); }
    renderBadges(card, sample);
    card.addEventListener('click', event => {
      if (event.target.closest('video, button, input, textarea')) return;
      if (!data.active_label) return;
      const existing = sample.labels.find(label => label.name === data.active_label.name);
      const assigned = !existing;
      if (assigned) sample.labels.push({...data.active_label});
      else sample.labels = sample.labels.filter(label => label.name !== data.active_label.name);
      renderBadges(card, sample);
      setTriggerValue('action', {type: 'membership', op_id: opId(), sample: sample.name, label: data.active_label.name, assigned});
    });
    card.addEventListener('contextmenu', event => {
      event.preventDefault(); contextSample = sample;
      root.querySelector('[data-role="open-viewer"]').hidden = sample.kind !== 'image' || !sample.source;
      menu.hidden = false;
      menu.style.left = `${Math.min(event.clientX, window.innerWidth - 190)}px`;
      menu.style.top = `${Math.min(event.clientY, window.innerHeight - 70)}px`;
    });
    grid.appendChild(card);
  });

  toolbar.replaceChildren();
  const activeStatus = make('span', 'active-label', data.active_label ? `当前标签：${data.active_label.name}` : '当前标签：未选择');
  if (data.active_label) activeStatus.style.color = data.active_label.color;
  toolbar.appendChild(activeStatus);
  const numberInput = (labelText, value, min, max, callback) => {
    const label = make('label', '', labelText);
    const input = make('input'); input.type = 'number'; input.min = min; input.value = value;
    if (max !== null) input.max = max;
    input.addEventListener('change', () => {
      let nextValue = Math.max(min, Math.floor(Number(input.value) || min));
      if (max !== null) nextValue = Math.min(max, nextValue);
      callback(nextValue);
    });
    label.appendChild(input); toolbar.appendChild(label);
  };
  numberInput('行', data.rows, 1, null, value => setStateValue('rows', value));
  numberInput('列', data.cols, 1, null, value => setStateValue('cols', value));
  const previous = make('button', '', '← 上一页'); previous.disabled = data.page <= 1;
  previous.onclick = () => setStateValue('page', data.page - 1); toolbar.appendChild(previous);
  numberInput('页码', data.page, 1, Math.max(1, data.total_pages), value => setStateValue('page', value));
  toolbar.appendChild(make('span', '', `/ ${data.total_pages || 0} 页 · ${data.total_count} 个样本`));
  const next = make('button', '', '下一页 →'); next.disabled = data.page >= data.total_pages;
  next.onclick = () => setStateValue('page', data.page + 1); toolbar.appendChild(next);
  const badgeLabel = make('label', '', '显示角标');
  const checkbox = make('input'); checkbox.type = 'checkbox'; checkbox.checked = data.show_badges;
  checkbox.onchange = () => setStateValue('show_badges', checkbox.checked); badgeLabel.prepend(checkbox); toolbar.appendChild(badgeLabel);
  const refresh = make('button', 'refresh-button', '↻ 刷新');
  refresh.title = '重新扫描输入目录；刷新后保持当前页';
  refresh.onclick = () => {
    refresh.disabled = true;
    setTriggerValue('action', {type: 'refresh', op_id: opId()});
  };
  toolbar.appendChild(refresh);

  root.querySelector('[data-role="open-viewer"]').onclick = () => { menu.hidden = true; if (contextSample) openViewer(contextSample); };
  root.querySelector('[data-role="open-note"]').onclick = () => { menu.hidden = true; if (contextSample) openNote(contextSample); };
  root.querySelector('[data-role="close-viewer"]').onclick = () => viewer.close();
  root.querySelector('[data-role="zoom-in"]').onclick = () => setViewerScale(viewerScale * 1.25);
  root.querySelector('[data-role="zoom-out"]').onclick = () => setViewerScale(viewerScale / 1.25);
  root.querySelector('[data-role="zoom-reset"]').onclick = () => { viewerScale = 1; viewerX = 0; viewerY = 0; updateViewer(); };
  viewerCanvas.onwheel = event => { event.preventDefault(); setViewerScale(viewerScale * (event.deltaY < 0 ? 1.12 : 0.89)); };
  viewerCanvas.onpointerdown = event => {
    dragging = true; dragStartX = event.clientX - viewerX; dragStartY = event.clientY - viewerY;
    viewerCanvas.classList.add('dragging'); viewerCanvas.setPointerCapture(event.pointerId);
  };
  viewerCanvas.onpointermove = event => {
    if (!dragging) return;
    viewerX = event.clientX - dragStartX; viewerY = event.clientY - dragStartY; updateViewer();
  };
  viewerCanvas.onpointerup = event => {
    dragging = false; viewerCanvas.classList.remove('dragging'); viewerCanvas.releasePointerCapture(event.pointerId);
  };
  root.querySelector('[data-role="save-note"]').onclick = () => {
    if (!contextSample) return;
    const text = root.querySelector('[data-role="note-text"]').value;
    dialog.close(); setTriggerValue('action', {type: 'note', op_id: opId(), sample: contextSample.name, text});
  };
  root.querySelector('[data-role="clear-note"]').onclick = () => {
    if (!contextSample) return;
    dialog.close(); setTriggerValue('action', {type: 'note', op_id: opId(), sample: contextSample.name, text: ''});
  };
  const dismissMenu = event => { if (!menu.contains(event.target)) menu.hidden = true; };
  const keyboard = event => {
    if (dialog.open || viewer.open || event.ctrlKey || event.metaKey || event.altKey) return;
    const tag = event.target.tagName;
    if (['INPUT', 'TEXTAREA', 'SELECT', 'VIDEO'].includes(tag) || event.target.isContentEditable) return;
    if ((event.key === 'a' || event.key === 'A') && data.page > 1) setStateValue('page', data.page - 1);
    if ((event.key === 'd' || event.key === 'D') && data.page < data.total_pages) setStateValue('page', data.page + 1);
  };
  document.addEventListener('click', dismissMenu);
  document.addEventListener('keydown', keyboard);
  return () => { document.removeEventListener('click', dismissMenu); document.removeEventListener('keydown', keyboard); };
}
