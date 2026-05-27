// services/router/dashboard/js/keys/models.js

// --- Model Operations ---
export async function createModel() {
    const name = this.modelForm.name.trim();
    const provider = this.modelForm.provider.trim();
    const capability = this.modelForm.capability.trim();

    if (!name || !provider) {
        alert('Please enter a model name and select a provider.');
        return;
    }

    let tempVal = null;
    if (this.modelForm.temperature !== '' && this.modelForm.temperature !== null && this.modelForm.temperature !== undefined) {
        tempVal = parseFloat(this.modelForm.temperature);
        if (isNaN(tempVal) || tempVal < 0 || tempVal > 2) {
            alert('Temperature must be a number between 0.0 and 2.0');
            return;
        }
    }

    try {
        const res = await this.adminFetch('/admin/api/models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name,
                provider,
                capability,
                temperature: tempVal,
                is_active: true,
                input_price: this.modelForm.input_price || 0,
                output_price: this.modelForm.output_price || 0,
                think_price: this.modelForm.think_price || 0
            })
        });
        if (res.ok) {
            this.modelForm = { name: '', provider: this.providerNames()[0] || '', capability: 'chat', temperature: null, input_price: 0, output_price: 0, think_price: 0 };
            this.showAddModelModal = false;
            await this.loadModels();
        } else {
            const err = await res.json();
            alert('Error: ' + (err.detail || 'Failed to add model'));
        }
    } catch (err) {
        console.error(err);
        alert('Failed to add model');
    }
}

export async function updateModel(model) {
    const name = model.name.trim();
    const provider = model.provider.trim();

    if (!name || !provider) {
        alert('Model name and provider cannot be empty.');
        return;
    }

    let tempVal = null;
    if (model.temperature !== '' && model.temperature !== null && model.temperature !== undefined) {
        tempVal = parseFloat(model.temperature);
        if (isNaN(tempVal) || tempVal < 0 || tempVal > 2) {
            alert('Temperature must be a number between 0.0 and 2.0');
            return;
        }
    }

    try {
        const res = await this.adminFetch(`/admin/api/models/${model.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                provider: provider,
                capability: model.capability,
                temperature: tempVal,
                is_active: !!model.is_active,
                input_price: model.input_price || 0,
                output_price: model.output_price || 0,
                think_price: model.think_price || 0
            })
        });
        if (res.ok) {
            alert('Model updated successfully!');
            this.showEditModelModal = false;
            await this.loadModels();
        } else {
            const err = await res.json();
            alert('Error: ' + (err.detail || 'Failed to update model'));
        }
    } catch (err) {
        console.error(err);
        alert('Failed to update model');
    }
}

export async function deleteModel(modelId, confirmed = false) {
    if (!confirmed) {
        this.confirmAction('Are you sure you want to delete this model?', () => this.deleteModel(modelId, true));
        return;
    }
    try {
        const res = await this.adminFetch(`/admin/api/models/${modelId}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            this.showEditModelModal = false;
            this.showToast('Model deleted successfully!', 'success');
            await this.loadModels();
        } else {
            const err = await res.json();
            this.showToast('Error: ' + (err.detail || 'Failed to delete model'), 'error');
        }
    } catch (err) {
        console.error(err);
        this.showToast('Failed to delete model', 'error');
    }
}
