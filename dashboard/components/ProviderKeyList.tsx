'use client';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useApp } from '@/components/AppContext';
import { runFlipUpdate } from '@/lib/list-flip';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ChevronUp, ChevronDown, Move } from 'lucide-react';

export interface ProviderKey {
  id: string; provider: string; label: string; priority: number; is_active: boolean;
  masked_key?: string; api_key?: string; display_name?: string; source?: 'shared'|'personal';
  key_id?: string; name?: string; hub_id?: string; hub_name?: string;
  _original?: {provider: string;label: string;priority: number;is_active: boolean};
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

export function ProviderKeyList({keys: incoming, loading, onEdit, onReorder}: {
  keys: ProviderKey[]; loading: boolean; onEdit: (key: ProviderKey)=>void;
  onReorder: (keys: ProviderKey[])=>Promise<void>;
}) {
  const {t,showToast} = useApp();
  const [keyPool,setKeyPool]=useState(incoming);
  useEffect(()=>setKeyPool(incoming),[incoming]);
  const openEditModal=onEdit;
  const loadKeyPool=async()=>setKeyPool(incoming);
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

  const persistPriorities = async (keysToUpdate: ProviderKey[]) => { await onReorder(keysToUpdate); };

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

        keysToUpdate = reordered;

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
      showToast(t('groups.toast.updateOrderFailed'), 'error'); // Shared translation
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

  return <>
      {/* Provider Group List */}
      <div className="group-list flex flex-col gap-6">
        {loading ? (
          <div className="glass-panel p-8 text-center text-zinc-400">{t('keyPool.loading')}</div>
        ) : Object.keys(groupedKeys).length === 0 ? (
          <div className="glass-panel p-8 text-center text-zinc-400">
            {t('keyPool.empty')}
          </div>
        ) : (
          Object.entries(groupedKeys).map(([provider, keys]) => (
            <div key={provider} className="glass-panel group-card p-6 bg-[#18181b] border border-zinc-800 rounded-md shadow-xl">
              <div className="group-card-header mb-5">
                <div className="group-card-title-section flex items-center gap-3 w-full">
                  <Badge className="bg-blue-500/10 text-blue-300 border border-blue-500/20 text-[10px] font-medium tracking-wide rounded uppercase px-2.5 py-0.5 capitalize">
                    {provider}
                  </Badge>
                  <h3 className="font-heading text-lg font-semibold text-white capitalize">
                    {t('keyPool.providerKeys', { provider: provider === 'openai' ? 'OpenAI' : provider.charAt(0).toUpperCase() + provider.slice(1) })}
                  </h3>
                  <div className="flex gap-2 ml-auto items-center text-xs text-zinc-500">
                    {keys.length} {keys.length === 1 ? t('keyPool.keyCount') : t('keyPool.keysCount')}
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
                    {t('keyPool.emptyItems')}
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
                          className={`key-item-row bg-black/20 border border-zinc-850 rounded px-4 py-3 min-h-[52px] grid grid-cols-[28px_minmax(0,1fr)_auto] sm:grid-cols-[28px_minmax(120px,1fr)_minmax(80px,180px)_auto_auto] gap-4 items-center ${
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

                          <div className="font-semibold text-sm text-white font-mono truncate select-all" title={key.display_name || key.label} id={key.id}>
                            {key.display_name || key.label}
                          </div>

                          <div className="hidden sm:block font-mono text-xs text-zinc-500 truncate select-all">
                            {key.masked_key || '••••••••••••••••'}
                          </div>

                          <div className="hidden sm:flex items-center">
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
                              title={t('keyPool.editModalTitle')}
                            >
                              {t('common.edit')}
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

  </>;
}
