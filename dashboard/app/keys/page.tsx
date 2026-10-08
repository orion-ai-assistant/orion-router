'use client';

import React, { useState, useEffect, useRef } from 'react';
import { adminFetch, getAdminKey } from '@/lib/api';
import { copyText } from '@/lib/clipboard';
import { money, dateTime } from '@/lib/utils';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Trash2 } from 'lucide-react';
import { KeyAccess, AccessDraft, HubManagement, ownerLabel } from '@/components/KeyAccess';

interface VirtualKey {
  id: string;
  name: string;
  hub_id?: string;
  hub_name?: string;
  is_active: boolean;
  budget: number;
  used_amount: number | null;
  created_at: string;
}

export default function VirtualKeysPage() {
  const { showToast, confirmAction, t } = useApp();
  const [search,setSearch]=useState('');
  const [createAccess,setCreateAccess]=useState<AccessDraft|null>(null);
  const [editAccess,setEditAccess]=useState<AccessDraft|null>(null);
  const [virtualKeys, setVirtualKeys] = useState<VirtualKey[]>([]);
  const createSequence = useRef(0);
  const [createdSecret, setCreatedSecret] = useState('');
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState<boolean>(true);

  const { adminKey } = useApp();
  useEffect(() => {
    createSequence.current++; setCreatedSecret(''); setShowKeyModal(false); setVirtualKeyForm(prev=>({...prev,api_key:''}));
  }, [adminKey]);

  // Modals visibility
  const [showKeyModal, setShowKeyModal] = useState<boolean>(false);
  const [showEditKeyModal, setShowEditKeyModal] = useState<boolean>(false);
  // Form states
  const [virtualKeyForm, setVirtualKeyForm] = useState({ name: '', budget: 0, api_key: '' });
  const [editingVirtualKey, setEditingVirtualKey] = useState<VirtualKey>({
    id: '',
    name: '',
    budget: 0,
    is_active: true,
    used_amount: 0,
    created_at: '',
  });

  const loadVirtualKeys = async () => {
    try {
      const res = await adminFetch('/dashboard/api/keys');
      if (res.ok) {
        const data = await res.json();
        setVirtualKeys(data.keys || []);
      }
    } catch (err) {
      console.error('Failed to load virtual keys:', err);
      showToast(t('keys.toast.loadFailed'), 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadVirtualKeys();

    const handleAuth = () => {
      loadVirtualKeys();
    };
    window.addEventListener('orion-authenticated', handleAuth);
    return () => {
      window.removeEventListener('orion-authenticated', handleAuth);
    };
  }, []);

  const handleCreateKey = async () => {
    if(!createAccess)return;
    const name = virtualKeyForm.name.trim();
    if (!name) {
      showToast(t('keys.toast.enterKeyName'), 'error');
      return;
    }
    const budget = parseFloat(virtualKeyForm.budget.toString());
    if (isNaN(budget) || budget < 0) {
      showToast(t('keys.toast.invalidBudget'), 'error');
      return;
    }

    if (creating) return;
    setCreating(true);
    const sequence = ++createSequence.current;
    // Generate here so the server only receives a write-only secret and never returns it.
    const bytes = new Uint8Array(32);
    crypto.getRandomValues(bytes);
    const credential = 'sk-orion-' + Array.from(bytes, byte=>byte.toString(16).padStart(2,'0')).join('');
    setVirtualKeyForm({...virtualKeyForm,api_key:''});
    try {
      const res = await adminFetch('/dashboard/api/keys', {
        method: 'POST',
        body: JSON.stringify({ name, budget, api_key: credential, access:createAccess }),
      });
      if (res.ok) {
        await res.json();
        if(sequence !== createSequence.current || getAdminKey() !== adminKey) return;
        setCreatedSecret(credential);
        setVirtualKeyForm({ name: '', budget: 0, api_key: '' });
        showToast(t('keys.toast.createSuccess'));
        await loadVirtualKeys();
      } else {
        const err = await res.json();
        showToast(t('common.error') + ': ' + (err.detail || t('keys.toast.createFailed')), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast(t('keys.toast.createFailed'), 'error');
    } finally {setCreating(false);}
  };

  const handleUpdateKey = async () => {
    if(!editAccess)return;
    const name = editingVirtualKey.name.trim();
    if (!name) {
      showToast(t('keys.toast.enterKeyName'), 'error');
      return;
    }
    const budget = parseFloat(editingVirtualKey.budget.toString());
    if (isNaN(budget) || budget < 0) {
      showToast(t('keys.toast.invalidBudget'), 'error');
      return;
    }

    try {
      const res = await adminFetch(`/dashboard/api/keys/${editingVirtualKey.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          name,
          budget,
          access:editAccess,
          is_active: !!editingVirtualKey.is_active,
        }),
      });
      if (res.ok) {
        setShowEditKeyModal(false);
        showToast(t('keys.toast.updateSuccess'));
        await loadVirtualKeys();
      } else {
        const err = await res.json();
        showToast(t('common.error') + ': ' + (err.detail || t('keys.toast.updateFailed')), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast(t('keys.toast.updateFailed'), 'error');
    }
  };

  const handleDeleteKey = async (keyId: string, confirmed = false) => {
    if (!confirmed) {
      confirmAction(t('common.confirm.deleteKey'), () =>
        handleDeleteKey(keyId, true)
      );
      return;
    }
    try {
      const res = await adminFetch(`/dashboard/api/keys/${keyId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setShowEditKeyModal(false);
        showToast(t('keys.toast.deleteSuccess'));
        await loadVirtualKeys();
      } else {
        const err = await res.json();
        showToast(t('common.error') + ': ' + (err.detail || t('keys.toast.deleteFailed')), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast(t('keys.toast.deleteFailed'), 'error');
    }
  };

  const openEditModal = (key: VirtualKey) => {
    setEditAccess(null);
    setEditingVirtualKey({ ...key });
    setShowEditKeyModal(true);
  };

  return (
    <section id="keys" className="tab-content active block pt-8">
      <header className="flex justify-between items-end mb-8 pb-6 border-b border-border">
        <div className="header-titles">
          <h1 className="font-heading text-3xl font-semibold tracking-tight">{t('keys.title')}</h1>
          <p className="text-zinc-400 text-sm mt-1">{t('keys.description')}</p>
        </div>
        <Button
          onClick={() => {createSequence.current++;setCreateAccess(null);setCreatedSecret('');setShowKeyModal(true);}}
          className="bg-white text-black hover:bg-zinc-200 font-medium px-6 py-2.5 rounded-full transition-all duration-200 shadow-md hover:shadow-lg flex items-center gap-1.5"
        >
          + {t('keys.new')}
        </Button>
      </header>

      <HubManagement />
      <div className="mb-5"><Input aria-label={t('access.searchVirtual')} placeholder={t('access.searchVirtual')} value={search} onChange={e=>setSearch(e.target.value)} className="max-w-md"/></div>
      {/* Table List */}
      <div className="table-container glass-panel bg-[#18181b] border border-zinc-800 rounded-md overflow-hidden shadow-xl">
        <Table>
          <TableHeader className="bg-black/25">
            <TableRow className="border-b border-zinc-850 hover:bg-transparent">
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 pl-6 text-left w-[25%]">{t('keys.table.name')}</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-left w-[18%]">{t('keys.table.budget')}</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-left w-[12%]">{t('keys.table.used')}</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-center w-[20%]">{t('keys.table.created')}</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-right pr-6 w-[25%]">{t('keys.table.actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={5} className="text-center text-zinc-400 py-8">
                  {t('keys.loading')}
                </TableCell>
              </TableRow>
            ) : virtualKeys.filter(key=>ownerLabel(key).toLocaleLowerCase().includes(search.toLocaleLowerCase())).length === 0 ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={5} className="text-center text-zinc-400 py-8">
                  {t('keys.empty')}
                </TableCell>
              </TableRow>
            ) : (
              virtualKeys.filter(key=>ownerLabel(key).toLocaleLowerCase().includes(search.toLocaleLowerCase())).map((key) => (
                <TableRow key={key.id} id={key.id} className="border-b border-zinc-900 hover:bg-white/[0.015] transition-colors">
                  <TableCell className="font-medium text-sm py-4 pl-6">
                    <div className="flex items-center gap-2">
                      <span className="truncate max-w-[240px]" title={key.name}>{ownerLabel(key)}</span>
                      {!key.is_active && (
                        <Badge className="bg-red-500/10 text-red-500 border border-red-500/20 text-[10px] font-semibold tracking-wide uppercase px-2.5 py-0.5 rounded-full shrink-0">
                          Inactive
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="py-4 text-left font-mono text-xs text-zinc-300">
                    {key.budget > 0 ? money(key.budget, 2) : t('common.unlimited')}
                  </TableCell>
                  <TableCell className="py-4 text-left font-mono text-xs text-zinc-300">
                    {(!key.used_amount || Number(key.used_amount) === 0)
                      ? '$0.00'
                      : money(key.used_amount, 4)}
                  </TableCell>
                  <TableCell className="py-4 text-center font-mono text-xs text-zinc-400">
                    {dateTime(key.created_at)}
                  </TableCell>
                  <TableCell className="text-right py-4 pr-6">
                    <Button
                      variant="outline"
                      onClick={() => openEditModal(key)}
                      className="border-zinc-800 text-white hover:bg-zinc-800 text-xs px-3.5 py-1.5 h-auto rounded"
                    >
                      {t('common.edit')}
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Create Key Dialog */}
      <Dialog open={showKeyModal} onOpenChange={open => {if(creating)return;setShowKeyModal(open); if(!open) {createSequence.current++;setCreatedSecret('');setVirtualKeyForm({...virtualKeyForm,api_key:''});}}}>
        <DialogContent className="max-w-[700px] max-h-[90vh] overflow-y-auto [color-scheme:dark] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">{t('keys.createModalTitle')}</DialogTitle>
          </DialogHeader>

          {createdSecret ? <div className="my-4 space-y-4 rounded-xl border border-purple-500/25 bg-purple-500/5 p-4"><p className="text-sm text-zinc-300">{t('access.createdNotice')}</p><Input readOnly aria-label={t('access.newSecret')} value={createdSecret} className="font-mono text-xs"/><div className="flex justify-center"><Button onClick={async()=>{if(await copyText(createdSecret)){showToast(t('access.copied'));setCreatedSecret('');setShowKeyModal(false);}else{showToast(t('access.copyError'),'error');}}}>{t('access.copyAndClose')}</Button></div></div> : <>
          <div className="flex flex-col gap-4 my-4">
            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">{t('keys.keyName')}</label>
              <Input
                value={virtualKeyForm.name}
                onChange={(e) => setVirtualKeyForm({ ...virtualKeyForm, name: e.target.value })}
                placeholder={t('keys.keyNamePlaceholder')}
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
              />
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">{t('keys.budgetLimit')}</label>
              <Input
                type="number"
                min="0"
                step="0.1"
                value={virtualKeyForm.budget || ''}
                onChange={(e) => setVirtualKeyForm({ ...virtualKeyForm, budget: parseFloat(e.target.value) || 0 })}
                placeholder={t('keys.budgetPlaceholder')}
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
              />
            </div>
          </div>

          <KeyAccess key={`create-${createSequence.current}`} kind="virtual" value={createAccess} onChange={setCreateAccess}/>
          <DialogFooter className="mt-4 flex gap-3 justify-end">
            <Button
              variant="outline"
              disabled={creating}
              onClick={() => {createSequence.current++;setShowKeyModal(false);setCreatedSecret('');}}
              className="border-zinc-800 text-white hover:bg-zinc-900 rounded font-medium"
            >
              {t('common.cancel')}
            </Button>
            <Button
              disabled={creating || !createAccess}
              onClick={handleCreateKey}
              className="bg-white text-black hover:bg-zinc-200 rounded font-medium"
            >
              {t('common.create')}
            </Button>
          </DialogFooter>
          </>}
        </DialogContent>
      </Dialog>

      {/* Edit Key Dialog */}
      <Dialog open={showEditKeyModal} onOpenChange={setShowEditKeyModal}>
        <DialogContent className="max-w-[700px] max-h-[90vh] overflow-y-auto [color-scheme:dark] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">{t('keys.editModalTitle')}</DialogTitle>
          </DialogHeader>

          <div className="flex flex-col gap-4 my-4">
            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">{t('keys.keyName')}</label>
              <Input
                value={editingVirtualKey.name}
                onChange={(e) => setEditingVirtualKey({ ...editingVirtualKey, name: e.target.value })}
                placeholder={t('keys.keyNamePlaceholder')}
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
              />
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">{t('keys.budgetLimit')}</label>
              <Input
                type="number"
                min="0"
                step="0.1"
                value={editingVirtualKey.budget || ''}
                onChange={(e) => setEditingVirtualKey({ ...editingVirtualKey, budget: parseFloat(e.target.value) || 0 })}
                placeholder={t('keys.budgetPlaceholder')}
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
              />
            </div>

            <div
              onClick={() => setEditingVirtualKey({ ...editingVirtualKey, is_active: !editingVirtualKey.is_active })}
              className={`flex items-center justify-between p-4 rounded-lg cursor-pointer border transition-all duration-200 ${editingVirtualKey.is_active
                ? 'bg-purple-950/10 border-purple-500/25'
                : 'bg-white/3 border-zinc-800'
                }`}
            >
              <div className="flex flex-col gap-0.5">
                <span className={`font-semibold text-sm ${editingVirtualKey.is_active ? 'text-purple-400' : 'text-white'}`}>{t('keys.activeStatus')}</span>
              </div>
              <Switch onClick={e=>e.stopPropagation()}
                checked={editingVirtualKey.is_active}
                onCheckedChange={(checked) => setEditingVirtualKey({ ...editingVirtualKey, is_active: checked })}
              />
            </div>
          </div>

          <KeyAccess key={editingVirtualKey.id} id={editingVirtualKey.id} kind="virtual" value={editAccess} onChange={setEditAccess}/>
          <DialogFooter className="mt-4 flex justify-between w-full gap-3">
            <Button
              onClick={() => handleDeleteKey(editingVirtualKey.id)}
              className="bg-transparent border border-red-500/20 text-red-500 hover:bg-red-500/10 rounded font-medium flex items-center gap-1.5"
            >
              <Trash2 className="w-4 h-4" /> {t('common.delete')}
            </Button>
            <div className="flex gap-3 justify-end">
              <Button
                variant="outline"
                onClick={() => setShowEditKeyModal(false)}
                className="border-zinc-800 text-white hover:bg-zinc-900 rounded font-medium"
              >
                {t('common.cancel')}
              </Button>
              <Button
                disabled={!editAccess}
                onClick={handleUpdateKey}
                className="bg-white text-black hover:bg-zinc-200 rounded font-medium"
              >
                {t('common.save')}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </section>
  );
}
