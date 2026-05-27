// services/router/dashboard/js/keys/clipboard.js

// --- Utility Operations ---
export async function copyToClipboard(text) {
    if (!text) return;
    try {
        await navigator.clipboard.writeText(text);
        alert('Copied to clipboard!');
    } catch (err) {
        console.error('Failed to copy: ', err);
        const textArea = document.createElement('textarea');
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            alert('Copied to clipboard!');
        } catch (e) {
            alert('Failed to copy to clipboard.');
        }
        document.body.removeChild(textArea);
    }
}
