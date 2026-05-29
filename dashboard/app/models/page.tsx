'use client';

import React, { useState, useEffect } from 'react';
import { adminFetch } from '@/lib/api';
import { money } from '@/lib/utils';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Trash2 } from 'lucide-react';

interface ModelItem {
  id: string;
  name: string;
  provider: string;
  capability: 'chat' | 'tts' | 'embed';
  temperature: number | null;
  is_active: boolean;
  input_price: number;
  output_price: number;
  think_price: number;
  _original?: {
    name: string;
    provider: string;
    capability: 'chat' | 'tts' | 'embed';
    temperature: number | null;
    is_active: boolean;
    input_price: number;
    output_price: number;
    think_price: number;
  };
}

export default function ModelsPage() {
  const { showToast, confirmAction } = useApp();
  const [models, setModels] = useState<ModelItem[]>([]);
  const [providers, setProviders] = useState<string[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Modals visibility
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [showEditModal, setShowEditModal] = useState<boolean>(false);

  // Form states
  const [addForm, setAddForm] = useState({
    name: '',
    provider: '',
    capability: 'chat' as 'chat' | 'tts' | 'embed',
    temperature: '' as string | number,
    input_price: 0,
    output_price: 0,
    think_price: 0,
  });

  const [editingModel, setEditingModel] = useState<ModelItem>({
    id: '',
    name: '',
    provider: '',
    capability: 'chat',
    temperature: null,
    is_active: true,
    input_price: 0,
    output_price: 0,
    think_price: 0,
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

  const loadModels = async () => {
    try {
      const res = await adminFetch('/dashboard/api/models');
      if (res.ok) {
        const data = await res.json();
        const loadedModels = (data.models || []).map((model: any) => {
          const name = model.name || '';
          const provider = model.provider || '';
          const capability = model.capability || 'chat';
          const temperature = model.temperature !== null ? parseFloat(model.temperature) : null;
          const is_active = !!model.is_active;
          const input_price = model.input_price || 0;
          const output_price = model.output_price || 0;
          const think_price = model.think_price || 0;

          return {
            ...model,
            name,
            provider,
            capability,
            temperature,
            is_active,
            input_price,
            output_price,
            think_price,
            _original: {
              name,
              provider,
              capability,
              temperature,
              is_active,
              input_price,
              output_price,
              think_price,
            },
          };
        });
        setModels(loadedModels);
      }
    } catch (err) {
      console.error('Failed to load models:', err);
      showToast('Failed to load models', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const initData = async () => {
      await loadProviders();
      await loadModels();
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

  const normalizeTemperature = (value: string | number | null | undefined): number | null => {
    if (value === '' || value === null || value === undefined) return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = addForm.name.trim();
    const provider = addForm.provider.trim();
    const capability = addForm.capability;

    if (!name || !provider) {
      showToast('Please enter a model name and select a provider.', 'error');
      return;
    }

    const tempVal = normalizeTemperature(addForm.temperature);
    if (tempVal !== null && (tempVal < 0 || tempVal > 2)) {
      showToast('Temperature must be a number between 0.0 and 2.0', 'error');
      return;
    }

    try {
      const res = await adminFetch('/dashboard/api/models', {
        method: 'POST',
        body: JSON.stringify({
          name,
          provider,
          capability,
          temperature: tempVal,
          is_active: true,
          input_price: addForm.input_price || 0,
          output_price: addForm.output_price || 0,
          think_price: addForm.think_price || 0,
        }),
      });
      if (res.ok) {
        setAddForm({
          name: '',
          provider: providers[0] || '',
          capability: 'chat',
          temperature: '',
          input_price: 0,
          output_price: 0,
          think_price: 0,
        });
        setShowAddModal(false);
        showToast('Model added successfully!');
        await loadModels();
      } else {
        const err = await res.json();
        showToast('Error: ' + (err.detail || 'Failed to add model'), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Failed to add model', 'error');
    }
  };

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = editingModel.name.trim();
    const provider = editingModel.provider.trim();

    if (!name || !provider) {
      showToast('Model name and provider cannot be empty.', 'error');
      return;
    }

    const tempVal = normalizeTemperature(editingModel.temperature);
    if (tempVal !== null && (tempVal < 0 || tempVal > 2)) {
      showToast('Temperature must be a number between 0.0 and 2.0', 'error');
      return;
    }

    try {
      const res = await adminFetch(`/dashboard/api/models/${editingModel.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          name,
          provider,
          capability: editingModel.capability,
          temperature: tempVal,
          is_active: !!editingModel.is_active,
          input_price: editingModel.input_price || 0,
          output_price: editingModel.output_price || 0,
          think_price: editingModel.think_price || 0,
        }),
      });
      if (res.ok) {
        showToast('Model updated successfully!');
        setShowEditModal(false);
        await loadModels();
      } else {
        const err = await res.json();
        showToast('Error: ' + (err.detail || 'Failed to update model'), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Failed to update model', 'error');
    }
  };

  const handleDelete = async (modelId: string, confirmed = false) => {
    if (!confirmed) {
      confirmAction('Are you sure you want to delete this model?', () =>
        handleDelete(modelId, true)
      );
      return;
    }
    try {
      const res = await adminFetch(`/dashboard/api/models/${modelId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setShowEditModal(false);
        showToast('Model deleted successfully!');
        await loadModels();
      } else {
        const err = await res.json();
        showToast('Error: ' + (err.detail || 'Failed to delete model'), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Failed to delete model', 'error');
    }
  };

  const isModelDirty = (model: ModelItem) => {
    if (!model || !model._original) return false;
    return (
      model.name !== model._original.name ||
      model.provider !== model._original.provider ||
      model.capability !== model._original.capability ||
      normalizeTemperature(model.temperature) !== model._original.temperature ||
      !!model.is_active !== model._original.is_active ||
      Number(model.input_price || 0) !== Number(model._original.input_price || 0) ||
      Number(model.output_price || 0) !== Number(model._original.output_price || 0) ||
      Number(model.think_price || 0) !== Number(model._original.think_price || 0)
    );
  };

  const openEditModal = (model: ModelItem) => {
    setEditingModel({
      ...model,
      temperature: model.temperature === null ? '' : (model.temperature as any),
    });
    setShowEditModal(true);
  };

  return (
    <section id="models" className="tab-content active block pt-8">
      <header className="flex justify-between items-end mb-8 pb-6 border-b border-border">
        <div className="header-titles">
          <h1 className="font-heading text-3xl font-semibold tracking-tight">Models</h1>
          <p className="text-zinc-400 text-sm mt-1">Register concrete models and their provider</p>
        </div>
        <Button
          onClick={() => setShowAddModal(true)}
          className="bg-white text-black hover:bg-zinc-200 font-medium px-6 py-2.5 rounded-full transition-all duration-200 shadow-md hover:shadow-lg flex items-center gap-1.5"
        >
          + Add Model
        </Button>
      </header>

      {/* Table List */}
      <div className="table-container glass-panel bg-[#18181b] border border-zinc-800 rounded-md overflow-hidden shadow-xl">
        <Table>
          <TableHeader className="bg-black/25">
            <TableRow className="border-b border-zinc-850 hover:bg-transparent">
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 pl-6 w-[260px]">Name</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 w-[100px]">Provider</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 w-[90px]">Capability</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 w-[110px]">Temperature</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-center w-[260px]">Pricing (1M)</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-center w-[80px]">Status</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-right pr-6 w-[90px]">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={7} className="text-center text-zinc-400 py-8">
                  Loading models registry...
                </TableCell>
              </TableRow>
            ) : models.length === 0 ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={7} className="text-center text-zinc-400 py-8">
                  No registered models found. Add one to start routing.
                </TableCell>
              </TableRow>
            ) : (
              models.map((model) => (
                <TableRow key={model.id} className="border-b border-zinc-900 hover:bg-white/[0.015] transition-colors">
                  <TableCell className="font-semibold text-sm py-4 pl-6 font-mono text-white select-all">{model.name}</TableCell>
                  <TableCell className="py-4">
                    <Badge className="bg-blue-500/10 text-blue-300 border border-blue-500/20 text-[10px] font-medium tracking-wide rounded uppercase px-2.5 py-0.5 capitalize">
                      {model.provider}
                    </Badge>
                  </TableCell>
                  <TableCell className="py-4">
                    <Badge className="bg-zinc-800 text-zinc-300 border border-zinc-700/50 text-[10px] tracking-wide rounded uppercase px-2.5 py-0.5">
                      {model.capability}
                    </Badge>
                  </TableCell>
                  <TableCell className="py-4 font-mono text-xs text-zinc-400">
                    {model.temperature !== null ? model.temperature.toFixed(1) : '-'}
                  </TableCell>
                  <TableCell className="py-4">
                    <div className="pricing-container flex items-center justify-center gap-4">
                      {/* Input pricing */}
                      {(model.capability === 'chat' || model.capability === 'tts' || model.capability === 'embed') && (
                        <div className="pricing-item relative flex flex-col items-center py-1">
                          <span className="pricing-label text-[8px] font-semibold text-zinc-500 uppercase tracking-wider scale-90 mb-0.5">in</span>
                          <span className="pricing-value text-xs font-mono">{money(model.input_price)}</span>
                        </div>
                      )}

                      {/* Output pricing */}
                      {(model.capability === 'chat' || model.capability === 'tts') && (
                        <div className="pricing-item relative flex flex-col items-center py-1">
                          <span className="pricing-label text-[8px] font-semibold text-zinc-500 uppercase tracking-wider scale-90 mb-0.5">out</span>
                          <span className="pricing-value text-xs font-mono">{money(model.output_price)}</span>
                        </div>
                      )}

                      {/* Think pricing */}
                      {model.capability === 'chat' && model.think_price > 0 && (
                        <div className="pricing-item relative flex flex-col items-center py-1">
                          <span className="pricing-label text-[8px] font-semibold text-zinc-500 uppercase tracking-wider scale-90 mb-0.5">think</span>
                          <span className="pricing-value text-xs font-mono">{money(model.think_price)}</span>
                        </div>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-center py-4">
                    <Badge
                      className={`text-[10px] font-semibold tracking-wide uppercase px-2.5 py-0.5 rounded-full ${
                        model.is_active
                          ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                          : 'bg-red-500/10 text-red-500 border border-red-500/20'
                      }`}
                    >
                      {model.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right py-4 pr-6">
                    <Button
                      variant="outline"
                      onClick={() => openEditModal(model)}
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

      {/* Add Model Dialog */}
      <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
        <DialogContent className="max-w-[440px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl overflow-y-auto max-h-[90vh]">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">Register New Model</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleCreate} className="flex flex-col gap-4 my-2">
            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">Model ID / Name</label>
              <Input
                value={addForm.name}
                onChange={(e) => setAddForm({ ...addForm, name: e.target.value })}
                required
                placeholder="e.g. gemini-2.5-pro"
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
              />
            </div>

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
              <label className="text-zinc-400 text-sm font-medium">Capability</label>
              <div className="custom-select-wrapper select-wrapper w-full">
                <select
                  value={addForm.capability}
                  onChange={(e) =>
                    setAddForm({
                      ...addForm,
                      capability: e.target.value as any,
                      temperature: (e.target.value === 'chat' || e.target.value === 'tts') ? addForm.temperature : '',
                    })
                  }
                  className="orion-native-select"
                >
                  <option value="chat">chat</option>
                  <option value="tts">tts</option>
                  <option value="embed">embed</option>
                </select>
              </div>
            </div>

            {(addForm.capability === 'chat' || addForm.capability === 'tts') && (
              <div className="flex flex-col gap-2">
                <label className="text-zinc-400 text-sm font-medium">Default Temperature (0.0 to 2.0)</label>
                <Input
                  type="number"
                  min="0"
                  max="2"
                  step="0.1"
                  value={addForm.temperature}
                  onChange={(e) => setAddForm({ ...addForm, temperature: e.target.value })}
                  placeholder="optional (e.g. 0.7)"
                  className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
                />
              </div>
            )}

            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">Pricing (per 1M tokens/chars)</label>
              <div className="flex gap-3">
                {(addForm.capability === 'chat' || addForm.capability === 'tts' || addForm.capability === 'embed') && (
                  <div className="flex-1 flex flex-col gap-1">
                    <span className="text-[11px] text-zinc-500 font-semibold uppercase">Input</span>
                    <Input
                      type="number"
                      min="0"
                      step="0.00000001"
                      value={addForm.input_price || ''}
                      onChange={(e) => setAddForm({ ...addForm, input_price: parseFloat(e.target.value) || 0 })}
                      placeholder="0.0"
                      className="bg-black/40 border border-zinc-855 text-white text-xs px-3 py-2"
                    />
                  </div>
                )}

                {(addForm.capability === 'chat' || addForm.capability === 'tts') && (
                  <div className="flex-1 flex flex-col gap-1">
                    <span className="text-[11px] text-zinc-500 font-semibold uppercase">Output</span>
                    <Input
                      type="number"
                      min="0"
                      step="0.00000001"
                      value={addForm.output_price || ''}
                      onChange={(e) => setAddForm({ ...addForm, output_price: parseFloat(e.target.value) || 0 })}
                      placeholder="0.0"
                      className="bg-black/40 border border-zinc-855 text-white text-xs px-3 py-2"
                    />
                  </div>
                )}

                {addForm.capability === 'chat' && (
                  <div className="flex-1 flex flex-col gap-1">
                    <span className="text-[11px] text-zinc-500 font-semibold uppercase">Think</span>
                    <Input
                      type="number"
                      min="0"
                      step="0.00000001"
                      value={addForm.think_price || ''}
                      onChange={(e) => setAddForm({ ...addForm, think_price: parseFloat(e.target.value) || 0 })}
                      placeholder="0.0"
                      className="bg-black/40 border border-zinc-855 text-white text-xs px-3 py-2"
                    />
                  </div>
                )}
              </div>
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
                Add Model
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit Model Dialog */}
      <Dialog open={showEditModal} onOpenChange={setShowEditModal}>
        <DialogContent className="max-w-[440px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl overflow-y-auto max-h-[90vh]">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">Edit Registered Model</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleUpdate} className="flex flex-col gap-4 my-2">
            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">Model ID / Name</label>
              <Input
                value={editingModel.name}
                onChange={(e) => setEditingModel({ ...editingModel, name: e.target.value })}
                required
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">Provider</label>
              <div className="custom-select-wrapper select-wrapper w-full">
                <select
                  value={editingModel.provider}
                  onChange={(e) => setEditingModel({ ...editingModel, provider: e.target.value })}
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
              <label className="text-zinc-400 text-sm font-medium">Capability</label>
              <div className="custom-select-wrapper select-wrapper w-full">
                <select
                  value={editingModel.capability}
                  onChange={(e) =>
                    setEditingModel({
                      ...editingModel,
                      capability: e.target.value as any,
                      temperature: (e.target.value === 'chat' || e.target.value === 'tts') ? editingModel.temperature : null,
                    })
                  }
                  className="orion-native-select"
                >
                  <option value="chat">chat</option>
                  <option value="tts">tts</option>
                  <option value="embed">embed</option>
                </select>
              </div>
            </div>

            {(editingModel.capability === 'chat' || editingModel.capability === 'tts') && (
              <div className="flex flex-col gap-2">
                <label className="text-zinc-400 text-sm font-medium">Default Temperature (0.0 to 2.0)</label>
                <Input
                  type="number"
                  min="0"
                  max="2"
                  step="0.1"
                  value={editingModel.temperature === null ? '' : editingModel.temperature}
                  onChange={(e) => setEditingModel({ ...editingModel, temperature: e.target.value === '' ? null : parseFloat(e.target.value) })}
                  placeholder="optional"
                  className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
                />
              </div>
            )}

            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">Pricing (per 1M tokens/chars)</label>
              <div className="flex gap-3">
                {(editingModel.capability === 'chat' || editingModel.capability === 'tts' || editingModel.capability === 'embed') && (
                  <div className="flex-1 flex flex-col gap-1">
                    <span className="text-[11px] text-zinc-500 font-semibold uppercase">Input</span>
                    <Input
                      type="number"
                      min="0"
                      step="0.00000001"
                      value={editingModel.input_price || ''}
                      onChange={(e) => setEditingModel({ ...editingModel, input_price: parseFloat(e.target.value) || 0 })}
                      placeholder="0.0"
                      className="bg-black/40 border border-zinc-855 text-white text-xs px-3 py-2"
                    />
                  </div>
                )}

                {(editingModel.capability === 'chat' || editingModel.capability === 'tts') && (
                  <div className="flex-1 flex flex-col gap-1">
                    <span className="text-[11px] text-zinc-500 font-semibold uppercase">Output</span>
                    <Input
                      type="number"
                      min="0"
                      step="0.00000001"
                      value={editingModel.output_price || ''}
                      onChange={(e) => setEditingModel({ ...editingModel, output_price: parseFloat(e.target.value) || 0 })}
                      placeholder="0.0"
                      className="bg-black/40 border border-zinc-855 text-white text-xs px-3 py-2"
                    />
                  </div>
                )}

                {editingModel.capability === 'chat' && (
                  <div className="flex-1 flex flex-col gap-1">
                    <span className="text-[11px] text-zinc-500 font-semibold uppercase">Think</span>
                    <Input
                      type="number"
                      min="0"
                      step="0.00000001"
                      value={editingModel.think_price || ''}
                      onChange={(e) => setEditingModel({ ...editingModel, think_price: parseFloat(e.target.value) || 0 })}
                      placeholder="0.0"
                      className="bg-black/40 border border-zinc-855 text-white text-xs px-3 py-2"
                    />
                  </div>
                )}
              </div>
            </div>

            <div
              onClick={() => setEditingModel({ ...editingModel, is_active: !editingModel.is_active })}
              className={`flex items-center justify-between p-4 rounded-lg cursor-pointer border transition-all duration-200 ${
                editingModel.is_active
                  ? 'bg-purple-950/10 border-purple-500/25'
                  : 'bg-white/3 border-zinc-800'
              }`}
            >
              <div className="flex flex-col gap-0.5">
                <span className={`font-semibold text-sm ${editingModel.is_active ? 'text-purple-400' : 'text-white'}`}>Active Status</span>
                <span className="text-zinc-400 text-xs">Enable for routing</span>
              </div>
              <Switch
                checked={editingModel.is_active}
                onCheckedChange={(checked) => setEditingModel({ ...editingModel, is_active: checked })}
              />
            </div>

            <DialogFooter className="mt-4 flex justify-between w-full gap-3">
              <Button
                onClick={() => handleDelete(editingModel.id)}
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
                  disabled={!isModelDirty(editingModel)}
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
