import path from 'node:path';
import fs from 'node:fs';

export interface Logger {
  info: (message: string, ...args: unknown[]) => void;
  warn: (message: string, ...args: unknown[]) => void;
  error: (message: string, ...args: unknown[]) => void;
  debug: (message: string, ...args: unknown[]) => void;
}

export function serializeLogArguments(args: unknown[]): string {
  const seen = new WeakSet<object>();
  return JSON.stringify(args, (_key, value: unknown) => {
    if (typeof value === 'bigint') return `${value}n`;
    if (value instanceof Error) {
      if (seen.has(value)) return '[Circular]';
      seen.add(value);
      return {
        name: value.name,
        message: value.message,
        stack: value.stack,
        ...(value.cause === undefined ? {} : { cause: value.cause }),
      };
    }
    if (value && typeof value === 'object') {
      if (seen.has(value)) return '[Circular]';
      seen.add(value);
    }
    return value;
  });
}

export function setupLogger(userDataDir: string): Logger {
  const logDir = path.join(userDataDir, 'logs');
  fs.mkdirSync(logDir, { recursive: true });

  const today = new Date().toISOString().split('T')[0];
  const logFile = path.join(logDir, `receiptbi-${today}.log`);
  const logStream = fs.createWriteStream(logFile, { flags: 'a' });

  const formatMessage = (level: string, message: string, args: unknown[]): string => {
    const timestamp = new Date().toISOString();
    const argsStr = args.length > 0 ? ` ${serializeLogArguments(args)}` : '';
    return `[${timestamp}] [${level}] ${message}${argsStr}\n`;
  };

  const log = (level: string, message: string, ...args: unknown[]) => {
    const formatted = formatMessage(level, message, args);
    logStream.write(formatted);
    if (process.env.NODE_ENV === 'development') {
      console.log(formatted.trim());
    }
  };

  return {
    info: (message: string, ...args: unknown[]) => log('INFO', message, ...args),
    warn: (message: string, ...args: unknown[]) => log('WARN', message, ...args),
    error: (message: string, ...args: unknown[]) => log('ERROR', message, ...args),
    debug: (message: string, ...args: unknown[]) => log('DEBUG', message, ...args),
  };
}
