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
