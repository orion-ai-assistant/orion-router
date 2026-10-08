'use client';
import { useEffect, useState } from 'react';
import { adminFetch } from '@/lib/api';
import { useApp } from '@/components/AppContext';
import { KeyUsage, ownerLabel } from '@/components/KeyAccess';
import { Button } from '@/components/ui/button';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select';
import { Activity, ChevronDown } from 'lucide-react';

type Account={id:string;name:string;hub_name?:string;hub_id?:string};
function Filter({value,options,onChange,label}: {value:string;options:Account[];onChange:(value:string)=>void;label:string}) {
  return <Select value={value} onValueChange={next=>{if(next)onChange(next);}}>
    <SelectTrigger aria-label={label} className="h-10 w-full"><SelectValue>{value==='all'?label:options.find(x=>x.id===value)?.name || label}</SelectValue></SelectTrigger>
    <SelectContent><SelectItem value="all">{label}</SelectItem>{options.map(option=><SelectItem key={option.id} value={option.id}>{option.name}</SelectItem>)}</SelectContent>
  </Select>;
}
export function UsageExplorer() {
  const {t,adminKey}=useApp();
  const [open,setOpen]=useState(false);
  const [account,setAccount]=useState('all');
  const [hub,setHub]=useState('all');
  const [provider,setProvider]=useState('all');
  const [accounts,setAccounts]=useState<Account[]>([]);
  const [hubs,setHubs]=useState<Account[]>([]);
  const [providers,setProviders]=useState<Account[]>([]);
  const [error,setError]=useState('');
  useEffect(()=>{
    const key=new URLSearchParams(window.location.search).get('key_id');
    if(key){setAccount(key);setOpen(true);}
  },[]);
  useEffect(()=>{
    if(!adminKey)return;
    let current=true;
    async function load() {
      try {
        const results=await Promise.all(['/keys','/hubs','/providers'].map(async path=>{const res=await adminFetch('/dashboard/api'+path);if(!res.ok)throw new Error();return res.json();}));
        if(!current)return;
        setAccounts(results[0].keys);setHubs(results[1].hubs);setProviders(Object.keys(results[2].providers || {}).map(id=>({id,name:id})));setError('');
      } catch {if(current)setError(t('access.loadError'));}
    }
    void load();return()=>{current=false;};
  },[adminKey]);
  const visibleAccounts=accounts.filter(k=>hub==='all'||k.hub_id===hub).map(k=>({...k,name:ownerLabel(k)}));
  return <section id="usage" className={`mt-5 min-h-0 rounded-xl border border-zinc-800 bg-[#18181b] ${open?'flex flex-1 flex-col overflow-hidden':'shrink-0'}`}>
    <Button type="button" variant="ghost" aria-expanded={open} className="h-auto w-full shrink-0 justify-between p-4 text-left" onClick={()=>setOpen(!open)}><span className="flex items-center gap-2"><Activity className="size-4 text-purple-400"/>{t('access.usage')}</span><ChevronDown className={`size-4 ${open?'rotate-180':''}`}/></Button>
    {open && <div tabIndex={0} aria-label={t('access.usage')} className="min-h-0 overflow-y-auto overscroll-contain border-t border-zinc-800 p-4 custom-scrollbar">
      <div className="grid gap-3 sm:grid-cols-3">
        <Filter label={t('access.allHubs')} value={hub} options={hubs} onChange={value=>{setHub(value);setAccount('all');}}/>
        <Filter label={t('access.allUsers')} value={account} options={visibleAccounts} onChange={setAccount}/>
        <Filter label={t('access.allProviders')} value={provider} options={providers} onChange={setProvider}/>
      </div>
      {error && <p role="alert" className="mt-3 text-xs text-red-400">{error}</p>}
      <KeyUsage id={account==='all'?'':account} hubId={hub==='all'?'':hub} provider={provider==='all'?'':provider} embedded/>
    </div>}
  </section>;
}
