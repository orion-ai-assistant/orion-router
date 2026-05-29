'use client';

import React, { useState, useEffect } from 'react';
import { adminFetch } from '@/lib/api';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Trash2 } from 'lucide-react';

interface ProviderKey {
  id: string;
  provider: string;
  label: string;
  priority: number;
  is_active: boolean;
  masked_key?: string;
  api_key?: string;
  _original?: {
    provider: string;
    label: string;
    priority: number;
    is_active: boolean;
  };
}

export default function KeyPoolPage() {
  const { showToast, confirmAction } = useApp();
  const [keyPool, setKeyPool] = useState<ProviderKey[]>([]);
  const [providers, setProviders] = useState<string[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Modals visibility
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [showEditModal, setShowEditModal] = useState<boolean>(false);

  // Form states
  const [addForm, setAddForm] = useState({ provider: '', label: '', api_key: '', priority: 100 });
  const [editingKey, setEditingKey] = useState<ProviderKey>({
    id: '',
    provider: '',
    label: '',
    priority: 100,
    is_active: true,
    api_key: '',
  });

  const loadProviders = async () => {
    try {
      const res = await adminFetch('/dashboard/api/providers');
      if (res.ok) {
        const data = await res.json();
        const pNames = Object.keys(data.providers || {});
        setProviders(pNames);
        if (pNames.length > 0) {
          setAddForm((prev) => ({ ...prev, provider: pNames[0] }));
        }
      }
    } catch (e) {
      console.error('Failed to load providers:', e);
    }
  };

  const loadKeyPool = async () => {
    try {
      const res = await adminFetch('/dashboard/api/provider-key-pool');
      if (res.ok) {
        const data = await res.json();
        const keys = (data.keys || []).map((key: any) => ({
          ...key,
          provider: key.provider || '',
          label: key.label || '',
          priority: Number.isFinite(Number(key.priority)) ? Number(key.priority) : 0,
          is_active: !!key.is_active,
          _original: {
            provider: key.provider || '',
            label: key.label || '',
            priority: Number.isFinite(Number(key.priority)) ? Number(key.priority) : 0,
            is_active: !!key.is_active,
          },
        }));
        setKeyPool(keys);
      }
    } catch (err) {
      console.error('Failed to load key pool:', err);
      showToast('Failed to load provider keys', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const initData = async () => {
      await loadProviders();
      await loadKeyPool();
    };
    initData();

    const handleAuth = () => {
      initData();
    };
    window.addEventListener('orion-authenticated', handleAuth);
    return () => {
      window.removeEventListener('orion-authenticated', handleAuth);
    };
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const provider = addForm.provider.trim();
    const label = addForm.label.trim();
    const api_key = addForm.api_key.trim();
    const priority = parseInt(addForm.priority.toString());

    if (!provider || !label || !api_key) {
      showToast('Please fill out all fields.', 'error');
      return;
    }
    if (isNaN(priority) || priority <= 0) {
      showToast('Priority must be a positive integer.', 'error');
      return;
    }

    try {
      const res = await adminFetch('/dashboard/api/provider-key-pool', {
        method: 'POST',
        body: JSON.stringify({ provider, label, api_key, priority, is_active: true }),
      });
      if (res.ok) {
        setAddForm({ provider: providers[0] || '', label: '', api_key: '', priority: 100 });
        setShowAddModal(false);
        showToast('Provider key added successfully!');
        await loadKeyPool();
      } else {
        const err = await res.json();
        showToast('Error: ' + (err.detail || 'Failed to add provider key'), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Failed to add provider key', 'error');
    }
  };

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    const provider = editingKey.provider.trim();
    const label = editingKey.label.trim();
    const priority = parseInt(editingKey.priority.toString());

    if (!provider || !label) {
      showToast('Provider and label cannot be empty.', 'error');
      return;
    }
    if (isNaN(priority) || priority <= 0) {
      showToast('Priority must be a positive integer.', 'error');
      return;
    }

    try {
      const res = await adminFetch(`/dashboard/api/provider-key-pool/${editingKey.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          provider,
          label,
          api_key: editingKey.api_key || '', // blank keeps original
          priority,
          is_active: !!editingKey.is_active,
        }),
      });
      if (res.ok) {
        showToast('Provider key updated successfully!');
        setShowEditModal(false);
        await loadKeyPool();
      } else {
        const err = await res.json();
        showToast('Error: ' + (err.detail || 'Failed to update key'), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Failed to update key', 'error');
    }
  };

  const handleDelete = async (keyId: string, confirmed = false) => {
    if (!confirmed) {
      confirmAction('Are you sure you want to delete this provider key?', () =>
        handleDelete(keyId, true)
      );
      return;
    }
    try {
      const res = await adminFetch(`/dashboard/api/provider-key-pool/${keyId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setShowEditModal(false);
        showToast('Provider key deleted successfully!');
        await loadKeyPool();
      } else {
        const err = await res.json();
        showToast('Error: ' + (err.detail || 'Failed to delete key'), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Failed to delete key', 'error');
    }
  };

  const isKeyDirty = (key: ProviderKey) => {
    if (!key || !key._original) return false;
    const priority = Number.isFinite(Number(key.priority)) ? Number(key.priority) : 0;
    return (
      key.provider !== key._original.provider ||
      key.label !== key._original.label ||
      priority !== key._original.priority ||
      !!key.is_active !== key._original.is_active ||
      !!(key.api_key && key.api_key.trim())
    );
  };

  const openEditModal = (key: ProviderKey) => {
    setEditingKey({
      ...key,
      api_key: '', // clear for modal input
    });
    setShowEditModal(true);
  };

  return (
    <section id="key-pool" className="tab-content active block pt-8">
      <header className="flex justify-between items-end mb-8 pb-6 border-b border-border">
        <div className="header-titles">
          <h1 className="font-heading text-3xl font-semibold tracking-tight">Provider Key Pool</h1>
          <p className="text-zinc-400 text-sm mt-1">Server-side upstream keys with fallback order</p>
        </div>
        <Button
          onClick={() => setShowAddModal(true)}
          className="bg-white text-black hover:bg-zinc-200 font-medium px-6 py-2.5 rounded-full transition-all duration-200 shadow-md hover:shadow-lg flex items-center gap-1.5"
        >
          + Add Provider Key
        </Button>
      </header>

      {/* Table List */}
      <div className="table-container glass-panel bg-[#18181b] border border-zinc-800 rounded-md overflow-hidden shadow-xl">
        <Table>
          <TableHeader className="bg-black/25">
            <TableRow className="border-b border-zinc-850 hover:bg-transparent">
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 pl-6 w-[160px]">Label</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 w-[120px]">Provider</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4">Key</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-center w-[90px]">Priority</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-center w-[80px]">Status</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-right pr-6 w-[90px]">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={6} className="text-center text-zinc-400 py-8">
                  Loading provider keys...
                </TableCell>
              </TableRow>
            ) : keyPool.length === 0 ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={6} className="text-center text-zinc-400 py-8">
                  No provider keys configured yet.
                </TableCell>
              </TableRow>
            ) : (
              keyPool.map((key) => (
                <TableRow key={key.id} className="border-b border-zinc-900 hover:bg-white/[0.015] transition-colors">
                  <TableCell className="font-medium text-sm py-4 pl-6">{key.label}</TableCell>
                  <TableCell className="py-4">
                    <Badge className="bg-blue-500/10 text-blue-300 border border-blue-500/20 text-[10px] font-medium tracking-wide rounded uppercase px-2.5 py-0.5 capitalize">
                      {key.provider}
                    </Badge>
                  </TableCell>
                  <TableCell className="py-4 font-mono text-xs text-zinc-400">
                    {key.masked_key || '••••••••••••••••'}
                  </TableCell>
                  <TableCell className="text-center py-4 font-mono text-xs">
                    {key.priority}
                  </TableCell>
                  <TableCell className="text-center py-4">
                    <Badge
                      className={`text-[10px] font-semibold tracking-wide uppercase px-2.5 py-0.5 rounded-full ${
                        key.is_active
                          ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                          : 'bg-red-500/10 text-red-500 border border-red-500/20'
                      }`}
                    >
                      {key.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right py-4 pr-6">
                    <Button
                      variant="outline"
                      onClick={() => openEditModal(key)}
                      className="border-zinc-800 text-white hover:bg-zinc-800 text-xs px-3 py-1 h-auto rounded"
                    >
                      Edit
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Add Upstream Key Dialog */}
      <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
        <DialogContent className="max-w-[440px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">Add Upstream Key</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleCreate} className="flex flex-col gap-4 my-2">
            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">Provider</label>
              <div className="custom-select-wrapper select-wrapper w-full">
                <select
                  value={addForm.provider}
                  onChange={(e) => setAddForm({ ...addForm, provider: e.target.value })}
                  required
                  className="w-full bg-black/45 border border-zinc-850 text-white rounded px-4 py-3 appearance-none cursor-pointer outline-none focus:border-purple-500"
                >
                  {providers.map((name) => (
                    <option key={name} value={name} className="bg-zinc-950 text-white">
                      {name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">Label</label>
              <Input
                value={addForm.label}
                onChange={(e) => setAddForm({ ...addForm, label: e.target.value })}
                required
                placeholder="e.g. Gemini Production Key"
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">API Key</label>
              <Input
                type="password"
                value={addForm.api_key}
                onChange={(e) => setAddForm({ ...addForm, api_key: e.target.value })}
                required
                placeholder="Provider API key"
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">Priority (lower is higher priority)</label>
              <Input
                type="number"
                min="1"
                value={addForm.priority}
                onChange={(e) => setAddForm({ ...addForm, priority: parseInt(e.target.value) || 0 })}
                required
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
              />
            </div>

            <DialogFooter className="mt-4 flex gap-3 justify-end">
              <Button
                variant="outline"
                type="button"
                onClick={() => setShowAddModal(false)}
                className="border-zinc-800 text-white hover:bg-zinc-900 rounded font-medium"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                className="bg-white text-black hover:bg-zinc-200 rounded font-medium"
              >
                Save Key
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit Upstream Key Dialog */}
      <Dialog open={showEditModal} onOpenChange={setShowEditModal}>
        <DialogContent className="max-w-[440px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">Edit Upstream Key</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleUpdate} className="flex flex-col gap-4 my-2">
            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">Provider</label>
              <div className="custom-select-wrapper select-wrapper w-full">
                <select
                  value={editingKey.provider}
                  onChange={(e) => setEditingKey({ ...editingKey, provider: e.target.value })}
                  required
                  className="w-full bg-black/45 border border-zinc-850 text-white rounded px-4 py-3 appearance-none cursor-pointer outline-none focus:border-purple-500"
                >
                  {providers.map((name) => (
                    <option key={name} value={name} className="bg-zinc-950 text-white">
                      {name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">Label</label>
              <Input
                value={editingKey.label}
                onChange={(e) => setEditingKey({ ...editingKey, label: e.target.value })}
                required
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">API Key</label>
              <Input
                type="password"
                value={editingKey.api_key}
                onChange={(e) => setEditingKey({ ...editingKey, api_key: e.target.value })}
                placeholder="leave blank to keep existing key"
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">Priority</label>
              <Input
                type="number"
                min="1"
                value={editingKey.priority}
                onChange={(e) => setEditingKey({ ...editingKey, priority: parseInt(e.target.value) || 0 })}
                required
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
              />
            </div>

            <div
              onClick={() => setEditingKey({ ...editingKey, is_active: !editingKey.is_active })}
              className={`flex items-center justify-between p-4 rounded-lg cursor-pointer border transition-all duration-200 ${
                editingKey.is_active
                  ? 'bg-purple-950/10 border-purple-500/25'
                  : 'bg-white/3 border-zinc-800'
              }`}
            >
              <div className="flex flex-col gap-0.5">
                <span className={`font-semibold text-sm ${editingKey.is_active ? 'text-purple-400' : 'text-white'}`}>Active Status</span>
                <span className="text-zinc-400 text-xs">Enable for routing</span>
              </div>
              <Switch
                checked={editingKey.is_active}
                onCheckedChange={(checked) => setEditingKey({ ...editingKey, is_active: checked })}
              />
            </div>

            <DialogFooter className="mt-4 flex justify-between w-full gap-3">
              <Button
                onClick={() => handleDelete(editingKey.id)}
                type="button"
                className="bg-transparent border border-red-500/20 text-red-500 hover:bg-red-500/10 rounded font-medium flex items-center gap-1.5"
              >
                <Trash2 className="w-4 h-4" /> Delete
              </Button>
              <div className="flex gap-3 justify-end">
                <Button
                  variant="outline"
                  type="button"
                  onClick={() => setShowEditModal(false)}
                  className="border-zinc-800 text-white hover:bg-zinc-900 rounded font-medium"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={!isKeyDirty(editingKey)}
                  className="bg-white text-black hover:bg-zinc-200 rounded font-medium disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Save Changes
                </Button>
              </div>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}
