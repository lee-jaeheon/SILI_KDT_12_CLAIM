async function apiFetch(url, options = {}) {
  const user = JSON.parse(sessionStorage.getItem('user') || 'null');
  if (user?.token) {
    options.headers = { 'Authorization': 'Bearer ' + user.token, ...(options.headers || {}) };
  }
  try {
    const res = await fetch(url, options);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      if (res.status === 401) {
        sessionStorage.removeItem('user');
        location.href = '/';
        return null;
      }
      console.error(`API 오류 [${res.status}]:`, err.detail || res.statusText);
      return null;
    }
    return await res.json();
  } catch (e) {
    console.error('네트워크 오류:', e);
    return null;
  }
}

// ── 서버 상태 실시간 표시 (footer-status) ─────────────────────
async function pollHealth() {
  const els = document.querySelectorAll('.footer-status');
  if (!els.length) return;

  let status = 'red', text = '서버 응답 없음';
  try {
    const res = await fetch('/health', { cache: 'no-store' });
    const data = await res.json();
    const c = data.checks || {};
    const failed = [];
    if (!c.db?.ok)     failed.push('DB');
    if (!c.ollama?.ok) failed.push('LLM');
    if (!c.model?.ok)  failed.push('모델');

    if (failed.length === 0) {
      status = 'green';
      text = '로컬 서버 · DB · LLM · 모델 정상';
    } else {
      status = 'yellow';
      text = `서버 정상 · ${failed.join('·')} 연결 안 됨`;
    }
  } catch { /* red 유지 */ }

  const color = { green: '#4caf50', yellow: '#ffa726', red: '#ef5350' }[status];
  els.forEach(el => {
    const dot = el.querySelector('.status-dot');
    if (dot) dot.style.background = color;
    // 점(span) 다음의 텍스트 노드만 교체
    let node = dot ? dot.nextSibling : el.firstChild;
    while (node && node.nodeType !== Node.TEXT_NODE) node = node.nextSibling;
    if (node) node.textContent = ' ' + text;
    else el.appendChild(document.createTextNode(' ' + text));
  });
}

// 페이지 로드 직후 1회 + 이후 30초마다
// (main.js는 페이지 하단에서 로드되므로 즉시 실행)
pollHealth();
setInterval(pollHealth, 30000);
