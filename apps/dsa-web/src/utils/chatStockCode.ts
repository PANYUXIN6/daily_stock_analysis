import { validateStockCode } from './validation';
import { normalizeStockCode, resolveRegisteredIndexCanonical } from './stockCode';
import type { StockIndexItem } from '../types/stockIndex';

export function extractStockCodeFromMessage(
  message: string,
  index?: ReadonlyArray<StockIndexItem>,
): string | null {
  return extractStockCodesFromMessage(message, index)[0] ?? null;
}

export function extractStockCodesFromMessage(
  message: string,
  index?: ReadonlyArray<StockIndexItem>,
): string[] {
  // Explicit dotted CSI/SH/SZ and csi-prefixed forms MUST precede the fallbacks so
  // a registered alias is captured as one token; the registry hit suppresses its
  // inner bare digits (a registry miss leaves the baseline patterns untouched).
  const patterns = [
    /\b(\d{6}\.(?:CSI|SH|SZ))\b/gi,
    /\b(CSI\d{6})\b/gi,
    /\b(\d{6}\.(?:SH|SZ|BJ))\b/gi,
    /\b((?:SH|SZ|BJ)\d{6})\b/gi,
    /\b(\d{6})\b/g,
  ];

  const matches: Array<{ value: string; index: number; priority: number; end: number }> = [];
  patterns.forEach((pattern, priority) => {
    pattern.lastIndex = 0;
    for (const match of message.matchAll(pattern)) {
      const value = match[1] ?? match[0];
      const start = match.index ?? 0;
      const end = start + value.length;
      matches.push({
        value,
        index: start,
        priority,
        end,
      });
    }
  });

  matches.sort((a, b) => a.index - b.index || a.priority - b.priority);

  const stockCodes: string[] = [];
  const seen = new Set<string>();
  // Spans of already-accepted tokens suppress strictly-inner matches so a
  // dotted index alias never leaks its inner bare digits as a separate stock.
  const acceptedSpans: Array<{ start: number; end: number }> = [];
  for (const match of matches) {
    if (acceptedSpans.some((span) => match.index >= span.start && match.end <= span.end)) {
      continue;
    }
    // Registered index exact hit (canonical / display / explicit alias) — use
    // the registry canonical verbatim; never stock-normalize it.
    const registeredCanonical = index && index.length > 0
      ? resolveRegisteredIndexCanonical(index, match.value)
      : null;
    if (registeredCanonical) {
      acceptedSpans.push({ start: match.index, end: match.end });
      if (!seen.has(registeredCanonical)) {
        seen.add(registeredCanonical);
        stockCodes.push(registeredCanonical);
      }
      continue;
    }
    // Priority 0-1 forms are REGISTRY-ONLY: on a miss, drop the whole token
    // (no accepted span) so the legacy patterns beneath keep the no-registry
    // baseline (930955.CSI → ['930955'], csi930955 → []).
    if (match.priority <= 1) {
      continue;
    }
    const { valid, normalized } = validateStockCode(match.value);
    if (!valid) {
      continue;
    }
    acceptedSpans.push({ start: match.index, end: match.end });
    const stockCode = normalizeStockCode(normalized);
    if (!seen.has(stockCode)) {
      seen.add(stockCode);
      stockCodes.push(stockCode);
    }
  }
  return stockCodes;
}
