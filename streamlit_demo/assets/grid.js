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
  const labelRank = new Map((data.label_order || []).map((name, index) => [name, index]));
  root._pendingMemberships ||= new Map();

  const make = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const opId = () => crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;

  function orderedLabels(sample) {
    return [...(sample.labels || [])].sort((left, right) => {
      const leftRank = labelRank.has(left.name) ? labelRank.get(left.name) : Number.MAX_SAFE_INTEGER;
      const rightRank = labelRank.has(right.name) ? labelRank.get(right.name) : Number.MAX_SAFE_INTEGER;
      return leftRank - rightRank || left.name.localeCompare(right.name, 'zh-CN');
    });
  }

  function renderMarks(card, sample) {
    card.querySelectorAll('.badges').forEach(node => node.remove());
    card.querySelectorAll('.frame-rings').forEach(node => node.remove());
    if (!data.show_badges || !sample.labels?.length) return;
    const labels = orderedLabels(sample);
    const borderLabels = labels.filter(label => label.style === 'border');
    const badgeLabels = labels.filter(label => label.style !== 'border');
    if (borderLabels.length) {
      const frame = make('div', 'frame-rings');
      frame.title = borderLabels.map(label => label.name).join('、');
      frame.style.boxShadow = borderLabels
        .map((label, index) => `inset 0 0 0 ${(index + 1) * 4}px ${label.color}`)
        .join(', ');
      card.appendChild(frame);
    }
    if (!badgeLabels.length) return;
    const holder = make('div', 'badges');
    holder.title = badgeLabels.map(label => label.name).join('、');
    badgeLabels.slice(0, 6).forEach(label => {
      const badge = make('span', 'badge');
      badge.style.backgroundColor = label.color;
      badge.title = label.name;
      holder.appendChild(badge);
    });
    if (badgeLabels.length > 6) holder.appendChild(make('span', 'badge-more', `+${badgeLabels.length - 6}`));
    card.appendChild(holder);
  }

  function queueMembership(sample, label, assigned) {
    root._pendingMemberships.set(`${label}\u0000${sample}`, {sample, label, assigned});
    clearTimeout(root._membershipTimer);
    root._membershipTimer = setTimeout(() => {
      const operations = [...root._pendingMemberships.values()];
      root._pendingMemberships.clear();
      if (operations.length) {
        setTriggerValue('action', {type: 'membership_batch', op_id: opId(), operations});
      }
    }, 350);
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
  grid.style.gridAutoRows = `${Math.max(190, Math.min(370, 700 / Math.max(1, data.rows)))}px`;
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
    renderMarks(card, sample);
    card.addEventListener('click', event => {
      if (event.target.closest('video, button, input, textarea')) return;
      if (!data.active_label) return;
      const existing = sample.labels.find(label => label.name === data.active_label.name);
      const assigned = !existing;
      if (assigned) sample.labels.push({...data.active_label});
      else sample.labels = sample.labels.filter(label => label.name !== data.active_label.name);
      renderMarks(card, sample);
      queueMembership(sample.name, data.active_label.name, assigned);
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
  numberInput('列', data.cols, 1, null, value => setStateValue('cols', value));
  toolbar.appendChild(make('span', '', `${data.total_count} 个样本 · 单页全部显示`));
  const badgeLabel = make('label', '', '显示标记');
  const checkbox = make('input'); checkbox.type = 'checkbox'; checkbox.checked = data.show_badges;
  checkbox.onchange = () => setStateValue('show_badges', checkbox.checked); badgeLabel.prepend(checkbox); toolbar.appendChild(badgeLabel);
  const refresh = make('button', 'refresh-button', '↻ 刷新');
  refresh.title = '重新扫描输入目录并更新全部样本';
  refresh.onclick = () => {
    refresh.disabled = true;
    setTriggerValue('action', {type: 'refresh', op_id: opId()});
  };
  toolbar.appendChild(refresh);
  const componentHost = root.getRootNode().host;
  let viewportWindow = window;
  let frameElement = null;
  let scrollContainer = componentHost?.closest('[data-testid="stMain"]') || document.querySelector('[data-testid="stMain"]');
  try {
    if (window.frameElement && window.parent.document) {
      viewportWindow = window.parent;
      frameElement = window.frameElement;
      scrollContainer = window.parent.document.querySelector('[data-testid="stMain"]');
    }
  } catch (_) {
    // Cross-origin embedding falls back to the component viewport.
  }
  const positionToolbar = () => {
    const bounds = root.getBoundingClientRect();
    const viewportBottom = scrollContainer?.getBoundingClientRect().bottom || viewportWindow.innerHeight;
    const componentTop = frameElement ? frameElement.getBoundingClientRect().top : bounds.top;
    const desiredTop = viewportBottom - componentTop - toolbar.offsetHeight - 8;
    const maximumTop = Math.max(0, root.offsetHeight - toolbar.offsetHeight);
    toolbar.style.top = `${Math.max(0, Math.min(maximumTop, desiredTop))}px`;
    toolbar.style.width = `${Math.max(260, bounds.width - 4)}px`;
  };
  positionToolbar();
  const toolbarObserver = new ResizeObserver(positionToolbar);
  toolbarObserver.observe(root);
  scrollContainer?.addEventListener('scroll', positionToolbar, {passive: true});
  viewportWindow.addEventListener('resize', positionToolbar, {passive: true});

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
  document.addEventListener('click', dismissMenu);
  return () => {
    document.removeEventListener('click', dismissMenu);
    scrollContainer?.removeEventListener('scroll', positionToolbar);
    viewportWindow.removeEventListener('resize', positionToolbar);
    toolbarObserver.disconnect();
  };
}
