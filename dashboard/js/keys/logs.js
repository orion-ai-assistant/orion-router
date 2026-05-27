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
                    const parsedReq = typeof data.request_json === 'string' ? JSON.parse(data.request_json) : data.request_json;
                    reqFull = JSON.stringify(parsedReq, null, 2);
                }
            } catch (e) {
                reqFull = typeof data.request_json === 'string' ? data.request_json : JSON.stringify(data.request_json) || '';
            }

            try {
                if (data.response_json) {
                    const parsedRes = typeof data.response_json === 'string' ? JSON.parse(data.response_json) : data.response_json;
                    resFull = JSON.stringify(parsedRes, null, 2);
                }
            } catch (e) {
                resFull = typeof data.response_json === 'string' ? data.response_json : JSON.stringify(data.response_json) || '';
            }

            let responseDataParsed = null;
            try {
                if (data.response_json) {
                    responseDataParsed = typeof data.response_json === 'string' ? JSON.parse(data.response_json) : data.response_json;
                }
            } catch (e) {
                console.error("Failed to parse response_json for responseData:", e);
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
                responseData: responseDataParsed
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
