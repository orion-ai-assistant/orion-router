'use client';
import {useEffect, useRef, useState, SyntheticEvent} from 'react';
import {createPortal} from 'react-dom';
import {useApp} from '@/components/AppContext';
import {Button} from '@/components/ui/button';
import {dailyRequests, UsageBucket} from '@/lib/usage';
const palette: Record<string,string> = {chat:'#c084fc',tts:'#60a5fa',stt:'#34d399',embed:'#fbbf24'};
export function DailyRequestsChart({rows,names}: {rows:UsageBucket[];names:Record<string,string>}) {
  const {t,locale}=useApp();
  const [hidden,setHidden]=useState<string[]>([]);
  const [tip,setTip]=useState<{day:string;type:string;count:number;x:number;y:number}|null>(null);
  const scroller=useRef<HTMLDivElement>(null);
  const [plotWidth,setPlotWidth]=useState(400);
  const days=dailyRequests(rows),types=[...new Set(rows.map(row=>row.capability))].sort();
  const lastDay=days.at(-1)?.day;
  useEffect(()=>{const element=scroller.current;if(element)element.scrollLeft=element.scrollWidth-element.clientWidth;},[lastDay,plotWidth]);
  const visible=types.filter(type=>!hidden.includes(type));
  const hasSeries=visible.length>0;
  useEffect(()=>{
    const element=scroller.current;if(!element)return;
    const measure=()=>setPlotWidth(element.clientWidth);
    measure();const observer=new ResizeObserver(measure);observer.observe(element);
    return()=>observer.disconnect();
  },[hasSeries]);
  const max=Math.max(1,...days.flatMap(day=>visible.map(type=>day.counts[type] ?? 0)));
  const step=Math.max(1,Math.ceil(max/4)),ceiling=step*4;
  const width=Math.max(plotWidth,days.length*72),height=220,top=12,bottom=172;
  const groupWidth=width/Math.max(1,days.length),barWidth=Math.min(24,72*.7/Math.max(1,visible.length));
  const showTip=(day:string,type:string,count:number,event:SyntheticEvent<SVGRectElement>)=>{const box=event.currentTarget.getBoundingClientRect(),panel=event.currentTarget.closest('#usage')?.querySelector(':scope > div')?.getBoundingClientRect();setTip({day,type,count,x:Math.min(window.innerWidth-140,Math.max(140,box.left+box.width/2)),y:Math.max((panel?.top ?? 0)+8,box.top-62)});};
  const number=(n:number)=>n.toLocaleString(locale),color=(type:string)=>palette[type] || '#94a3b8';
  return <section className="relative rounded-xl border border-zinc-800 bg-zinc-900/30 p-3">
    <h4 className="mb-3 text-sm font-medium">{t('access.daily')}</h4>
    <div className="flex flex-col gap-3 lg:flex-row">
      <div className="relative flex min-w-0 flex-1">
        {visible.length ? <>
          <svg aria-hidden="true" viewBox={`0 0 48 ${height}`} className="h-[220px] w-12 shrink-0">
            {[0,1,2,3,4].map(i=><text key={i} x={40} y={bottom-i*(bottom-top)/4+4} textAnchor="end" fill="#a1a1aa" fontSize="11">{number(i*step)}</text>)}
          </svg>
          <div ref={scroller} className="min-w-0 flex-1 overflow-x-auto overscroll-x-contain" onScroll={()=>setTip(null)}>
            <svg role="img" aria-label={t('access.daily')} viewBox={`0 0 ${width} ${height}`} style={{width,height}} className="block max-w-none" onMouseLeave={()=>setTip(null)}>
              {[0,1,2,3,4].map(i=>{const y=bottom-i*(bottom-top)/4;return <line key={i} x1={0} x2={width} y1={y} y2={y} stroke="#27272a" strokeDasharray={i?'4 4':undefined}/>;})}
              {days.map((day,index)=>{const center=groupWidth*(index+.5);return <g key={day.day}>
                {visible.map((type,i)=>{const count=day.counts[type] ?? 0,h=count/ceiling*(bottom-top);return <rect key={type} tabIndex={0} role="graphics-symbol" aria-label={`${day.day} · ${names[type] || type}: ${number(count)}`} onMouseEnter={event=>showTip(day.day,type,count,event)} onFocus={event=>showTip(day.day,type,count,event)} onBlur={()=>setTip(null)} onClick={event=>showTip(day.day,type,count,event)} x={center-visible.length*barWidth/2+i*barWidth+1} y={bottom-h} width={Math.max(2,barWidth-2)} height={h} rx={3} fill={color(type)} className="cursor-pointer outline-none hover:opacity-80 focus:stroke-white"/>;})}
                <text x={center} y={bottom+22} textAnchor="middle" fill="#a1a1aa" fontSize="11">{new Date(`${day.day}T12:00:00`).toLocaleDateString(locale,{day:'2-digit',month:'2-digit'})}</text>
                <text x={center} y={bottom+38} textAnchor="middle" fill="#52525b" fontSize="10">{day.day.slice(0,4)}</text>
              </g>;})}
            </svg>
          </div>
          {tip && createPortal(<div role="tooltip" style={{left:tip.x,top:tip.y}} className="pointer-events-none fixed z-50 -translate-x-1/2 whitespace-nowrap rounded-lg border border-zinc-700 bg-zinc-950/95 px-3 py-2 shadow-xl"><p className="mb-1 text-[11px] text-zinc-400">{new Date(`${tip.day}T12:00:00`).toLocaleDateString(locale)}</p><p className="flex items-center gap-2 text-xs"><span className="size-2 rounded-full" style={{backgroundColor:color(tip.type)}}/>{names[tip.type] || tip.type}<strong className="ml-2 font-mono text-white">{number(tip.count)} {t('access.requests')}</strong></p></div>,document.body)}
        </>:<p className="flex h-[220px] w-full items-center justify-center text-zinc-500">{t('access.chooseSeries')}</p>}
      </div>
      <div className="flex shrink-0 flex-wrap items-start gap-2 lg:w-44 lg:flex-col" aria-label={t('access.chartTypes')}>
        {types.map(type=><Button key={type} type="button" variant="ghost" aria-pressed={!hidden.includes(type)} onClick={()=>{setTip(null);setHidden(previous=>previous.includes(type)?previous.filter(x=>x!==type):[...previous,type]);}} className={`h-auto justify-start gap-2 rounded-lg border px-3 py-2 text-xs lg:w-full ${hidden.includes(type)?'border-transparent text-zinc-600':'border-zinc-800 bg-zinc-900 text-zinc-200'}`}><span className="size-2 shrink-0 rounded-sm" style={{backgroundColor:color(type),opacity:hidden.includes(type)?.3:1}}/>{names[type] || type}</Button>)}
      </div>
    </div>
    <div className="sr-only"><table><caption>{t('access.daily')}</caption><thead><tr><th>{t('access.date')}</th>{visible.map(type=><th key={type}>{names[type] || type}</th>)}</tr></thead><tbody>{days.map(day=><tr key={day.day}><th>{day.day}</th>{visible.map(type=><td key={type}>{day.counts[type] ?? 0}</td>)}</tr>)}</tbody></table></div>
  </section>;
}
