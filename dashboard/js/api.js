// services/router/dashboard/js/api.js

export function getAdminKey() {
    return sessionStorage.getItem('adminKey') || '';
}

export function setAdminKey(key) {
    if (key) {
        sessionStorage.setItem('adminKey', key);
    } else {
        sessionStorage.removeItem('adminKey');
    }
}

export async function adminFetch(url, options = {}) {
    const adminKey = getAdminKey();
    options.headers = options.headers || {};
    options.headers['X-Admin-Key'] = adminKey;

    try {
        const res = await fetch(url, options);
        if (res.status === 401) {
            // Because this is bound to the Vue instance, 'this' refers to the Vue component.
            if (this && typeof this === 'object') {
                this.showLogin = true;
            }
            throw new Error('Unauthorized');
        }
        return res;
    } catch (err) {
        if (err.message !== 'Unauthorized') {
            console.error(`Fetch error on ${url}:`, err);
        }
        throw err;
    }
}
