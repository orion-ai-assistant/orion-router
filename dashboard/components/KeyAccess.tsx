'use client';

import { useEffect, useRef, useState, ReactNode } from 'react';
import { useApp } from '@/components/AppContext';
import { adminFetch } from '@/lib/api';
import { summarizeUsage, UsageBucket } from '@/lib/usage';
import { DailyRequestsChart } from '@/components/DailyRequestsChart';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select';
import { ChevronDown, ShieldCheck, Network, Activity, Check } from 'lucide-react';

type Key = {id: string; name: string; hub_name?: string; hub_id?: string};
type Candidate = {id: string; provider: string; label: string; source: string; layer_a: boolean; layer_b: boolean; allowed: boolean; reason?: string};
export function ownerLabel(key: Key) {
  return key.hub_name ? `${key.hub_name} · ${key.name}` : key.name;
}
async function read(path: string) {
  const res = await adminFetch(path);
  if (!res.ok) throw new Error();
  return res.json();
}
const panel = 'rounded-xl border border-zinc-800 bg-black/20';
export function Status({active}: {active: boolean}) {
  const {t} = useApp();
  return <Badge className={active ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-400' : 'border-zinc-700 bg-zinc-800 text-zinc-400'}>{active ? 'Active' : 'Inactive'}</Badge>;
}
function Disclosure({title, icon, open, onClick}: {title: string; icon: ReactNode; open: boolean; onClick: () => void}) {
  return <Button type="button" variant="ghost" aria-expanded={open} onClick={onClick} className="h-auto w-full justify-between gap-3 whitespace-normal p-4 text-left text-zinc-200"><span className="flex items-center gap-2">{icon}{title}</span><ChevronDown className={`size-4 transition-transform ${open ? 'rotate-180' : ''}`}/></Button>;
}
function PermissionCheckbox({checked, disabled, onChange}: {checked:boolean;disabled?:boolean;onChange:()=>void}) {
  return <span className={`relative mt-0.5 flex size-4 shrink-0 items-center justify-center rounded border ${checked?'border-purple-400 bg-purple-400 text-zinc-950':'border-zinc-600 bg-zinc-950'} ${disabled?'opacity-40':''}`}><input type="checkbox" checked={checked} disabled={disabled} onChange={onChange} className="absolute inset-0 size-full cursor-pointer opacity-0 focus-visible:opacity-50"/>{checked && <Check className="pointer-events-none size-3"/>}</span>;
}
export type AccessDraft = {mode: string; selected: string[]};
export function KeyAccess({id, kind, value, onChange}: {
  id?: string; kind: 'provider'|'virtual'; value: AccessDraft|null; onChange: (value: AccessDraft)=>void;
}) {
  const {t} = useApp();
  const [open,setOpen]=useState(false);
  const [keys,setKeys]=useState<Key[]>([]);
  const [candidates,setCandidates]=useState<Candidate[]>([]);
  const [search,setSearch]=useState('');
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(true);
  useEffect(()=>{
    let current=true;
    setBusy(true);
    async function load() {
      try {
        const data=id ? await read(`/dashboard/api/${kind==='provider'?'provider-key-pool':'keys'}/${id}/access`)
          : kind==='virtual' ? await read('/dashboard/api/keys/access-options') : {scope:'all',selected:[]};
        const accounts=kind==='provider' ? (await read('/dashboard/api/keys')).keys : [];
        if(!current)return;
        onChange({mode:data.scope || data.mode,selected:data.selected});
        setCandidates(data.keys || []);setKeys(accounts);setMessage('');
      } catch {if(current)setMessage(t('access.loadError'));}
      finally {if(current)setBusy(false);}
    }
    void load();
    return()=>{current=false;};
  },[id,kind]);
  const mode=value?.mode || (kind==='provider'?'all':'unrestricted');
  const selected=value?.selected || [];
  const restricted=mode==='selected' || mode==='only_selected';
  const options=kind==='provider'?['all','selected']:['unrestricted','only_selected'];
  const matches=(label:string)=>label.toLocaleLowerCase().includes(search.toLocaleLowerCase());
  const toggle=(target:string)=>onChange({mode,selected:selected.includes(target)?selected.filter(x=>x!==target):[...selected,target]});
  return <div className={panel}>
    <Disclosure title={t('access.title')} icon={<ShieldCheck className="size-4 text-purple-400"/>} open={open} onClick={()=>setOpen(!open)}/>
    {open && <div className="space-y-4 border-t border-zinc-800 p-4 text-sm">
      {busy ? <p className="text-xs text-zinc-400">{t('common.loading')}</p> : <>
        <div className="flex flex-wrap items-center gap-3">
          <Select value={mode} onValueChange={next=>{if(next)onChange({mode:next,selected});}}>
            <SelectTrigger aria-label={t('access.title')} className="h-10 min-w-0 flex-1 bg-zinc-900"><SelectValue>{t('access.'+mode)}</SelectValue></SelectTrigger>
            <SelectContent>{options.map(option=><SelectItem key={option} value={option}>{t('access.'+option)}</SelectItem>)}</SelectContent>
          </Select>
          {restricted && <span className="text-xs text-zinc-400">{t('access.selectionCount',{count:selected.length})}</span>}
        </div>
        <p className="text-xs leading-relaxed text-zinc-400">{t(kind==='provider'?(restricted?'access.futureClosed':'access.futureOpen'):'access.providerRule')}</p>
        {(kind==='virtual' || restricted) && <Input aria-label={t('access.search')} placeholder={t('access.search')} value={search} onChange={e=>setSearch(e.target.value)}/>}
        {kind==='provider' ? restricted && <div className="max-h-60 space-y-2 overflow-y-auto [color-scheme:dark]">
          {keys.filter(k=>matches(ownerLabel(k))).map(k=><label key={k.id} className="flex cursor-pointer items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
            <PermissionCheckbox checked={selected.includes(k.id)} onChange={()=>toggle(k.id)}/><span className="break-words">{ownerLabel(k)}</span>
          </label>)}
        </div> : <div className="max-h-72 space-y-2 overflow-y-auto [color-scheme:dark]">
          {candidates.filter(c=>matches(c.provider+' '+c.label)).map(c=><label key={c.id} className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
            <PermissionCheckbox checked={!restricted || selected.includes(c.id)} disabled={!restricted || !c.layer_a} onChange={()=>toggle(c.id)}/>
            <span className="flex min-w-0 flex-1 flex-wrap items-center gap-2"><Badge variant="outline">{c.provider}</Badge><span>{c.label}</span>
              {c.reason && c.reason!=='Bu sanal anahtarın kısıtı dışında' && <span className="text-xs text-amber-400">{c.reason}</span>}
            </span>
          </label>)}
        </div>}
        {restricted && !selected.length && <p role="alert" className="rounded-lg bg-amber-500/10 p-3 text-xs text-amber-400">{t('access.noneSelected')}</p>}
      </>}
    </div>}
    {message && <p role="alert" className="px-4 pb-3 text-xs text-red-400">{message}</p>}
  </div>;
}

export function KeyUsage({id='', provider='', hubId='', embedded=false}: {id?: string; provider?: string; hubId?: string; embedded?: boolean}) {
  const {t,locale} = useApp();
  const [data,setData] = useState<{totals: UsageBucket[]; daily: UsageBucket[]} | null>(null);
  const [start,setStart] = useState(''); const [end,setEnd] = useState('');
  const [range,setRange] = useState('all');
  function preset(days:number, label:string) {
    setRange(label);
    if(!days){setStart('');setEnd('');return;}
    const endDate=new Date(),startDate=new Date();startDate.setDate(startDate.getDate()-days+1);
    const date=(d:Date)=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    setStart(date(startDate));setEnd(date(endDate));
  }
  const [message,setMessage] = useState(''); const [busy,setBusy] = useState(false);
  const [open,setOpen] = useState(true);
  const sequence = useRef(0);
  async function load() {
    const seq = ++sequence.current;
    if(start && end && start > end) {setBusy(false);setMessage(t('access.invalidDates'));return;}
    const params = new URLSearchParams({timezone:Intl.DateTimeFormat().resolvedOptions().timeZone});
    if(id) params.set('key_id',id);
    if(provider) params.set('provider',provider);
    if(hubId) params.set('hub_id',hubId);
    if(start) params.set('start',new Date(`${start}T00:00:00`).toISOString());
    if(end) {const exclusive=new Date(`${end}T00:00:00`);exclusive.setDate(exclusive.getDate()+1);params.set('end',exclusive.toISOString());}
    setBusy(true);
    try {const next=await read('/dashboard/api/usage?'+params);if(seq===sequence.current){setData(next);setMessage('');}} catch {if(seq===sequence.current)setMessage(t('access.usageError'));}
    finally {if(seq===sequence.current)setBusy(false);}
  }
  useEffect(() => {const timer=window.setTimeout(()=>{void load();},200);return()=>{window.clearTimeout(timer);sequence.current++;};}, [id,provider,hubId,start,end]);
  const summaries = summarizeUsage(data?.totals || []);
  const unitName=(unit:string)=>({token:t('access.unit.token'),character:t('access.unit.character'),second:t('access.unit.second')}[unit] || unit);
  const totalUsage=(b:ReturnType<typeof summarizeUsage>[number])=>b.capability==='chat' || b.capability==='embed' ? number(b.total) : Object.entries(b.amounts).map(([unit,amount])=>`${number(amount)} ${unitName(unit)}`).join(' · ') || '—';
  const number=(value: number|null|undefined) => value == null ? '—' : Number(value).toLocaleString(locale);
  const names: Record<string,string> = {chat:t('access.chat'),embed:t('access.embed'),stt:t('access.stt'),tts:t('access.tts')};
  return <div className={`${panel} mt-4`}>
    {!embedded && <Disclosure title={t('access.usage')} icon={<Activity className="size-4 text-purple-400"/>} open={open} onClick={()=>setOpen(!open)}/>}
    {(open || embedded) && <div className="space-y-5 p-4 text-sm">
      <p className="text-xs text-zinc-400">{t('access.localDates')}</p>
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1">{[[1,'day'],[7,'week'],[30,'month'],[0,'all']].map(([days,label])=><Button key={label} type="button" size="sm" variant={range===label?'secondary':'ghost'} aria-pressed={range===label} onClick={()=>preset(Number(days),String(label))}>{t('access.range.'+label)}</Button>)}</div>
        <label className="flex items-center gap-2 text-xs text-zinc-400">{t('access.startShort')}<Input aria-label={t('access.start')} className="h-8 w-36 [color-scheme:dark]" type="date" value={start} onChange={e=>{setRange('custom');setStart(e.target.value);}}/></label>
        <label className="flex items-center gap-2 text-xs text-zinc-400">{t('access.endShort')}<Input aria-label={t('access.end')} className="h-8 w-36 [color-scheme:dark]" type="date" value={end} onChange={e=>{setRange('custom');setEnd(e.target.value);}}/></label>
      </div>
      {!data?.totals.length && <p className="py-4 text-center text-zinc-500">{t(busy ? 'common.loading' : 'access.noUsage')}</p>}
      <div className="grid gap-3 lg:grid-cols-2">{summaries.map(b=><div key={b.capability} className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-3"><div className="mb-3 flex items-center justify-between"><h4 className="font-semibold">{names[b.capability] || b.capability}</h4><Badge variant="outline">{number(b.requests)} {t('access.requests')}</Badge></div><dl className="grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-3 xl:grid-cols-4">{[[t('access.success'),number(b.succeeded)],[t('access.failed'),number(b.failed)],[t('access.cost'),b.cost==null ? '—' : '$'+Number(b.cost).toLocaleString(locale,{maximumFractionDigits:6})],[t('access.input'),number(b.input)],[t('access.output'),number(b.output)],[t('access.thoughts'),number(b.thoughts)],[t('access.total'),totalUsage(b)],[t('access.unit'),Object.keys(b.amounts).map(unitName).join(' · ') || t('access.unknown')]].map(([label,value])=><div key={label}><dt className="text-xs text-zinc-500">{label}</dt><dd className="mt-1 font-mono text-sm text-zinc-200">{value}</dd></div>)}</dl></div>)}</div>
      {!!data?.daily.length && <DailyRequestsChart rows={data.daily} names={names}/>}
    </div>}{message && <p role="alert" className="px-4 pb-3 text-xs text-red-400">{message}</p>}
  </div>;
}

export function HubManagement() {
  const {t,adminKey}=useApp();
  const [hubs,setHubs]=useState<(Key & {is_active:boolean})[]>([]);
  const [message,setMessage]=useState('');
  const [open,setOpen]=useState(false);
  const [busy,setBusy]=useState('');
  async function load() {
    try {setHubs((await read('/dashboard/api/hubs')).hubs);setMessage('');}
    catch {setMessage(t('access.loadError'));}
  }
  useEffect(()=>{if(adminKey)void load();else setHubs([]);},[adminKey]);
  async function change(h:Key & {is_active:boolean}) {
    setBusy(h.id);
    try {const r=await adminFetch(`/dashboard/api/hubs/${h.id}`,{method:'PUT',body:JSON.stringify({is_active:!h.is_active})});if(!r.ok)throw new Error();await load();}
    catch {setMessage(t('access.saveError'));}finally {setBusy('');}
  }
  return <div className={`${panel} mb-6`}>
    <Disclosure title={`${t('access.hubs')}${open?' · '+hubs.length:''}`} icon={<Network className="size-4 text-purple-400"/>} open={open} onClick={()=>setOpen(!open)}/>
    {open && <div className="space-y-3 border-t border-zinc-800 p-4">
      {!hubs.length && <p className="text-sm text-zinc-500">{t('access.noHubs')}</p>}
      {hubs.map(h=><div key={h.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <span className="font-medium">{h.name}</span>{!h.is_active && <Status active={false}/>}
        <Button type="button" className="ml-auto" variant="outline" disabled={busy===h.id} onClick={()=>change(h)}>{t(h.is_active?'access.deactivate':'access.activate')}</Button>
      </div>)}
    </div>}
    {message && <p role="alert" className="p-4 text-xs text-red-400">{message}</p>}
  </div>;
}
