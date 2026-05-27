// services/router/dashboard/js/playground.js

export async function sendChat() {
    const text = this.playground.chat.input.trim();
    if (!text) return;

    const model = this.playground.chat.model;
    const temperature = this.playground.chat.temperature;
    const thinkingConfig = this.playground.chat.thinking.trim();

    const userMsg = {
        id: 'user-' + Date.now() + '-' + Math.random(),
        role: 'user',
        type: 'content',
        html: this.escapeHtml(text).replace(/\n/g, '<br>')
    };
    this.playground.chat.messages.push(userMsg);
    this.playground.chat.input = '';

    let thinkingMsg = null;
    let contentMsg = null;

    const payload = {
        model: model,
        messages: this.playground.chat.messages.map(m => ({
            role: m.role,
            content: m.html.replace(/<br>/g, '\n').replace(/🤔 /g, '')
        })),
        stream: true
    };

    if (temperature !== '' && temperature !== null && temperature !== undefined) {
        payload.temperature = parseFloat(temperature);
    }
    if (thinkingConfig && thinkingConfig.toLowerCase() !== 'none') {
        payload.thinking_level = thinkingConfig;
    }

    const adminKey = sessionStorage.getItem('adminKey') || '';

    try {
        const res = await fetch('/v1/chat/completions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${adminKey}`
            },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            const err = await res.text();
            this.playground.chat.messages.push({
                id: 'err-' + Date.now(),
                role: 'assistant',
                type: 'content',
                html: `Error: ${res.status} - ${err}`
            });
            return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = '';

        const handleDataLine = (line) => {
            const trimmed = line.trim();
            if (!trimmed.startsWith('data:')) return;

            const dataStr = trimmed.slice(5).trim();
            if (!dataStr || dataStr === '[DONE]') return;

            let data;
            try {
                data = JSON.parse(dataStr);
            } catch (e) {
                return;
            }

            if (data.error) {
                const errMsg = typeof data.error === 'string'
                    ? data.error
                    : (data.error.message || JSON.stringify(data.error));
                this.playground.chat.messages.push({
                    id: 'err-' + Date.now(),
                    role: 'assistant',
                    type: 'content',
                    html: `Error: ${errMsg}`
                });
                return;
            }

            const delta = (data.choices && data.choices[0] && data.choices[0].delta) || null;
            if (!delta) return;

            if (delta.reasoning_content) {
                if (!thinkingMsg) {
                    const uniqueId = 'think-' + Date.now() + '-' + Math.random();
                    const newMsg = {
                        id: uniqueId,
                        role: 'assistant',
                        type: 'thinking',
                        html: '🤔 '
                    };
                    this.playground.chat.messages.push(newMsg);
                    thinkingMsg = this.playground.chat.messages.find(m => m.id === uniqueId);
                }
                if (thinkingMsg) {
                    thinkingMsg.html += this.escapeHtml(delta.reasoning_content).replace(/\n/g, '<br>');
                }
            }

            if (delta.content) {
                if (!contentMsg) {
                    const uniqueId = 'content-' + Date.now() + '-' + Math.random();
                    const newMsg = {
                        id: uniqueId,
                        role: 'assistant',
                        type: 'content',
                        html: ''
                    };
                    this.playground.chat.messages.push(newMsg);
                    contentMsg = this.playground.chat.messages.find(m => m.id === uniqueId);
                }
                if (contentMsg) {
                    contentMsg.html += this.escapeHtml(delta.content).replace(/\n/g, '<br>');
                }
            }
        };

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split(/\r?\n/);
            buffer = lines.pop() || '';

            for (const line of lines) {
                handleDataLine(line);
            }

            this.$nextTick(() => {
                const msgArea = document.querySelector('.chat-messages');
                if (msgArea) msgArea.scrollTop = msgArea.scrollHeight;
            });
        }

        if (buffer.trim()) {
            handleDataLine(buffer);
        }

        this.$nextTick(() => {
            const msgArea = document.querySelector('.chat-messages');
            if (msgArea) msgArea.scrollTop = msgArea.scrollHeight;
        });
    } catch (e) {
        this.playground.chat.messages.push({
            id: 'err-' + Date.now(),
            role: 'assistant',
            type: 'content',
            html: 'Connection error: ' + e.message
        });
    }
}

export async function generateTTS() {
    const text = this.playground.tts.input.trim();
    const model = this.playground.tts.model;
    const voice = this.playground.tts.voice;
    const temperature = this.playground.tts.temperature;

    if (!text) {
        alert('Lütfen bir metin girin.');
        return;
    }

    this.playground.tts.error = '';
    this.playground.tts.url = '';

    const adminKey = sessionStorage.getItem('adminKey') || '';

    const payload = { model, input: text, voice };
    if (temperature !== '' && temperature !== null && temperature !== undefined) {
        payload.temperature = parseFloat(temperature);
    }

    try {
        const res = await fetch('/v1/audio/speech', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${adminKey}`
            },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || res.statusText);
        }

        const blob = await res.blob();
        this.playground.tts.url = URL.createObjectURL(blob);
    } catch (e) {
        this.playground.tts.error = '❌ Hata: ' + e.message;
    }
}

export async function generateEmbedding() {
    const text = this.playground.embed.input.trim();
    const model = this.playground.embed.model;

    if (!text) {
        alert('Lütfen bir metin girin.');
        return;
    }

    this.playground.embed.error = '';
    this.playground.embed.preview = '';
    this.playground.embed.dim = '';
    this.playground.embed.json = '';

    const adminKey = sessionStorage.getItem('adminKey') || '';

    try {
        const res = await fetch('/v1/embeddings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${adminKey}`
            },
            body: JSON.stringify({ model, input: text })
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || res.statusText);
        }

        const data = await res.json();
        const vector = data.data[0].embedding;
        const dim = vector.length;

        this.playground.embed.dim = `📐 Boyut: ${dim} | Model: ${data.model}`;

        const previewVec = vector.slice(0, 8).map(v => v.toFixed(6)).join(', ');
        this.playground.embed.preview = `[${previewVec}${dim > 8 ? ', ...' : ''}]`;

        const truncated = {
            ...data,
            data: [{
                ...data.data[0],
                embedding: vector.slice(0, 32).concat(['... (truncated)'])
            }]
        };
        this.playground.embed.json = JSON.stringify(truncated, null, 2);
    } catch (e) {
        this.playground.embed.error = '❌ Hata: ' + e.message;
    }
}
