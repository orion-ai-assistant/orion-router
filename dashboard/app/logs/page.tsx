'use client';

import React, { useState, useEffect } from 'react';
import { adminFetch } from '@/lib/api';
import { money, dateTime } from '@/lib/utils';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { RefreshCw, Copy, Check } from 'lucide-react';

interface LogItem {
  id: number;
  key_name: string | null;
  provider: string;
  requested_model: string;
  tokens_used: number;
  prompt_tokens: number;
  completion_tokens: number;
  thoughts_tokens: number;
  cost: number | null;
  success: boolean;
  capability: string;
  created_at: string;
}

interface LogDetails {
  requestText: string;
  responseText: string;
  fullRequest: string;
  fullResponse: string;
  capability: string;
  responseData: any;
}

function sanitizeForDisplay(obj: any): any {
  if (obj === null || obj === undefined) return obj;
  if (Array.isArray(obj)) {
    return obj.map(sanitizeForDisplay);
  }
  if (typeof obj === 'object') {
    const result: any = {};
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

export default function LogsPage() {
  const { showToast } = useApp();
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [activeLogDetails, setActiveLogDetails] = useState<LogDetails | null>(null);
  
  // Copies tracking
  const [copiedReq, setCopiedReq] = useState(false);
  const [copiedRes, setCopiedRes] = useState(false);

  const loadLogs = async () => {
    setLoading(true);
    try {
      const res = await adminFetch('/dashboard/api/logs');
      if (res.ok) {
        const data = await res.json();
        setLogs(data.logs || []);
      }
    } catch (err) {
      console.error('Failed to load logs:', err);
      showToast('Failed to load logs', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
    
    const handleAuth = () => {
      loadLogs();
    };
    window.addEventListener('orion-authenticated', handleAuth);
    return () => {
      window.removeEventListener('orion-authenticated', handleAuth);
    };
  }, []);

  const handleShowDetails = async (logId: number) => {
    setActiveLogDetails({
      requestText: 'Loading...',
      responseText: 'Loading...',
      fullRequest: '',
      fullResponse: '',
      capability: 'chat',
      responseData: null
    });
    
    try {
      const res = await adminFetch(`/dashboard/api/logs/${logId}`);
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

        const limitText = (fullText: string) => {
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
            text += '\n\n... [Content too long and was truncated. Use "Copy Full" to get complete JSON] ...';
          }
          
          return text;
        };

        setActiveLogDetails({
          requestText: limitText(reqFullDisplay),
          responseText: limitText(resFullDisplay),
          fullRequest: reqFullActual,
          fullResponse: resFullActual,
          capability: data.capability,
          responseData: responseDataParsed
        });
      } else {
        showToast('Failed to load log details', 'error');
        setActiveLogDetails(null);
      }
    } catch (err) {
      console.error(err);
      showToast('Failed to load log details', 'error');
      setActiveLogDetails(null);
    }
  };

  const copyText = (text: string, isReq: boolean) => {
    navigator.clipboard.writeText(text);
    showToast('Payload copied to clipboard!');
    if (isReq) {
      setCopiedReq(true);
      setTimeout(() => setCopiedReq(false), 2000);
    } else {
      setCopiedRes(true);
      setTimeout(() => setCopiedRes(false), 2000);
    }
  };

  return (
    <section id="logs" className="tab-content active block pt-8">
      <header className="flex justify-between items-end mb-8 pb-6 border-b border-border">
        <div className="header-titles">
          <h1 className="font-heading text-3xl font-semibold tracking-tight">Request Logs</h1>
          <p className="text-zinc-400 text-sm mt-1">Recent routed calls</p>
        </div>
        <Button
          onClick={loadLogs}
          className="bg-transparent border border-zinc-800 text-white hover:bg-zinc-800 font-medium px-5 py-2.5 rounded-md transition-all flex items-center gap-1.5"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </Button>
      </header>

      {/* Table List */}
      <div className="table-container glass-panel bg-[#18181b] border border-zinc-800 rounded-md overflow-hidden shadow-xl">
        <Table>
          <TableHeader className="bg-black/25">
            <TableRow className="border-b border-zinc-850 hover:bg-transparent">
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 pl-6 w-[80px]">Key</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 w-[260px]">Model</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 w-[100px]">Provider</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 w-[90px]">Capability</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-center w-[150px]">Tokens</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-center w-[80px]">Cost</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-center w-[80px]">Status</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-center w-[130px]">Time</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-right pr-6 w-[70px]">Details</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading && logs.length === 0 ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={9} className="text-center text-zinc-400 py-8">
                  Loading request logs...
                </TableCell>
              </TableRow>
            ) : logs.length === 0 ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={9} className="text-center text-zinc-400 py-8">
                  No request logs found.
                </TableCell>
              </TableRow>
            ) : (
              logs.map((log) => (
                <TableRow key={log.id} className="border-b border-zinc-900 hover:bg-white/[0.015] transition-colors">
                  <TableCell className="font-medium text-sm py-4 pl-6 text-zinc-300">
                    {log.key_name || 'Admin'}
                  </TableCell>
                  <TableCell className="py-4 font-mono text-xs text-white max-w-[260px] truncate">
                    {log.requested_model}
                  </TableCell>
                  <TableCell className="py-4">
                    <Badge className="bg-blue-500/10 text-blue-300 border border-blue-500/20 text-[10px] font-medium tracking-wide rounded uppercase px-2 py-0.5 capitalize">
                      {log.provider}
                    </Badge>
                  </TableCell>
                  <TableCell className="py-4">
                    <Badge className="bg-zinc-800 text-zinc-300 border border-zinc-700/50 text-[10px] tracking-wide rounded uppercase px-2 py-0.5">
                      {log.capability || 'chat'}
                    </Badge>
                  </TableCell>
                  <TableCell className="py-4 text-center">
                    <div className="pricing-container flex items-center justify-center gap-4">
                      <div className="pricing-item relative flex flex-col items-center py-1">
                        <span className="pricing-label text-[8px] font-semibold text-zinc-500 uppercase tracking-wider scale-90 mb-0.5">in</span>
                        <span className="pricing-value text-xs font-mono">{log.prompt_tokens || 0}</span>
                      </div>
                      
                      {log.capability !== 'embed' && (
                        <div className="pricing-item relative flex flex-col items-center py-1">
                          <span className="pricing-label text-[8px] font-semibold text-zinc-500 uppercase tracking-wider scale-90 mb-0.5">out</span>
                          <span className="pricing-value text-xs font-mono">{log.completion_tokens || 0}</span>
                        </div>
                      )}

                      {log.capability === 'embed' && (
                        <div className="pricing-item relative flex flex-col items-center py-1">
                          <span className="pricing-label text-[8px] font-semibold text-zinc-500 uppercase tracking-wider scale-90 mb-0.5">dim</span>
                          <span className="pricing-value text-xs font-mono">{log.completion_tokens || 0}</span>
                        </div>
                      )}

                      {log.capability !== 'tts' && log.capability !== 'embed' && (
                        <div className="pricing-item relative flex flex-col items-center py-1">
                          <span className="pricing-label text-[8px] font-semibold text-zinc-500 uppercase tracking-wider scale-90 mb-0.5">think</span>
                          <span className="pricing-value text-xs font-mono">{log.thoughts_tokens || 0}</span>
                        </div>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="py-4 text-center font-mono text-xs">
                    {log.cost === null || log.cost === undefined
                      ? '-'
                      : Number(log.cost) === 0
                      ? '$0.00'
                      : money(log.cost, 6)}
                  </TableCell>
                  <TableCell className="py-4 text-center">
                    <Badge
                      className={`text-[10px] font-semibold tracking-wide uppercase px-2 py-0.5 rounded-full ${
                        log.success
                          ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                          : 'bg-red-500/10 text-red-500 border border-red-500/20'
                      }`}
                    >
                      {log.success ? 'Success' : 'Failed'}
                    </Badge>
                  </TableCell>
                  <TableCell className="py-4 text-center font-mono text-xs text-zinc-400">
                    {dateTime(log.created_at)}
                  </TableCell>
                  <TableCell className="py-4 text-right pr-6">
                    <Button
                      variant="outline"
                      onClick={() => handleShowDetails(log.id)}
                      className="border-zinc-800 text-white hover:bg-zinc-800 text-xs px-3 py-1 h-auto rounded"
                    >
                      View
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Payloads Modal */}
      <Dialog open={!!activeLogDetails} onOpenChange={(open) => !open && setActiveLogDetails(null)}>
        <DialogContent className="max-w-[950px] w-[95%] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl overflow-y-auto max-h-[90vh]">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">Request & Response Payloads</DialogTitle>
          </DialogHeader>

          {/* Audio Player for TTS */}
          {activeLogDetails && activeLogDetails.capability === 'tts' && activeLogDetails.responseData?.audio_base64 && (
            <div className="my-4 p-4 bg-white/5 border border-white/10 rounded-lg flex items-center justify-between gap-4">
              <span className="font-semibold text-purple-400 flex items-center gap-2 text-sm">
                🔊 Generated Audio Output:
              </span>
              <audio
                controls
                className="flex-grow max-w-[600px] h-10"
                src={`data:${activeLogDetails.responseData.content_type || 'audio/wav'};base64,${activeLogDetails.responseData.audio_base64}`}
              />
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 my-4 text-left">
            {/* Request Payload */}
            <div className="min-w-0 flex flex-col">
              <div className="flex justify-between items-center mb-2">
                <h3 className="text-purple-400 font-semibold text-sm">Request JSON</h3>
                {activeLogDetails?.fullRequest && (
                  <Button
                    variant="outline"
                    onClick={() => copyText(activeLogDetails.fullRequest, true)}
                    className="border-zinc-800 hover:bg-zinc-800 text-xs px-2.5 py-1 h-auto flex items-center gap-1 rounded"
                  >
                    {copiedReq ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                    {copiedReq ? 'Copied' : 'Copy Full'}
                  </Button>
                )}
              </div>
              <pre className="custom-scrollbar bg-black/40 border border-zinc-850 p-4 rounded-lg font-mono text-xs overflow-auto h-[350px] text-zinc-300 whitespace-pre-wrap break-all">
                {activeLogDetails ? activeLogDetails.requestText : 'Loading...'}
              </pre>
            </div>

            {/* Response Payload */}
            <div className="min-w-0 flex flex-col">
              <div className="flex justify-between items-center mb-2">
                <h3 className="text-purple-400 font-semibold text-sm">Response JSON</h3>
                {activeLogDetails?.fullResponse && (
                  <Button
                    variant="outline"
                    onClick={() => copyText(activeLogDetails.fullResponse, false)}
                    className="border-zinc-800 hover:bg-zinc-800 text-xs px-2.5 py-1 h-auto flex items-center gap-1 rounded"
                  >
                    {copiedRes ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                    {copiedRes ? 'Copied' : 'Copy Full'}
                  </Button>
                )}
              </div>
              <pre className="custom-scrollbar bg-black/40 border border-zinc-850 p-4 rounded-lg font-mono text-xs overflow-auto h-[350px] text-zinc-300 whitespace-pre-wrap break-all">
                {activeLogDetails ? activeLogDetails.responseText : 'Loading...'}
              </pre>
            </div>
          </div>

          <DialogFooter className="mt-4">
            <Button
              onClick={() => setActiveLogDetails(null)}
              className="w-full bg-white text-black hover:bg-zinc-200 font-medium py-3 rounded-md transition-all shadow-lg"
            >
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
