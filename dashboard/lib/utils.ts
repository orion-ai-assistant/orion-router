import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function money(val: any, maxDecimals = 8): string {
  if (val === null || val === undefined) return '$0.00';
  const num = parseFloat(val);
  if (isNaN(num) || num === 0) return '$0.00';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: maxDecimals
  }).format(num);
}

export function formatNumber(val: any): string {
  if (val === null || val === undefined) return '0';
  const num = parseInt(val);
  if (isNaN(num)) return '0';
  return num.toLocaleString();
}

export function dateTime(str: string | null | undefined): string {
  if (!str) return '';
  return new Date(str).toLocaleString();
}
