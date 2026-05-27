// services/router/dashboard/js/keys/logs.js

// --- Log Operations ---
export async function showLogDetails(logId) {
    this.activeLogDetails = {
        requestText: 'Loading...',
        responseText: 'Loading...',
        requestLines: [],
        responseLines: [],
        requestLoadedCount: 0,
        responseLoadedCount: 0,
        fullRequest: '',
        fullResponse: ''
    };
    try {
        const res = await this.adminFetch(`/admin/api/logs/${logId}`);
        if (res.ok) {
            const data = await res.json();

            let reqFull = '';
            let resFull = '';

            try {
                if (data.request_json) {
                    const parsed = JSON.parse(data.request_json);
                    reqFull = JSON.stringify(parsed, null, 2);
                }
            } catch (e) {
                reqFull = data.request_json || '';
            }

            try {
                if (data.response_json) {
                    const parsed = JSON.parse(data.response_json);
                    resFull = JSON.stringify(parsed, null, 2);
                }
            } catch (e) {
                resFull = data.response_json || '';
            }

            const reqLines = reqFull ? reqFull.split('\n') : ['Null'];
            const resLines = resFull ? resFull.split('\n') : ['Null'];
            const reqInitialCount = Math.min(200, reqLines.length);
            const resInitialCount = Math.min(200, resLines.length);

            this.activeLogDetails = {
                requestLines: reqLines,
                requestLoadedCount: reqInitialCount,
                requestText: reqLines.slice(0, reqInitialCount).join('\n'),

                responseLines: resLines,
                responseLoadedCount: resInitialCount,
                responseText: resLines.slice(0, resInitialCount).join('\n'),

                fullRequest: reqFull,
                fullResponse: resFull,
                capability: data.capability,
                responseData: data.response_json ? JSON.parse(data.response_json) : null
            };
        } else {
            alert('Failed to load log details');
            this.activeLogDetails = null;
        }
    } catch (err) {
        console.error(err);
        alert('Failed to load log details');
        this.activeLogDetails = null;
    }
}

export function handleJsonScroll(event, type) {
    if (!this.activeLogDetails) return;
    const el = event.target;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 100) {
        if (type === 'request') {
            if (this.activeLogDetails.requestLoadedCount < this.activeLogDetails.requestLines.length) {
                this.activeLogDetails.requestLoadedCount = Math.min(
                    this.activeLogDetails.requestLoadedCount + 200,
                    this.activeLogDetails.requestLines.length
                );
                this.activeLogDetails.requestText = this.activeLogDetails.requestLines
                    .slice(0, this.activeLogDetails.requestLoadedCount)
                    .join('\n');
            }
        } else if (type === 'response') {
            if (this.activeLogDetails.responseLoadedCount < this.activeLogDetails.responseLines.length) {
                this.activeLogDetails.responseLoadedCount = Math.min(
                    this.activeLogDetails.responseLoadedCount + 200,
                    this.activeLogDetails.responseLines.length
                );
                this.activeLogDetails.responseText = this.activeLogDetails.responseLines
                    .slice(0, this.activeLogDetails.responseLoadedCount)
                    .join('\n');
            }
        }
    }
}
