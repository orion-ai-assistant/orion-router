'use client';

import React from 'react';
import { Button } from '@/components/ui/button';
import { Copy, Check } from 'lucide-react';

interface PayloadViewerProps {
  label: string;
  displayHtml: string;
  fullText: string;
  copied: boolean;
  onCopy: () => void;
}

export const PayloadViewer = React.memo(function PayloadViewer({
  label,
  displayHtml,
  fullText,
  copied,
  onCopy,
}: PayloadViewerProps) {
  const isLoading = !displayHtml || displayHtml === 'Loading...';

  return (
    <div className="min-w-0 flex flex-col flex-1">
      <div className="flex justify-between items-center mb-2 shrink-0">
        <h3 className="text-zinc-300 font-semibold text-sm tracking-wide">{label}</h3>
        {fullText ? (
          <Button
            variant="outline"
            type="button"
            onClick={onCopy}
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800 hover:text-white text-xs px-2.5 py-1 h-auto flex items-center gap-1 rounded"
          >
            {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
            {copied ? 'Copied' : 'Copy Full'}
          </Button>
        ) : null}
      </div>
      <pre
        className="payload-viewer custom-scrollbar"
        aria-label={label}
      >
        {isLoading ? (
          'Loading...'
        ) : (
          <code dangerouslySetInnerHTML={{ __html: displayHtml }} />
        )}
      </pre>
    </div>
  );
});
