'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { adminFetch } from '@/lib/api';
import { runFlipUpdate } from '@/lib/list-flip';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Trash2, ChevronUp, ChevronDown, Move } from 'lucide-react';

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

function gapIndexFromPointer(clientY: number, rows: NodeListOf<Element>): number {
  const count = rows.length;
  if (count === 0) return 0;
  for (let i = 0; i < count; i++) {
    const rect = rows[i].getBoundingClientRect();
    if (clientY < rect.top + rect.height / 2) {
      return i;
    }
  }
  return count;
}

function insertIndexFromGap(sourceIndex: number, gapIndex: number): number {
  return sourceIndex < gapIndex ? gapIndex - 1 : gapIndex;
}

function isValidDropGap(sourceIndex: number, gapIndex: number): boolean {
  return gapIndex !== sourceIndex && gapIndex !== sourceIndex + 1;
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
  const [addForm, setAddForm] = useState({ provider: '', label: '', api_key: '' });
  const [editingKey, setEditingKey] = useState<ProviderKey>({
    id: '',
    provider: '',
    label: '',
    priority: 100,
    is_active: true,
    api_key: '',
  });

  // Drag and Drop state
  const [draggedItem, setDraggedItem] = useState<{
    provider: string;
    itemId: string;
    sourceIndex: number;
  } | null>(null);
  const [dragOverGap, setDragOverGap] = useState<{ provider: string; gapIndex: number } | null>(null);
  const draggedItemRef = useRef(draggedItem);
  const dragOverGapRef = useRef(dragOverGap);
  const dropHandledRef = useRef(false);

  useEffect(() => {
    draggedItemRef.current = draggedItem;
  }, [draggedItem]);

  useEffect(() => {
    dragOverGapRef.current = dragOverGap;
  }, [dragOverGap]);

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

  // Grouped keys by provider, sorted by priority
  const groupedKeys = useMemo(() => {
    const groups: Record<string, ProviderKey[]> = {};
    keyPool.forEach(k => {
      if (!groups[k.provider]) groups[k.provider] = [];
      groups[k.provider].push(k);
    });
    // Sort each group by priority
    Object.keys(groups).forEach(p => {
      groups[p].sort((a, b) => a.priority - b.priority);
    });
    return groups;
  }, [keyPool]);

  const getGroupItemsContainer = (provider: string) =>
    document.getElementById(`provider-keys-${provider}`);

  const getGroupRows = (provider: string) => {
    const container = getGroupItemsContainer(provider);
    return container?.querySelectorAll('.key-item-row') ?? null;
  };

  const resolveDropGap = (clientY: number, provider: string): number => {
    const rows = getGroupRows(provider);
    if (!rows) return 0;
    return gapIndexFromPointer(clientY, rows);
  };

  const persistPriorities = async (keysToUpdate: ProviderKey[]) => {
    for (const key of keysToUpdate) {
      const res = await adminFetch(`/dashboard/api/provider-key-pool/${key.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          provider: key.provider,
          label: key.label,
          priority: key.priority,
          is_active: key.is_active,
        }),
      });
      if (!res.ok) {
        throw new Error('Failed to update priority');
      }
    }
  };

  const applyKeyReorder = async (
    provider: string,
    sourceIndex: number,
    targetIndex: number
  ) => {
    if (sourceIndex === targetIndex) return;

    let keysToUpdate: ProviderKey[] = [];
    const container = getGroupItemsContainer(provider);
    
    runFlipUpdate(container, () => {
      setKeyPool((prev) => {
        const pKeys = [...(groupedKeys[provider] || [])];
        const [moved] = pKeys.splice(sourceIndex, 1);
        pKeys.splice(targetIndex, 0, moved);
        
        const reordered = pKeys.map((k, idx) => ({
          ...k,
          priority: idx + 1
        }));

        keysToUpdate = reordered.filter(k => k.priority !== k._original?.priority);

        return prev.map(k => {
          if (k.provider === provider) {
            const found = reordered.find(r => r.id === k.id);
            if (found) {
              return {
                ...found,
                _original: found._original ? {
                  ...found._original,
                  priority: found.priority
                } : undefined
              };
            }
          }
          return k;
        });
      });
    });

    if (keysToUpdate.length === 0) return;

    try {
      await persistPriorities(keysToUpdate);
    } catch (err) {
      console.error(err);
      showToast('Failed to update order', 'error');
      await loadKeyPool();
    }
  };

  const finishDragSession = () => {
    setDraggedItem(null);
    setDragOverGap(null);
  };

  useEffect(() => {
    if (!draggedItem) return;
    const keepMoveCursor = (e: DragEvent) => {
      e.preventDefault();
      if (e.dataTransfer) {
        e.dataTransfer.dropEffect = 'move';
      }
    };
    document.addEventListener('dragover', keepMoveCursor);
    document.body.classList.add('group-drag-active');
    return () => {
      document.removeEventListener('dragover', keepMoveCursor);
      document.body.classList.remove('group-drag-active');
    };
  }, [draggedItem]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const provider = addForm.provider.trim();
    const label = addForm.label.trim();
    const api_key = addForm.api_key.trim();

    if (!provider || !label || !api_key) {
      showToast('Please fill out all fields.', 'error');
      return;
    }

    // Auto-calculate priority: bottom of the list
    const pKeys = groupedKeys[provider] || [];
    const priority = pKeys.length + 1;

    try {
      const res = await adminFetch('/dashboard/api/provider-key-pool', {
        method: 'POST',
        body: JSON.stringify({ provider, label, api_key, priority, is_active: true }),
      });
      if (res.ok) {
        setAddForm({ provider: providers[0] || '', label: '', api_key: '' });
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
    const label = editingKey.label.trim();

    if (!label) {
      showToast('Label cannot be empty.', 'error');
      return;
    }

    try {
      const res = await adminFetch(`/dashboard/api/provider-key-pool/${editingKey.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          provider: editingKey.provider, // keep original
          label,
          api_key: editingKey.api_key || '', // blank keeps original
          priority: editingKey.priority, // keep original
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
    return (
      key.label !== key._original.label ||
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

  const handleDragStart = (e: React.DragEvent, provider: string, itemIndex: number, keyId: string) => {
    dropHandledRef.current = false;
    setDragOverGap(null);
    setDraggedItem({
      provider,
      itemId: keyId,
      sourceIndex: itemIndex,
    });
    e.dataTransfer.effectAllowed = 'move';
  };

  const updateDropTarget = (e: React.DragEvent, provider: string) => {
    e.preventDefault();
    const drag = draggedItemRef.current;
    if (!drag || drag.provider !== provider) return;

    e.dataTransfer.dropEffect = 'move';
    const gapIndex = resolveDropGap(e.clientY, provider);

    if (!isValidDropGap(drag.sourceIndex, gapIndex)) {
      setDragOverGap(null);
      return;
    }

    setDragOverGap((prev) =>
      prev?.provider === provider && prev.gapIndex === gapIndex ? prev : { provider, gapIndex }
    );
  };

  const handleDragEnd = async () => {
    if (!dropHandledRef.current) {
      const drag = draggedItemRef.current;
      const over = dragOverGapRef.current;
      if (
        drag &&
        over &&
        drag.provider === over.provider &&
        isValidDropGap(drag.sourceIndex, over.gapIndex)
      ) {
        dropHandledRef.current = true;
        await applyKeyReorder(
          drag.provider,
          drag.sourceIndex,
          insertIndexFromGap(drag.sourceIndex, over.gapIndex)
        );
      }
    }
    dropHandledRef.current = false;
    finishDragSession();
  };

  const handleProviderDrop = async (e: React.DragEvent, provider: string) => {
    e.preventDefault();
    const drag = draggedItemRef.current;
    if (!drag || drag.provider !== provider) return;

    const gapIndex = resolveDropGap(e.clientY, provider);
    if (!isValidDropGap(drag.sourceIndex, gapIndex)) {
      finishDragSession();
      return;
    }

    dropHandledRef.current = true;
    await applyKeyReorder(
      provider,
      drag.sourceIndex,
      insertIndexFromGap(drag.sourceIndex, gapIndex)
    );
    finishDragSession();
  };

  const handleMoveKey = async (provider: string, index: number, direction: number) => {
    const pKeys = groupedKeys[provider] || [];
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= pKeys.length) return;
    await applyKeyReorder(provider, index, targetIndex);
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

      {/* Provider Group List */}
      <div className="group-list flex flex-col gap-6">
        {loading ? (
          <div className="glass-panel p-8 text-center text-zinc-400">Loading provider keys...</div>
        ) : Object.keys(groupedKeys).length === 0 ? (
          <div className="glass-panel p-8 text-center text-zinc-400">
            No provider keys configured yet.
          </div>
        ) : (
          Object.entries(groupedKeys).map(([provider, keys]) => (
            <div key={provider} className="glass-panel group-card p-6 bg-[#18181b] border border-zinc-800 rounded-md shadow-xl">
              <div className="group-card-header mb-5">
                <div className="group-card-title-section flex items-center gap-3 w-full">
                  <Badge className="bg-blue-500/10 text-blue-300 border border-blue-500/20 text-[10px] font-medium tracking-wide rounded uppercase px-2.5 py-0.5 capitalize">
                    {provider}
                  </Badge>
                  <h3 className="font-heading text-lg font-semibold text-white capitalize">{provider} Keys</h3>
                  <div className="flex gap-2 ml-auto items-center text-xs text-zinc-500">
                    {keys.length} {keys.length === 1 ? 'key' : 'keys'}
                  </div>
                </div>
              </div>

              <div
                id={`provider-keys-${provider}`}
                className={`group-items flex flex-col gap-2 ${draggedItem?.provider === provider ? 'select-none' : ''}`}
                onDragOver={(e) => updateDropTarget(e, provider)}
                onDrop={(e) => void handleProviderDrop(e, provider)}
              >
                {keys.length === 0 ? (
                  <div className="text-zinc-500 text-xs py-4 text-center border border-dashed border-zinc-850 rounded bg-black/10">
                    No keys. Add one above.
                  </div>
                ) : (
                  <>
                    {draggedItem?.provider === provider &&
                      dragOverGap?.provider === provider &&
                      dragOverGap.gapIndex === 0 && (
                        <div className="group-drop-indicator" aria-hidden="true" />
                      )}
                    {keys.map((key, index) => (
                      <React.Fragment key={key.id}>
                        <div
                          data-flip-id={key.id}
                          className={`key-item-row bg-black/20 border border-zinc-850 rounded px-4 py-3 min-h-[52px] grid grid-cols-[36px_minmax(120px,220px)_minmax(150px,280px)_1fr_auto] gap-4 items-center ${
                            draggedItem?.provider === provider
                              ? ''
                              : 'hover:border-zinc-600 hover:bg-black/35'
                          } ${
                            draggedItem?.provider === provider && draggedItem.itemId === key.id
                              ? 'is-dragging'
                              : ''
                          }`}
                        >
                          <div className="flex items-center justify-start">
                            <span className="inline-flex items-center justify-center min-w-[22px] h-[22px] bg-zinc-800 border border-zinc-600 rounded-full text-zinc-300 text-[11px] font-bold">
                              {index + 1}
                            </span>
                          </div>

                          <div className="font-semibold text-sm text-white font-mono truncate select-all" title={key.label}>
                            {key.label}
                          </div>

                          <div className="font-mono text-xs text-zinc-500 truncate select-all">
                            {key.masked_key || '••••••••••••••••'}
                          </div>

                          <div className="flex items-center">
                            {!key.is_active && (
                              <Badge className="bg-red-500/10 text-red-500 border border-red-500/20 text-[9px] font-semibold tracking-wide uppercase px-1.5 py-0 rounded-full">
                                Inactive
                              </Badge>
                            )}
                          </div>

                          <div className="flex items-center justify-end gap-1.5">
                            <div
                              draggable
                              onDragStart={(e) => handleDragStart(e, provider, index, key.id)}
                              onDragEnd={handleDragEnd}
                              className="text-zinc-500 hover:text-zinc-300 cursor-grab active:cursor-grabbing p-1.5 mr-1 hover:bg-zinc-800/50 rounded touch-none"
                              title="Drag to reorder"
                            >
                              <Move className="w-4 h-4 pointer-events-none" />
                            </div>
                            <Button
                              variant="outline"
                              onClick={() => handleMoveKey(provider, index, -1)}
                              disabled={index === 0}
                              className="border-zinc-850 text-zinc-400 hover:bg-zinc-800/50 hover:text-white p-1.5 h-8 w-8 rounded disabled:opacity-30 disabled:cursor-not-allowed"
                              title="Move Up"
                            >
                              <ChevronUp className="w-4 h-4" />
                            </Button>
                            <Button
                              variant="outline"
                              onClick={() => handleMoveKey(provider, index, 1)}
                              disabled={index === keys.length - 1}
                              className="border-zinc-850 text-zinc-400 hover:bg-zinc-800/50 hover:text-white p-1.5 h-8 w-8 rounded disabled:opacity-30 disabled:cursor-not-allowed"
                              title="Move Down"
                            >
                              <ChevronDown className="w-4 h-4" />
                            </Button>
                            <Button
                              variant="outline"
                              onClick={() => openEditModal(key)}
                              className="border-zinc-850 text-white hover:bg-zinc-800/50 hover:text-white text-xs px-3 py-1 h-8 rounded ml-5"
                              title="Edit Key"
                            >
                              Edit
                            </Button>
                          </div>
                        </div>

                        {draggedItem?.provider === provider &&
                          dragOverGap?.provider === provider &&
                          dragOverGap.gapIndex === index + 1 && (
                            <div className="group-drop-indicator" aria-hidden="true" />
                          )}
                      </React.Fragment>
                    ))}
                  </>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Add Upstream Key Dialog */}
      <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
        <DialogContent className="max-w-[400px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
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
                  className="orion-native-select"
                >
                  {providers.map((name) => (
                    <option key={name} value={name}>
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
        <DialogContent className="max-w-[400px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">Edit Upstream Key</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleUpdate} className="flex flex-col gap-4 my-2">
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
