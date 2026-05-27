// services/router/dashboard/js/keys/loaders.js

// --- Data Loading Operations ---
export async function loadStats() {
    const res = await this.adminFetch('/admin/api/stats');
    if (res.ok) {
        this.stats = await res.json();
    }
}

export async function loadVirtualKeys() {
    const res = await this.adminFetch('/admin/api/keys');
    if (res.ok) {
        const data = await res.json();
        this.virtualKeys = data.keys || [];
    }
}

export async function loadLogs() {
    const res = await this.adminFetch('/admin/api/logs');
    if (res.ok) {
        const data = await res.json();
        this.logs = data.logs || [];
    }
}

export async function loadKeyPool() {
    const res = await this.adminFetch('/admin/api/provider-key-pool');
    if (res.ok) {
        const data = await res.json();
        this.keyPool = (data.keys || []).map(key => ({
            ...key,
            provider: key.provider || '',
            label: key.label || '',
            priority: Number.isFinite(Number(key.priority)) ? Number(key.priority) : 0,
            is_active: !!key.is_active,
            _original: {
                provider: key.provider || '',
                label: key.label || '',
                priority: Number.isFinite(Number(key.priority)) ? Number(key.priority) : 0,
                is_active: !!key.is_active
            }
        }));
    }
}

export async function loadModels() {
    const res = await this.adminFetch('/admin/api/models');
    if (res.ok) {
        const data = await res.json();
        this.models = (data.models || []).map(model => {
            const normalizedName = model.name || '';
            const normalizedProvider = model.provider || '';
            const normalizedCapability = model.capability || 'chat';
            const normalizedTemperature = normalizeTemperature(model.temperature);
            const normalizedActive = !!model.is_active;

            return {
                ...model,
                name: normalizedName,
                provider: normalizedProvider,
                capability: normalizedCapability,
                temperature: normalizedTemperature,
                is_active: normalizedActive,
                input_price: model.input_price || 0,
                output_price: model.output_price || 0,
                think_price: model.think_price || 0,
                _original: {
                    name: normalizedName,
                    provider: normalizedProvider,
                    capability: normalizedCapability,
                    temperature: normalizedTemperature,
                    is_active: normalizedActive,
                    input_price: model.input_price || 0,
                    output_price: model.output_price || 0,
                    think_price: model.think_price || 0
                }
            };
        });
    }
}

export async function loadGroups() {
    const res = await this.adminFetch('/admin/api/model-groups');
    if (res.ok) {
        const data = await res.json();
        this.groups = (data.groups || []).map(group => {
            const normalizedName = group.name || '';
            const normalizedDescription = group.description || '';
            const normalizedCapability = group.capability || 'chat';
            const normalizedActive = !!group.is_active;
            const items = (group.items || []).map(item => ({
                ...item,
                _original: {
                    priority: Number.isFinite(Number(item.priority)) ? Number(item.priority) : 0
                }
            }));

            return {
                ...group,
                name: normalizedName,
                description: normalizedDescription,
                capability: normalizedCapability,
                is_active: normalizedActive,
                items,
                _original: {
                    name: normalizedName,
                    description: normalizedDescription,
                    capability: normalizedCapability,
                    is_active: normalizedActive
                },
                newModelId: group.newModelId === undefined ? '' : group.newModelId,
                newPriority: group.newPriority === undefined ? 100 : group.newPriority
            };
        });
    }
}

export async function loadModelInfo() {
    try {
        const res = await fetch('/v1/model-info');
        if (res.ok) {
            const data = await res.json();
            this.modelFamilies = data.families || [];
            if (this.modelFamilies.length > 0 && !this.selectedFamily) {
                this.selectedFamily = this.modelFamilies[0];
            }
        }
    } catch (err) {
        console.error('Failed to fetch model info:', err);
    }
}

function normalizeTemperature(value) {
    if (value === '' || value === null || value === undefined) return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
}
