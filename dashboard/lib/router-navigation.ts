// Discovery is navigation only. Never attach credentials or infer TLS trust.
export function safeRouterDashboard(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  try {
    const url = new URL(value);
    if (url.username || url.password || url.search || url.hash || url.pathname !== '/dashboard') return null;
    const loopback = url.hostname === 'localhost' || url.hostname === '127.0.0.1';
    const octets = url.hostname.split('.').map(Number);
    const ipv4 = /^\d+\.\d+\.\d+\.\d+$/.test(url.hostname) && octets.every(n => n >= 0 && n <= 255);
    const lan = ipv4 && (octets[0] === 10 || (octets[0] === 192 && octets[1] === 168)
      || (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31));
    if (url.protocol === 'https:' && (lan || loopback)) return url.href;
    if (url.protocol === 'http:' && loopback && url.port === '20128') return url.href;
  } catch { /* Invalid URL cannot become a link. */ }
  return null;
}
