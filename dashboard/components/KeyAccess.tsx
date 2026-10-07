'use client';

import { useEffect, useState } from 'react';
import { useApp } from '@/components/AppContext';
import { adminFetch } from '@/lib/api';

type Key = {id: string; name: string; hub_name?: string; hub_id?: string};
type Candidate = {id: string; provider: string; label: string; source: string; layer_a: boolean; layer_b: boolean; allowed: boolean; reason?: string};
export function ownerLabel(key: Key) {
  return key.hub_name ? `${key.hub_name} [${key.hub_id?.slice(0,8)}] · ${key.name}` : key.name;
}
async function read(path: string) {
  const res = await adminFetch(path);
  if (!res.ok) throw new Error('İşlem tamamlanamadı.');
  return res.json();
}

export function KeyAccess({id, kind}: {id: string; kind: 'provider' | 'virtual'}) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [keys, setKeys] = useState<Key[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const path = `/dashboard/api/${kind === 'provider' ? 'provider-key-pool' : 'keys'}/${id}/access`;
  async function load() {
    try {
      const data = await read(path);
      setMode(data.scope || data.mode); setSelected(data.selected); setCandidates(data.keys || []);
      if (kind === 'provider') setKeys((await read('/dashboard/api/keys')).keys);
      setOpen(true); setMessage('');
    } catch { setMessage('İzinler alınamadı.'); }
  }
  async function save() {
    setBusy(true);
    try {
      const res = await adminFetch(path, {method:'PUT',body:JSON.stringify({[kind === 'provider' ? 'scope' : 'mode']:mode,selected})});
      if (!res.ok) throw new Error();
      await load(); setMessage('Kaydedildi.');
    } catch { setMessage('İzinler kaydedilemedi.'); }
    finally { setBusy(false); }
  }
  function toggle(target: string) { setSelected(prev => prev.includes(target) ? prev.filter(x => x !== target) : [...prev,target]); }
  function row(c: Candidate) {
    return <div key={c.id} className="my-2"><label><input type="checkbox" checked={mode === 'unrestricted' || selected.includes(c.id)} disabled={mode !== 'only_selected' || !c.layer_a} onChange={() => toggle(c.id)}/> {c.provider} · {c.label} [{c.id.slice(0,8)}]</label>
      {c.reason && <p className="text-sm text-zinc-400">{c.reason} {!c.layer_a && c.source === 'shared' && <a href={`/dashboard/key-pool#${c.id}`} className="underline">Sağlayıcı anahtarı ekranından değiştir</a>}</p>}</div>;
  }
  return <div className="my-2 text-sm"><button type="button" onClick={() => open ? setOpen(false) : load()} className="underline">Anahtar izinleri</button>
    {open && <div className="p-3 border rounded my-2 text-left">
      <select aria-label="İzin kapsamı" value={mode} onChange={e => setMode(e.target.value)} className="bg-zinc-900 p-2">
        {kind === 'provider' ? <><option value="all">Tümü</option><option value="selected">Seçili sanal anahtarlar</option></> : <><option value="unrestricted">Kısıtsız</option><option value="only_selected">Yalnız seçilen sağlayıcı anahtarları</option></>}
      </select>
      <p className="my-2">{kind === 'provider' ? (mode === 'all' ? 'Yeni oluşturulan sanal anahtarlara otomatik açık.' : 'Yeni oluşturulan sanal anahtarlara otomatik kapalı.') : (mode === 'unrestricted' ? 'Sağlayıcı anahtarının izni her zaman geçerlidir.' : 'Yeni sağlayıcı anahtarlarına otomatik kapalı.')}</p>
      {kind === 'provider' ? <>{mode === 'selected' && keys.map(k => <label key={k.id} className="block my-1"><input type="checkbox" checked={selected.includes(k.id)} onChange={() => toggle(k.id)}/> {ownerLabel(k)}</label>)}{mode === 'selected' && !selected.length && <p role="alert">Hiçbir sanal anahtar bu sağlayıcı anahtarını kullanamayacak.</p>}</> : <>
        <h3>Kullanabildiği sağlayıcı anahtarları</h3>{candidates.filter(c => c.allowed).map(row)}
        <details><summary>Kullanamadığı sağlayıcı anahtarları</summary>{candidates.filter(c => !c.allowed).map(row)}</details>
      </>}
      <button type="button" onClick={save} disabled={busy} className="border rounded px-3 py-1 mt-2">İzinleri kaydet</button>
    </div>}<p role="status">{message}</p></div>;
}

type Bucket = {capability: string; usage_unit?: string; usage_amount?: number; day?: string; requests: number; input: number|null; output: number|null; thoughts: number|null; total: number|null; cost: number|null; succeeded: number; failed: number; missing_usage: number; missing_cost: number};
export function KeyUsage({id}: {id: string}) {
  const [data,setData] = useState<{totals: Bucket[]; daily: Bucket[]} | null>(null);
  const [start,setStart] = useState(''); const [end,setEnd] = useState('');
  const [message,setMessage] = useState('');
  async function load() {
    const params = new URLSearchParams({key_id:id});
    if(start) params.set('start',`${start}T00:00:00Z`);
    if(end) params.set('end',`${end}T00:00:00Z`);
    try {setData(await read('/dashboard/api/usage?'+params));setMessage('');} catch {setMessage('İstatistikler alınamadı.');}
  }
  useEffect(() => {void load();}, [id]);
  const max = Math.max(1,...(data?.daily.map(x=>x.requests) || []));
  return <div className="text-sm my-3"><h3>Kullanım · tüm kayıtlar · UTC</h3>
    <label>Başlangıç <input type="date" value={start} onChange={e=>setStart(e.target.value)}/></label>
    <label>Bitiş (hariç) <input type="date" value={end} onChange={e=>setEnd(e.target.value)}/></label><button type="button" onClick={load}>Filtrele</button>
    {data?.totals.map(b=><p key={`${b.capability}-${b.usage_unit}`}>{b.capability} · {b.requests} istek · {b.succeeded} başarılı · {b.failed} başarısız · Giriş: {b.input ?? 'bilgi yok'} · Çıkış: {b.output ?? 'bilgi yok'} · Düşünme: {b.thoughts ?? 'bilgi yok'} · Birim: {b.usage_unit ?? 'bilgi yok'} · Toplam: {(b.usage_unit === 'second' ? b.usage_amount : b.total) ?? 'bilgi yok'} · Maliyet: {b.cost == null ? 'bilgi yok' : `$${b.cost}`} {b.missing_usage > 0 && `· ${b.missing_usage} kayıtta token bilgisi yok`} {b.missing_cost > 0 && `· ${b.missing_cost} kayıtta maliyet yok`}</p>)}
    <div aria-label="Günlük istek grafiği">{data?.daily.map(b=><div key={`${b.day}-${b.capability}-${b.usage_unit}`} className="my-1"><span>{b.day} · {b.capability} · {b.requests}</span><div className="h-2 bg-purple-400" style={{width:`${b.requests/max*100}%`}}/></div>)}</div><p role="alert">{message}</p>
  </div>;
}

export function HubManagement() {
  const [hubs,setHubs] = useState<(Key & {is_active:boolean})[]>([]);
  const [accounts,setAccounts] = useState<(Key & {is_active:boolean})[]>([]);
  const [message,setMessage] = useState('');
  async function load(){try{const [hubData,keyData]=await Promise.all([read('/dashboard/api/hubs'),read('/dashboard/api/keys')]);setHubs(hubData.hubs);setAccounts(keyData.keys);}catch{setMessage('Hub listesi alınamadı.');}}
  useEffect(()=>{void load();},[]);
  return <details className="my-4 border rounded p-3"><summary>Bağlı Hub yönetimi</summary>{hubs.map(h=><div key={h.id} className="my-2">{h.name} [{h.id.slice(0,8)}] · {h.is_active ? 'Etkin' : 'Pasif'} <button type="button" className="underline" onClick={async()=>{try{const r=await adminFetch(`/dashboard/api/hubs/${h.id}`,{method:'PUT',body:JSON.stringify({is_active:!h.is_active})});if(!r.ok)throw new Error();await load();}catch{setMessage('Hub güncellenemedi.');}}}>{h.is_active ? 'Pasifleştir' : 'Etkinleştir'}</button>
    <details className="ml-4"><summary>Bu Hub’ın sanal anahtarları</summary>{accounts.filter(k=>k.hub_id===h.id).map(k=><p key={k.id}><a className="underline" href={`#${k.id}`}>{ownerLabel(k)}</a> · {k.is_active?'Etkin':'Pasif'}</p>)}</details>
  </div>)}<p role="alert">{message}</p></details>;
}

export function PersonalKeyManagement() {
  const {adminKey} = useApp();
  useEffect(()=>{setSecret('');setEditing('');},[adminKey]);
  const [keys,setKeys]=useState<(Key & {provider:string; label:string; is_active:boolean})[]>([]);
  const [secret,setSecret]=useState(''); const [editing,setEditing]=useState(''); const [message,setMessage]=useState('');
  async function load(){try{setKeys((await read('/dashboard/api/personal-provider-keys')).keys);}catch{setMessage('Kişisel kayıtlar alınamadı.');}}
  useEffect(()=>{void load();},[]);
  async function change(id:string,method:string,body?:object){try{const r=await adminFetch(`/dashboard/api/personal-provider-keys/${id}`,{method,body:body?JSON.stringify(body):undefined});if(!r.ok)throw new Error();await load();}catch{setMessage('İşlem tamamlanamadı.');}}
  return <details className="my-4 border rounded p-3"><summary>Kişisel sağlayıcı anahtarları</summary>{keys.map(k=><div key={k.id} className="my-3">{ownerLabel(k)} · {k.provider} · {k.label} · {k.is_active?'Etkin':'Pasif'} <button type="button" className="underline mx-2" onClick={()=>change(k.id,'PUT',{is_active:!k.is_active})}>{k.is_active?'Pasifleştir':'Etkinleştir'}</button><button type="button" className="underline mx-2" onClick={()=>{setSecret('');setEditing(k.id);}}>Yeni değer yaz</button><button type="button" className="underline" onClick={()=>change(k.id,'DELETE')}>Sil</button></div>)}
    {editing && <form onSubmit={e=>{e.preventDefault();const value=secret;setSecret('');setEditing('');void change(editing,'PUT',{api_key:value});}}><input type="password" autoComplete="off" aria-label="Yeni kişisel anahtar" value={secret} onChange={e=>setSecret(e.target.value)} required/><button>Güncelle</button><button type="button" onClick={()=>{setEditing('');setSecret('');}}>İptal</button></form>}<p role="alert">{message}</p></details>;
}
