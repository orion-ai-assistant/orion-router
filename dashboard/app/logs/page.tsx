'use client';

import React, { useState, useEffect } from 'react';
import { adminFetch } from '@/lib/api';
import { money, dateTime } from '@/lib/utils';
import { formatPayloadForDisplay, extractTtsAudio } from '@/lib/format-payload';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { PayloadViewer } from '@/components/PayloadViewer';
import { RefreshCw } from 'lucide-react';

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
  success: boolean | null;
  capability: string;
  created_at: string;
}

interface LogDetails {
  requestHtml: string;
  responseHtml: string;
  fullRequest: string;
  fullResponse: string;
  capability: string;
  ttsAudio: { audio_base64: string; content_type?: string } | null;
}

export default function LogsPage() {
  const { showToast, t } = useApp();
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [payloadDialogOpen, setPayloadDialogOpen] = useState(false);
  const [activeLogDetails, setActiveLogDetails] = useState<LogDetails | null>(null);

  // Copies tracking
  const [copiedReq, setCopiedReq] = useState(false);
  const [copiedRes, setCopiedRes] = useState(false);

  const fetchLogs = async (mode: 'initial' | 'poll' | 'refresh') => {
    if (mode === 'initial') {
      setLoading(true);
    }
    try {
      const res = await adminFetch('/dashboard/api/logs');
      if (res.ok) {
        const data = await res.json();
        const incoming: LogItem[] = data.logs || [];
        if (mode === 'poll') {
          setLogs((prev) => {
            const ids = new Set(prev.map((l) => l.id));
            const fresh = incoming.filter((l) => !ids.has(l.id));
            if (fresh.length === 0) return prev;
            return [...fresh, ...prev];
          });
        } else {
          setLogs(incoming);
        }
      }
    } catch (err) {
      console.error('Failed to load logs:', err);
      if (mode !== 'poll') {
        showToast('Failed to load logs', 'error');
      }
    } finally {
      if (mode === 'initial') {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    fetchLogs('initial');

    const pollId = window.setInterval(() => {
      fetchLogs('poll');
    }, 5000);

    const handleAuth = () => {
      fetchLogs('refresh');
    };
    window.addEventListener('orion-authenticated', handleAuth);
    return () => {
      window.clearInterval(pollId);
      window.removeEventListener('orion-authenticated', handleAuth);
    };
  }, []);

  const handleShowDetails = async (logId: number) => {
    setPayloadDialogOpen(true);
    setActiveLogDetails({
      requestHtml: '',
      responseHtml: '',
      fullRequest: '',
      fullResponse: '',
      capability: 'chat',
      ttsAudio: null,
    });

    try {
      const res = await adminFetch(`/dashboard/api/logs/${logId}`);
      if (res.ok) {
        const data = await res.json();
        const request = formatPayloadForDisplay(data.request_json);
        const response = formatPayloadForDisplay(data.response_json);
        const capability = data.capability || 'chat';
        const ttsAudio =
          capability === 'tts' ? extractTtsAudio(data.response_json) : null;

        setActiveLogDetails({
          requestHtml: request.displayHtml,
          responseHtml: response.displayHtml,
          fullRequest: request.fullText,
          fullResponse: response.fullText,
          capability,
          ttsAudio,
        });
      } else {
        showToast('Failed to load log details', 'error');
        setPayloadDialogOpen(false);
        setActiveLogDetails(null);
      }
    } catch (err) {
      console.error(err);
      showToast('Failed to load log details', 'error');
      setPayloadDialogOpen(false);
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
          <h1 className="font-heading text-3xl font-semibold tracking-tight">{t('logs.title')}</h1>
          <p className="text-zinc-400 text-sm mt-1">{t('logs.description')}</p>
        </div>
        <Button
          onClick={() => fetchLogs('refresh')}
          className="bg-transparent border border-zinc-800 text-white hover:bg-zinc-800 font-medium px-5 py-2.5 rounded-md transition-all flex items-center gap-1.5"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> {t('logs.refresh')}
        </Button>
      </header>

      {/* Table List */}
      <div className="table-container glass-panel bg-[#18181b] border border-zinc-800 rounded-md overflow-hidden shadow-xl">
        <Table>
          <TableHeader className="bg-black/25">
            <TableRow className="border-b border-zinc-850 hover:bg-transparent">
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 pl-6 w-[80px]">{t('keys.table.key')}</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 pl-16 w-[180px]">{t('logs.table.model')}</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 pl-8 w-[120px]">{t('logs.table.provider')}</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 pl-8 w-[110px]">{t('logs.table.capability')}</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-center w-[150px]">{t('logs.table.tokens')}</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-center w-[90px]">{t('logs.table.cost')}</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-center w-[110px]">{t('logs.table.status')}</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-center w-[140px]">{t('logs.table.time')}</TableHead>
              <TableHead className="text-zinc-400 font-semibold text-xs tracking-wider uppercase py-4 text-right pr-6 w-[80px]">{t('logs.table.details')}</TableHead>
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
                  <TableCell className="py-4 pl-16 font-mono text-xs text-white max-w-[180px] truncate">
                    {log.requested_model}
                  </TableCell>
                  <TableCell className="py-4 pl-8">
                    <Badge className="bg-blue-500/10 text-blue-300 border border-blue-500/20 text-[10px] font-medium tracking-wide rounded uppercase px-2 py-0.5 capitalize">
                      {log.provider}
                    </Badge>
                  </TableCell>
                  <TableCell className="py-4 pl-8">
                    <Badge className="bg-zinc-800 text-zinc-300 border border-zinc-700/50 text-[10px] tracking-wide rounded uppercase px-2 py-0.5">
                      {log.capability || 'chat'}
                    </Badge>
                  </TableCell>
                  <TableCell className="py-4 text-center">
                    <div className="pricing-container flex items-center justify-center gap-4">
                      <div className="pricing-item relative flex flex-col items-center py-1">
                        <span className="pricing-label text-[8px] font-semibold text-zinc-500 uppercase tracking-wider scale-90 mb-0.5">in</span>
                        <span className="pricing-value text-xs font-mono">{log.prompt_tokens ?? '-'}</span>
                      </div>

                      {log.capability !== 'embed' && (
                        <div className="pricing-item relative flex flex-col items-center py-1">
                          <span className="pricing-label text-[8px] font-semibold text-zinc-500 uppercase tracking-wider scale-90 mb-0.5">out</span>
                          <span className="pricing-value text-xs font-mono">{log.completion_tokens ?? '-'}</span>
                        </div>
                      )}

                      {log.capability === 'embed' && (
                        <div className="pricing-item relative flex flex-col items-center py-1">
                          <span className="pricing-label text-[8px] font-semibold text-zinc-500 uppercase tracking-wider scale-90 mb-0.5">dim</span>
                          <span className="pricing-value text-xs font-mono">{log.completion_tokens ?? '-'}</span>
                        </div>
                      )}

                      {log.capability !== 'tts' && log.capability !== 'embed' && (
                        <div className="pricing-item relative flex flex-col items-center py-1">
                          <span className="pricing-label text-[8px] font-semibold text-zinc-500 uppercase tracking-wider scale-90 mb-0.5">think</span>
                          <span className="pricing-value text-xs font-mono">{log.thoughts_tokens ?? '-'}</span>
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
                        log.success === true
                          ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                          : log.success === false
                          ? 'bg-red-500/10 text-red-500 border border-red-500/20'
                          : 'bg-amber-500/10 text-amber-500 border border-amber-500/20'
                        }`}
                    >
                      {log.success === true ? 'Success' : log.success === false ? 'Failed' : 'Interrupted'}
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
                      {t('logs.table.view')}
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Payloads Modal */}
      <Dialog
        open={payloadDialogOpen}
        onOpenChange={setPayloadDialogOpen}
        onOpenChangeComplete={(open) => {
          if (!open) setActiveLogDetails(null);
        }}
      >
        <DialogContent className="w-[min(96vw,1720px)] max-w-[min(96vw,1720px)] border border-zinc-800 bg-[#18181b] p-6 sm:p-8 rounded-2xl text-white shadow-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">{t('logs.payloadModalTitle')}</DialogTitle>
          </DialogHeader>

          {activeLogDetails?.ttsAudio && (
            <div className="my-4 p-4 bg-zinc-800/40 border border-zinc-700 rounded-lg flex flex-col sm:flex-row sm:items-center gap-3">
              <span className="font-medium text-zinc-300 text-sm shrink-0">Audio output</span>
              <audio
                controls
                className="w-full sm:max-w-[600px] h-10"
                src={`data:${activeLogDetails.ttsAudio.content_type || 'audio/wav'};base64,${activeLogDetails.ttsAudio.audio_base64}`}
              />
            </div>
          )}

          {activeLogDetails && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 lg:gap-6 my-4 text-left min-h-0">
              <PayloadViewer
                label="Request JSON"
                displayHtml={activeLogDetails.requestHtml || 'Loading...'}
                fullText={activeLogDetails.fullRequest}
                copied={copiedReq}
                onCopy={() => copyText(activeLogDetails.fullRequest, true)}
              />
              <PayloadViewer
                label="Response JSON"
                displayHtml={activeLogDetails.responseHtml || 'Loading...'}
                fullText={activeLogDetails.fullResponse}
                copied={copiedRes}
                onCopy={() => copyText(activeLogDetails.fullResponse, false)}
              />
            </div>
          )}

          <DialogFooter className="mt-2">
            <Button
              onClick={() => setPayloadDialogOpen(false)}
              className="w-full border border-zinc-700 bg-zinc-800 text-white hover:bg-zinc-700 font-medium py-3 rounded-md transition-all"
            >
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
