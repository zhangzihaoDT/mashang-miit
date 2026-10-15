// Read-only adaptation of mashang-fetch FileSidebar / PreviewPane / PreviewBody.
// Real directories replace Fetch's flat directory groups; expansion and selection persist on refresh.
const reportsExpanded = new Set();
let reportSelection = null, reportsTreeGeneration = 0, disposeMarkdown = null;
const libraryUrl = path => '/api/miit/library/file/' + path.split('/').map(encodeURIComponent).join('/');
const formatSize = size => size < 1024 ? size + ' B' : (size / 1024).toFixed(1) + ' KiB';
async function refreshReports() {
  const version = ++reportsTreeGeneration;
  const tree = node('div', '', 'file-tree');
  $('#count').textContent = 'reports/ · 报告文件';
  async function populate(container, path) {
    const data = await api('library/tree?path=' + encodeURIComponent(path));
    if (version !== reportsTreeGeneration || scope !== 'reports') return;
    container.replaceChildren();
    if (!data.items.length) container.append(node('small', '空文件夹'));
    for (const file of data.items) {
      if (file.directory) {
        const details = document.createElement('details'), summary = node('summary', file.name);
        const children = node('div', '', 'folder-children');
        details.append(summary, children); container.append(details);
        details.open = reportsExpanded.has(file.path);
        let loadPromise = null;
        const load = () => {
          if (!loadPromise) loadPromise = populate(children, file.path).catch(e => {
            children.replaceChildren(node('p',e.message)); loadPromise = null;
          });
          return loadPromise;
        };
        details.addEventListener('toggle', () => {
          if(details.open) {reportsExpanded.add(file.path); load();}
          else reportsExpanded.delete(file.path);
        });
        if(details.open) {await load();}
      } else {
        const button = node('button', file.name, 'file-main'); button.title = file.path;
        button.dataset.filePath = file.path;
        button.setAttribute('aria-pressed', String(file.path === reportSelection));
        button.append(node('small', formatSize(file.size)));
        button.onclick = () => showReportFile(file.path).catch(e => notice(e.message));
        container.append(button);
      }
    }
  }
  await populate(tree, 'reports');
  if(version === reportsTreeGeneration && scope === 'reports') $('#list').replaceChildren(tree);
}
async function showReportFile(path) {
  const token = ++generation;
  reportSelection = path;
  document.querySelectorAll('[data-file-path]').forEach(b => b.setAttribute('aria-pressed',String(b.dataset.filePath === path)));
  const box = $('#preview'); box.className = 'task-preview'; box.replaceChildren(node('p','加载中…'));
  const p = await api('library/preview?path=' + encodeURIComponent(path));
  if(token !== generation || scope !== 'reports') return;
  if(disposeMarkdown) {disposeMarkdown(); disposeMarkdown = null;}
  box.replaceChildren(node('h2', p.name), node('p', p.path, 'hash'), node('p', formatSize(p.size) + ' · 修改于 ' + new Date(p.mtime * 1000).toLocaleString()));
  const actions = node('div', '', 'detail-actions');
  const download = node('a', '下载原文件'); download.href = libraryUrl(path) + '?download=1'; download.download = p.name;
  const open = node('button', '本地打开'); open.onclick = async () => {open.disabled = true; try {await api('library/open',{path}); notice('已交给本地默认应用打开');} catch(e) {notice(e.message);} finally {open.disabled = false;}};
  actions.append(download, open); box.append(actions);
  if(p.message) box.append(node('p',p.message));
  const content = node('div', '', 'preview-content'); box.append(content);
  if(p.kind === 'html') {
    const frame = document.createElement('iframe'); frame.title = p.name; frame.setAttribute('sandbox',''); frame.src = libraryUrl(path); frame.className = 'html-preview'; content.append(frame);
  } else if(p.kind === 'image') {
    const img = document.createElement('img'); img.alt = p.name; img.src = libraryUrl(path); img.className = 'image-preview'; content.append(img);
  } else if(p.kind === 'markdown') {
    disposeMarkdown = window.renderLibraryMarkdown(content, p.content);
  } else if(p.kind === 'table') {
    if(p.truncated) content.append(node('p','预览前 500 行；下载原文件可获取完整数据。'));
    const wrap = node('div','','table-wrap'), table = document.createElement('table');
    const head = document.createElement('thead'), hr = document.createElement('tr');
    p.header.forEach(value => hr.append(node('th',value))); head.append(hr); table.append(head);
    const body = document.createElement('tbody');
    p.rows.forEach(row => {const tr = document.createElement('tr'); row.forEach(value => tr.append(node('td',value))); body.append(tr);});
    table.append(body); wrap.append(table); content.append(wrap);
  } else if(p.content !== undefined) content.append(node('pre',p.content));
  notice('报告来自 reports/ 下的现有文件。');
}
