async function apiFetch(url, options = {}) {
  try {
    const res = await fetch(url, options);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      console.error(`API 오류 [${res.status}]:`, err.detail || res.statusText);
      return null;
    }
    return await res.json();
  } catch (e) {
    console.error('네트워크 오류:', e);
    return null;
  }
}
