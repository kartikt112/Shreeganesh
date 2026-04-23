import axios from 'axios';

// Backend origin (e.g. "https://backend-production.up.railway.app").
// Empty string = same-origin / Vite dev proxy.
const rawBackend = (import.meta.env.VITE_BACKEND_URL || '').trim();
const backendOrigin = rawBackend.replace(/\/+$/, '');

// Axios baseURL always points at the backend's /api/ prefix.
const apiBase = backendOrigin ? `${backendOrigin}/api/` : '/api/';

const api = axios.create({
    baseURL: apiBase,
    headers: {
        'Content-Type': 'application/json',
    },
});

api.interceptors.request.use(config => {
    // Requests call api.get('/admin/rfqs') — strip the leading slash so
    // it resolves against the baseURL's /api/ prefix, not the origin root.
    if (config.url && config.url.startsWith('/')) {
        config.url = config.url.substring(1);
    }
    return config;
});

// Build an absolute URL on the backend for non-API assets (images, downloads).
// If VITE_BACKEND_URL is unset, returns a relative path so the dev proxy / same-origin deploy handles it.
export function backendUrl(path = '') {
    const p = path.startsWith('/') ? path : `/${path}`;
    return `${backendOrigin}${p}`;
}

export const balloonEditorUrl = (import.meta.env.VITE_BALLOON_EDITOR_URL || '').trim().replace(/\/+$/, '');

export default api;
