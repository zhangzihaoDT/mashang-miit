// Interaction structure references mashang-fetch FetchBar/FileSidebar/PreviewPane.
const $ = s => document.querySelector(s);
let scope = 'inbox', activeTask = null, generation = 0;
const node = (tag, value, cls) => { const n = document.createElement(tag); n.textContent = value; if (cls) n.className = cls; return n; };
async function api(path, body) {
  const response = await fetch('/api/miit/' + path, body ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {});
  const data = await response.json(); if (!response.ok) throw Error(data.message); return data;
}
function notice(message) { $('#notice').textContent = message; }
function showTask(task) {
  activeTask = task.task_id;
  const box = $('#preview'); box.replaceChildren(node('h2', '采集任务'), node('p', task.task_id), node('p', task.status), node('p', task.url));
  if (task.error) box.append(node('pre', JSON.stringify(JSON.parse(task.error), null, 2)));
  if (task.retry_of) box.append(node('p', '重试自：' + task.retry_of));
  if (task.status === 'failed' || task.status === 'partial_success') {
    const retry = node('button', '重新采集'); retry.onclick = async () => { retry.disabled = true; try {await api('tasks/' + task.task_id + '/retry', {idempotency_key: crypto.randomUUID()}); await refresh();} catch(e) {notice(e.message);} finally {retry.disabled = false;} }; box.append(retry);
  }
  if (task.candidate_id) { const open = node('button','查看候选'); open.onclick = () => showCandidate(task.candidate_id).catch(e => notice(e.message)); box.append(open); }
}
async function showCandidate(id) {
  activeTask = null; const token = ++generation; const data = await api('candidates/' + id); if (token !== generation) return;
  const p = data.payload, box = $('#preview'); box.replaceChildren(node('span', '待核验 · revision ' + data.revision, 'eyebrow'), node('h2', '第 ' + p.batch_no + ' 批 · 正式公告'), node('p', p.rows.length + ' 条来源记录 / ' + p.issues.length + ' 条记录需处理 · ' + (p.capture_mode === 'archive_replay' ? '历史证据回放' : '实时采集')));
  const source = node('a', '打开官方来源'); source.href = p.source_url; source.target='_blank'; source.rel='noreferrer'; box.append(source);
  box.append(node('p', '官方阶段：' + p.stage + '；核验状态：' + data.review_status), node('p', '内容摘要：' + data.content_hash, 'hash'));
  const tabs = node('div', '', 'tabs'), content = node('div');
  const structured = node('button','结构化数据'); structured.onclick = () => {content.replaceChildren(node('pre',JSON.stringify(p.rows, null, 2)));}; tabs.append(structured);
  const issues = node('button','质量问题'); issues.onclick = () => content.replaceChildren(node('pre', JSON.stringify(p.issues, null, 2))); tabs.append(issues);
  for (const evidence of data.evidence) {
    const button = node('button', '原文 · ' + evidence.metadata.name);
    button.onclick = async () => { try {
      if (evidence.metadata.kind === 'doc') { const a = node('a','下载原始附件'); a.href='/api/miit/evidence/' + evidence.evidence_id; a.download='road.doc'; content.replaceChildren(a); return; }
      const response = await fetch('/api/miit/evidence/' + evidence.evidence_id); if (!response.ok) throw Error('证据读取失败'); content.replaceChildren(node('pre', await response.text()));
    } catch(e) {notice(e.message);} }; tabs.append(button);
  }
  box.append(tabs, content); structured.click();
}
async function refresh() {
  const current = scope;
  if (scope === 'library') { $('#list').replaceChildren(node('p','核验入库后将在此展示。')); $('#count').textContent = '资料库'; return; }
  const data = await api(scope === 'tasks' ? 'tasks' : 'inbox'); if (current !== scope) return;
  $('#count').textContent = (scope === 'tasks' ? '最近任务 ' : '待核验候选 ') + data.items.length + ' / 最多 100';
  if (scope === 'tasks' && activeTask) { const task = data.items.find(t => t.task_id === activeTask); if (task) showTask(task); }
  const list = $('#list'); list.replaceChildren();
  if (!data.items.length) list.append(node('p','暂无记录。'));
  for (const item of data.items) {
    const button = node('button', '', 'item'); button.append(node('strong', scope === 'tasks' ? item.status : '待核验候选'), node('small', item.task_id.slice(0,12) + ' · ' + new Date(item.created_at).toLocaleString()));
    button.onclick = () => { generation++; activeTask = null; if(scope === 'tasks') showTask(item); else showCandidate(item.candidate_id).catch(e=>notice(e.message)); }; list.append(button);
  }
}
$('#capture').onsubmit = async e => {e.preventDefault(); $('#submit').disabled = true; try {const task = await api('tasks',{url:$('#url').value.trim(), idempotency_key:crypto.randomUUID()}); notice('任务已创建：' + task.task_id); scope='tasks'; setNav(); await refresh(); showTask(task);} catch(e) {notice(e.message);} finally {$('#submit').disabled=false;} };
function setNav() {document.querySelectorAll('[data-scope]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.scope===scope)));}
document.querySelectorAll('[data-scope]').forEach(b => b.onclick=()=>{scope=b.dataset.scope; activeTask = null; generation++; setNav(); $('#preview').replaceChildren(node('h2',scope==='library'?'资料库将在核验入库后开放':'选择记录查看预览')); refresh().catch(e=>notice(e.message));});
$('#refresh').onclick = () => refresh().catch(e=>notice(e.message));
refresh().catch(e=>notice(e.message));
setInterval(()=>refresh().catch(e=>notice(e.message)),3000);
