// MarkdownPreview.jsx reused from mashang-fetch (ReactMarkdown + remark-gfm).
import React from 'react';
import {createRoot} from 'react-dom/client';
import MarkdownPreview from './MarkdownPreview.jsx';
window.renderLibraryMarkdown = (element, content) => {
  const root = createRoot(element);
  root.render(React.createElement(MarkdownPreview, {content}));
  return () => root.unmount();
};
