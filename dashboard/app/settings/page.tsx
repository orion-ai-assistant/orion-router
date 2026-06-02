'use client';

import React, { useState } from 'react';
import { adminFetch } from '@/lib/api';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';

export default function SettingsPage() {
  const { showToast, updateAdminKey } = useApp();
  
  // Change Admin Secret states
  const [showChangeKeyModal, setShowChangeKeyModal] = useState<boolean>(false);
  const [currentSecret, setCurrentSecret] = useState<string>( '');
  const [newSecret, setNewSecret] = useState<string>('');
  const [confirmNewSecret, setConfirmNewSecret] = useState<string>('');
  const [updatingKey, setUpdatingKey] = useState<boolean>(false);
  
  // Clear logs states
  const [showClearLogsModal, setShowClearLogsModal] = useState<boolean>(false);
  const [confirmAdminKey, setConfirmAdminKey] = useState<string>('');
  const [clearing, setClearing] = useState<boolean>(false);

  const handleChangeAdminSecret = async (e: React.FormEvent) => {
    e.preventDefault();
    const currentSec = currentSecret.trim();
    const newSec = newSecret.trim();
    const confirmNewSec = confirmNewSecret.trim();

    if (!currentSec) {
      showToast('Current admin secret is required', 'error');
      return;
    }
    if (!newSec) {
      showToast('New admin secret cannot be empty', 'error');
      return;
    }
    if (newSec !== confirmNewSec) {
      showToast('New secrets do not match', 'error');
      return;
    }

    setUpdatingKey(true);
    try {
      const res = await adminFetch('/dashboard/api/settings/admin-secret', {
        method: 'PUT',
        body: JSON.stringify({
          old_secret: currentSec,
          new_secret: newSec,
        }),
      });
      if (res.ok) {
        showToast('Admin secret updated successfully!');
        updateAdminKey(newSec);
        setShowChangeKeyModal(false);
        setCurrentSecret('');
        setNewSecret('');
        setConfirmNewSecret('');
      } else {
        const data = await res.json().catch(() => ({}));
        showToast(data.detail || 'Failed to update admin secret', 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Network error updating admin secret', 'error');
    } finally {
      setUpdatingKey(false);
    }
  };

  const handleClearLogs = async (e: React.FormEvent) => {
    e.preventDefault();
    const key = confirmAdminKey.trim();
    if (!key) {
      showToast('Admin key is required for confirmation.', 'error');
      return;
    }

    setClearing(true);
    try {
      // Direct fetch bypasses global 401 interceptor that resets authentication
      const res = await fetch('/dashboard/api/logs', {
        method: 'DELETE',
        headers: {
          'X-Admin-Key': encodeURIComponent(key),
        },
      });

      if (res.ok) {
        showToast('All logs have been cleared and usage stats reset!');
        setShowClearLogsModal(false);
        setConfirmAdminKey('');
      } else {
        const data = await res.json().catch(() => ({}));
        if (res.status === 401) {
          showToast('Incorrect admin key. Verification failed.', 'error');
        } else {
          showToast(data.detail || 'Failed to clear logs', 'error');
        }
      }
    } catch (err) {
      console.error(err);
      showToast('Network error clearing logs', 'error');
    } finally {
      setClearing(false);
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
        
        <div className="flex">
          <Button
            type="button"
            onClick={() => setShowChangeKeyModal(true)}
            className="bg-white text-black hover:bg-zinc-200 font-semibold px-6 py-2.5 rounded transition-all duration-200 shadow-md"
          >
            Change Admin Secret
          </Button>
        </div>
      </div>

      {/* Danger Zone */}
      <div className="glass-panel p-8 bg-[#18181b] border border-red-950/20 rounded-md shadow-xl max-w-2xl mt-8">
        <h2 className="font-heading text-lg font-semibold text-red-500 mb-2">Danger Zone</h2>
        <p className="text-zinc-400 text-sm mb-6">
          Permanently delete all request logs and reset key usage statistics. Virtual keys, model registries, and configurations will not be deleted.
        </p>
        
        <div className="flex">
          <Button
            type="button"
            onClick={() => setShowClearLogsModal(true)}
            className="bg-red-950/20 hover:bg-red-900/30 text-red-400 border border-red-500/25 font-semibold px-6 py-2.5 rounded transition-all duration-200 shadow-md"
          >
            Clear All Logs & Reset Stats
          </Button>
        </div>
      </div>

      {/* Confirm Clear Logs Dialog */}
      <Dialog open={showClearLogsModal} onOpenChange={setShowClearLogsModal}>
        <DialogContent className="max-w-[400px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">Confirm Log Deletion</DialogTitle>
            <DialogDescription className="text-zinc-400 text-sm mt-2">
              This action is permanent and cannot be undone. All request log history will be deleted, and all virtual key statistics (Total Cost, Tokens) will be reset.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleClearLogs} className="flex flex-col gap-4 my-4">
            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">Verify Admin Secret</label>
              <Input
                type="password"
                value={confirmAdminKey}
                onChange={(e) => setConfirmAdminKey(e.target.value)}
                placeholder="Enter admin key to confirm"
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
                required
              />
            </div>
            
            <DialogFooter className="mt-4 flex gap-3 justify-end">
              <Button
                type="button"
                variant="outline"
                disabled={clearing}
                onClick={() => {
                  setShowClearLogsModal(false);
                  setConfirmAdminKey('');
                }}
                className="border-zinc-800 text-white hover:bg-zinc-900 rounded font-medium"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={clearing}
                className="bg-red-600 hover:bg-red-700 text-white rounded font-medium border border-red-700/30 flex items-center justify-center min-w-[120px]"
              >
                {clearing ? 'Clearing...' : 'Confirm & Delete'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Change Admin Secret Dialog */}
      <Dialog open={showChangeKeyModal} onOpenChange={setShowChangeKeyModal}>
        <DialogContent className="max-w-[400px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">Change Admin Secret</DialogTitle>
            <DialogDescription className="text-zinc-400 text-sm mt-2">
              To change your admin secret, please enter your current secret, then enter the new secret twice to confirm.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleChangeAdminSecret} className="flex flex-col gap-4 my-4">
            <div className="flex flex-col gap-2">
              <label className="text-zinc-450 text-sm font-medium">Current Admin Secret</label>
              <Input
                type="password"
                value={currentSecret}
                onChange={(e) => setCurrentSecret(e.target.value)}
                placeholder="Enter current secret"
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
                required
              />
            </div>
            
            <div className="flex flex-col gap-2">
              <label className="text-zinc-450 text-sm font-medium">New Admin Secret</label>
              <Input
                type="password"
                value={newSecret}
                onChange={(e) => setNewSecret(e.target.value)}
                placeholder="Enter new secret"
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
                required
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-zinc-450 text-sm font-medium">Confirm New Admin Secret</label>
              <Input
                type="password"
                value={confirmNewSecret}
                onChange={(e) => setConfirmNewSecret(e.target.value)}
                placeholder="Re-enter new secret"
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
                required
              />
            </div>
            
            <DialogFooter className="mt-4 flex gap-3 justify-end">
              <Button
                type="button"
                variant="outline"
                disabled={updatingKey}
                onClick={() => {
                  setShowChangeKeyModal(false);
                  setCurrentSecret('');
                  setNewSecret('');
                  setConfirmNewSecret('');
                }}
                className="border-zinc-800 text-white hover:bg-zinc-900 rounded font-medium"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={updatingKey}
                className="bg-white text-black hover:bg-zinc-200 rounded font-medium flex items-center justify-center min-w-[120px]"
              >
                {updatingKey ? 'Updating...' : 'Change Secret'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}
