'use client';

import {useState} from 'react';
import {useApp} from '@/components/AppContext';
import {Button} from '@/components/ui/button';
import {dailyRequests, UsageBucket} from '@/lib/usage';

const palette: Record<string,string> = {chat:'#c084fc',tts:'#60a5fa',stt:'#34d399',embed:'#fbbf24'};
export function DailyRequestsChart({rows,names}: {rows:UsageBucket[];names:Record<string,string>}) {
  const {t,locale}=useApp();
  const [hidden,setHidden]=useState<string[]>([]);
  const days=dailyRequests(rows);
  const types=[...new Set(rows.map(row=>row.capability))].sort();
  const visible=types.filter(type=>!hidden.includes(type));
  const max=Math.max(1,...days.flatMap(day=>visible.map(type=>day.counts[type] ?? 0)));
  const step=Math.max(1,Math.ceil(max/4));
  const ceiling=step*4;
  const width=Math.max(480,days.length*76+72),height=280,left=48,top=16,bottom=228;
  const groupWidth=(width-left-16)/Math.max(1,days.length);
  const barWidth=Math.min(24,groupWidth*.7/Math.max(1,visible.length));
  const number=(n:number)=>n.toLocaleString(locale);
  const color=(type:string)=>palette[type] || '#94a3b8';
  return <section className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4">
    <h4 className="mb-5 font-medium">{t('access.daily')}</h4>
    <div className="flex flex-col gap-5 lg:flex-row">
      <div className="min-w-0 flex-1 overflow-x-auto">
        {visible.length ? <svg role="img" aria-label={t('access.daily')} viewBox={`0 0 ${width} ${height}`} style={{minWidth:Math.max(300,days.length*76+72)}} className="h-72 w-full">
          {[0,1,2,3,4].map(i=>{const y=bottom-i*(bottom-top)/4;return <g key={i}>
            <line x1={left} x2={width-16} y1={y} y2={y} stroke="#27272a" strokeDasharray={i?'4 4':undefined}/>
            <text x={left-10} y={y+4} textAnchor="end" fill="#71717a" fontSize="11">{number(i*step)}</text>
          </g>;})}
          {days.map((day,index)=>{
            const center=left+groupWidth*(index+.5);
            return <g key={day.day}>
              {visible.map((type,i)=>{const count=day.counts[type] ?? 0,h=count/ceiling*(bottom-top);return <rect key={type} x={center-visible.length*barWidth/2+i*barWidth+1} y={bottom-h} width={Math.max(2,barWidth-2)} height={h} rx={3} fill={color(type)}>
                <title>{new Date(`${day.day}T12:00:00`).toLocaleDateString(locale)} · {names[type] || type}: {number(count)} {t('access.requests')}</title>
              </rect>;})}
              <text x={center} y={bottom+24} textAnchor="middle" fill="#a1a1aa" fontSize="11">{new Date(`${day.day}T12:00:00`).toLocaleDateString(locale,{day:'2-digit',month:'2-digit'})}</text>
              <text x={center} y={bottom+40} textAnchor="middle" fill="#52525b" fontSize="10">{day.day.slice(0,4)}</text>
            </g>;
          })}
        </svg>:<p className="flex h-72 items-center justify-center text-zinc-500">{t('access.chooseSeries')}</p>}
      </div>
      <div className="flex shrink-0 flex-wrap items-start gap-2 lg:w-52 lg:flex-col" aria-label={t('access.chartTypes')}>
        <p className="w-full pb-1 text-xs text-zinc-500">{t('access.chartTypes')}</p>
        {types.map(type=><Button key={type} type="button" variant="ghost" aria-pressed={!hidden.includes(type)} onClick={()=>setHidden(previous=>previous.includes(type)?previous.filter(x=>x!==type):[...previous,type])} className={`h-auto justify-start gap-2 rounded-lg border p-3 text-xs lg:w-full ${hidden.includes(type)?'border-transparent text-zinc-600':'border-zinc-800 bg-zinc-900 text-zinc-200'}`}>
          <span className="size-2.5 shrink-0 rounded-sm" style={{backgroundColor:color(type),opacity:hidden.includes(type)?.3:1}}/>{names[type] || type}
        </Button>)}
      </div>
    </div>
    <table className="sr-only"><caption>{t('access.daily')}</caption><thead><tr><th>{t('access.date')}</th>{visible.map(type=><th key={type}>{names[type] || type}</th>)}</tr></thead><tbody>{days.map(day=><tr key={day.day}><th>{day.day}</th>{visible.map(type=><td key={type}>{day.counts[type] ?? 0}</td>)}</tr>)}</tbody></table>
  </section>;
}
