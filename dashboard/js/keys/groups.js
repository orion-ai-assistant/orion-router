// services/router/dashboard/js/keys/groups.js

// --- Group CRUD ---

export async function createGroup() {
    const name = this.groupForm.name.trim();
    if (!name) { alert('Please enter a group name.'); return; }
    try {
        const res = await this.adminFetch('/admin/api/model-groups', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description: '', capability: this.groupForm.capability, is_active: true })
        });
        if (res.ok) {
            this.groupForm = { name: '', capability: 'chat' };
            this.showAddGroupModal = false;
            await this.loadGroups();
        } else {
            const err = await res.json();
            alert('Error: ' + (err.detail || 'Failed to create group'));
        }
    } catch (err) {
        console.error(err);
        alert('Failed to create group');
    }
}

export async function toggleGroupActive(group) {
    try {
        const res = await this.adminFetch(`/admin/api/model-groups/${group.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: group.name, description: group.description, capability: group.capability, is_active: !group.is_active })
        });
        if (res.ok) {
            this.showToast(`Group ${!group.is_active ? 'activated' : 'deactivated'} successfully!`, 'success');
            await this.loadGroups();
        } else {
            const err = await res.json();
            this.showToast('Error: ' + (err.detail || 'Failed'), 'error');
        }
    } catch (err) {
        console.error(err);
        this.showToast('Failed to toggle active status', 'error');
    }
}

export async function deleteGroup(groupId, confirmed = false) {
    if (!confirmed) {
        this.confirmAction('Are you sure you want to delete this model group?', () => this.deleteGroup(groupId, true));
        return;
    }
    try {
        const res = await this.adminFetch(`/admin/api/model-groups/${groupId}`, { method: 'DELETE' });
        if (res.ok) {
            this.showEditGroupModal = false;
            await this.loadGroups();
            this.showToast('Model group deleted successfully!', 'success');
        } else {
            const err = await res.json();
            this.showToast('Error: ' + (err.detail || 'Failed to delete group'), 'error');
        }
    } catch (err) {
        console.error(err);
        this.showToast('Failed to delete group', 'error');
    }
}

export async function updateGroup(group) {
    const name = group.name.trim();
    if (!name) { this.showToast('Group name cannot be empty.', 'error'); return; }
    try {
        const res = await this.adminFetch(`/admin/api/model-groups/${group.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description: '', capability: group.capability, is_active: !!group.is_active })
        });
        if (res.ok) {
            this.showToast('Group updated successfully!', 'success');
            this.showEditGroupModal = false;
            await this.loadGroups();
        } else {
            const err = await res.json();
            this.showToast('Error: ' + (err.detail || 'Failed to update group'), 'error');
        }
    } catch (err) {
        console.error(err);
        this.showToast('Failed to update group', 'error');
    }
}

export async function addGroupItem() {
    const group = this.activeGroupForItems;
    const item = this.editingGroupItem;
    if (!item.model_id) { this.showToast('Please select a model.', 'error'); return; }
    const priority = group.items.length + 1;
    try {
        const res = await this.adminFetch(`/admin/api/model-groups/${group.id}/items`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model_id: item.model_id, priority })
        });
        if (res.ok) {
            this.showAddGroupItemModal = false;
            await this.loadGroups();
            this.showToast('Model added to group!', 'success');
        } else {
            const err = await res.json();
            this.showToast('Error: ' + (err.detail || 'Failed to add model'), 'error');
        }
    } catch (err) {
        console.error(err);
        this.showToast('Failed to add model to group', 'error');
    }
}

export async function moveGroupItem(group, index, direction) {
    const items = [...group.items];
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= items.length) return;
    // Insert (not swap): remove from current, insert at target
    const [moved] = items.splice(index, 1);
    items.splice(targetIndex, 0, moved);
    try {
        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            const newPriority = i + 1;
            if (item.priority !== newPriority) {
                const res = await this.adminFetch(`/admin/api/model-groups/${group.id}/items/${item.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ priority: newPriority })
                });
                if (!res.ok) {
                    const err = await res.json();
                    this.showToast('Error updating priority: ' + (err.detail || 'Failed'), 'error');
                    return;
                }
            }
        }
        await this.loadGroups();
        this.showToast('Model group order updated!', 'success');
    } catch (err) {
        console.error(err);
        this.showToast('Failed to update order', 'error');
    }
}

export async function deleteGroupItem(group, itemId, confirmed = false) {
    if (!confirmed) {
        this.confirmAction('Are you sure you want to remove this model from the group?', () => this.deleteGroupItem(group, itemId, true));
        return;
    }
    try {
        const res = await this.adminFetch(`/admin/api/model-groups/${group.id}/items/${itemId}`, { method: 'DELETE' });
        if (res.ok) {
            await this.loadGroups();
        } else {
            const err = await res.json();
            alert('Error: ' + (err.detail || 'Failed to remove model from group'));
        }
    } catch (err) {
        console.error(err);
        alert('Failed to remove model from group');
    }
}

// // --- Drag & Drop (Ghost + Drop Indicator) ---
//
// During drag:
//   - Original row stays in place but dims.
//   - A floating clone (ghost) follows the cursor.
//   - A purple line shows where the item will be inserted.
//
// On release:
//   - Ghost removed, list performs a single insert, then saves to API.
//   - No mid-drag reordering — one clean commit on drop.

export function pointerDragStart(group, index, event) {
    event.preventDefault();

    const handle   = event.currentTarget;
    const origRow  = handle.closest('.group-item-row');
    if (!origRow) return;

    // ── Measure original row ─────────────────────────────────────────
    const rowRect = origRow.getBoundingClientRect();
    const offsetY = event.clientY - rowRect.top;   // click offset inside row

    // ── Create floating ghost ────────────────────────────────────────
    const ghost = document.createElement('div');
    ghost.style.cssText = [
        'position:fixed',
        `left:${rowRect.left}px`,
        `top:${rowRect.top}px`,
        `width:${rowRect.width}px`,
        `height:${rowRect.height}px`,
        'pointer-events:none',
        'z-index:9999',
        'background:rgba(168,85,247,0.12)',
        'border:1px solid rgba(168,85,247,0.5)',
        'border-radius:6px',
        'box-shadow:0 8px 32px rgba(168,85,247,0.25)',
        'display:flex',
        'align-items:center',
        'padding:0 16px',
        'gap:12px',
        'box-sizing:border-box',
        'transition:none',
        'font-size:13px',
        'color:#e4e4e7',
        'font-weight:500',
    ].join(';');
    // Copy the text content of the original row into the ghost
    const nameSpan = origRow.querySelector('[style*="font-weight: 500"]');
    if (nameSpan) ghost.textContent = nameSpan.textContent;
    document.body.appendChild(ghost);

    // Dim original row while dragging
    origRow.style.opacity = '0.35';

    // ── Pointer capture & cursor lock ────────────────────────────────
    handle.setPointerCapture(event.pointerId);
    document.body.style.cursor        = 'grabbing';
    document.body.style.userSelect    = 'none';
    document.body.style.webkitUserSelect = 'none';

    let targetIndex = index;

    const getRows = () =>
        document.querySelectorAll(`.group-item-row[data-group-id="${group.id}"]`);

    const clearIndicators = () => {
        getRows().forEach(r => {
            r.style.boxShadow  = '';
            r.style.marginTop  = '';
        });
    };

    // ── pointermove ──────────────────────────────────────────────────
    const onMove = (e) => {
        // Move ghost
        ghost.style.top = (e.clientY - offsetY) + 'px';

        // Calculate where the item would drop
        const rows = getRows();
        let newTarget = rows.length;          // default: after all rows

        for (let i = 0; i < rows.length; i++) {
            const rect = rows[i].getBoundingClientRect();
            if (e.clientY < rect.top + rect.height / 2) {
                newTarget = i;
                break;
            }
        }
        targetIndex = newTarget;

        // Draw drop indicator: a glowing top-border line on target row
        clearIndicators();
        if (targetIndex < rows.length) {
            rows[targetIndex].style.boxShadow = 'inset 0 2px 0 0 #a855f7';
        } else if (rows.length > 0) {
            rows[rows.length - 1].style.boxShadow = 'inset 0 -2px 0 0 #a855f7';
        }
    };

    // ── pointerup / pointercancel ────────────────────────────────────
    const onUp = async (e) => {
        ghost.remove();
        origRow.style.opacity = '';
        clearIndicators();

        document.body.style.cursor        = '';
        document.body.style.userSelect    = '';
        document.body.style.webkitUserSelect = '';

        handle.releasePointerCapture(e.pointerId);
        handle.removeEventListener('pointermove', onMove);
        handle.removeEventListener('pointerup',   onUp);
        handle.removeEventListener('pointercancel', onUp);

        // No-op: dropped at current position or adjacent (same result)
        if (targetIndex === index || targetIndex === index + 1) return;

        const currentGroup = this.groups.find(g => g.id === group.id);
        if (!currentGroup) return;

        // Insert (not swap):
        //   After splice(index, 1) the array shrinks, so indices > index shift by -1.
        //   Account for that when targetIndex > index.
        const items    = [...currentGroup.items];
        const [moved]  = items.splice(index, 1);
        const insertAt = targetIndex > index ? targetIndex - 1 : targetIndex;
        items.splice(insertAt, 0, moved);
        currentGroup.items = items;

        try {
            for (let i = 0; i < currentGroup.items.length; i++) {
                const item        = currentGroup.items[i];
                const newPriority = i + 1;
                if (item.priority !== newPriority) {
                    const res = await this.adminFetch(
                        `/admin/api/model-groups/${currentGroup.id}/items/${item.id}`,
                        {
                            method:  'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body:    JSON.stringify({ priority: newPriority })
                        }
                    );
                    if (!res.ok) {
                        const err = await res.json();
                        this.showToast('Error saving order: ' + (err.detail || 'Failed'), 'error');
                        await this.loadGroups();
                        return;
                    }
                }
            }
            await this.loadGroups();
            this.showToast('Model group order updated!', 'success');
        } catch (err) {
            console.error(err);
            this.showToast('Failed to save order', 'error');
            await this.loadGroups();
        }
    };

    handle.addEventListener('pointermove',   onMove);
    handle.addEventListener('pointerup',     onUp);
    handle.addEventListener('pointercancel', onUp);
}

// Stubs — kept so existing imports in app.js don't break
export function dragStart() {}
export function dragOver() {}
export function dragEnter() {}
export function dragEnd() {}
