'use client';

import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export type DateRangeValue = { start: string; end: string; range: string };

export function DateRangeFilter({ value, onChange }: { value: DateRangeValue; onChange: (next: DateRangeValue) => void }) {
  const { t } = useApp();
  function preset(days: number, range: string) {
    if (!days) { onChange({ start: '', end: '', range }); return; }
    const last = new Date(), first = new Date(); first.setDate(first.getDate() - days + 1);
    const date = (day: Date) => `${day.getFullYear()}-${String(day.getMonth()+1).padStart(2,'0')}-${String(day.getDate()).padStart(2,'0')}`;
    onChange({ start: date(first), end: date(last), range });
  }
  return <div className="space-y-3">
    <p className="text-xs text-zinc-400">{t('access.localDates')}</p>
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex flex-wrap gap-1">{[[1,'day'],[7,'week'],[30,'month'],[0,'all']].map(([days,range]) => <Button key={range} type="button" size="sm" variant={value.range===range?'secondary':'ghost'} aria-pressed={value.range===range} onClick={() => preset(Number(days),String(range))}>{t('access.range.'+range)}</Button>)}</div>
      <label className="flex items-center gap-2 text-xs text-zinc-400">{t('access.startShort')}<Input aria-label={t('access.start')} className="h-8 w-36 [color-scheme:dark]" type="date" value={value.start} onChange={event => onChange({ ...value, range: 'custom', start: event.target.value })} /></label>
      <label className="flex items-center gap-2 text-xs text-zinc-400">{t('access.endShort')}<Input aria-label={t('access.end')} className="h-8 w-36 [color-scheme:dark]" type="date" value={value.end} onChange={event => onChange({ ...value, range: 'custom', end: event.target.value })} /></label>
    </div>
  </div>;
}
