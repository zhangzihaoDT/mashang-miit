const $ = selector => document.querySelector(selector);
let scope = 'tasks', generation = 0;
let tasks = [], selectedTask = null, detailSignature = '', refreshing = false;
let pendingCapture = null, submitting = false;
const labels = {queued: '排队中', running: '采集中', succeeded: '采集完成', failed: '采集失败', partial_success: '部分成功'};
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
  if (!response.ok) throw Error(data.message || '请求失败');
  return data;
}
function notice(message) { $('#notice').textContent = message; }
function setNav() {
  document.querySelectorAll('[data-scope]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.scope === scope));
  });
}
function resetPreview(message, eyebrow) {
  const preview = $('#preview');
  preview.className = 'task-preview empty-preview';
  const picture = document.createElement('picture'); picture.className = 'empty-icon';
  const source = document.createElement('source'); source.media = '(prefers-reduced-motion: reduce)'; source.srcset = '/brand.png';
  const image = document.createElement('img'); image.src = '/favicon.gif'; image.alt = '浣熊伙伴'; image.width = 88; image.height = 88;
  picture.append(source, image);
  preview.replaceChildren(picture, node('h2', message), node('p', eyebrow === 'REPORTS' ? '在左侧选择报告，即可预览或下载。' : '输入公告链接并点击开始采集，任务将在左侧显示，点击即可查看进度与结果。'));
}
function taskList() {
  $('#tasks-count').textContent = tasks.length;
  $('#tasks-count').title = '最近 100 条任务中的记录数';
  $('#open-folder').disabled = !selectedTask;
  $('#count').textContent = `最近任务 · ${tasks.length} / 100`;
  const list = $('#list'); list.replaceChildren();
  if (!tasks.length) list.append(node('p', '暂无采集任务，请在顶部输入正式公告链接。'));
  for (const task of tasks) {
    const button = node('button', '', 'task-select');
    button.dataset.taskId = task.task_id;
    button.setAttribute('aria-pressed', String(selectedTask === task.task_id));
    button.append(node('strong', labels[task.status] || task.status),
      node('small', new Date(task.created_at).toLocaleString()), node('small', task.url));
    button.onclick = () => {
      selectedTask = task.task_id; detailSignature = ''; generation++;
      taskList(); showTask(task).catch(e => notice(e.message));
    };
    list.append(button);
  }
}
function jsonBlock(parent, title, value) {
  const section = node('details', '', 'task-section');
  section.append(node('summary', title), node('pre', JSON.stringify(value, null, 2)));
  parent.append(section);
}
async function showTask(task) {
  const signature = JSON.stringify(task);
  if (signature === detailSignature) return;
  const token = ++generation;
  const box = $('#preview'); box.className = 'task-preview';
  box.replaceChildren(node('p', '加载任务详情…'));
  try {
    const candidate = task.candidate_id ? await api('candidates/' + task.candidate_id) : null;
    if (token !== generation || scope !== 'tasks' || selectedTask !== task.task_id) return;
    detailSignature = signature;
    box.replaceChildren(node('h2', '任务详情与产出'), node('h3', labels[task.status] || task.status));
    box.append(node('p', '任务 ID · ' + task.task_id, 'hash'));
    const source = node('a', task.url); source.href = task.url; source.target = '_blank'; source.rel = 'noopener noreferrer';
    box.append(source, node('p', '创建于 ' + new Date(task.created_at).toLocaleString() + ' · 更新于 ' + new Date(task.updated_at).toLocaleString()));
    if (task.retry_of) box.append(node('p', '重试自 · ' + task.retry_of, 'hash'));
    if (task.error) {
      let error; try { error = JSON.parse(task.error); } catch { error = {message: task.error}; }
      box.append(node('p', `${error.code || '采集错误'} · ${error.message}`, 'task-error'));
    }
    if (['failed', 'partial_success'].includes(task.status)) {
      const retry = node('button', '重新采集');
      const retryKey = crypto.randomUUID();
      retry.onclick = async () => {
        retry.disabled = true;
        try { activateTask(await api('tasks/' + task.task_id + '/retry', {idempotency_key: retryKey})); await refresh(); }
        catch (e) { notice(e.message); } finally { retry.disabled = false; }
      };
      const actions = node('div', '', 'detail-actions'); actions.append(retry); box.append(actions);
    }
    if (!candidate) {
      box.append(node('p', ['queued', 'running'].includes(task.status) ? '正在等待采集结果，状态自动更新。' : '本任务尚无已提交的候选结果或产物。'));
      return;
    }
    const payload = candidate.payload;
    box.append(node('h3', `第 ${payload.batch_no} 批 · 候选结果`),
      node('p', `${payload.rows.length} 条来源记录 · ${payload.issues.length} 行质量/范围标记 · 待核验`),
      node('p', `官方阶段：${payload.stage} · 来源：${payload.source} · ${payload.capture_mode === 'archive_replay' ? '归档离线回放' : '实时采集'}`),
      node('p', '采集完成不等于已核验或正式入库。'), node('p', '候选 ID · ' + candidate.candidate_id, 'hash'));
    jsonBlock(box, '结构化候选记录（完整 JSON）', payload.rows);
    jsonBlock(box, '质量与作用域标记', payload.issues);
    jsonBlock(box, '公告元数据', payload.metadata);
    box.append(node('h3', '本任务已有产物与来源证据'));
    const snapshot = node('a', '下载候选快照 JSON');
    snapshot.href = '/api/miit/candidates/' + candidate.candidate_id;
    snapshot.download = `candidate-${candidate.candidate_id}.json`; box.append(snapshot);
    for (const evidence of candidate.evidence) {
      const row = node('div', '', 'task-section'), meta = evidence.metadata;
      row.append(node('p', `${meta.name} · ${meta.size} B`), node('p', 'SHA-256 · ' + meta.sha256, 'hash'));
      const actions = node('div', '', 'detail-actions');
      const download = node('a', '下载'); download.href = '/api/miit/evidence/' + evidence.evidence_id; download.download = meta.name; actions.append(download);
      if (meta.kind !== 'doc') {
        const preview = node('button', '预览原文'); const content = node('pre', ''); content.hidden = true;
        preview.onclick = async () => {
          if (!content.hidden) { content.hidden = true; return; }
          preview.disabled = true;
          try {
            const response = await fetch(download.href);
            if (!response.ok) throw Error('证据读取失败');
            content.textContent = await response.text(); content.hidden = false;
          } catch (e) { notice(e.message); } finally { preview.disabled = false; }
        };
        actions.append(preview); row.append(actions, content);
      } else row.append(actions);
      box.append(row);
    }
    box.append(node('p', '只展示本任务明确关联的产物；历史 data/ 文件不推断归属。'));
  } catch (e) {
    if (token === generation && scope === 'tasks') { detailSignature = ''; box.replaceChildren(node('p', '任务详情读取失败：' + e.message)); }
    throw e;
  }
}
function activateTask(task) {
  scope = 'tasks'; selectedTask = task.task_id; detailSignature = ''; generation++; setNav();
  tasks = [task, ...tasks.filter(item => item.task_id !== task.task_id)];
  taskList(); showTask(task).catch(e => notice(e.message));
  notice('任务已创建，正在自动跟踪采集状态。');
}
async function refresh() {
  if (scope === 'reports') { await refreshReports(); return; }
  if (refreshing) return;
  refreshing = true;
  const token = generation;
  try {
    const data = await api('tasks');
    if (scope !== 'tasks' || token !== generation) return;
    tasks = data.items;
    if (!selectedTask && tasks.length) selectedTask = tasks[0].task_id;
    // A selected task can fall outside the latest 100 records.
    let task = tasks.find(item => item.task_id === selectedTask);
    if (!task && selectedTask) task = await api('tasks/' + selectedTask);
    if (scope !== 'tasks' || token !== generation) return;
    taskList();
    if (task) await showTask(task);
    else resetPreview('输入公告链接开始采集', 'MIIT / TASKS');
  } finally { refreshing = false; }
}
$('#capture').onsubmit = async event => {
  event.preventDefault();
  if (submitting) return;
  submitting = true;
  const url = $('#url').value.trim();
  if (!pendingCapture || pendingCapture.url !== url) pendingCapture = {url, idempotency_key: crypto.randomUUID()};
  $('#submit').disabled = true;
  notice('正在提交采集任务…');
  try {
    const task = await api('tasks', pendingCapture);
    pendingCapture = null; activateTask(task);
    await refresh().catch(e => notice('任务已创建，列表刷新失败：' + e.message));
  } catch (e) { notice('提交失败：' + e.message + '。可再次提交。'); }
  finally { submitting = false; $('#submit').disabled = false; }
};
document.querySelectorAll('[data-scope]').forEach(button => {
  button.onclick = () => {
    if (scope === button.dataset.scope) return;
    scope = button.dataset.scope; generation++; detailSignature = ''; setNav();
    resetPreview(scope === 'reports' ? '选择报告查看预览' : '加载任务…', scope.toUpperCase());
    notice('');
    refresh().catch(e => notice(e.message));
  };
});
$('#open-folder').onclick = async () => {
  const button = $('#open-folder'); button.disabled = true;
  try {
    if (scope === 'reports') await api('library/open-folder', {path: 'reports'});
    else if (selectedTask) await api('tasks/' + selectedTask + '/open-folder', {});
    notice('已在 Finder 中打开' + (scope === 'reports' ? ' reports/ 目录' : '当前任务产物目录'));
  } catch (e) { notice(e.message); } finally { button.disabled = scope === 'tasks' && !selectedTask; }
};
async function refreshReportCount() {
  const data = await api('library/tree?path=reports');
  $('#reports-count').textContent = data.file_count;
}
setTimeout(() => refreshReportCount().catch(e => notice(e.message)), 0);
$('#refresh').onclick = () => refresh().catch(e => notice(e.message));
setNav();
// Defer until library.js has initialized the Reports helpers.
setTimeout(() => refresh().catch(e => notice('任务读取失败：' + e.message)), 0);
setInterval(() => { if (scope === 'tasks' && !document.hidden) refresh().catch(e => notice('自动刷新失败：' + e.message)); }, 2000);
