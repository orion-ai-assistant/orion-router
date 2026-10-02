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
  temperature?: number | null;
  default_config?: Record<string, any>;
}

interface ModelGroup {
  id: string;
  name: string;
  description: string;
  capability: 'chat' | 'tts' | 'embed' | 'stt';
  is_active: boolean;
  items: GroupItem[];
}

interface ModelItem {
  id: string;
  name: string;
  provider: string;
  capability: 'chat' | 'tts' | 'embed' | 'stt';
  is_active: boolean;
  temperature?: number | null;
  thinking_level?: string | null;
  system_prompt?: string | null;
  default_config?: Record<string, any>;
  thinking?: any;
  builtin_thinking?: any;
  is_builtin_thinking?: boolean;
}

interface EditingGroupItemState {
  groupId: string;
  itemId: string;
  model_id: string;
  name: string;
  provider: string;
  priority: number;
  thinking_level: string;
  system_prompt: string;
  temperature: string;
  default_config: Record<string, any>;
  targetModel?: ModelItem;
}

type LocalSamplingKey = 'top_p' | 'top_k' | 'min_p' | 'repeat_penalty';

const localSamplingDefaults: Record<LocalSamplingKey, string> = {
  top_p: '0.9',
  top_k: '40',
  min_p: '0.05',
  repeat_penalty: '1.05',
};

const localSamplingConfig = (config: Record<string, any> | undefined): Record<LocalSamplingKey, string> => {
  const current = config?.local_sampling || {};
  return {
    top_p: current.top_p !== undefined && current.top_p !== null ? String(current.top_p) : localSamplingDefaults.top_p,
    top_k: current.top_k !== undefined && current.top_k !== null ? String(current.top_k) : localSamplingDefaults.top_k,
    min_p: current.min_p !== undefined && current.min_p !== null ? String(current.min_p) : localSamplingDefaults.min_p,
    repeat_penalty:
      current.repeat_penalty !== undefined && current.repeat_penalty !== null
        ? String(current.repeat_penalty)
        : localSamplingDefaults.repeat_penalty,
  };
};

const validateLocalSampling = (config: Record<string, any> | undefined) => {
  const sampling = localSamplingConfig(config);
  const topP = parseFloat(sampling.top_p);
  const topK = parseInt(sampling.top_k, 10);
  const minP = parseFloat(sampling.min_p);
  const repeatPenalty = parseFloat(sampling.repeat_penalty);

  if (isNaN(topP) || topP < 0 || topP > 1) return false;
  if (isNaN(topK) || topK < 0) return false;
  if (isNaN(minP) || minP < 0 || minP > 1) return false;
  if (isNaN(repeatPenalty) || repeatPenalty < 0) return false;
  return true;
};

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
  const { showToast, confirmAction, t } = useApp();
  const [groups, setGroups] = useState<ModelGroup[]>([]);
  const [models, setModels] = useState<ModelItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Modals visibility
  const [showAddGroupModal, setShowAddGroupModal] = useState<boolean>(false);
  const [showEditGroupModal, setShowEditGroupModal] = useState<boolean>(false);
  const [showAddGroupItemModal, setShowAddGroupItemModal] = useState<boolean>(false);
  const [showEditGroupItemModal, setShowEditGroupItemModal] = useState<boolean>(false);

  // Form states
  const [groupForm, setGroupForm] = useState({ name: '', capability: 'chat' as 'chat' | 'tts' | 'embed' | 'stt' });
  const [editingGroup, setEditingGroup] = useState<ModelGroup>({
    id: '',
    name: '',
    description: '',
    capability: 'chat',
    is_active: true,
    items: [],
  });
  
  const [activeGroupForItems, setActiveGroupForItems] = useState<ModelGroup | null>(null);
  const [addItemForm, setAddItemForm] = useState<{
    model_id: string;
    thinking_level: string;
    temperature: string;
    system_prompt: string;
    default_config: Record<string, any>;
  }>({
    model_id: '',
    thinking_level: '',
    temperature: '',
    system_prompt: '',
    default_config: {},
  });
  const [showAddItemThinking, setShowAddItemThinking] = useState<boolean>(false);
  const [showAddItemLocalSampling, setShowAddItemLocalSampling] = useState<boolean>(false);
  const [editingGroupItem, setEditingGroupItem] = useState<EditingGroupItemState | null>(null);
  const [showEditItemThinking, setShowEditItemThinking] = useState<boolean>(false);
  const [showEditItemLocalSampling, setShowEditItemLocalSampling] = useState<boolean>(false);
  
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
      showToast(err instanceof Error ? err.message : t('groups.toast.updateOrderFailed'), 'error');
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
      showToast(t('groups.toast.loadFailed'), 'error');
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
      showToast(t('groups.toast.enterGroupName'), 'error');
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
        showToast(t('groups.toast.createSuccess'));
        await loadGroups();
      } else {
        const err = await res.json();
        showToast(t('common.error') + ': ' + (err.detail || t('groups.toast.createFailed')), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast(t('groups.toast.createFailed'), 'error');
    }
  };

  const handleUpdateGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = editingGroup.name.trim();
    if (!name) {
      showToast(t('groups.toast.nameEmpty'), 'error');
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
        showToast(t('groups.toast.updateSuccess'));
        setShowEditGroupModal(false);
        await loadGroups();
      } else {
        const err = await res.json();
        showToast(t('common.error') + ': ' + (err.detail || t('groups.toast.updateFailed')), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast(t('groups.toast.updateFailed'), 'error');
    }
  };

  const handleDeleteGroup = async (groupId: string, confirmed = false) => {
    if (!confirmed) {
      confirmAction(t('common.confirm.deleteGroup'), () =>
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
        showToast(t('groups.toast.deleteSuccess'));
        await loadGroups();
      } else {
        const err = await res.json();
        showToast(t('common.error') + ': ' + (err.detail || t('groups.toast.deleteFailed')), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast(t('groups.toast.deleteFailed'), 'error');
    }
  };

  const openAddGroupItem = (group: ModelGroup) => {
    setActiveGroupForItems(group);
    setAddItemForm({
      model_id: '',
      thinking_level: '',
      temperature: '',
      system_prompt: '',
      default_config: {},
    });
    setShowAddItemThinking(false);
    setShowAddItemLocalSampling(false);
    setShowAddGroupItemModal(true);
  };

  const handleSelectModelInAddModal = (modelId: string) => {
    const selectedModel = models.find((m) => m.id === modelId);
    if (!selectedModel) {
      setAddItemForm({
        model_id: '',
        thinking_level: '',
        temperature: '',
        system_prompt: '',
        default_config: {},
      });
      return;
    }

    setAddItemForm({
      model_id: selectedModel.id,
      thinking_level: selectedModel.thinking_level || '',
      temperature: selectedModel.temperature !== undefined && selectedModel.temperature !== null ? String(selectedModel.temperature) : '',
      system_prompt: selectedModel.system_prompt || '',
      default_config: { ...(selectedModel.default_config || {}) },
    });
    setShowAddItemThinking(false);
    setShowAddItemLocalSampling(false);
  };

  const handleAddGroupItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeGroupForItems) return;
    if (!addItemForm.model_id) {
      showToast(t('groups.toast.selectModel'), 'error');
      return;
    }
    const selectedModel = models.find((m) => m.id === addItemForm.model_id);
    const priority = activeGroupForItems.items.length + 1;

    const tempVal = addItemForm.temperature === '' ? null : parseFloat(addItemForm.temperature);
    if (tempVal !== null && (tempVal < 0 || tempVal > 2)) {
      showToast(t('models.toast.invalidTemperature'), 'error');
      return;
    }

    if (selectedModel?.provider === 'local' && activeGroupForItems.capability === 'chat' && !validateLocalSampling(addItemForm.default_config)) {
      showToast(t('models.toast.invalidLocalSampling'), 'error');
      return;
    }

    const isBuiltIn = !!selectedModel?.is_builtin_thinking;
    const builtInSchema = selectedModel?.builtin_thinking || (isBuiltIn ? selectedModel?.thinking : null);
    const dbSchema = addItemForm.default_config?.thinking_schema || selectedModel?.default_config?.thinking_schema;
    const schema = dbSchema && dbSchema.type !== 'none' ? dbSchema : builtInSchema;

    if (!validateThinking(addItemForm, schema, isBuiltIn)) return;

    let configObj = { ...(addItemForm.default_config || {}) };
    if (configObj.thinking_schema && configObj.thinking_schema._raw_options !== undefined) {
      delete configObj.thinking_schema._raw_options;
    }
    if (selectedModel?.provider === 'local' && activeGroupForItems.capability === 'chat') {
      configObj = {
        ...configObj,
        local_chat_defaults_version: 1,
        local_sampling: localSamplingConfig(configObj),
      };
    }

    try {
      const res = await adminFetch(`/dashboard/api/model-groups/${activeGroupForItems.id}/items`, {
        method: 'POST',
        body: JSON.stringify({ 
          model_id: addItemForm.model_id, 
          priority, 
          thinking_level: addItemForm.thinking_level || null,
          system_prompt: addItemForm.system_prompt || null,
          temperature: tempVal,
          default_config: configObj,
        }),
      });
      if (res.ok) {
        setShowAddGroupItemModal(false);
        showToast(t('groups.toast.addModelSuccess'));
        await loadGroups();
      } else {
        const err = await res.json();
        showToast(t('common.error') + ': ' + (err.detail || t('groups.toast.addModelFailed')), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast(t('groups.toast.addModelFailed'), 'error');
    }
  };

  const validateThinking = (itemState: { thinking_level?: string | null; default_config?: Record<string, any> }, schema: any, isBuiltIn: boolean) => {
    const dbSchema = itemState.default_config?.thinking_schema;
    let type = 'none';
    if (dbSchema?.type === 'none') {
      type = 'none';
    } else if (dbSchema?.type) {
      type = dbSchema.type;
    } else if (isBuiltIn && schema) {
      type = schema.type;
    }

    if (type === 'none') {
      return true;
    }

    if (type === 'budget') {
      const val = parseInt(itemState.thinking_level || '');
      if (isNaN(val)) {
        showToast("Bütçe (Budget) için Default değeri bir sayı olmalıdır", "error");
        return false;
      }
      if (val !== -1 && (val < (schema?.min || 1) || val > (schema?.max || 8192))) {
        showToast(`Bütçe (Budget) için Default değeri -1 (Auto) veya ${schema?.min || 1} ile ${schema?.max || 8192} arasında olmalıdır`, "error");
        return false;
      }
      
      if (!isBuiltIn) {
        if (schema?.min === undefined || schema?.min === '' || isNaN(parseInt(schema.min as any))) {
          showToast("Min Limit boş olamaz", "error");
          return false;
        }
        if (schema?.max === undefined || schema?.max === '' || isNaN(parseInt(schema.max as any))) {
          showToast("Max Limit boş olamaz", "error");
          return false;
        }
        const schemaMin = parseInt(schema.min as any);
        const schemaMax = parseInt(schema.max as any);
        if (schemaMin < 0) {
          showToast("Min Limit 0'dan küçük olamaz", "error");
          return false;
        }
        if (schemaMin > schemaMax) {
          showToast("Min Limit, Max Limit'ten küçük veya eşit olmalıdır", "error");
          return false;
        }
      }
    } else if (type === 'level') {
      if (!schema?.options?.includes(itemState.thinking_level)) {
        showToast(`Level modu için geçerli bir varsayılan değer seçmelisiniz. Geçerli seçenekler: ${(schema?.options || []).join(', ')}`, "error");
        return false;
      }
    }
    return true;
  };

  const openEditGroupItem = (group: ModelGroup, item: GroupItem) => {
    const targetModel = models.find((m) => m.id === item.model_id || m.name === item.name);
    const itemConfig = { ...(targetModel?.default_config || {}), ...(item.default_config || {}) };
    const initialThinking = item.thinking_level !== undefined && item.thinking_level !== null 
      ? item.thinking_level 
      : (targetModel?.thinking_level || '');

    setEditingGroupItem({
      groupId: group.id,
      itemId: item.id,
      model_id: item.model_id,
      name: item.name,
      provider: item.provider,
      priority: item.priority,
      thinking_level: initialThinking,
      system_prompt: item.system_prompt !== undefined && item.system_prompt !== null ? item.system_prompt : (targetModel?.system_prompt || ''),
      temperature: item.temperature !== undefined && item.temperature !== null ? item.temperature.toString() : (targetModel?.temperature !== undefined && targetModel?.temperature !== null ? targetModel.temperature.toString() : ''),
      default_config: itemConfig,
      targetModel: targetModel,
    });
    setShowEditItemThinking(false);
    setShowEditItemLocalSampling(false);
    setShowEditGroupItemModal(true);
  };

  const handleUpdateGroupItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingGroupItem) return;

    const group = groups.find((g) => g.id === editingGroupItem.groupId);
    const tempVal = editingGroupItem.temperature === '' ? null : parseFloat(editingGroupItem.temperature);
    if (tempVal !== null && (tempVal < 0 || tempVal > 2)) {
      showToast(t('models.toast.invalidTemperature'), 'error');
      return;
    }

    if (editingGroupItem.provider === 'local' && group?.capability === 'chat' && !validateLocalSampling(editingGroupItem.default_config)) {
      showToast(t('models.toast.invalidLocalSampling'), 'error');
      return;
    }

    const targetModel = editingGroupItem.targetModel || models.find((m) => m.id === editingGroupItem.model_id || m.name === editingGroupItem.name);
    const isBuiltIn = !!targetModel?.is_builtin_thinking;
    const builtInSchema = targetModel?.builtin_thinking || (isBuiltIn ? targetModel?.thinking : null);
    const dbSchema = editingGroupItem.default_config?.thinking_schema || targetModel?.default_config?.thinking_schema;
    const schema = dbSchema && dbSchema.type !== 'none' ? dbSchema : builtInSchema;

    if (!validateThinking(editingGroupItem, schema, isBuiltIn)) return;

    let configObj = { ...(editingGroupItem.default_config || {}) };
    if (configObj.thinking_schema && configObj.thinking_schema._raw_options !== undefined) {
      delete configObj.thinking_schema._raw_options;
    }
    if (editingGroupItem.provider === 'local' && group?.capability === 'chat') {
      configObj = {
        ...configObj,
        local_chat_defaults_version: 1,
        local_sampling: localSamplingConfig(configObj),
      };
    }

    try {
      const res = await adminFetch(`/dashboard/api/model-groups/${editingGroupItem.groupId}/items/${editingGroupItem.itemId}`, {
        method: 'PUT',
        body: JSON.stringify({ 
          priority: editingGroupItem.priority, 
          thinking_level: editingGroupItem.thinking_level || null,
          system_prompt: editingGroupItem.system_prompt || null,
          temperature: tempVal,
          default_config: configObj,
        }),
      });
      if (res.ok) {
        setShowEditGroupItemModal(false);
        showToast(t('groups.toast.itemUpdated'));
        await loadGroups();
      } else {
        const err = await res.json();
        showToast(t('common.error') + ': ' + (err.detail || t('groups.toast.updateItemFailed')), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast(t('groups.toast.updateItemFailed'), 'error');
    }
  };

  const renderItemThinkingBuilder = (
    formState: any,
    setFormState: any,
    targetModel: ModelItem | undefined,
    capability: string,
    expanded: boolean,
    setExpanded: (val: boolean) => void
  ) => {
    if (capability !== 'chat') return null;

    const isBuiltIn = !!targetModel?.is_builtin_thinking;
    const builtInSchema = targetModel?.builtin_thinking || (isBuiltIn ? targetModel?.thinking : null);
    const dbSchema = formState.default_config?.thinking_schema || targetModel?.default_config?.thinking_schema;

    let type = 'none';
    if (dbSchema?.type === 'none') {
      type = 'none';
    } else if (dbSchema?.type) {
      type = dbSchema.type;
    } else if (isBuiltIn && builtInSchema) {
      type = builtInSchema.type;
    } else if (formState.thinking_level) {
      if (formState.thinking_level === '-1' || !isNaN(Number(formState.thinking_level))) {
        type = 'budget';
      } else {
        type = 'level';
      }
    }

    const schema = dbSchema && dbSchema.type !== 'none' ? dbSchema : builtInSchema;
    const allowedType = builtInSchema?.type || schema?.type;

    return (
      <div className="flex flex-col gap-3 bg-zinc-900/60 p-3 rounded-lg border border-zinc-800/80 mb-1">
        <div 
          className="flex justify-between items-center cursor-pointer select-none"
          onClick={() => setExpanded(!expanded)}
        >
          <label className="text-zinc-400 text-sm font-medium cursor-pointer">
            {t('playground.thinking')} 
            <span className="text-[10px] text-zinc-500 font-normal ml-2 uppercase">Schema & Default</span>
          </label>
          <div className={`transform transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-zinc-400">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </div>
        </div>
        
        {expanded && (
          <div className="flex flex-col gap-3 mt-1 animate-in fade-in slide-in-from-top-2 duration-200">
            <div className="flex flex-col gap-1">
              <label className="text-zinc-500 text-[10px] uppercase">Mode</label>
              <div className="custom-select-wrapper select-wrapper w-full">
                <select
                  value={type}
                  onChange={(e) => {
                    const val = e.target.value;
                    if (val === 'none') {
                      setFormState({ 
                        ...formState, 
                        default_config: { ...formState.default_config, thinking_schema: { type: 'none' } }, 
                        thinking_level: '' 
                      });
                    } else if (val === 'budget') {
                      const newMin = builtInSchema?.type === 'budget' && builtInSchema?.min !== undefined ? builtInSchema.min : 1;
                      const newMax = builtInSchema?.type === 'budget' && builtInSchema?.max !== undefined ? builtInSchema.max : 8192;
                      setFormState({
                        ...formState,
                        default_config: { ...formState.default_config, thinking_schema: { type: 'budget', min: newMin, max: newMax, auto_value: -1 } },
                        thinking_level: '-1'
                      });
                    } else if (val === 'level') {
                      const newOpts = builtInSchema?.type === 'level' && builtInSchema?.options ? builtInSchema.options : ['low', 'medium', 'high'];
                      setFormState({
                        ...formState,
                        default_config: { ...formState.default_config, thinking_schema: { type: 'level', options: newOpts } },
                        thinking_level: newOpts[0] || 'low'
                      });
                    }
                  }}
                  className="orion-native-select orion-native-select-sm"
                >
                  <option value="none">API Default</option>
                  {(!allowedType || allowedType === 'budget') && (
                    <option value="budget">Budget</option>
                  )}
                  {(!allowedType || allowedType === 'level') && (
                    <option value="level">Level</option>
                  )}
                </select>
              </div>
            </div>

            {type === 'budget' && (
              <div className="grid grid-cols-2 gap-2">
                <div className="flex flex-col gap-1">
                  <label className="text-zinc-500 text-[10px]">Min Limit</label>
                  <Input
                    type="number"
                    value={schema?.min === undefined ? '' : schema.min}
                    onChange={(e) => {
                      const val = e.target.value === '' ? '' : parseInt(e.target.value);
                      setFormState({
                        ...formState,
                        default_config: { ...formState.default_config, thinking_schema: { ...schema, min: val, auto_value: -1 } }
                      });
                    }}
                    className="bg-black/40 border border-zinc-855 text-white rounded px-2 py-1 text-xs"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-zinc-500 text-[10px]">Max Limit</label>
                  <Input
                    type="number"
                    value={schema?.max === undefined ? '' : schema.max}
                    onChange={(e) => {
                      const val = e.target.value === '' ? '' : parseInt(e.target.value);
                      setFormState({
                        ...formState,
                        default_config: { ...formState.default_config, thinking_schema: { ...schema, max: val, auto_value: -1 } }
                      });
                    }}
                    className="bg-black/40 border border-zinc-855 text-white rounded px-2 py-1 text-xs"
                  />
                </div>
              </div>
            )}

            {type === 'level' && (
              <div className="flex flex-col gap-1">
                <label className="text-zinc-500 text-[10px]">Options (Comma separated)</label>
                <Input
                  value={schema?._raw_options !== undefined ? schema._raw_options : (schema?.options || []).join(', ')}
                  onChange={(e) => {
                    const rawVal = e.target.value;
                    const opts = rawVal.split(',').map((s: string) => s.trim()).filter(Boolean);
                    setFormState({
                      ...formState,
                      default_config: { ...formState.default_config, thinking_schema: { ...schema, options: opts, _raw_options: rawVal } },
                      thinking_level: opts[0] || ''
                    });
                  }}
                  className="bg-black/40 border border-zinc-855 text-white rounded px-2 py-1 text-xs"
                  placeholder="low, medium, high"
                />
              </div>
            )}

            {type !== 'none' && (
              <div className="flex flex-col gap-1 pt-2 border-t border-zinc-800/50 mt-1">
                <label className="text-zinc-500 text-[10px] uppercase">Default</label>
                {type === 'budget' ? (
                  <Input
                    type="number"
                    value={formState.thinking_level || ''}
                    onChange={(e) => setFormState({ ...formState, thinking_level: e.target.value })}
                    className="bg-black/40 border border-zinc-855 text-white rounded px-2 py-2 text-sm placeholder:text-xs"
                    placeholder="-1 (Auto/Infinite) veya sayı"
                  />
                ) : (
                  <div className="custom-select-wrapper select-wrapper w-full">
                    <select
                      value={formState.thinking_level || (schema?.options?.[0] || '')}
                      onChange={(e) => setFormState({ ...formState, thinking_level: e.target.value })}
                      className="orion-native-select orion-native-select-sm"
                    >
                      {(schema?.options || []).map((opt: string) => (
                        <option key={opt} value={opt}>{opt}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderItemLocalSampling = (
    formState: any,
    setFormState: any,
    provider: string,
    capability: string,
    expanded: boolean,
    setExpanded: (value: boolean) => void,
  ) => {
    if (provider !== 'local' || capability !== 'chat') return null;
    const config = formState.default_config || {};
    const sampling = localSamplingConfig(config);
    const updateSampling = (key: string, value: boolean | string) => {
      setFormState({
        ...formState,
        default_config: { ...config, local_sampling: { ...sampling, [key]: value } },
      });
    };

    return (
      <div className="flex flex-col gap-2">
        <button 
          type="button" 
          onClick={() => setExpanded(!expanded)} 
          aria-expanded={expanded} 
          className="self-start flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <span>{t('models.localSampling')}</span>
          <span aria-hidden="true" className="text-[11px]">{expanded ? '▾' : '▸'}</span>
        </button>
        {expanded && (
          <div className="grid grid-cols-2 gap-2 pl-1 animate-in fade-in slide-in-from-top-1 duration-150">
            {(Object.keys(localSamplingDefaults) as LocalSamplingKey[]).map((key) => (
              <label key={key} className="flex flex-col gap-1 text-xs text-zinc-400 font-medium">
                {key.toUpperCase().replace('_', ' ')}
                <Input
                  type="number"
                  min="0"
                  max={key === 'top_p' || key === 'min_p' ? '1' : undefined}
                  step={key === 'top_k' ? '1' : '0.01'}
                  value={sampling[key]}
                  onChange={(e) => updateSampling(key, e.target.value)}
                  className="bg-black/40 border border-zinc-855 text-white rounded px-2 py-2 text-sm"
                />
              </label>
            ))}
          </div>
        )}
      </div>
    );
  };

  const handleDeleteGroupItem = async (group: ModelGroup, itemId: string, confirmed = false) => {
    if (!confirmed) {
      confirmAction(t('common.confirm.removeModelFromGroup'), () =>
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
        showToast(t('groups.toast.removeModelSuccess'));
        await loadGroups();
      } else {
        const err = await res.json();
        showToast(t('common.error') + ': ' + (err.detail || t('groups.toast.removeModelFailed')), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast(t('groups.toast.removeModelFailed'), 'error');
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
          <h1 className="font-heading text-3xl font-semibold tracking-tight">{t('groups.title')}</h1>
          <p className="text-zinc-400 text-sm mt-1">{t('groups.description')}</p>
        </div>
        <Button
          onClick={() => setShowAddGroupModal(true)}
          className="bg-white text-black hover:bg-zinc-200 font-medium px-6 py-2.5 rounded-full transition-all duration-200 shadow-md hover:shadow-lg flex items-center gap-1.5"
        >
          + {t('groups.createGroup')}
        </Button>
      </header>

      {/* Group List Container */}
      <div className="group-list flex flex-col gap-6">
        {loading ? (
          <div className="glass-panel p-8 text-center text-zinc-400">{t('groups.loading')}</div>
        ) : groups.length === 0 ? (
          <div className="glass-panel p-8 text-center text-zinc-400">{t('groups.empty')}</div>
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
                      {t('groups.inactive')}
                    </Badge>
                  )}
                  <div className="flex gap-2 ml-auto items-center">
                    <Button
                      onClick={() => openAddGroupItem(group)}
                      className="bg-white text-black hover:bg-zinc-200 text-xs px-3.5 py-1.5 h-auto rounded font-semibold flex items-center gap-1"
                    >
                      + {t('groups.addModelItem')}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => openEditGroupModal(group)}
                      className="border-zinc-800 text-white hover:bg-zinc-800 text-xs px-3.5 py-1.5 h-auto rounded"
                    >
                      {t('common.edit')}
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
                    {t('groups.emptyItems')}
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
                                <Badge className="bg-purple-500/10 text-purple-300 border border-purple-500/20 text-[9px] font-normal tracking-wide rounded uppercase px-1.5 py-0 normal-case">
                                  {t('models.think')}: {item.thinking_level}
                                </Badge>
                              )}
                              {item.system_prompt && (
                                <Badge className="bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 text-[9px] font-normal tracking-wide rounded normal-case px-1.5 py-0">
                                  {t('models.systemPrompt')}
                                </Badge>
                              )}
                              {item.temperature !== undefined && item.temperature !== null && (
                                <Badge className="bg-orange-500/10 text-orange-300 border border-orange-500/20 text-[9px] font-normal tracking-wide rounded uppercase px-1.5 py-0 normal-case">
                                  {t('models.temp')}: {item.temperature}
                                </Badge>
                              )}
                            </div>

                            <div className="flex items-center">
                              {isModelInactive && (
                                <Badge className="bg-red-500/10 text-red-500 border border-red-500/20 text-[9px] font-semibold tracking-wide uppercase px-1.5 py-0 rounded">
                                  {t('models.inactive')}
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
                                {t('common.edit')}
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
            <DialogTitle className="text-xl font-heading font-semibold text-white">{t('groups.createModalTitle')}</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleCreateGroup} className="flex flex-col gap-4 my-2">
            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">{t('groups.groupName')}</label>
              <Input
                value={groupForm.name}
                onChange={(e) => setGroupForm({ ...groupForm, name: e.target.value })}
                required
                placeholder={t('groups.groupNamePlaceholder')}
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">{t('models.capability')}</label>
              <div className="custom-select-wrapper select-wrapper w-full">
                <select
                  value={groupForm.capability}
                  onChange={(e) => setGroupForm({ ...groupForm, capability: e.target.value as any })}
                  className="orion-native-select"
                >
                  <option value="chat">chat</option>
                  <option value="tts">tts</option>
                  <option value="embed">embed</option>
                  <option value="stt">stt</option>
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
                {t('common.cancel')}
              </Button>
              <Button
                type="submit"
                className="bg-white text-black hover:bg-zinc-200 rounded font-medium"
              >
                {t('common.create')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit Group Dialog */}
      <Dialog open={showEditGroupModal} onOpenChange={setShowEditGroupModal}>
        <DialogContent className="max-w-[400px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">{t('groups.editModalTitle')}</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleUpdateGroup} className="flex flex-col gap-4 my-2">
            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">{t('groups.groupName')}</label>
              <Input
                value={editingGroup.name}
                onChange={(e) => setEditingGroup({ ...editingGroup, name: e.target.value })}
                required
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">{t('models.capability')}</label>
              <div className="custom-select-wrapper select-wrapper w-full">
                <select
                  value={editingGroup.capability}
                  disabled
                  className="orion-native-select"
                >
                  <option value="chat">chat</option>
                  <option value="tts">tts</option>
                  <option value="embed">embed</option>
                  <option value="stt">stt</option>
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
                <span className={`font-semibold text-sm ${editingGroup.is_active ? 'text-purple-400' : 'text-white'}`}>{t('common.activeStatus')}</span>
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
                <Trash2 className="w-4 h-4" /> {t('common.delete')}
              </Button>
              <div className="flex gap-3 justify-end">
                <Button
                  variant="outline"
                  type="button"
                  onClick={() => setShowEditGroupModal(false)}
                  className="border-zinc-800 text-white hover:bg-zinc-900 rounded font-medium"
                >
                  {t('common.cancel')}
                </Button>
                <Button
                  type="submit"
                  className="bg-white text-black hover:bg-zinc-200 rounded font-medium"
                >
                  {t('common.saveChanges')}
                </Button>
              </div>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Add Model to Group Dialog */}
      <Dialog open={showAddGroupItemModal} onOpenChange={setShowAddGroupItemModal}>
        <DialogContent className="max-w-[420px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl overflow-y-auto max-h-[90vh]">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">{t('groups.addItemModalTitle')}</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleAddGroupItem} className="flex flex-col gap-4 my-2">
            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">{t('groups.selectModel')}</label>
              {activeGroupForItems &&
              getModelsByCapability(
                activeGroupForItems.capability,
                activeGroupForItems.items.map((i) => i.model_id)
              ).length === 0 ? (
                <p className="text-zinc-500 text-sm py-3 px-4 rounded border border-dashed border-zinc-800 bg-black/20">
                  {t('groups.noModelsAvailable')}
                </p>
              ) : (
                <div className="custom-select-wrapper select-wrapper w-full">
                  <select
                    value={addItemForm.model_id}
                    onChange={(e) => handleSelectModelInAddModal(e.target.value)}
                    required
                    className="orion-native-select"
                  >
                    <option value="">{t('groups.chooseModelPlaceholder')}</option>
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

            {addItemForm.model_id && (
              <>
                {renderItemThinkingBuilder(
                  addItemForm,
                  setAddItemForm,
                  models.find((m) => m.id === addItemForm.model_id),
                  activeGroupForItems?.capability || 'chat',
                  showAddItemThinking,
                  setShowAddItemThinking
                )}

                {(activeGroupForItems?.capability === 'chat' || activeGroupForItems?.capability === 'tts') && (
                  <div className="flex flex-col gap-2">
                    <label className="text-zinc-400 text-sm font-medium">{t('models.temperature')}</label>
                    <Input
                      type="number"
                      min="0"
                      max="2"
                      step="0.1"
                      value={addItemForm.temperature}
                      onChange={(e) => setAddItemForm({ ...addItemForm, temperature: e.target.value })}
                      placeholder={t('groups.temperaturePlaceholder')}
                      className="bg-black/40 border border-zinc-855 text-white rounded px-3 py-2 text-xs"
                    />
                  </div>
                )}

                {activeGroupForItems?.capability === 'chat' && (
                  <div className="flex flex-col gap-2">
                    <label className="text-zinc-400 text-sm font-medium">{t('models.systemPrompt')}</label>
                    <Textarea
                      value={addItemForm.system_prompt}
                      onChange={(e) => setAddItemForm({ ...addItemForm, system_prompt: e.target.value })}
                      placeholder={t('models.systemPromptPlaceholder')}
                      className="bg-black/40 border border-zinc-850 text-white rounded px-3 py-2 text-xs h-14 resize-none custom-scrollbar overflow-y-auto no-field-sizing"
                    />
                  </div>
                )}

                {renderItemLocalSampling(
                  addItemForm,
                  setAddItemForm,
                  models.find((m) => m.id === addItemForm.model_id)?.provider || '',
                  activeGroupForItems?.capability || 'chat',
                  showAddItemLocalSampling,
                  setShowAddItemLocalSampling
                )}
              </>
            )}

            <DialogFooter className="mt-4 flex gap-3 justify-end">
              <Button
                variant="outline"
                type="button"
                onClick={() => setShowAddGroupItemModal(false)}
                className="border-zinc-800 text-white hover:bg-zinc-900 rounded font-medium"
              >
                {t('common.cancel')}
              </Button>
              <Button
                type="submit"
                disabled={
                  !activeGroupForItems ||
                  !addItemForm.model_id ||
                  getModelsByCapability(
                    activeGroupForItems.capability,
                    activeGroupForItems.items.map((i) => i.model_id)
                  ).length === 0
                }
                className="bg-white text-black hover:bg-zinc-200 rounded font-medium disabled:opacity-50"
              >
                {t('groups.addModelItem')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit Group Item Dialog */}
      <Dialog open={showEditGroupItemModal} onOpenChange={setShowEditGroupItemModal}>
        <DialogContent className="max-w-[420px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl overflow-y-auto max-h-[90vh]">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">{t('groups.editItemModalTitle')}</DialogTitle>
          </DialogHeader>

          {editingGroupItem && (
            <form onSubmit={handleUpdateGroupItem} className="flex flex-col gap-4 my-2">
              <div className="flex flex-col gap-2">
                <label className="text-zinc-400 text-sm font-medium">{t('common.model')}</label>
                <div className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3 font-mono text-sm opacity-70">
                  {editingGroupItem.name} ({editingGroupItem.provider})
                </div>
              </div>

              {renderItemThinkingBuilder(
                editingGroupItem,
                setEditingGroupItem,
                editingGroupItem.targetModel || models.find((m) => m.id === editingGroupItem.model_id || m.name === editingGroupItem.name),
                groups.find((g) => g.id === editingGroupItem.groupId)?.capability || 'chat',
                showEditItemThinking,
                setShowEditItemThinking
              )}

              {(() => {
                const capability = groups.find((g) => g.id === editingGroupItem.groupId)?.capability;
                return (capability === 'chat' || capability === 'tts') && (
                  <div className="flex flex-col gap-2">
                    <label className="text-zinc-400 text-sm font-medium">{t('models.temperature')}</label>
                    <Input
                      type="number"
                      min="0"
                      max="2"
                      step="0.1"
                      value={editingGroupItem.temperature}
                      onChange={(e) => setEditingGroupItem({ ...editingGroupItem, temperature: e.target.value })}
                      placeholder={t('groups.temperaturePlaceholder')}
                      className="bg-black/40 border border-zinc-855 text-white rounded px-3 py-2 text-xs"
                    />
                  </div>
                );
              })()}

              {groups.find((g) => g.id === editingGroupItem.groupId)?.capability === 'chat' && (
                <div className="flex flex-col gap-2">
                  <label className="text-zinc-400 text-sm font-medium">{t('models.systemPrompt')}</label>
                  <Textarea
                    value={editingGroupItem.system_prompt}
                    onChange={(e) => setEditingGroupItem({ ...editingGroupItem, system_prompt: e.target.value })}
                    placeholder={t('models.systemPromptPlaceholder')}
                    className="bg-black/40 border border-zinc-850 text-white rounded px-3 py-2 text-xs h-14 resize-none custom-scrollbar overflow-y-auto no-field-sizing"
                  />
                </div>
              )}

              {renderItemLocalSampling(
                editingGroupItem,
                setEditingGroupItem,
                editingGroupItem.provider,
                groups.find((g) => g.id === editingGroupItem.groupId)?.capability || 'chat',
                showEditItemLocalSampling,
                setShowEditItemLocalSampling
              )}

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
                  <Trash2 className="w-4 h-4" /> {t('common.delete')}
                </Button>
                <div className="flex gap-3 justify-end">
                  <Button
                    variant="outline"
                    type="button"
                    onClick={() => setShowEditGroupItemModal(false)}
                    className="border-zinc-800 text-white hover:bg-zinc-900 rounded font-medium"
                  >
                    {t('common.cancel')}
                  </Button>
                  <Button
                    type="submit"
                    className="bg-white text-black hover:bg-zinc-200 rounded font-medium"
                  >
                    {t('common.saveChanges')}
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
