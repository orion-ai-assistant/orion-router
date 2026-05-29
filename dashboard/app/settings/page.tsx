'use client';

import React, { useState } from 'react';
import { adminFetch } from '@/lib/api';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export default function SettingsPage() {
  const { showToast, updateAdminKey } = useApp();
  const [adminSecret, setAdminSecret] = useState<string>('');

  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    const secret = adminSecret.trim();
    if (!secret) {
      showToast('Admin secret cannot be empty', 'error');
      return;
    }

    try {
      const res = await adminFetch('/dashboard/api/settings/admin-secret', {
        method: 'PUT',
        body: JSON.stringify({ admin_secret: secret }),
      });
      if (res.ok) {
        showToast('Admin secret updated successfully!');
        updateAdminKey(secret);
        setAdminSecret('');
      } else {
        const data = await res.json().catch(() => ({}));
        showToast(data.detail || 'Failed to update admin secret', 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Network error updating admin secret', 'error');
    }
  };

  return (
    <section id="settings" className="tab-content active block pt-8">
      <header className="flex justify-between items-end mb-8 pb-6 border-b border-border">
        <div className="header-titles">
          <h1 className="font-heading text-3xl font-semibold tracking-tight">Settings</h1>
          <p className="text-zinc-400 text-sm mt-1">Manage gateway configurations</p>
        </div>
      </header>

      <div className="glass-panel p-8 bg-[#18181b] border border-zinc-800 rounded-md shadow-xl max-w-2xl">
        <h2 className="font-heading text-lg font-semibold text-white mb-2">Admin Authentication</h2>
        <p className="text-zinc-400 text-sm mb-6">Change the admin secret used to access this dashboard.</p>
        
        <form onSubmit={handleSaveSettings} className="max-w-md flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <label className="text-zinc-450 text-sm font-medium">New Admin Secret</label>
            <Input
              type="password"
              value={adminSecret}
              onChange={(e) => setAdminSecret(e.target.value)}
              placeholder="Enter new secret"
              className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
            />
          </div>
          <div className="mt-2 flex">
            <Button
              type="submit"
              className="bg-white text-black hover:bg-zinc-200 font-semibold px-6 py-2.5 rounded transition-all duration-200 shadow-md"
            >
              Save Changes
            </Button>
          </div>
        </form>
      </div>
    </section>
  );
}
