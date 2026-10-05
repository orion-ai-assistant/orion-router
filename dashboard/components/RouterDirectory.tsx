'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { safeRouterDashboard } from '@/lib/router-navigation';

type Peer = { id: string; name: string; url: string; current: boolean; conflict?: boolean };
const SELECTION_KEY = 'orion.router.selected-id';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function shortName(name: string) {
  return name.replace(/\s*[—–-]\s*Orion Router$/i, '').replace(/^Orion Router\s*[—–-]\s*/i, '').trim().slice(0, 40) || 'Router';
}

export default function RouterDirectory({ locale, onCurrentSelection }: {
  locale: string; onCurrentSelection: (ready: boolean) => void;
}) {
  const [peers, setPeers] = useState<Peer[]>([]);
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const selectedId = useRef('');
  const knownIds = useRef<Set<string> | null>(null);
  const inFlight = useRef(false);
  const alive = useRef(false);
  const request = useRef<AbortController | null>(null);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tr = locale.startsWith('tr');

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    const started = Date.now();
    request.current = new AbortController();
    try {
      const response = await fetch('/dashboard/api/routers/browse', {
        credentials: 'omit', redirect: 'error', referrerPolicy: 'no-referrer', cache: 'no-store',
        signal: request.current.signal,
      });
      if (!response.ok) throw new Error();
      const data = await response.json();
      if (!Array.isArray(data.routers)) throw new Error();
      const found: Peer[] = data.routers.filter((peer: Peer) => UUID.test(peer.id) && typeof peer.name === 'string'
        && (peer.conflict || safeRouterDashboard(peer.url)));
      if (data.current && UUID.test(data.current.id) && typeof data.current.name === 'string') {
        const existing = found.find(peer => peer.id === data.current.id);
        if (!existing) found.unshift({id: data.current.id, name: data.current.name,
          url: `${window.location.origin}/dashboard`, current: true});
      }
      if (!alive.current) return;
      if (knownIds.current && found.some(peer => !knownIds.current!.has(peer.id))) {
        setNotice(tr ? 'Yeni Router bulundu.' : 'New Router found.');
        if (noticeTimer.current) clearTimeout(noticeTimer.current);
        noticeTimer.current = setTimeout(() => setNotice(''), 3000);
      }
      knownIds.current = new Set(found.map(peer => peer.id));
      setPeers(found);
      // A prior UUID remains selected even when missing. Never choose its replacement.
      if (!selectedId.current) {
        const available = found.filter(peer => !peer.conflict);
        const first = available.length === 1 ? available[0] : undefined;
        if (first) {
          selectedId.current = first.id;
          setSelected(first.id);
          try { localStorage.setItem(SELECTION_KEY, first.id); } catch { /* Optional storage. */ }
        }
      }
      const choice = found.find(peer => peer.id === selectedId.current && !peer.conflict);
      onCurrentSelection(Boolean(choice?.current));
    } catch {
      if (alive.current) setNotice(tr ? 'Router araması tamamlanamadı.' : 'Router discovery failed.');
    } finally {
      await new Promise(resolve => setTimeout(resolve, Math.max(0, 1000 - (Date.now() - started))));
      inFlight.current = false;
      if (alive.current) setBusy(false);
    }
  }, [tr, onCurrentSelection]);

  useEffect(() => {
    alive.current = true;
    onCurrentSelection(false);
    try {
      const saved = localStorage.getItem(SELECTION_KEY);
      if (saved && UUID.test(saved)) { selectedId.current = saved; setSelected(saved); }
    } catch { /* Optional storage. */ }
    queueMicrotask(() => { if (alive.current) void refresh(); });
    const interval = setInterval(() => void refresh(), 10000);
    return () => {
      alive.current = false;
      request.current?.abort();
      clearInterval(interval);
      if (noticeTimer.current) clearTimeout(noticeTimer.current);
    };
  }, [refresh, onCurrentSelection]);

  function choose(id: string) {
    const peer = peers.find(candidate => candidate.id === id && !candidate.conflict);
    if (!peer) return;
    selectedId.current = id;
    setSelected(id);
    try { localStorage.setItem(SELECTION_KEY, id); } catch { /* Optional storage. */ }
    onCurrentSelection(peer.current);
    if (!peer.current) {
      const url = safeRouterDashboard(peer.url);
      if (url) window.location.assign(url); // Explicit selection; no credentials are forwarded.
    }
  }
  const missing = selected && !peers.some(peer => peer.id === selected && !peer.conflict);
  return <div className="mt-5 pt-4 border-t border-zinc-800">
    <div className="flex items-center justify-between mb-2">
      <span id="router-selection-label" className="text-xs text-zinc-400">{tr ? 'Bağlanılacak Router' : 'Router to connect'}</span>
      <button type="button" onClick={() => void refresh()} disabled={busy}
        aria-label={tr ? 'Router listesini yenile' : 'Refresh Routers'} title={tr ? 'Yenile' : 'Refresh'}
        className="p-1 text-zinc-400 hover:text-white disabled:opacity-60">
        <RefreshCw className={`h-3.5 w-3.5 ${busy ? 'animate-spin' : ''}`} />
      </button>
    </div>
    <select aria-labelledby="router-selection-label" value={selected} onChange={event => choose(event.target.value)}
      className="w-full h-9 bg-zinc-900 border border-zinc-800 rounded-md px-3 text-sm text-white outline-none focus:border-zinc-600">
      {!selected && <option value="" disabled>{tr ? 'Router seçin' : 'Choose Router'}</option>}
      {missing && <option value={selected} disabled>{tr ? 'Seçili Router bulunamadı' : 'Selected Router unavailable'}</option>}
      {peers.map(peer => <option key={peer.id} value={peer.id} disabled={peer.conflict}>{shortName(peer.name)}</option>)}
    </select>
    {notice && <p className="text-xs text-zinc-500 mt-2" role="status">{notice}</p>}
  </div>;
}
