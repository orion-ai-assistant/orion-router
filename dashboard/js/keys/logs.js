function sanitizeForDisplay(obj) {
    if (obj === null || obj === undefined) return obj;
    if (Array.isArray(obj)) {
        return obj.map(sanitizeForDisplay);
    }
    if (typeof obj === 'object') {
        const result = {};
        for (const key in obj) {
            if (Object.prototype.hasOwnProperty.call(obj, key)) {
                const val = obj[key];
                if (typeof val === 'string' && val.length > 200 && (
                    key === 'audio_base64' || 
                    key === 'b64_json' || 
                    key === 'audio' || 
                    key.endsWith('_base64') || 
                    val.startsWith('data:image/') || 
                    val.startsWith('data:audio/')
                )) {
                    result[key] = val.substring(0, 50) + `... [truncated base64, length: ${val.length}]`;
                } else {
                    result[key] = sanitizeForDisplay(val);
                }
            }
        }
        return result;
    }
    return obj;
}

// --- Log Operations ---
export async function showLogDetails(logId) {
    this.activeLogDetails = {
        requestText: 'Loading...',
        responseText: 'Loading...',
        fullRequest: '',
        fullResponse: ''
    };
    try {
        const res = await this.adminFetch(`/admin/api/logs/${logId}`);
        if (res.ok) {
            const data = await res.json();

            let reqFullDisplay = '';
            let resFullDisplay = '';
            let reqFullActual = '';
            let resFullActual = '';

            try {
                if (data.request_json) {
                    const parsedReq = typeof data.request_json === 'string' ? JSON.parse(data.request_json) : data.request_json;
                    reqFullActual = JSON.stringify(parsedReq, null, 2);
                    const displayReq = sanitizeForDisplay(parsedReq);
                    reqFullDisplay = JSON.stringify(displayReq, null, 2);
                }
            } catch (e) {
                reqFullActual = typeof data.request_json === 'string' ? data.request_json : JSON.stringify(data.request_json) || '';
                reqFullDisplay = reqFullActual;
            }

            try {
                if (data.response_json) {
                    const parsedRes = typeof data.response_json === 'string' ? JSON.parse(data.response_json) : data.response_json;
                    resFullActual = JSON.stringify(parsedRes, null, 2);
                    const displayRes = sanitizeForDisplay(parsedRes);
                    resFullDisplay = JSON.stringify(displayRes, null, 2);
                }
            } catch (e) {
                resFullActual = typeof data.response_json === 'string' ? data.response_json : JSON.stringify(data.response_json) || '';
                resFullDisplay = resFullActual;
            }

            let responseDataParsed = null;
            try {
                if (data.response_json) {
                    responseDataParsed = typeof data.response_json === 'string' ? JSON.parse(data.response_json) : data.response_json;
                }
            } catch (e) {
                console.error("Failed to parse response_json for responseData:", e);
            }

            const limitText = (fullText) => {
                if (!fullText) return 'Null';
                const lines = fullText.split('\n');
                let isTruncated = false;
                let text = fullText;
                
                if (lines.length > 500) {
                    text = lines.slice(0, 500).join('\n');
                    isTruncated = true;
                }
                
                if (text.length > 50000) {
                    text = text.substring(0, 50000);
                    isTruncated = true;
                }
                
                if (isTruncated) {
                    text += '\n\n... [İçerik çok uzun olduğu için kısaltıldı. Tamamını görmek için "Copy Full" butonunu kullanın] ...';
                }
                
                return text;
            };

            this.activeLogDetails = {
                requestText: limitText(reqFullDisplay),
                responseText: limitText(resFullDisplay),
                fullRequest: reqFullActual,
                fullResponse: resFullActual,
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

