'use client';

import React, { useEffect, useState } from 'react';
import { adminFetch } from '@/lib/api';
import { useApp } from '@/components/AppContext';
import { KeyAccess, AccessDraft, ownerLabel } from '@/components/KeyAccess';
import { ProviderKeyList, ProviderKey } from '@/components/ProviderKeyList';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Trash2, Search } from 'lucide-react';

type Account={id:string;name:string;hub_name?:string;hub_id?:string};
function Choice({value,options,onChange,label}: {value:string;options:{value:string;label:string}[];onChange:(value:string)=>void;label:string}) {
  return <Select value={value} onValueChange={next=>{if(next)onChange(next);}}>
    <SelectTrigger aria-label={label} className="h-10 w-full"><SelectValue>{options.find(x=>x.value===value)?.label || label}</SelectValue></SelectTrigger>
    <SelectContent>{options.map(option=><SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}</SelectContent>
  </Select>;
}
const emptyForm={provider:'',label:'',api_key:'',target:'all'};
export default function KeyPoolPage() {
  const {t,adminKey,showToast,confirmAction}=useApp();
  const [tab,setTab]=useState<'shared'|'personal'>('shared');
  const [shared,setShared]=useState<ProviderKey[]>([]);
  const [personal,setPersonal]=useState<ProviderKey[]>([]);
  const [accounts,setAccounts]=useState<Account[]>([]);
  const [providers,setProviders]=useState<string[]>([]);
  const [loading,setLoading]=useState(true);
  const [search,setSearch]=useState('');
  const [owner,setOwner]=useState('all');
  const [adding,setAdding]=useState(false);
  const [form,setForm]=useState(emptyForm);
  const [editing,setEditing]=useState<ProviderKey|null>(null);
  const [addAccess,setAddAccess]=useState<AccessDraft|null>(null);
  const [editAccess,setEditAccess]=useState<AccessDraft|null>(null);
  const [busy,setBusy]=useState(false);
  useEffect(()=>{setAdding(false);setEditing(null);setForm(emptyForm);},[adminKey]);
  const normalize=(keys:ProviderKey[],source:'shared'|'personal')=>keys.map(k=>({...k,source,priority:Number(k.priority)||100,
    display_name:source==='personal'?ownerLabel({id:k.key_id || '',name:k.name || '',hub_name:k.hub_name}):k.label,
    _original:{provider:k.provider,label:k.label,priority:Number(k.priority)||100,is_active:k.is_active}}));
  async function read(path:string) {const res=await adminFetch(path);if(!res.ok)throw new Error();return res.json();}
  async function load() {
    try {
      const [pool,privateKeys,users,providerData]=await Promise.all([read('/dashboard/api/provider-key-pool'),read('/dashboard/api/personal-provider-keys'),read('/dashboard/api/keys'),read('/dashboard/api/providers')]);
      setShared(normalize(pool.keys,'shared'));setPersonal(normalize(privateKeys.keys,'personal'));setAccounts(users.keys);setProviders(Object.keys(providerData.providers || {}));
    } catch {showToast(t('access.loadError'),'error');}
    finally {setLoading(false);}
  }
  useEffect(()=>{if(adminKey)void load();else {setShared([]);setPersonal([]);}},[adminKey]);
  const endpoint=(key:ProviderKey)=>`/dashboard/api/${key.source==='personal'?'personal-provider-keys':'provider-key-pool'}/${key.id}`;
  async function reorder(visible:ProviderKey[]) {
    if(!visible.length)return;
    const full=(visible[0].source==='personal'?personal:shared).filter(k=>k.provider===visible[0].provider).sort((a,b)=>a.priority-b.priority);
    const ids=new Set(visible.map(k=>k.id));let index=0;
    const merged=full.map(k=>ids.has(k.id)?visible[index++]:k);
    for(let i=0;i<merged.length;i++) {
      const key=merged[i];
      const res=await adminFetch(endpoint(key),{method:'PUT',body:JSON.stringify({priority:i+1})});
      if(!res.ok) {await load();throw new Error();}
    }
    await load();
  }
  function openAdd() {
    setAddAccess(null);
    setForm({...emptyForm,provider:providers[0] || '',target:tab==='personal' && owner!=='all'?owner:'all'});
    setAdding(true);
  }
  function openEdit(key:ProviderKey) {setEditAccess(null);setEditing({...key,api_key:''});}
  async function create(e:React.FormEvent) {
    e.preventDefault();if(busy || !form.api_key.trim() || (form.target==='all' && !addAccess))return;
    setBusy(true);const submitted={...form};setForm(prev=>({...prev,api_key:''}));
    try {
      const personalTarget=submitted.target!=='all';
      const res=await adminFetch(`/dashboard/api/${personalTarget?'personal-provider-keys':'provider-key-pool'}`,{method:'POST',body:JSON.stringify({provider:submitted.provider,label:submitted.label.trim() || 'Kişisel',api_key:submitted.api_key,
        priority:Math.max(0,...(personalTarget?personal:shared).filter(k=>k.provider===submitted.provider).map(k=>k.priority))+1,
        ...(personalTarget?{key_id:submitted.target}:{access:addAccess})})});
      if(!res.ok) {const error=await res.json();throw new Error(error.detail || t('keyPool.toast.addFailed'));}
      setAdding(false);setTab(personalTarget?'personal':'shared');if(personalTarget)setOwner(submitted.target);
      showToast(t('keyPool.toast.addSuccess'));await load();
    } catch(error) {showToast(error instanceof Error?error.message:t('keyPool.toast.addFailed'),'error');}
    finally {setBusy(false);}
  }
  async function update(e:React.FormEvent) {
    e.preventDefault();if(!editing || busy || (editing.source==='shared' && !editAccess))return;
    const submitted={...editing};setEditing(prev=>prev?{...prev,api_key:''}:null);setBusy(true);
    try {
      const res=await adminFetch(endpoint(submitted),{method:'PUT',body:JSON.stringify({label:submitted.label,api_key:submitted.api_key || '',is_active:submitted.is_active,...(submitted.source==='shared'?{access:editAccess}:{})})});
      if(!res.ok)throw new Error();setEditing(null);showToast(t('keyPool.toast.updateSuccess'));await load();
    } catch {showToast(t('keyPool.toast.updateFailed'),'error');}finally {setBusy(false);}
  }
  function remove(key:ProviderKey) {
    confirmAction(t('common.confirm.deleteProviderKey'),async()=>{
      setBusy(true);
      try {const res=await adminFetch(endpoint(key),{method:'DELETE'});if(!res.ok)throw new Error();setEditing(null);await load();showToast(t('keyPool.toast.deleteSuccess'));}
      catch {showToast(t('keyPool.toast.deleteFailed'),'error');}finally {setBusy(false);}
    });
  }
  const targetOptions=[{value:'all',label:t('access.everyone')},...accounts.map(k=>({value:k.id,label:ownerLabel(k)}))];
  const visible=personal.filter(k=>(owner==='all'||k.key_id===owner) && `${k.display_name} ${k.provider}`.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  return <section id="key-pool" className="tab-content active block pt-8">
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4 border-b border-border pb-6">
      <div><h1 className="font-heading text-3xl font-semibold tracking-tight">{t('keyPool.title')}</h1><p className="mt-1 text-sm text-zinc-400">{t('keyPool.description')}</p></div>
      <Button onClick={openAdd} className="rounded-full bg-white px-6 py-2.5 font-medium text-black hover:bg-zinc-200">+ {t('keyPool.addKey')}</Button>
    </header>
    <div role="tablist" aria-label={t('keyPool.title')} className="mb-6 flex w-fit max-w-full gap-1 rounded-xl border border-zinc-800 bg-zinc-900/60 p-1">
      {(['shared','personal'] as const).map(value=><Button key={value} role="tab" aria-selected={tab===value} variant="ghost" className={`h-auto whitespace-normal px-5 py-3 ${tab===value?'bg-zinc-800 text-white':'text-zinc-400'}`} onClick={()=>setTab(value)}>{t('access.'+value)}</Button>)}
    </div>
    {tab==='personal' && <div className="mb-6 flex flex-wrap items-center gap-3 rounded-xl border border-zinc-800 bg-black/20 p-4">
      <Search className="size-4 text-zinc-500"/><Input className="min-w-40 flex-1" aria-label={t('access.searchOwner')} placeholder={t('access.searchOwner')} value={search} onChange={e=>setSearch(e.target.value)}/>
      <div className="w-full sm:w-64"><Choice value={owner} options={[{value:'all',label:t('access.allUsers')},...targetOptions.slice(1)]} onChange={setOwner} label={t('access.user')}/></div>
    </div>}
    <ProviderKeyList keys={tab==='shared'?shared:visible} loading={loading} onEdit={openEdit} onReorder={reorder}/>
    <Dialog open={adding} onOpenChange={open=>{if(busy)return;setAdding(open);if(!open)setForm(prev=>({...prev,api_key:''}));}}>
      <DialogContent className="max-w-[560px] max-h-[90vh] overflow-y-auto [color-scheme:dark] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
        <DialogHeader><DialogTitle>{t('keyPool.addModalTitle')}</DialogTitle></DialogHeader>
        <form onSubmit={create} className="my-2 flex flex-col gap-4">
          <label className="space-y-2 text-sm text-zinc-400">{t('keyPool.provider')}<Choice label={t('keyPool.provider')} value={form.provider} options={providers.map(value=>({value,label:value}))} onChange={value=>setForm(prev=>({...prev,provider:value}))}/></label>
          <label className="space-y-2 text-sm text-zinc-400">{t('keyPool.label')}<Input value={form.label} onChange={e=>setForm(prev=>({...prev,label:e.target.value}))} required={form.target==='all'} placeholder={t('keyPool.labelPlaceholder')}/></label>
          <label className="space-y-2 text-sm text-zinc-400">{t('keyPool.apiKey')}<Input type="password" autoComplete="off" value={form.api_key} onChange={e=>setForm(prev=>({...prev,api_key:e.target.value}))} required/></label>
          <div className="space-y-2"><label className="text-sm text-zinc-400">{t('access.keyOwner')}</label><Choice value={form.target} options={targetOptions} onChange={value=>setForm(prev=>({...prev,target:value}))} label={t('access.keyOwner')}/></div>
          {form.target==='all'?<KeyAccess kind="provider" value={addAccess} onChange={setAddAccess}/>:<p className="rounded-xl border border-zinc-800 bg-black/20 p-4 text-xs text-zinc-400">{t('access.personalOwnerOnly')}</p>}
          <DialogFooter className="mt-4"><Button type="button" variant="outline" disabled={busy} onClick={()=>{setAdding(false);setForm(prev=>({...prev,api_key:''}));}}>{t('common.cancel')}</Button><Button type="submit" disabled={busy || (form.target==='all' && !addAccess)}>{t('common.save')}</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
    <Dialog open={!!editing} onOpenChange={open=>{if(!busy && !open)setEditing(null);}}>
      <DialogContent className="max-w-[560px] max-h-[90vh] overflow-y-auto [color-scheme:dark] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
        <DialogHeader><DialogTitle>{t('keyPool.editModalTitle')}</DialogTitle></DialogHeader>
        {editing && <form onSubmit={update} className="my-2 flex flex-col gap-4">
          {editing.source==='personal' && <p className="text-sm text-zinc-400">{editing.display_name}</p>}
          <label className="space-y-2 text-sm text-zinc-400">{t('keyPool.label')}<Input required value={editing.label} onChange={e=>setEditing({...editing,label:e.target.value})}/></label>
          <label className="space-y-2 text-sm text-zinc-400">{t('keyPool.apiKey')}<Input type="password" autoComplete="off" value={editing.api_key || ''} placeholder={t('keyPool.leaveBlankToKeep')} onChange={e=>setEditing({...editing,api_key:e.target.value})}/></label>
          {editing.source==='shared'?<KeyAccess key={editing.id} id={editing.id} kind="provider" value={editAccess} onChange={setEditAccess}/>:<p className="rounded-xl border border-zinc-800 p-4 text-xs text-zinc-400">{t('access.personalOwnerOnly')}</p>}
          <label className={`flex items-center justify-between rounded-lg border p-4 ${editing.is_active?'border-purple-500/25 bg-purple-950/10':'border-zinc-800 bg-white/3'}`}><span className="text-sm text-purple-400">{t('keys.activeStatus')}</span><Switch checked={editing.is_active} onCheckedChange={active=>setEditing({...editing,is_active:active})}/></label>
          <DialogFooter className="mt-4 flex justify-between gap-3"><Button type="button" variant="destructive" disabled={busy} onClick={()=>remove(editing)}><Trash2 className="size-4"/>{t('common.delete')}</Button><div className="ml-auto flex gap-3"><Button type="button" variant="outline" disabled={busy} onClick={()=>setEditing(null)}>{t('common.cancel')}</Button><Button type="submit" disabled={busy || (editing.source==='shared' && !editAccess)}>{t('common.save')}</Button></div></DialogFooter>
        </form>}
      </DialogContent>
    </Dialog>
  </section>;
}
