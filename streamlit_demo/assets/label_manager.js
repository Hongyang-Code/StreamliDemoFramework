export default function(component) {
  const { data, parentElement, setTriggerValue } = component;
  const root = parentElement.querySelector('[data-role="label-list"]');
  root._editing ??= null;
  let pressTimer = null;
  let dragged = null;
  let suppressClick = false;
  const opId = () => crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  const emit = action => setTriggerValue('action', {...action, op_id: opId()});
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const backendLabels = [...(data.labels || [])];
  const backendOrder = backendLabels.map(label => label.name);
  const sameOrder = (left, right) => left.length === right.length && left.every((name, index) => name === right[index]);
  if (root._optimisticOrder && sameOrder(root._optimisticOrder, backendOrder)) root._optimisticOrder = null;
  const labelByName = new Map(backendLabels.map(label => [label.name, label]));
  const optimisticOrder = (root._optimisticOrder || []).filter(name => labelByName.has(name));
  const renderedLabels = optimisticOrder.map(name => labelByName.get(name));
  renderedLabels.push(...backendLabels.filter(label => !optimisticOrder.includes(label.name)));

  root.replaceChildren();
  renderedLabels.forEach(label => {
    const card = make('section', `label-card st-key-label_card_${label.token}`);
    card.dataset.label = label.name;
    card.style.setProperty('--label-color', label.color);
    if (label.name === data.active_label) card.classList.add('active');
    const row = make('div', 'label-row');
    const name = make('button', 'label-name', `${label.name === data.active_label ? '✓ ' : ''}${label.name}`);
    name.type = 'button'; name.title = label.name; name.setAttribute('aria-label', label.name);
    name.onclick = event => {
      event.stopPropagation();
      if (suppressClick) { suppressClick = false; return; }
      emit({type: 'select', name: label.name});
    };
    const edit = make('button', 'edit', '编辑'); edit.type = 'button';
    const remove = make('button', 'delete', '删除'); remove.type = 'button';
    row.append(name, edit, remove); card.appendChild(row);

    const editor = make('div', 'editor');
    editor.hidden = root._editing !== label.name;
    const nameLabel = make('label', '', '新名称');
    const nameInput = make('input'); nameInput.type = 'text'; nameInput.value = label.name; nameInput.setAttribute('aria-label', '新名称');
    nameLabel.appendChild(nameInput);
    const colorLabel = make('label', '', '颜色');
    const colorInput = make('input'); colorInput.type = 'color'; colorInput.value = label.color; colorInput.setAttribute('aria-label', '颜色');
    colorLabel.appendChild(colorInput);
    const styleLabel = make('label', '', '标记形式');
    const styleSelect = make('select'); styleSelect.setAttribute('aria-label', '标记形式');
    [['badge', '角标'], ['border', '外框']].forEach(([value, text]) => {
      const option = make('option', '', text); option.value = value; option.selected = label.style === value; styleSelect.appendChild(option);
    });
    styleLabel.appendChild(styleSelect);
    const editorGrid = make('div', 'editor-grid'); editorGrid.append(colorLabel, styleLabel);
    const save = make('button', 'save', '保存设置'); save.type = 'button';
    save.onclick = event => {
      event.stopPropagation();
      root._editing = null; editor.hidden = true;
      emit({type: 'update', name: label.name, new_name: nameInput.value, color: colorInput.value, style: styleSelect.value});
    };
    editor.append(nameLabel, editorGrid, save); card.appendChild(editor);

    edit.onclick = event => {
      event.stopPropagation();
      root._editing = root._editing === label.name ? null : label.name;
      editor.hidden = root._editing !== label.name;
    };
    remove.onclick = event => { event.stopPropagation(); emit({type: 'delete', name: label.name}); };
    card.onclick = () => {
      if (suppressClick) { suppressClick = false; return; }
      emit({type: 'select', name: label.name});
    };

    row.onpointerdown = event => {
      if (event.target.closest('.edit, .delete, input, select')) return;
      clearTimeout(pressTimer);
      pressTimer = setTimeout(() => {
        dragged = card; suppressClick = true; card.classList.add('drag-ready');
        row.setPointerCapture(event.pointerId);
      }, 320);
    };
    row.onpointermove = event => {
      if (!dragged) return;
      const siblings = [...root.querySelectorAll('.label-card')].filter(item => item !== dragged);
      const target = siblings.find(item => event.clientY < item.getBoundingClientRect().bottom);
      if (!target) root.insertBefore(dragged, root.querySelector('.drag-hint'));
      else if (event.clientY < target.getBoundingClientRect().top + target.getBoundingClientRect().height / 2) root.insertBefore(dragged, target);
      else root.insertBefore(dragged, target.nextSibling);
    };
    const finishPointer = event => {
      clearTimeout(pressTimer);
      if (!dragged) return;
      dragged.classList.remove('drag-ready'); dragged = null;
      if (row.hasPointerCapture(event.pointerId)) row.releasePointerCapture(event.pointerId);
      const order = [...root.querySelectorAll('.label-card')].map(item => item.dataset.label);
      root._optimisticOrder = order;
      emit({type: 'reorder', order});
    };
    row.onpointerup = finishPointer;
    row.onpointercancel = finishPointer;
    root.appendChild(card);
  });
  if (renderedLabels.length > 1) root.appendChild(make('div', 'drag-hint', '长按标签卡片后可上下拖动排序'));

  return () => clearTimeout(pressTimer);
}
