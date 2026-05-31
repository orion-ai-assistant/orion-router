'use client';

import React, { useState, useEffect, useRef } from 'react';
import { adminFetch } from '@/lib/api';
import { runFlipUpdate } from '@/lib/list-flip';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Trash2, ChevronUp, ChevronDown, Move } from 'lucide-react';

interface GroupItem {
  id: string;
  model_id: string;
  priority: number;
  name: string;
  provider: string;
  capability: string;
  thinking_level?: string | null;
  system_prompt?: string | null;
}

interface ModelGroup {
  id: string;
  name: string;
  description: string;
  capability: 'chat' | 'tts' | 'embed';
  is_active: boolean;
  items: GroupItem[];
}

interface ModelItem {
  id: string;
  name: string;
  provider: string;
  capability: 'chat' | 'tts' | 'embed';
  is_active: boolean;
}

function reorderGroupItemsInState(
  groups: ModelGroup[],
  groupId: string,
  fromIndex: number,
  toIndex: number
): ModelGroup[] {
  if (fromIndex === toIndex) return groups;
  return groups.map((g) => {
    if (g.id !== groupId) return g;
    const items = [...g.items];
    const [moved] = items.splice(fromIndex, 1);
    items.splice(toIndex, 0, moved);
    return { ...g, items };
  });
}

/** Gap 0 = before first row; gap n = after last row */
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

async function persistGroupPriorities(groupId: string, items: GroupItem[]): Promise<void> {
  for (let i = 0; i < items.length; i++) {
    const newPriority = i + 1;
    if (items[i].priority !== newPriority) {
      const res = await adminFetch(`/dashboard/api/model-groups/${groupId}/items/${items[i].id}`, {
        method: 'PUT',
        body: JSON.stringify({ priority: newPriority }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to update priority');
      }
    }
  }
}

export default function GroupsPage() {
  const { showToast, confirmAction } = useApp();
  const [groups, setGroups] = useState<ModelGroup[]>([]);
  const [models, setModels] = useState<ModelItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Modals visibility
  const [showAddGroupModal, setShowAddGroupModal] = useState<boolean>(false);
  const [showEditGroupModal, setShowEditGroupModal] = useState<boolean>(false);
  const [showAddGroupItemModal, setShowAddGroupItemModal] = useState<boolean>(false);
  const [showEditGroupItemModal, setShowEditGroupItemModal] = useState<boolean>(false);

  // Form states
  const [groupForm, setGroupForm] = useState({ name: '', capability: 'chat' as 'chat' | 'tts' | 'embed' });
  const [editingGroup, setEditingGroup] = useState<ModelGroup>({
    id: '',
    name: '',
    description: '',
    capability: 'chat',
    is_active: true,
    items: [],
  });
  
  const [activeGroupForItems, setActiveGroupForItems] = useState<ModelGroup | null>(null);
  const [selectedModelId, setSelectedModelId] = useState<string>('');
  const [selectedThinkingLevel, setSelectedThinkingLevel] = useState<string>('');
  const [selectedSystemPrompt, setSelectedSystemPrompt] = useState<string>('');
  const [editingGroupItem, setEditingGroupItem] = useState<{groupId: string, itemId: string, name: string, provider: string, priority: number, thinking_level: string, system_prompt: string} | null>(null);
  
  // Drag and Drop state
  const [draggedItem, setDraggedItem] = useState<{
    groupId: string;
    itemId: string;
    sourceIndex: number;
  } | null>(null);
  const [dragOverGap, setDragOverGap] = useState<{ groupId: string; gapIndex: number } | null>(null);
  const draggedItemRef = useRef(draggedItem);
  const dragOverGapRef = useRef(dragOverGap);
  const dropHandledRef = useRef(false);

  useEffect(() => {
    draggedItemRef.current = draggedItem;
  }, [draggedItem]);

  useEffect(() => {
    dragOverGapRef.current = dragOverGap;
  }, [dragOverGap]);

  const getGroupItemsContainer = (groupId: string) =>
    document.getElementById(`group-items-${groupId}`);

  const getGroupRows = (groupId: string) => {
    const container = getGroupItemsContainer(groupId);
    return container?.querySelectorAll('.group-item-row') ?? null;
  };

  const resolveDropGap = (clientY: number, groupId: string): number => {
    const rows = getGroupRows(groupId);
    if (!rows) return 0;
    return gapIndexFromPointer(clientY, rows);
  };

  const applyGroupItemReorder = async (
    groupId: string,
    sourceIndex: number,
    targetIndex: number
  ) => {
    if (sourceIndex === targetIndex) return;

    let reordered: GroupItem[] = [];
    const container = getGroupItemsContainer(groupId);
    runFlipUpdate(container, () => {
      setGroups((prev) => {
        const next = reorderGroupItemsInState(prev, groupId, sourceIndex, targetIndex);
        const group = next.find((g) => g.id === groupId);
        if (group) reordered = group.items;
        return next;
      });
    });

    if (reordered.length === 0) return;

    try {
      await persistGroupPriorities(groupId, reordered);
      setGroups((prev) =>
        prev.map((g) =>
          g.id === groupId
            ? {
                ...g,
                items: reordered.map((it, i) => ({ ...it, priority: i + 1 })),
              }
            : g
        )
      );
    } catch (err) {
      console.error(err);
      showToast(err instanceof Error ? err.message : 'Failed to update order', 'error');
      await loadGroups();
    }
  };

  const finishDragSession = () => {
    setDraggedItem(null);
    setDragOverGap(null);
  };

  const loadModels = async () => {
    try {
      const res = await adminFetch('/dashboard/api/models');
      if (res.ok) {
        const data = await res.json();
        setModels(data.models || []);
      }
    } catch (e) {
      console.error('Failed to load models:', e);
    }
  };

  const loadGroups = async () => {
    try {
      const res = await adminFetch('/dashboard/api/model-groups');
      if (res.ok) {
        const data = await res.json();
        setGroups(data.groups || []);
      }
    } catch (err) {
      console.error('Failed to load groups:', err);
      showToast('Failed to load model groups', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const initData = async () => {
      await loadModels();
      await loadGroups();
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

  const handleCreateGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = groupForm.name.trim();
    if (!name) {
      showToast('Please enter a group name.', 'error');
      return;
    }

    try {
      const res = await adminFetch('/dashboard/api/model-groups', {
        method: 'POST',
        body: JSON.stringify({
          name,
          description: '',
          capability: groupForm.capability,
          is_active: true,
        }),
      });
      if (res.ok) {
        setGroupForm({ name: '', capability: 'chat' });
        setShowAddGroupModal(false);
        showToast('Model group created successfully!');
        await loadGroups();
      } else {
        const err = await res.json();
        showToast('Error: ' + (err.detail || 'Failed to create group'), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Failed to create group', 'error');
    }
  };

  const handleUpdateGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = editingGroup.name.trim();
    if (!name) {
      showToast('Group name cannot be empty.', 'error');
      return;
    }

    try {
      const res = await adminFetch(`/dashboard/api/model-groups/${editingGroup.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          name,
          description: '',
          capability: editingGroup.capability,
          is_active: !!editingGroup.is_active,
        }),
      });
      if (res.ok) {
        showToast('Group updated successfully!');
        setShowEditGroupModal(false);
        await loadGroups();
      } else {
        const err = await res.json();
        showToast('Error: ' + (err.detail || 'Failed to update group'), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Failed to update group', 'error');
    }
  };

  const handleDeleteGroup = async (groupId: string, confirmed = false) => {
    if (!confirmed) {
      confirmAction('Are you sure you want to delete this model group?', () =>
        handleDeleteGroup(groupId, true)
      );
      return;
    }
    try {
      const res = await adminFetch(`/dashboard/api/model-groups/${groupId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setShowEditGroupModal(false);
        showToast('Model group deleted successfully!');
        await loadGroups();
      } else {
        const err = await res.json();
        showToast('Error: ' + (err.detail || 'Failed to delete group'), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Failed to delete group', 'error');
    }
  };

  const openAddGroupItem = (group: ModelGroup) => {
    setActiveGroupForItems(group);
    setSelectedModelId('');
    setSelectedThinkingLevel('');
    setSelectedSystemPrompt('');
    setShowAddGroupItemModal(true);
  };

  const handleAddGroupItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeGroupForItems) return;
    if (!selectedModelId) {
      showToast('Please select a model.', 'error');
      return;
    }
    const priority = activeGroupForItems.items.length + 1;

    try {
      const res = await adminFetch(`/dashboard/api/model-groups/${activeGroupForItems.id}/items`, {
        method: 'POST',
        body: JSON.stringify({ 
          model_id: selectedModelId, 
          priority, 
          thinking_level: selectedThinkingLevel || null,
          system_prompt: selectedSystemPrompt || null 
        }),
      });
      if (res.ok) {
        setShowAddGroupItemModal(false);
        showToast('Model added to group!');
        await loadGroups();
      } else {
        const err = await res.json();
        showToast('Error: ' + (err.detail || 'Failed to add model to group'), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Failed to add model to group', 'error');
    }
  };

  const openEditGroupItem = (group: ModelGroup, item: GroupItem) => {
    setEditingGroupItem({
      groupId: group.id,
      itemId: item.id,
      name: item.name,
      provider: item.provider,
      priority: item.priority,
      thinking_level: item.thinking_level || '',
      system_prompt: item.system_prompt || '',
    });
    setShowEditGroupItemModal(true);
  };

  const handleUpdateGroupItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingGroupItem) return;

    try {
      const res = await adminFetch(`/dashboard/api/model-groups/${editingGroupItem.groupId}/items/${editingGroupItem.itemId}`, {
        method: 'PUT',
        body: JSON.stringify({ 
          priority: editingGroupItem.priority, 
          thinking_level: editingGroupItem.thinking_level || null,
          system_prompt: editingGroupItem.system_prompt || null
        }),
      });
      if (res.ok) {
        setShowEditGroupItemModal(false);
        showToast('Model group item updated!');
        await loadGroups();
      } else {
        const err = await res.json();
        showToast('Error: ' + (err.detail || 'Failed to update item'), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Failed to update item', 'error');
    }
  };

  const handleDeleteGroupItem = async (group: ModelGroup, itemId: string, confirmed = false) => {
    if (!confirmed) {
      confirmAction('Are you sure you want to remove this model from the group?', () =>
        handleDeleteGroupItem(group, itemId, true)
      );
      return;
    }
    try {
      const res = await adminFetch(`/dashboard/api/model-groups/${group.id}/items/${itemId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setShowEditGroupItemModal(false);
        showToast('Model removed from group successfully!');
        await loadGroups();
      } else {
        const err = await res.json();
        showToast('Error: ' + (err.detail || 'Failed to remove model'), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Failed to remove model', 'error');
    }
  };

  const handleMoveGroupItem = async (group: ModelGroup, index: number, direction: number) => {
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= group.items.length) return;
    await applyGroupItemReorder(group.id, index, targetIndex);
  };

  const handleDragStart = (e: React.DragEvent, group: ModelGroup, itemIndex: number) => {
    dropHandledRef.current = false;
    setDragOverGap(null);
    setDraggedItem({
      groupId: group.id,
      itemId: group.items[itemIndex].id,
      sourceIndex: itemIndex,
    });
    e.dataTransfer.effectAllowed = 'move';
  };

  const updateDropTarget = (e: React.DragEvent, groupId: string) => {
    e.preventDefault();
    const drag = draggedItemRef.current;
    if (!drag || drag.groupId !== groupId) return;

    e.dataTransfer.dropEffect = 'move';
    const gapIndex = resolveDropGap(e.clientY, groupId);

    if (!isValidDropGap(drag.sourceIndex, gapIndex)) {
      setDragOverGap(null);
      return;
    }

    setDragOverGap((prev) =>
      prev?.groupId === groupId && prev.gapIndex === gapIndex ? prev : { groupId, gapIndex }
    );
  };

  const handleDragEnd = async () => {
    if (!dropHandledRef.current) {
      const drag = draggedItemRef.current;
      const over = dragOverGapRef.current;
      if (
        drag &&
        over &&
        drag.groupId === over.groupId &&
        isValidDropGap(drag.sourceIndex, over.gapIndex)
      ) {
        dropHandledRef.current = true;
        await applyGroupItemReorder(
          drag.groupId,
          drag.sourceIndex,
          insertIndexFromGap(drag.sourceIndex, over.gapIndex)
        );
      }
    }
    dropHandledRef.current = false;
    finishDragSession();
  };

  const handleGroupDrop = async (e: React.DragEvent, groupId: string) => {
    e.preventDefault();
    const drag = draggedItemRef.current;
    if (!drag || drag.groupId !== groupId) return;

    const gapIndex = resolveDropGap(e.clientY, groupId);
    if (!isValidDropGap(drag.sourceIndex, gapIndex)) {
      finishDragSession();
      return;
    }

    dropHandledRef.current = true;
    await applyGroupItemReorder(
      groupId,
      drag.sourceIndex,
      insertIndexFromGap(drag.sourceIndex, gapIndex)
    );
    finishDragSession();
  };

  const openEditGroupModal = (group: ModelGroup) => {
    setEditingGroup({ ...group });
    setShowEditGroupModal(true);
  };

  const getModelsByCapability = (capability: string, excludeModelIds: string[] = []) => {
    return models.filter(
      (m) =>
        m.capability === capability &&
        m.is_active &&
        !excludeModelIds.includes(m.id)
    );
  };

  return (
    <section id="groups" className="tab-content active block pt-8">
      <header className="flex justify-between items-end mb-8 pb-6 border-b border-border">
        <div className="header-titles">
          <h1 className="font-heading text-3xl font-semibold tracking-tight">Model Groups</h1>
          <p className="text-zinc-400 text-sm mt-1">Create fallback chains from registered models</p>
        </div>
        <Button
          onClick={() => setShowAddGroupModal(true)}
          className="bg-white text-black hover:bg-zinc-200 font-medium px-6 py-2.5 rounded-full transition-all duration-200 shadow-md hover:shadow-lg flex items-center gap-1.5"
        >
          + Create Group
        </Button>
      </header>

      {/* Group List Container */}
      <div className="group-list flex flex-col gap-6">
        {loading ? (
          <div className="glass-panel p-8 text-center text-zinc-400">Loading model groups...</div>
        ) : groups.length === 0 ? (
          <div className="glass-panel p-8 text-center text-zinc-400">No model groups configured yet. Create one to set up a fallback chain.</div>
        ) : (
          groups.map((group) => (
            <div key={group.id} className="glass-panel group-card p-6 bg-[#18181b] border border-zinc-800 rounded-md shadow-xl">
              <div className="group-card-header mb-5">
                <div className="group-card-title-section flex items-center gap-3 w-full">
                  <Badge className="bg-zinc-800 text-zinc-300 border border-zinc-700/50 text-[10px] tracking-wide rounded uppercase px-2 py-0.5">
                    {group.capability}
                  </Badge>
                  <h3 className="font-heading text-lg font-semibold text-white">{group.name}</h3>
                  {!group.is_active && (
                    <Badge className="text-[10px] font-semibold tracking-wide uppercase px-2 py-0.5 rounded-full bg-red-500/10 text-red-500 border border-red-500/20">
                      Inactive
                    </Badge>
                  )}
                  <div className="flex gap-2 ml-auto items-center">
                    <Button
                      onClick={() => openAddGroupItem(group)}
                      className="bg-white text-black hover:bg-zinc-200 text-xs px-3.5 py-1.5 h-auto rounded font-semibold flex items-center gap-1"
                    >
                      + Add Model
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => openEditGroupModal(group)}
                      className="border-zinc-800 text-white hover:bg-zinc-800 text-xs px-3.5 py-1.5 h-auto rounded"
                    >
                      Edit
                    </Button>
                  </div>
                </div>
              </div>

              {/* Group Items / Fallback Chain List */}
              <div
                id={`group-items-${group.id}`}
                className={`group-items flex flex-col gap-2 ${draggedItem?.groupId === group.id ? 'select-none' : ''}`}
                onDragOver={(e) => updateDropTarget(e, group.id)}
                onDrop={(e) => void handleGroupDrop(e, group.id)}
              >
                {group.items.length === 0 ? (
                  <div className="text-zinc-500 text-xs py-4 text-center border border-dashed border-zinc-850 rounded bg-black/10">
                    No models in this group fallback chain. Click "+ Add Model" to add one.
                  </div>
                ) : (
                  <>
                    {draggedItem?.groupId === group.id &&
                      dragOverGap?.groupId === group.id &&
                      dragOverGap.gapIndex === 0 && (
                        <div className="group-drop-indicator" aria-hidden="true" />
                      )}
                    {group.items.map((item, index) => {
                      const underlyingModel = models.find((m) => m.id === item.model_id);
                      const isModelInactive = underlyingModel ? !underlyingModel.is_active : false;

                      return (
                        <React.Fragment key={item.id}>
                          <div
                            data-flip-id={item.id}
                            className={`group-item-row bg-black/20 border border-zinc-850 rounded px-4 py-3 min-h-[52px] grid grid-cols-[36px_minmax(120px,250px)_100px_1fr_auto] gap-4 items-center ${
                              draggedItem?.groupId === group.id
                                ? ''
                                : 'hover:border-zinc-600 hover:bg-black/35'
                            } ${
                              draggedItem?.groupId === group.id && draggedItem.itemId === item.id
                                ? 'is-dragging'
                                : ''
                            }`}
                          >
                            <div className="flex items-center justify-start">
                              <span className="inline-flex items-center justify-center min-w-[22px] h-[22px] bg-zinc-800 border border-zinc-600 rounded-full text-zinc-300 text-[11px] font-bold">
                                {index + 1}
                              </span>
                            </div>

                            <div className="font-semibold text-sm text-white font-mono truncate select-all" title={item.name}>
                              {item.name}
                            </div>

                            <div className="flex items-center gap-2.5">
                              <Badge className="bg-blue-500/10 text-blue-300 border border-blue-500/20 text-[9px] font-normal tracking-wide rounded uppercase px-1.5 py-0 capitalize">
                                {item.provider}
                              </Badge>
                              {item.thinking_level && (
                                <Badge className="bg-purple-500/10 text-purple-300 border border-purple-500/20 text-[9px] font-normal tracking-wide rounded uppercase px-1.5 py-0">
                                  Think: {item.thinking_level}
                                </Badge>
                              )}
                              {item.system_prompt && (
                                <Badge className="bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 text-[9px] font-normal tracking-wide rounded uppercase px-1.5 py-0">
                                  System Prompt
                                </Badge>
                              )}
                            </div>

                            <div className="flex items-center">
                              {isModelInactive && (
                                <Badge className="bg-red-500/10 text-red-500 border border-red-500/20 text-[9px] font-semibold tracking-wide uppercase px-1.5 py-0 rounded">
                                  Inactive
                                </Badge>
                              )}
                            </div>

                            <div className="flex items-center justify-end gap-1.5">
                              <div
                                draggable
                                onDragStart={(e) => handleDragStart(e, group, index)}
                                onDragEnd={handleDragEnd}
                                className="text-zinc-500 hover:text-zinc-300 cursor-grab active:cursor-grabbing p-1.5 mr-1 hover:bg-zinc-800/50 rounded touch-none"
                                title="Drag to reorder"
                              >
                                <Move className="w-4 h-4 pointer-events-none" />
                              </div>
                              <Button
                                variant="outline"
                                onClick={() => handleMoveGroupItem(group, index, -1)}
                                disabled={index === 0}
                                className="border-zinc-850 text-zinc-400 hover:bg-zinc-800/50 hover:text-white p-1.5 h-8 w-8 rounded disabled:opacity-30 disabled:cursor-not-allowed"
                                title="Move Up"
                              >
                                <ChevronUp className="w-4 h-4" />
                              </Button>
                              <Button
                                variant="outline"
                                onClick={() => handleMoveGroupItem(group, index, 1)}
                                disabled={index === group.items.length - 1}
                                className="border-zinc-850 text-zinc-400 hover:bg-zinc-800/50 hover:text-white p-1.5 h-8 w-8 rounded disabled:opacity-30 disabled:cursor-not-allowed"
                                title="Move Down"
                              >
                                <ChevronDown className="w-4 h-4" />
                              </Button>
                              <Button
                                variant="outline"
                                onClick={() => openEditGroupItem(group, item)}
                                className="border-zinc-850 text-white hover:bg-zinc-800/50 hover:text-white text-xs px-3 py-1 h-8 rounded ml-5"
                                title="Edit Item"
                              >
                                Edit
                              </Button>
                            </div>
                          </div>

                        {draggedItem?.groupId === group.id &&
                          dragOverGap?.groupId === group.id &&
                          dragOverGap.gapIndex === index + 1 && (
                            <div className="group-drop-indicator" aria-hidden="true" />
                          )}
                      </React.Fragment>
                    )})}
                  </>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Add Group Dialog */}
      <Dialog open={showAddGroupModal} onOpenChange={setShowAddGroupModal}>
        <DialogContent className="max-w-[400px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">Create Model Group</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleCreateGroup} className="flex flex-col gap-4 my-2">
            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">Group Name</label>
              <Input
                value={groupForm.name}
                onChange={(e) => setGroupForm({ ...groupForm, name: e.target.value })}
                required
                placeholder="e.g. fast-chat-group"
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">Capability</label>
              <div className="custom-select-wrapper select-wrapper w-full">
                <select
                  value={groupForm.capability}
                  onChange={(e) => setGroupForm({ ...groupForm, capability: e.target.value as any })}
                  className="orion-native-select"
                >
                  <option value="chat">chat</option>
                  <option value="tts">tts</option>
                  <option value="embed">embed</option>
                </select>
              </div>
            </div>

            <DialogFooter className="mt-4 flex gap-3 justify-end">
              <Button
                variant="outline"
                type="button"
                onClick={() => setShowAddGroupModal(false)}
                className="border-zinc-800 text-white hover:bg-zinc-900 rounded font-medium"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                className="bg-white text-black hover:bg-zinc-200 rounded font-medium"
              >
                Create Group
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit Group Dialog */}
      <Dialog open={showEditGroupModal} onOpenChange={setShowEditGroupModal}>
        <DialogContent className="max-w-[400px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">Edit Model Group</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleUpdateGroup} className="flex flex-col gap-4 my-2">
            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">Group Name</label>
              <Input
                value={editingGroup.name}
                onChange={(e) => setEditingGroup({ ...editingGroup, name: e.target.value })}
                required
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">Capability</label>
              <div className="custom-select-wrapper select-wrapper w-full">
                <select
                  value={editingGroup.capability}
                  disabled
                  className="orion-native-select"
                >
                  <option value="chat">chat</option>
                  <option value="tts">tts</option>
                  <option value="embed">embed</option>
                </select>
              </div>
            </div>

            <div
              onClick={() => setEditingGroup({ ...editingGroup, is_active: !editingGroup.is_active })}
              className={`flex items-center justify-between p-4 rounded-lg cursor-pointer border transition-all duration-200 hover:border-zinc-600 ${
                editingGroup.is_active
                  ? 'bg-purple-950/10 border-purple-500/25'
                  : 'bg-white/3 border-zinc-800 hover:bg-white/5'
              }`}
            >
              <div className="flex flex-col gap-0.5">
                <span className={`font-semibold text-sm ${editingGroup.is_active ? 'text-purple-400' : 'text-white'}`}>Active Status</span>
              </div>
              <Switch
                checked={editingGroup.is_active}
                onCheckedChange={(checked) => setEditingGroup({ ...editingGroup, is_active: checked })}
              />
            </div>

            <DialogFooter className="mt-4 flex justify-between w-full gap-3">
              <Button
                onClick={() => handleDeleteGroup(editingGroup.id)}
                type="button"
                className="bg-transparent border border-red-500/20 text-red-500 hover:bg-red-500/10 rounded font-medium flex items-center gap-1.5"
              >
                <Trash2 className="w-4 h-4" /> Delete
              </Button>
              <div className="flex gap-3 justify-end">
                <Button
                  variant="outline"
                  type="button"
                  onClick={() => setShowEditGroupModal(false)}
                  className="border-zinc-800 text-white hover:bg-zinc-900 rounded font-medium"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  className="bg-white text-black hover:bg-zinc-200 rounded font-medium"
                >
                  Save Changes
                </Button>
              </div>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Add Model to Group Dialog */}
      <Dialog open={showAddGroupItemModal} onOpenChange={setShowAddGroupItemModal}>
        <DialogContent className="max-w-[400px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">Add Model to Group</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleAddGroupItem} className="flex flex-col gap-4 my-2">
            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">Select Model</label>
              {activeGroupForItems &&
              getModelsByCapability(
                activeGroupForItems.capability,
                activeGroupForItems.items.map((i) => i.model_id)
              ).length === 0 ? (
                <p className="text-zinc-500 text-sm py-3 px-4 rounded border border-dashed border-zinc-800 bg-black/20">
                  No available models for this capability. Register a model first or remove duplicates from the group.
                </p>
              ) : (
                <div className="custom-select-wrapper select-wrapper w-full">
                  <select
                    value={selectedModelId}
                    onChange={(e) => setSelectedModelId(e.target.value)}
                    required
                    className="orion-native-select"
                  >
                    <option value="">-- Choose a model --</option>
                    {activeGroupForItems &&
                      getModelsByCapability(
                        activeGroupForItems.capability,
                        activeGroupForItems.items.map((i) => i.model_id)
                      ).map((model) => (
                        <option key={model.id} value={model.id}>
                          {model.name} ({model.provider})
                        </option>
                      ))}
                  </select>
                </div>
              )}
            </div>

            {activeGroupForItems?.capability === 'chat' && (
              <div className="flex flex-col gap-2">
                <label className="text-zinc-400 text-sm font-medium">Thinking Level</label>
                <Input
                  value={selectedThinkingLevel}
                  onChange={(e) => setSelectedThinkingLevel(e.target.value)}
                  placeholder="Optional (low, 1024)"
                  className="bg-black/40 border border-zinc-850 text-white rounded px-3 py-2 text-xs"
                />
              </div>
            )}

            {activeGroupForItems?.capability === 'chat' && (
              <div className="flex flex-col gap-2">
                <label className="text-zinc-400 text-sm font-medium">System Prompt</label>
                <Textarea
                  value={selectedSystemPrompt}
                  onChange={(e) => setSelectedSystemPrompt(e.target.value)}
                  placeholder="Optional system instructions..."
                  className="bg-black/40 border border-zinc-850 text-white rounded px-3 py-2 text-xs h-14 resize-none custom-scrollbar overflow-y-auto no-field-sizing"
                />
              </div>
            )}

            <DialogFooter className="mt-4 flex gap-3 justify-end">
              <Button
                variant="outline"
                type="button"
                onClick={() => setShowAddGroupItemModal(false)}
                className="border-zinc-800 text-white hover:bg-zinc-900 rounded font-medium"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={
                  !activeGroupForItems ||
                  getModelsByCapability(
                    activeGroupForItems.capability,
                    activeGroupForItems.items.map((i) => i.model_id)
                  ).length === 0
                }
                className="bg-white text-black hover:bg-zinc-200 rounded font-medium disabled:opacity-50"
              >
                Add Model
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit Group Item Dialog */}
      <Dialog open={showEditGroupItemModal} onOpenChange={setShowEditGroupItemModal}>
        <DialogContent className="max-w-[400px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">Edit Group Item</DialogTitle>
          </DialogHeader>

          {editingGroupItem && (
            <form onSubmit={handleUpdateGroupItem} className="flex flex-col gap-4 my-2">
              <div className="flex flex-col gap-2">
                <label className="text-zinc-400 text-sm font-medium">Model</label>
                <div className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3 font-mono text-sm opacity-70">
                  {editingGroupItem.name} ({editingGroupItem.provider})
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-zinc-400 text-sm font-medium">Thinking Level</label>
                <Input
                  value={editingGroupItem.thinking_level}
                  onChange={(e) => setEditingGroupItem({ ...editingGroupItem, thinking_level: e.target.value })}
                  placeholder="Optional (low, 1024)"
                  className="bg-black/40 border border-zinc-850 text-white rounded px-3 py-2 text-xs"
                />
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-zinc-400 text-sm font-medium">System Prompt</label>
                <Textarea
                  value={editingGroupItem.system_prompt}
                  onChange={(e) => setEditingGroupItem({ ...editingGroupItem, system_prompt: e.target.value })}
                  placeholder="Optional system instructions..."
                  className="bg-black/40 border border-zinc-850 text-white rounded px-3 py-2 text-xs h-14 resize-none custom-scrollbar overflow-y-auto no-field-sizing"
                />
              </div>

              <DialogFooter className="mt-4 flex justify-between w-full gap-3">
                <Button
                  onClick={() => {
                    const group = groups.find((g) => g.id === editingGroupItem.groupId);
                    if (group) {
                      handleDeleteGroupItem(group, editingGroupItem.itemId);
                    }
                  }}
                  type="button"
                  className="bg-transparent border border-red-500/20 text-red-500 hover:bg-red-500/10 rounded font-medium flex items-center gap-1.5"
                >
                  <Trash2 className="w-4 h-4" /> Delete
                </Button>
                <div className="flex gap-3 justify-end">
                  <Button
                    variant="outline"
                    type="button"
                    onClick={() => setShowEditGroupItemModal(false)}
                    className="border-zinc-800 text-white hover:bg-zinc-900 rounded font-medium"
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    className="bg-white text-black hover:bg-zinc-200 rounded font-medium"
                  >
                    Save Changes
                  </Button>
                </div>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}
