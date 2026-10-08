export type UsageBucket = {capability: string; usage_unit?: string | null; usage_amount?: number | null; day?: string; requests: number; input: number|null; output: number|null; thoughts: number|null; total: number|null; cost: number|null; succeeded: number; failed: number; missing_usage: number; missing_cost: number};
export type UsageSummary = UsageBucket & {amounts: Record<string, number|null>};
const nullableSum = (a: number|null|undefined, b: number|null|undefined): number|null =>
  a == null && b == null ? null : Number(a ?? 0) + Number(b ?? 0);

/** One card per operation; amounts in different units never share a sum. */
export function summarizeUsage(rows: UsageBucket[]): UsageSummary[] {
  const groups = new Map<string, UsageSummary>();
  for (const row of rows) {
    let group = groups.get(row.capability);
    if (!group) {
      group = {...row, requests:0, succeeded:0, failed:0, missing_usage:0, missing_cost:0,
        input:null, output:null, thoughts:null, total:null, cost:null, amounts:{}};
      groups.set(row.capability, group);
    }
    for (const field of ['requests','succeeded','failed','missing_usage','missing_cost'] as const)
      group[field] += Number(row[field] ?? 0);
    for (const field of ['input','output','thoughts','total','cost'] as const)
      group[field] = nullableSum(group[field], row[field]);
    if (row.usage_unit)
      group.amounts[row.usage_unit] = nullableSum(group.amounts[row.usage_unit], row.usage_amount);
  }
  return [...groups.values()];
}

export function dailyRequests(rows: UsageBucket[]): {day:string; counts:Record<string,number>}[] {
  const days = new Map<string, Record<string,number>>();
  for (const row of rows) {
    if (!row.day) continue;
    const counts = days.get(row.day) ?? {};
    counts[row.capability] = (counts[row.capability] ?? 0) + Number(row.requests);
    days.set(row.day, counts);
  }
  return [...days].sort(([a],[b])=>a.localeCompare(b)).map(([day,counts])=>({day,counts}));
}
