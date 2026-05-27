// services/router/dashboard/js/keys/provider_keys.js

// --- Provider Key Operations ---
export async function createProviderKey() {
    const provider = this.keyForm.provider.trim();
    const label = this.keyForm.label.trim();
    const api_key = this.keyForm.api_key.trim();
    const priority = parseInt(this.keyForm.priority);

    if (!provider || !label || !api_key) {
        alert('Please fill out all fields.');
        return;
    }
    if (isNaN(priority) || priority <= 0) {
        alert('Priority must be a positive integer.');
        return;
    }

    try {
        const res = await this.adminFetch('/admin/api/provider-key-pool', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider, label, api_key, priority, is_active: true })
        });
        if (res.ok) {
            this.keyForm = { provider: this.providerNames()[0] || '', label: '', api_key: '', priority: 100 };
            this.showAddProviderKeyModal = false;
            await this.loadKeyPool();
        } else {
            const err = await res.json();
            alert('Error: ' + (err.detail || 'Failed to add provider key'));
        }
    } catch (err) {
        console.error(err);
        alert('Failed to add provider key');
    }
}

export async function updateProviderKey(key) {
    const provider = key.provider.trim();
    const label = key.label.trim();
    const priority = parseInt(key.priority);

    if (!provider || !label) {
        alert('Provider and label cannot be empty.');
        return;
    }
    if (isNaN(priority) || priority <= 0) {
        alert('Priority must be a positive integer.');
        return;
    }

    try {
        const res = await this.adminFetch(`/admin/api/provider-key-pool/${key.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                provider: provider,
                label: label,
                api_key: key.api_key || '', // blank keeps original
                priority: priority,
                is_active: !!key.is_active
            })
        });
        if (res.ok) {
            alert('Provider key updated successfully!');
            this.showEditProviderKeyModal = false;
            await this.loadKeyPool();
        } else {
            const err = await res.json();
            alert('Error: ' + (err.detail || 'Failed to update key'));
        }
    } catch (err) {
        console.error(err);
        alert('Failed to update key');
    }
}

export async function deleteProviderKey(keyId, confirmed = false) {
    if (!confirmed) {
        this.confirmAction('Are you sure you want to delete this provider key?', () => this.deleteProviderKey(keyId, true));
        return;
    }
    try {
        const res = await this.adminFetch(`/admin/api/provider-key-pool/${keyId}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            this.showEditProviderKeyModal = false;
            this.showToast('Provider key deleted successfully!', 'success');
            await this.loadKeyPool();
        } else {
            const err = await res.json();
            this.showToast('Error: ' + (err.detail || 'Failed to delete key'), 'error');
        }
    } catch (err) {
        console.error(err);
        this.showToast('Failed to delete key', 'error');
    }
}
