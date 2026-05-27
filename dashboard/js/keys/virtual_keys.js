// services/router/dashboard/js/keys/virtual_keys.js

// --- Virtual Key Operations ---
export async function createVirtualKey() {
    const name = this.virtualKeyForm.name.trim();
    if (!name) {
        alert('Please enter a key name.');
        return;
    }
    const budget = parseFloat(this.virtualKeyForm.budget);
    if (isNaN(budget) || budget < 0) {
        alert('Budget limit must be a positive number.');
        return;
    }

    try {
        const res = await this.adminFetch('/admin/api/keys', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, budget })
        });
        if (res.ok) {
            const data = await res.json();
            this.showKeyModal = false;
            this.rawKey = data.raw_key;
            this.virtualKeyForm = { name: '', budget: 0 };
            await this.loadVirtualKeys();
        } else {
            const err = await res.json();
            alert('Error: ' + (err.detail || 'Failed to create key'));
        }
    } catch (err) {
        console.error(err);
        alert('Failed to create key');
    }
}

export async function updateVirtualKey() {
    const key = this.editingVirtualKey;
    const name = key.name.trim();
    if (!name) {
        this.showToast('Please enter a key name.', 'error');
        return;
    }
    const budget = parseFloat(key.budget);
    if (isNaN(budget) || budget < 0) {
        this.showToast('Budget limit must be a positive number.', 'error');
        return;
    }

    try {
        const res = await this.adminFetch(`/admin/api/keys/${key.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name,
                budget,
                is_active: !!key.is_active
            })
        });
        if (res.ok) {
            this.showEditKeyModal = false;
            this.showToast('Virtual key updated successfully!', 'success');
            await this.loadVirtualKeys();
        } else {
            const err = await res.json();
            this.showToast('Error: ' + (err.detail || 'Failed to update key'), 'error');
        }
    } catch (err) {
        console.error(err);
        this.showToast('Failed to update key', 'error');
    }
}

export async function deleteVirtualKey(keyId, confirmed = false) {
    if (!confirmed) {
        this.confirmAction('Are you sure you want to delete this virtual key?', () => this.deleteVirtualKey(keyId, true));
        return;
    }
    try {
        const res = await this.adminFetch(`/admin/api/keys/${keyId}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            this.showEditKeyModal = false;
            this.showToast('Virtual key deleted successfully!', 'success');
            await this.loadVirtualKeys();
        } else {
            const err = await res.json();
            this.showToast('Error: ' + (err.detail || 'Failed to delete key'), 'error');
        }
    } catch (err) {
        console.error(err);
        this.showToast('Failed to delete key', 'error');
    }
}
