import path from "node:path";

export class UnsafePathSegmentError extends Error {
  override readonly name = "UnsafePathSegmentError";
}

function assertSinglePathSegment(segment: string): void {
  if (
    segment.length === 0 ||
    segment === "." ||
    segment === ".." ||
    segment.includes("/") ||
    segment.includes("\\") ||
    segment.includes(":") ||
    segment.includes("\0") ||
    segment.endsWith(".") ||
    segment.endsWith(" ") ||
    path.posix.isAbsolute(segment) ||
    path.win32.isAbsolute(segment) ||
    isWindowsReservedName(segment)
  ) {
    throw new UnsafePathSegmentError(`Unsafe path segment: ${JSON.stringify(segment)}`);
  }
}

function isWindowsReservedName(segment: string): boolean {
  const [baseName = segment] = segment.split(".", 1);
  const normalized = baseName.toUpperCase();
  return (
    normalized === "CON" ||
    normalized === "PRN" ||
    normalized === "AUX" ||
    normalized === "NUL" ||
    /^(?:COM|LPT)[1-9]$/u.test(normalized)
  );
}

export function joinPath(baseDirectory: string, ...segments: readonly string[]): string {
  if (!path.isAbsolute(baseDirectory) || path.normalize(baseDirectory) !== baseDirectory) {
    throw new UnsafePathSegmentError(
      "Base directory must be an absolute, normalized host path.",
    );
  }

  for (const segment of segments) {
    assertSinglePathSegment(segment);
  }

  return path.join(baseDirectory, ...segments);
}

export function joinSandboxPath(
  sandboxRoot: string,
  sandboxId: string,
  ...segments: readonly string[]
): string {
  return joinPath(sandboxRoot, sandboxId, ...segments);
}
