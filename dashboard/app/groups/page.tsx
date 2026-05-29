'use client';

import React, { useState, useEffect } from 'react';
import { adminFetch } from '@/lib/api';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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

export default function GroupsPage() {
  const { showToast, confirmAction } = useApp();
  const [groups, setGroups] = useState<ModelGroup[]>([]);
  const [models, setModels] = useState<ModelItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Modals visibility
  const [showAddGroupModal, setShowAddGroupModal] = useState<boolean>(false);
  const [showEditGroupModal, setShowEditGroupModal] = useState<boolean>(false);
  const [showAddGroupItemModal, setShowAddGroupItemModal] = useState<boolean>(false);

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
  
  // Drag and Drop state
  const [draggedItem, setDraggedItem] = useState<{ groupId: string; itemIndex: number } | null>(null);
  const [dragOverItem, setDragOverItem] = useState<{ groupId: string; itemIndex: number } | null>(null);

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
        body: JSON.stringify({ model_id: selectedModelId, priority }),
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
    const items = [...group.items];
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= items.length) return;

    // Shift in array
    const [moved] = items.splice(index, 1);
    items.splice(targetIndex, 0, moved);

    try {
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        const newPriority = i + 1;
        if (item.priority !== newPriority) {
          const res = await adminFetch(`/dashboard/api/model-groups/${group.id}/items/${item.id}`, {
            method: 'PUT',
            body: JSON.stringify({ priority: newPriority }),
          });
          if (!res.ok) {
            const err = await res.json();
            showToast('Error updating priority: ' + (err.detail || 'Failed'), 'error');
            return;
          }
        }
      }
      await loadGroups();
      showToast('Model group order updated!');
    } catch (err) {
      console.error(err);
      showToast('Failed to update order', 'error');
    }
  };

  const handleDragStart = (e: React.DragEvent, groupId: string, itemIndex: number) => {
    setDraggedItem({ groupId, itemIndex });
    e.dataTransfer.effectAllowed = 'move';
    setTimeout(() => {
      if (e.target instanceof HTMLElement) {
        e.target.classList.add('opacity-40', 'border-dashed', 'border-purple-500/50');
      }
    }, 0);
  };

  const handleDragEnd = (e: React.DragEvent) => {
    setDraggedItem(null);
    setDragOverItem(null);
    if (e.target instanceof HTMLElement) {
      e.target.classList.remove('opacity-40', 'border-dashed', 'border-purple-500/50');
    }
  };

  const handleDragOver = (e: React.DragEvent, groupId: string, itemIndex: number) => {
    e.preventDefault();
    if (draggedItem && draggedItem.groupId === groupId) {
      e.dataTransfer.dropEffect = 'move';
      if (!dragOverItem || dragOverItem.groupId !== groupId || dragOverItem.itemIndex !== itemIndex) {
        setDragOverItem({ groupId, itemIndex });
      }
    }
  };

  const handleDrop = async (e: React.DragEvent, group: ModelGroup, targetItemIndex: number) => {
    e.preventDefault();
    setDragOverItem(null);
    if (!draggedItem) return;
    if (draggedItem.groupId !== group.id) return;
    if (draggedItem.itemIndex === targetItemIndex) return;

    const items = [...group.items];
    const srcIndex = draggedItem.itemIndex;
    const destIndex = targetItemIndex;

    const [moved] = items.splice(srcIndex, 1);
    items.splice(destIndex, 0, moved);

    // Optimistic UI update
    setGroups(prev => prev.map(g => {
      if (g.id === group.id) {
        return { ...g, items };
      }
      return g;
    }));

    try {
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        const newPriority = i + 1;
        if (item.priority !== newPriority) {
          const res = await adminFetch(`/dashboard/api/model-groups/${group.id}/items/${item.id}`, {
            method: 'PUT',
            body: JSON.stringify({ priority: newPriority }),
          });
          if (!res.ok) {
            const err = await res.json();
            showToast('Error updating priority: ' + (err.detail || 'Failed'), 'error');
            await loadGroups();
            return;
          }
          item.priority = newPriority;
        }
      }
      showToast('Model group order updated!');
    } catch (err) {
      console.error(err);
      showToast('Failed to update order', 'error');
      await loadGroups();
    }
  };

  const openEditGroupModal = (group: ModelGroup) => {
    setEditingGroup({ ...group });
    setShowEditGroupModal(true);
  };

  const getModelsByCapability = (capability: string) => {
    return models.filter((m) => m.capability === capability && m.is_active);
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
                  <Badge
                    className={`text-[10px] font-semibold tracking-wide uppercase px-2 py-0.5 rounded-full ${
                      group.is_active
                        ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                        : 'bg-red-500/10 text-red-500 border border-red-500/20'
                    }`}
                  >
                    {group.is_active ? 'Active' : 'Inactive'}
                  </Badge>
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
              <div className="group-items flex flex-col gap-2">
                {group.items.length === 0 ? (
                  <div className="text-zinc-500 text-xs py-4 text-center border border-dashed border-zinc-850 rounded bg-black/10">
                    No models in this group fallback chain. Click "+ Add Model" to add one.
                  </div>
                ) : (
                  group.items.map((item, index) => (
                    <React.Fragment key={item.id}>
                      {/* Top Drop Indicator (dragging upwards) */}
                      {draggedItem && dragOverItem && dragOverItem.groupId === group.id && dragOverItem.itemIndex === index && draggedItem.itemIndex > index && (
                        <div className="h-1.5 bg-gradient-to-r from-purple-500 via-pink-500 to-indigo-500 rounded-full my-1 shadow-[0_0_10px_rgba(168,85,247,0.6)] animate-pulse" />
                      )}

                      <div
                        draggable
                        onDragStart={(e) => handleDragStart(e, group.id, index)}
                        onDragEnd={handleDragEnd}
                        onDragOver={(e) => handleDragOver(e, group.id, index)}
                        onDrop={(e) => handleDrop(e, group, index)}
                        className={`group-item-row bg-black/20 border rounded px-4 py-3 min-h-[52px] flex justify-between items-center transition-all duration-200 hover:bg-black/40 ${
                          draggedItem && draggedItem.groupId === group.id && draggedItem.itemIndex === index
                            ? 'opacity-40 border-dashed border-purple-500/50'
                            : 'border-zinc-850 hover:border-zinc-700/80'
                        }`}
                      >
                        <div className="flex items-center gap-3 flex-1">
                          <span className="inline-flex items-center justify-center w-5.5 h-5.5 bg-purple-950/20 border border-purple-500/20 rounded-full text-purple-400 text-[11px] font-bold">
                            {index + 1}
                          </span>
                          <span className="font-medium text-sm text-white font-mono select-all">
                            {item.name}
                          </span>
                          <Badge className="bg-blue-500/10 text-blue-300 border border-blue-500/20 text-[9px] font-normal tracking-wide rounded uppercase px-1.5 py-0 capitalize">
                            {item.provider}
                          </Badge>
                        </div>

                        <div className="flex items-center gap-1.5 ml-4">
                          <div
                            className="text-zinc-500 hover:text-zinc-300 cursor-grab active:cursor-grabbing p-1.5 mr-1 hover:bg-zinc-800/50 rounded"
                            title="Drag to reorder"
                          >
                            <Move className="w-4 h-4" />
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
                            onClick={() => handleDeleteGroupItem(group, item.id)}
                            className="bg-transparent border border-red-500/10 text-red-400/80 hover:bg-red-500/10 hover:text-red-500 p-1.5 h-8 w-8 rounded"
                            title="Remove from Group"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      </div>

                      {/* Bottom Drop Indicator (dragging downwards) */}
                      {draggedItem && dragOverItem && dragOverItem.groupId === group.id && dragOverItem.itemIndex === index && draggedItem.itemIndex < index && (
                        <div className="h-1.5 bg-gradient-to-r from-purple-500 via-pink-500 to-indigo-500 rounded-full my-1 shadow-[0_0_10px_rgba(168,85,247,0.6)] animate-pulse" />
                      )}
                    </React.Fragment>
                  ))
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Add Group Dialog */}
      <Dialog open={showAddGroupModal} onOpenChange={setShowAddGroupModal}>
        <DialogContent className="max-w-[440px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
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
                  className="w-full bg-black/45 border border-zinc-850 text-white rounded px-4 py-3 appearance-none cursor-pointer outline-none focus:border-purple-500"
                >
                  <option value="chat" className="bg-zinc-950 text-white">chat</option>
                  <option value="tts" className="bg-zinc-950 text-white">tts</option>
                  <option value="embed" className="bg-zinc-950 text-white">embed</option>
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
        <DialogContent className="max-w-[440px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
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
                  className="w-full bg-black/40 border border-zinc-850 text-zinc-500 rounded px-4 py-3 appearance-none cursor-not-allowed outline-none"
                >
                  <option value="chat">chat</option>
                  <option value="tts">tts</option>
                  <option value="embed">embed</option>
                </select>
              </div>
            </div>

            <div
              onClick={() => setEditingGroup({ ...editingGroup, is_active: !editingGroup.is_active })}
              className={`flex items-center justify-between p-4 rounded-lg cursor-pointer border transition-all duration-200 ${
                editingGroup.is_active
                  ? 'bg-purple-950/10 border-purple-500/25'
                  : 'bg-white/3 border-zinc-800'
              }`}
            >
              <div className="flex flex-col gap-0.5">
                <span className={`font-semibold text-sm ${editingGroup.is_active ? 'text-purple-400' : 'text-white'}`}>Active Status</span>
                <span className="text-zinc-400 text-xs">Enable group for routing</span>
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
        <DialogContent className="max-w-[440px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">Add Model to Group</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleAddGroupItem} className="flex flex-col gap-4 my-2">
            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">Select Model</label>
              <div className="custom-select-wrapper select-wrapper w-full">
                <select
                  value={selectedModelId}
                  onChange={(e) => setSelectedModelId(e.target.value)}
                  required
                  className="w-full bg-black/45 border border-zinc-850 text-white rounded px-4 py-3 appearance-none cursor-pointer outline-none focus:border-purple-500"
                >
                  <option value="" className="bg-zinc-950 text-zinc-400">
                    -- Choose a model --
                  </option>
                  {activeGroupForItems &&
                    getModelsByCapability(activeGroupForItems.capability).map((model) => (
                      <option key={model.id} value={model.id} className="bg-zinc-950 text-white">
                        {model.name} ({model.provider})
                      </option>
                    ))}
                </select>
              </div>
            </div>

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
                className="bg-white text-black hover:bg-zinc-200 rounded font-medium"
              >
                Add Model
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}
