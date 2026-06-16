'use client';

import React, { useState, useEffect } from 'react';
import { adminFetch } from '@/lib/api';
import { money, dateTime } from '@/lib/utils';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Copy, Check, Trash2 } from 'lucide-react';

interface VirtualKey {
  id: string;
  name: string;
  is_active: boolean;
  budget: number;
  used_amount: number | null;
  created_at: string;
}

export default function VirtualKeysPage() {
  const { showToast, confirmAction, t } = useApp();
  const [virtualKeys, setVirtualKeys] = useState<VirtualKey[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Modals visibility
  const [showKeyModal, setShowKeyModal] = useState<boolean>(false);
  const [showEditKeyModal, setShowEditKeyModal] = useState<boolean>(false);
  const [newRawKey, setNewRawKey] = useState<string>('');
  const [rawKeyDialogOpen, setRawKeyDialogOpen] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  // Form states
  const [virtualKeyForm, setVirtualKeyForm] = useState({ name: '', budget: 0 });
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
      showToast('Failed to load virtual keys', 'error');
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
    const name = virtualKeyForm.name.trim();
    if (!name) {
      showToast('Please enter a key name.', 'error');
      return;
    }
    const budget = parseFloat(virtualKeyForm.budget.toString());
    if (isNaN(budget) || budget < 0) {
      showToast('Budget limit must be a positive number.', 'error');
      return;
    }

    try {
      const res = await adminFetch('/dashboard/api/keys', {
        method: 'POST',
        body: JSON.stringify({ name, budget }),
      });
      if (res.ok) {
        const data = await res.json();
        setShowKeyModal(false);
        setNewRawKey(data.raw_key);
        setRawKeyDialogOpen(true);
        setVirtualKeyForm({ name: '', budget: 0 });
        showToast('Virtual key created successfully!');
        await loadVirtualKeys();
      } else {
        const err = await res.json();
        showToast('Error: ' + (err.detail || 'Failed to create key'), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Failed to create key', 'error');
    }
  };

  const handleUpdateKey = async () => {
    const name = editingVirtualKey.name.trim();
    if (!name) {
      showToast('Please enter a key name.', 'error');
      return;
    }
    const budget = parseFloat(editingVirtualKey.budget.toString());
    if (isNaN(budget) || budget < 0) {
      showToast('Budget limit must be a positive number.', 'error');
      return;
    }

    try {
      const res = await adminFetch(`/dashboard/api/keys/${editingVirtualKey.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          name,
          budget,
          is_active: !!editingVirtualKey.is_active,
        }),
      });
      if (res.ok) {
        setShowEditKeyModal(false);
        showToast('Virtual key updated successfully!');
        await loadVirtualKeys();
      } else {
        const err = await res.json();
        showToast('Error: ' + (err.detail || 'Failed to update key'), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Failed to update key', 'error');
    }
  };

  const handleDeleteKey = async (keyId: string, confirmed = false) => {
    if (!confirmed) {
      confirmAction('Are you sure you want to delete this virtual key?', () =>
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
        showToast('Virtual key deleted successfully!');
        await loadVirtualKeys();
      } else {
        const err = await res.json();
        showToast('Error: ' + (err.detail || 'Failed to delete key'), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Failed to delete key', 'error');
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    showToast('API key copied to clipboard!');
    setRawKeyDialogOpen(false);
    setTimeout(() => setCopied(false), 2000);
  };

  const openEditModal = (key: VirtualKey) => {
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
          onClick={() => setShowKeyModal(true)}
          className="bg-white text-black hover:bg-zinc-200 font-medium px-6 py-2.5 rounded-full transition-all duration-200 shadow-md hover:shadow-lg flex items-center gap-1.5"
        >
          + {t('keys.new')}
        </Button>
      </header>

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
                  Loading virtual keys...
                </TableCell>
              </TableRow>
            ) : virtualKeys.length === 0 ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={5} className="text-center text-zinc-400 py-8">
                  No virtual keys found. Create one to get started.
                </TableCell>
              </TableRow>
            ) : (
              virtualKeys.map((key) => (
                <TableRow key={key.id} className="border-b border-zinc-900 hover:bg-white/[0.015] transition-colors">
                  <TableCell className="font-medium text-sm py-4 pl-6">
                    <div className="flex items-center gap-2">
                      <span className="truncate max-w-[240px]" title={key.name}>{key.name}</span>
                      {!key.is_active && (
                        <Badge className="bg-red-500/10 text-red-500 border border-red-500/20 text-[10px] font-semibold tracking-wide uppercase px-2.5 py-0.5 rounded-full shrink-0">
                          Inactive
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="py-4 text-left font-mono text-xs text-zinc-300">
                    {key.budget > 0 ? money(key.budget, 2) : 'Unlimited'}
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
      <Dialog open={showKeyModal} onOpenChange={setShowKeyModal}>
        <DialogContent className="max-w-[400px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">{t('keys.createModalTitle')}</DialogTitle>
          </DialogHeader>

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

          <DialogFooter className="mt-4 flex gap-3 justify-end">
            <Button
              variant="outline"
              onClick={() => setShowKeyModal(false)}
              className="border-zinc-800 text-white hover:bg-zinc-900 rounded font-medium"
            >
              {t('common.cancel')}
            </Button>
            <Button
              onClick={handleCreateKey}
              className="bg-white text-black hover:bg-zinc-200 rounded font-medium"
            >
              {t('common.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Key Dialog */}
      <Dialog open={showEditKeyModal} onOpenChange={setShowEditKeyModal}>
        <DialogContent className="max-w-[400px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
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
              <Switch
                checked={editingVirtualKey.is_active}
                onCheckedChange={(checked) => setEditingVirtualKey({ ...editingVirtualKey, is_active: checked })}
              />
            </div>
          </div>

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
                onClick={handleUpdateKey}
                className="bg-white text-black hover:bg-zinc-200 rounded font-medium"
              >
                {t('common.save')}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Raw Key Success Modal */}
      <Dialog
        open={rawKeyDialogOpen}
        onOpenChange={setRawKeyDialogOpen}
        onOpenChangeComplete={(open) => {
          if (!open) setNewRawKey('');
        }}
      >
        <DialogContent className="max-w-[400px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl text-center">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">{t('keys.createdModalTitle')}</DialogTitle>
            <DialogDescription className="text-zinc-400 text-sm mt-2">
              {t('keys.createdModalDesc')}
            </DialogDescription>
          </DialogHeader>

          <div className="raw-key-box bg-black/50 border border-dashed border-emerald-500 p-4 rounded text-sm text-emerald-400 font-mono break-all my-5 select-all select-none">
            {newRawKey}
          </div>

          <DialogFooter className="justify-center mt-4">
            <Button
              onClick={() => copyToClipboard(newRawKey)}
              className="bg-white text-black hover:bg-zinc-200 font-medium px-6 py-2.5 rounded shadow-lg flex items-center gap-1.5 mx-auto"
            >
              {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
              {copied ? t('common.copied') : t('keys.copyClose')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
