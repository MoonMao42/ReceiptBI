export const RENDERER_CHUNK_FAILURE_CHANNEL = 'renderer-chunk-load-failed';

export interface RendererChunkFailureReport {
  readonly kind: 'chunk-load';
  readonly documentId: string;
  readonly name: string;
  readonly message: string;
}

export type ChunkRecoveryAction = 'reload' | 'show-error' | 'ignore';

const DOCUMENT_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const NEXT_STATIC_PATH = '/_next/static/';
const MAX_FAILURE_DETAIL_LENGTH = 500;

function readErrorField(reason: unknown, field: 'name' | 'message'): string {
  if (typeof reason === 'string') return field === 'message' ? reason : 'Error';
  if (!reason || typeof reason !== 'object') {
    return field === 'message' ? String(reason ?? '') : 'Error';
  }

  const value = (reason as Record<string, unknown>)[field];
  return typeof value === 'string' ? value : field === 'name' ? 'Error' : '';
}

function conciseFailureDetail(value: string): string {
  return value.replace(/\s+/g, ' ').trim().slice(0, MAX_FAILURE_DETAIL_LENGTH);
}

/**
 * Recognize the runtime errors emitted by webpack/Next.js when a JavaScript
 * chunk cannot be fetched. Generic renderer errors deliberately do not enter
 * the recovery path.
 */
export function describeChunkLoadFailure(
  reason: unknown
): Pick<RendererChunkFailureReport, 'kind' | 'name' | 'message'> | null {
  const name = readErrorField(reason, 'name');
  const message = readErrorField(reason, 'message');
  const detail = `${name}: ${message}`;
  const namesChunkFailure = name === 'ChunkLoadError';
  const namesWebpackFailure = /Loading (?:CSS )?chunk [\w-]+ failed/i.test(message);
  const namesDynamicImportFailure = /Failed to fetch dynamically imported module/i.test(message);
  const referencesNextStaticAsset = detail.includes(NEXT_STATIC_PATH);

  if (
    !namesChunkFailure &&
    !((namesWebpackFailure || namesDynamicImportFailure) && referencesNextStaticAsset)
  ) {
    return null;
  }

  return {
    kind: 'chunk-load',
    name: conciseFailureDetail(name) || 'ChunkLoadError',
    message: conciseFailureDetail(message) || 'A Next.js chunk failed to load',
  };
}

export function isRendererChunkFailureReport(
  value: unknown
): value is RendererChunkFailureReport {
  if (!value || typeof value !== 'object') return false;
  const report = value as Partial<RendererChunkFailureReport>;
  return (
    report.kind === 'chunk-load' &&
    typeof report.documentId === 'string' &&
    DOCUMENT_ID_PATTERN.test(report.documentId) &&
    typeof report.name === 'string' &&
    report.name.length > 0 &&
    report.name.length <= MAX_FAILURE_DETAIL_LENGTH &&
    typeof report.message === 'string' &&
    report.message.length > 0 &&
    report.message.length <= MAX_FAILURE_DETAIL_LENGTH
  );
}

/**
 * One document may surface the same rejected chunk through both `error` and
 * `unhandledrejection`. Deduplicate that document, allow exactly one fresh
 * document reload, and make the next document's failure terminal.
 */
export class ChunkLoadRecoveryGate {
  private readonly handledDocuments = new Set<string>();
  private attempted = false;
  private failed = false;

  get recoveryAttempted(): boolean {
    return this.attempted;
  }

  get terminal(): boolean {
    return this.failed;
  }

  recordFailure(documentId: string): ChunkRecoveryAction {
    if (this.failed || this.handledDocuments.has(documentId)) return 'ignore';
    this.handledDocuments.add(documentId);

    if (!this.attempted) {
      this.attempted = true;
      return 'reload';
    }

    this.failed = true;
    return 'show-error';
  }

  terminateRecovery(): ChunkRecoveryAction {
    if (this.failed) return 'ignore';
    this.failed = true;
    return 'show-error';
  }
}

function decodeHtmlAttribute(value: string): string {
  return value.replace(/&amp;/gi, '&');
}

export function isNextStaticScriptUrl(value: string, pageUrl: string): boolean {
  try {
    const page = new URL(pageUrl);
    const asset = new URL(decodeHtmlAttribute(value), page);
    return (
      asset.origin === page.origin &&
      asset.pathname.startsWith(NEXT_STATIC_PATH) &&
      asset.pathname.endsWith('.js')
    );
  } catch {
    return false;
  }
}

/** Extract same-origin Next.js JavaScript assets referenced by the rendered HTML. */
export function extractNextStaticScriptUrls(html: string, pageUrl: string): string[] {
  const page = new URL(pageUrl);
  const urls = new Set<string>();
  const scriptPattern = /<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["'][^>]*>/gi;

  for (const match of html.matchAll(scriptPattern)) {
    try {
      const asset = new URL(decodeHtmlAttribute(match[1]), page);
      if (isNextStaticScriptUrl(asset.toString(), page.toString())) {
        urls.add(asset.toString());
      }
    } catch {
      // A malformed script URL cannot count as a readiness signal.
    }
  }

  return [...urls];
}

export function isHtmlContentType(value: string | string[] | undefined): boolean {
  const contentType = Array.isArray(value) ? value.join(';') : value ?? '';
  return /^text\/html(?:\s*;|$)/i.test(contentType.trim());
}

export function isJavaScriptContentType(value: string | string[] | undefined): boolean {
  const contentType = Array.isArray(value) ? value.join(';') : value ?? '';
  return /^(?:application|text)\/(?:javascript|x-javascript)(?:\s*;|$)/i.test(
    contentType.trim()
  );
}
