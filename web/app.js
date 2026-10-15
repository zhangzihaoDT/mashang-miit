// Task examples are intentionally illustrative; Reports continue to load real files.
const $ = selector => document.querySelector(selector);
let scope = 'tasks';
let generation = 0;
let selectedDemoTask = 'batch-409';
let selectedDemoSection = 'details';

const node = (tag, value, cls) => {
  const element = document.createElement(tag);
  element.textContent = value;
  if (cls) element.className = cls;
  return element;
};

async function api(path, body) {
  const response = await fetch('/api/miit/' + path, body ? {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  } : {});
  const data = await response.json();
  if (!response.ok) throw Error(data.message);
  return data;
}

function notice(message) { $('#notice').textContent = message; }

const demoTasks = [
  {id: 'batch-409', title: '第 409 批', subtitle: '历史批次 · 示意', status: '执行状态 · 示意'},
  {id: 'batch-410', title: '第 410 批', subtitle: '历史批次 · 示意', status: '历史任务 · 示意'},
  {id: 'new-task', title: '新采集任务', subtitle: '示意状态', status: '等待执行 · 示意'},
];

function renderDemoTaskList() {
  const list = $('#list');
  list.replaceChildren();
  for (const task of demoTasks) {
    const card = node('article', '', 'demo-task' + (task.id === selectedDemoTask ? ' selected' : ''));
    const select = node('button', '', 'demo-task-select');
    select.setAttribute('aria-pressed', String(task.id === selectedDemoTask));
    select.append(node('span', task.id === selectedDemoTask ? '⌄' : '›', 'task-caret'));
    const copy = node('span', '', 'demo-task-copy');
    copy.append(node('strong', task.title), node('small', task.subtitle));
    select.append(copy);
    select.onclick = () => {
      selectedDemoTask = task.id;
      selectedDemoSection = 'details';
      renderDemoTask();
    };
    card.append(select);
    if (task.id === selectedDemoTask) {
      const actions = node('div', '', 'demo-task-actions');
      const outputs = node('button', '▱　data/ · 采集及加工产物', 'demo-task-action');
      outputs.setAttribute('aria-pressed', String(selectedDemoSection === 'outputs'));
      outputs.onclick = () => { selectedDemoSection = 'outputs'; renderDemoTask(); };
      const logs = node('button', '▤　任务详情与执行记录', 'demo-task-action');
      logs.setAttribute('aria-pressed', String(selectedDemoSection === 'details'));
      logs.onclick = () => { selectedDemoSection = 'details'; renderDemoTask(); };
      actions.append(outputs, logs);
      card.append(actions);
    }
    list.append(card);
  }
}

function renderDemoTask() {
  renderDemoTaskList();
  const task = demoTasks.find(item => item.id === selectedDemoTask) || demoTasks[0];
  const preview = $('#preview');
  preview.className = 'task-preview';
  preview.replaceChildren();

  const title = node('div', '', 'preview-title');
  title.append(node('span', '▤', 'preview-icon'), node('h2', '任务详情与产出'));
  preview.append(title, node('div', '', 'preview-divider'));

  const heading = node('div', '', 'demo-detail-heading');
  heading.append(node('h3', task.title), node('span', '示意', 'demo-badge'));
  preview.append(heading);

  const section = node('section', '', 'demo-detail-section');
  if (selectedDemoSection === 'outputs') {
    section.append(node('h4', 'data/ · 采集及加工产物'));
    section.append(node('p', '此处展示与当前任务明确关联的文件及结构化数据。示意页面不绑定或虚构实际文件。'));
    section.append(node('p', '历史数据缺少任务关联记录时，不推断文件归属。', 'detail-note'));
  } else {
    section.append(node('h4', '执行状态 / 数据产出'));
    section.append(node('p', task.status));
    section.append(node('p', '任务详情区用于呈现执行记录、采集候选，以及 data/ 中能够明确关联的文件与结构化数据。'));
    section.append(node('div', '', 'demo-detail-rule'));
    section.append(node('p', '历史批次 · 候选结果与执行记录仅作信息层级示意，不对应真实运行数据。', 'detail-note'));
  }
  preview.append(section);
}

async function refresh() {
  if (scope === 'reports') {
    await refreshReports();
    return;
  }
  $('#count').textContent = '任务及产出文件';
  renderDemoTask();
}

$('#capture').onsubmit = event => {
  event.preventDefault();
  notice('交互原型：采集按钮不连接后端。');
};

function setNav() {
  document.querySelectorAll('[data-scope]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.scope === scope));
  });
}

function resetPreview(message, eyebrow) {
  const preview = $('#preview');
  preview.className = 'task-preview empty-preview';
  preview.replaceChildren(node('span', eyebrow, 'eyebrow'), node('h2', message));
}

document.querySelectorAll('[data-scope]').forEach(button => {
  button.onclick = () => {
    if (scope === button.dataset.scope) return;
    scope = button.dataset.scope;
    generation++;
    setNav();
    if (scope === 'reports') {
      notice('Reports 按实际 reports/ 文件夹结构浏览。');
      resetPreview('选择报告查看预览', 'REPORTS / FILES');
    } else {
      notice('交互原型：示意任务不代表真实运行记录。');
    }
    refresh().catch(error => notice(error.message));
  };
});

$('#refresh').onclick = () => refresh().catch(error => notice(error.message));
setNav();
refresh().catch(error => notice(error.message));
