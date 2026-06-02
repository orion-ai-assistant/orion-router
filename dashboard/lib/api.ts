// lib/api.ts

export function getAdminKey(): string {
  if (typeof window === 'undefined') return '';
  return sessionStorage.getItem('adminKey') || '';
}

export function setAdminKey(key: string) {
  if (typeof window === 'undefined') return;
  if (key) {
    sessionStorage.setItem('adminKey', key);
  } else {
    sessionStorage.removeItem('adminKey');
  }
}

// Custom event to signal 401 Unauthorized globally
export const UNAUTHORIZED_EVENT = 'orion-unauthorized';

export async function adminFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const adminKey = getAdminKey();
  
  const headers = new Headers(options.headers || {});
  headers.set('X-Admin-Key', encodeURIComponent(adminKey));
  
  // Set default body type as JSON if it's an object and not FormData
  if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  
  const finalOptions: RequestInit = {
    ...options,
    headers,
  };

  try {
    const res = await fetch(url, finalOptions);
    if (res.status === 401) {
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
      }
      throw new Error('Unauthorized');
    }
    return res;
  } catch (err: any) {
    if (err.message !== 'Unauthorized') {
      console.error(`Fetch error on ${url}:`, err);
    }
    throw err;
  }
}
