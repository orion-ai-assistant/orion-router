// services/router/dashboard/js/app.js

import { adminFetch, getAdminKey, setAdminKey } from './api.js';
import * as keys from './keys.js';
import * as playground from './playground.js';

const { createApp } = window.Vue;

createApp({
    data() {
        return {
            // --- Navigation & UI state ---
            tabs: [
                { id: 'dashboard', label: 'Overview', icon: 'layout-dashboard' },
                { id: 'keys', label: 'Virtual Keys', icon: 'key' },
                { id: 'logs', label: 'Logs', icon: 'file-text' },
                { id: 'key-pool', label: 'Provider Keys', icon: 'lock' },
                { id: 'models', label: 'Models', icon: 'bot' },
                { id: 'groups', label: 'Groups', icon: 'network' },
                { id: 'playground', label: 'Playground', icon: 'terminal' },
                { id: 'model-info', label: 'Model Info', icon: 'info' }
            ],
            activeTab: 'dashboard',
            showLogin: false,
            adminKeyInput: '',
            loginError: '',
            showKeyModal: false,
            showEditKeyModal: false,
            editingVirtualKey: { id: '', name: '', budget: 0, is_active: true },
            rawKey: '',
            activeLogDetails: null,
            draggedIndex: null,
            draggedGroupId: null,

            // --- Toast Notifications ---
            toasts: [],
            
            // --- Global Confirm Dialog ---
            confirmDialog: {
                show: false,
                message: '',
                callback: null
            },


            // --- Modals & Editing ---
            showAddProviderKeyModal: false,
            showEditProviderKeyModal: false,
            editingProviderKey: { provider: '', label: '', api_key: '', priority: 100, is_active: true },
            showAddModelModal: false,
            showEditModelModal: false,
            editingModel: { name: '', provider: '', capability: 'chat', temperature: null, is_active: true },
            showAddGroupModal: false,
            showEditGroupModal: false,
            editingGroup: { name: '', capability: 'chat', is_active: true },
            showAddGroupItemModal: false,
            activeGroupForItems: null,
            editingGroupItem: { model_id: '', priority: 100 },

            // --- Data Lists ---
            stats: { total_cost: 0.0, total_tokens: 0, total_keys: 0 },
            virtualKeys: [],
            logs: [],
            keyPool: [],
            models: [],
            groups: [],
            modelFamilies: [],
            selectedFamily: null,
            loadedProviders: {},

            // --- Forms ---
            keyForm: { provider: '', label: '', api_key: '', priority: 100 },
            modelForm: { name: '', provider: '', capability: 'chat', temperature: null },
            groupForm: { name: '', description: '', capability: 'chat' },
            virtualKeyForm: { name: '', budget: 0 },

            // --- Playground state ---
            voices: [],
            voicesByProvider: {},
            playground: {
                tab: 'chat',
                chat: {
                    model: '',
                    temperature: '',
                    thinking: '',
                    messages: [],
                    input: ''
                },
                tts: {
                    model: '',
                    voice: 'alloy',
                    temperature: '',
                    input: '',
                    error: '',
                    url: ''
                },
                embed: {
                    model: '',
                    input: '',
                    error: '',
                    preview: '',
                    dim: '',
                    json: ''
                }
            }
        };
    },

    methods: {
        // --- API & Auth helper ---
        adminFetch,

        // --- Auth methods ---
        async init() {
            // Determine active tab from URL path
            const path = window.location.pathname;
            if (path.includes('/keys')) {
                this.activeTab = 'keys';
            } else if (path.includes('/logs')) {
                this.activeTab = 'logs';
            } else if (path.includes('/key-pool')) {
                this.activeTab = 'key-pool';
            } else if (path.includes('/models')) {
                this.activeTab = 'models';
            } else if (path.includes('/groups')) {
                this.activeTab = 'groups';
            } else if (path.includes('/playground')) {
                this.activeTab = 'playground';
            } else if (path.includes('/model-info')) {
                this.activeTab = 'model-info';
            } else {
                this.activeTab = 'dashboard';
            }

            const key = getAdminKey();
            if (!key) {
                this.showLogin = true;
            } else {
                await this.loadActiveTab();
            }
        },

        async login() {
            const key = this.adminKeyInput.trim();
            if (!key) return;
            this.loginError = '';

            try {
                setAdminKey(key);
                const res = await this.adminFetch('/admin/api/stats');
                if (res.ok) {
                    this.showLogin = false;
                    this.adminKeyInput = '';
                    await this.loadActiveTab();
                } else {
                    this.loginError = 'Invalid admin secret key';
                    setAdminKey('');
                }
            } catch (err) {
                this.loginError = 'Authentication failed';
                setAdminKey('');
            }
        },

        setTab(tabId) {
            this.activeTab = tabId;
            if (tabId === 'dashboard') {
                window.location.href = '/admin';
            } else {
                window.location.href = `/admin/${tabId}`;
            }
        },

        async loadActiveTab() {
            const tab = this.activeTab;
            try {
                if (Object.keys(this.loadedProviders).length === 0) {
                    await this.loadProviders();
                }

                if (tab === 'dashboard') {
                    await this.loadStats();
                } else if (tab === 'keys') {
                    await this.loadVirtualKeys();
                } else if (tab === 'logs') {
                    await this.loadLogs();
                } else if (tab === 'key-pool') {
                    await this.loadKeyPool();
                } else if (tab === 'models') {
                    await this.loadModels();
                } else if (tab === 'groups') {
                    await this.loadGroups();
                    await this.loadModels();
                } else if (tab === 'playground') {
                    await this.loadModels();
                    await this.loadGroups();
                    await this.loadVoices();
                    // Select default playground targets if not already set
                    if (!this.playground.chat.model) {
                        const options = this.routeOptions('chat');
                        if (options.length > 0) this.playground.chat.model = options[0].value;
                    }
                    if (!this.playground.tts.model) {
                        const options = this.routeOptions('tts');
                        if (options.length > 0) this.playground.tts.model = options[0].value;
                    }
                    if (!this.playground.embed.model) {
                        const options = this.routeOptions('embed');
                        if (options.length > 0) this.playground.embed.model = options[0].value;
                    }
                } else if (tab === 'model-info') {
                    await this.loadModelInfo();
                }
            } catch (err) {
                console.error(`Error loading active tab (${tab}):`, err);
            }
        },

        async loadProviders() {
            try {
                const res = await this.adminFetch('/admin/api/providers');
                if (res.ok) {
                    const data = await res.json();
                    this.loadedProviders = data.providers || {};
                    const pNames = this.providerNames();
                    if (pNames.length > 0) {
                        if (!this.keyForm.provider) this.keyForm.provider = pNames[0];
                        if (!this.modelForm.provider) this.modelForm.provider = pNames[0];
                    }
                }
            } catch (e) {
                console.error('Failed to load providers list:', e);
            }
        },

        async loadVoices() {
            try {
                const res = await this.adminFetch('/admin/api/voices');
                if (res.ok) {
                    const data = await res.json();
                    this.voicesByProvider = data.voices || {};
                    this.updatePlaygroundVoices();
                }
            } catch (e) {
                console.error('Failed to load voices list:', e);
            }
        },

        updatePlaygroundVoices() {
            const selectedModelName = this.playground.tts.model;
            if (!selectedModelName) {
                this.voices = [];
                return;
            }

            let provider = null;
            // Check if it's a group
            const group = this.groups.find(g => g.name === selectedModelName && g.capability === 'tts');
            if (group && group.items && group.items.length > 0) {
                // Get provider from the first item
                provider = group.items[0].provider;
            } else {
                // Get provider from models
                const model = this.models.find(m => m.name === selectedModelName && m.capability === 'tts');
                if (model) {
                    provider = model.provider;
                }
            }

            if (provider && this.voicesByProvider[provider]) {
                this.voices = this.voicesByProvider[provider];
            } else {
                // Fallback to all loaded voices if provider not resolved
                this.voices = Object.values(this.voicesByProvider).flat();
            }

            // If current selected voice is not in the new voices list, set it to the first voice in the list
            if (this.voices.length > 0 && !this.voices.includes(this.playground.tts.voice)) {
                this.playground.tts.voice = this.voices[0];
            }
        },

        // --- Spreading imported methods dynamically ---
        ...keys,
        ...playground,

        // --- Helpers & Formatters ---
        money(val, decimals = 4) {
            if (val === null || val === undefined) return '$0.0000';
            return '$' + parseFloat(val).toFixed(decimals);
        },

        number(val) {
            if (val === null || val === undefined) return '0';
            return parseInt(val).toLocaleString();
        },

        dateTime(str) {
            if (!str) return '';
            return new Date(str).toLocaleString();
        },

        providerNames() {
            return Object.keys(this.loadedProviders);
        },

        modelsByCapability(capability) {
            return this.models.filter(m => m.capability === capability && m.is_active);
        },

        routeOptions(capability) {
            const options = [];
            this.groups.forEach(g => {
                if (g.capability === capability && g.is_active) {
                    options.push({ value: g.name, label: `[Group] ${g.name}` });
                }
            });
            this.models.forEach(m => {
                if (m.capability === capability && m.is_active) {
                    options.push({ value: m.name, label: `${m.name} (${m.provider})` });
                }
            });
            return options;
        },

        escapeHtml(text) {
            if (!text) return '';
            return text
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        },

        normalizeTemperature(value) {
            if (value === '' || value === null || value === undefined) return null;
            const parsed = Number(value);
            return Number.isFinite(parsed) ? parsed : null;
        },

        isKeyDirty(key) {
            if (!key || !key._original) return false;
            const priority = Number.isFinite(Number(key.priority)) ? Number(key.priority) : 0;
            return (
                key.provider !== key._original.provider ||
                key.label !== key._original.label ||
                priority !== key._original.priority ||
                !!key.is_active !== key._original.is_active ||
                !!(key.api_key && key.api_key.trim())
            );
        },

        isModelDirty(model) {
            if (!model || !model._original) return false;
            return (
                model.name !== model._original.name ||
                model.provider !== model._original.provider ||
                model.capability !== model._original.capability ||
                this.normalizeTemperature(model.temperature) !== model._original.temperature ||
                !!model.is_active !== model._original.is_active
            );
        },

        isGroupDirty(group) {
            if (!group || !group._original) return false;
            return (
                group.name !== group._original.name ||
                group.description !== group._original.description ||
                group.capability !== group._original.capability ||
                !!group.is_active !== group._original.is_active
            );
        },

        isGroupItemDirty(item) {
            if (!item || !item._original) return false;
            const priority = Number.isFinite(Number(item.priority)) ? Number(item.priority) : 0;
            return priority !== item._original.priority;
        },

        openEditProviderKey(key) {
            this.editingProviderKey = JSON.parse(JSON.stringify(key));
            this.editingProviderKey.api_key = ''; // clear api key field for modal (blank keeps original)
            this.showEditProviderKeyModal = true;
        },
        openEditVirtualKey(key) {
            this.editingVirtualKey = JSON.parse(JSON.stringify(key));
            this.showEditKeyModal = true;
        },

        openEditModel(model) {
            this.editingModel = JSON.parse(JSON.stringify(model));
            this.showEditModelModal = true;
        },

        openEditGroup(group) {
            this.editingGroup = JSON.parse(JSON.stringify(group));
            this.showEditGroupModal = true;
        },
        openAddGroupItem(group) {
            this.activeGroupForItems = group;
            this.editingGroupItem = { model_id: '', priority: 100 };
            this.showAddGroupItemModal = true;
        },

        // --- Toast Methods ---
        showToast(message, type = 'success') {
            const id = Date.now() + Math.random().toString(36).substr(2, 9);
            this.toasts.push({ id, message, type });
            setTimeout(() => {
                this.removeToast(id);
            }, 3000);
        },
        removeToast(id) {
            this.toasts = this.toasts.filter(t => t.id !== id);
        },

        // --- Confirm Methods ---
        confirmAction(message, callback) {
            this.confirmDialog.message = message;
            this.confirmDialog.callback = callback;
            this.confirmDialog.show = true;
        },
        executeConfirm() {
            if (this.confirmDialog.callback) {
                this.confirmDialog.callback();
            }
            this.confirmDialog.show = false;
        },
        cancelConfirm() {
            this.confirmDialog.show = false;
        }
    },

    watch: {
        'playground.tts.model'(newModel) {
            this.updatePlaygroundVoices();
        }
    },

    mounted() {
        this.init();
        // Intercept all alerts and show as toasts
        window.alert = (msg) => {
            const type = (msg.toLowerCase().includes('error') || msg.toLowerCase().includes('fail')) ? 'error' : 'success';
            this.showToast(msg, type);
        };
    }
}).mount('#app');
