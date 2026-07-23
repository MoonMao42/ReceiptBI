import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import { describe, expect, it } from "vitest";

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SRC_ROOT = path.join(WEB_ROOT, "src");
const CATALOG_PATHS = {
  en: path.join(SRC_ROOT, "messages", "en.json"),
  zh: path.join(SRC_ROOT, "messages", "zh.json"),
} as const;

type Catalog = Record<string, unknown>;
type CatalogNodeKind =
  | "array"
  | "boolean"
  | "null"
  | "number"
  | "object"
  | "string";

interface DuplicateKey {
  path: string;
  firstLine: number;
  duplicateLine: number;
}

interface TranslatorBinding {
  name: string;
  namespace: string;
  declarationStart: number;
  scope: ts.Node;
  scopeDepth: number;
}

interface HardcodedHanViolation {
  file: string;
  line: number;
  kind: string;
  text: string;
}

function readCatalog(locale: keyof typeof CATALOG_PATHS): Catalog {
  return JSON.parse(readFileSync(CATALOG_PATHS[locale], "utf8")) as Catalog;
}

function sourceFilesUnder(root: string): string[] {
  return readdirSync(root, { withFileTypes: true }).flatMap((entry) => {
    const candidate = path.join(root, entry.name);
    if (entry.isDirectory()) return sourceFilesUnder(candidate);
    return /\.(?:ts|tsx)$/.test(entry.name) ? [candidate] : [];
  });
}

function unwrapExpression(expression: ts.Expression): ts.Expression {
  let current = expression;
  while (
    ts.isAsExpression(current) ||
    ts.isParenthesizedExpression(current) ||
    ts.isSatisfiesExpression(current) ||
    ts.isTypeAssertionExpression(current) ||
    ts.isNonNullExpression(current) ||
    ts.isAwaitExpression(current)
  ) {
    current = current.expression;
  }
  return current;
}

function propertyName(property: ts.ObjectLiteralElementLike): string | null {
  if (
    !ts.isPropertyAssignment(property) &&
    !ts.isShorthandPropertyAssignment(property) &&
    !ts.isMethodDeclaration(property) &&
    !ts.isGetAccessorDeclaration(property) &&
    !ts.isSetAccessorDeclaration(property)
  ) {
    return null;
  }
  const { name } = property;
  if (!name || ts.isComputedPropertyName(name)) return null;
  if (
    ts.isIdentifier(name) ||
    ts.isStringLiteralLike(name) ||
    ts.isNumericLiteral(name)
  ) {
    return name.text;
  }
  return null;
}

/**
 * JSON.parse silently keeps the final duplicate property. Parse the raw JSON as
 * a wrapped TypeScript object literal instead so every property remains in the
 * syntax tree and duplicates can be reported at their original line numbers.
 */
function duplicateKeysInCatalog(file: string): DuplicateKey[] {
  const raw = readFileSync(file, "utf8");
  const sourceFile = ts.createSourceFile(
    file,
    `const catalog = (${raw}) as const;`,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  const statement = sourceFile.statements.find(ts.isVariableStatement);
  const declaration = statement?.declarationList.declarations[0];
  if (!declaration?.initializer) {
    throw new Error(`Could not parse catalog object in ${file}`);
  }
  const root = unwrapExpression(declaration.initializer);
  if (!ts.isObjectLiteralExpression(root)) {
    throw new Error(`Catalog root is not an object in ${file}`);
  }

  const duplicates: DuplicateKey[] = [];
  const visitValue = (node: ts.Expression, valuePath: string) => {
    const value = unwrapExpression(node);
    if (ts.isObjectLiteralExpression(value)) {
      visitObject(value, valuePath);
      return;
    }
    if (ts.isArrayLiteralExpression(value)) {
      value.elements.forEach((element, index) => {
        visitValue(element as ts.Expression, `${valuePath}[${index}]`);
      });
    }
  };
  const visitObject = (node: ts.ObjectLiteralExpression, parentPath: string) => {
    const seen = new Map<string, number>();
    for (const property of node.properties) {
      const key = propertyName(property);
      if (key === null) continue;
      const line = sourceFile.getLineAndCharacterOfPosition(property.getStart(sourceFile)).line + 1;
      const pathToProperty = parentPath ? `${parentPath}.${key}` : key;
      const firstLine = seen.get(key);
      if (firstLine !== undefined) {
        duplicates.push({ path: pathToProperty, firstLine, duplicateLine: line });
      } else {
        seen.set(key, line);
      }
      if (ts.isPropertyAssignment(property)) {
        visitValue(property.initializer, pathToProperty);
      }
    }
  };

  visitObject(root, "");
  return duplicates;
}

function catalogNodeKind(value: unknown): CatalogNodeKind {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  return typeof value as Exclude<CatalogNodeKind, "array" | "null">;
}

function catalogShape(
  value: unknown,
  currentPath = "<root>",
  result = new Map<string, CatalogNodeKind>(),
): Map<string, CatalogNodeKind> {
  const kind = catalogNodeKind(value);
  result.set(currentPath, kind);
  if (kind === "object") {
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      catalogShape(child, currentPath === "<root>" ? key : `${currentPath}.${key}`, result);
    }
  } else if (kind === "array") {
    (value as unknown[]).forEach((child, index) => {
      catalogShape(child, `${currentPath}[${index}]`, result);
    });
  }
  return result;
}

function stringLeaves(
  value: unknown,
  currentPath = "",
  result = new Map<string, string>(),
): Map<string, string> {
  if (typeof value === "string") {
    result.set(currentPath, value);
    return result;
  }
  if (Array.isArray(value)) {
    value.forEach((child, index) => stringLeaves(child, `${currentPath}[${index}]`, result));
    return result;
  }
  if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      stringLeaves(child, currentPath ? `${currentPath}.${key}` : key, result);
    }
  }
  return result;
}

function icuPlaceholders(message: string): string[] {
  const placeholders = new Set<string>();
  for (const match of message.matchAll(/\{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*(?=[,}])/g)) {
    placeholders.add(match[1]);
  }
  return [...placeholders].sort();
}

function nearestTranslationScope(node: ts.Node): ts.Node {
  let current: ts.Node | undefined = node.parent;
  while (current) {
    if (ts.isFunctionLike(current) || ts.isSourceFile(current)) return current;
    current = current.parent;
  }
  return node.getSourceFile();
}

function nodeDepth(node: ts.Node): number {
  let depth = 0;
  let current: ts.Node | undefined = node;
  while (current.parent) {
    depth += 1;
    current = current.parent;
  }
  return depth;
}

function isDescendantOf(node: ts.Node, ancestor: ts.Node): boolean {
  let current: ts.Node | undefined = node;
  while (current) {
    if (current === ancestor) return true;
    current = current.parent;
  }
  return false;
}

function translationBinding(
  declaration: ts.VariableDeclaration,
): Omit<TranslatorBinding, "declarationStart" | "scope" | "scopeDepth"> | null {
  if (!ts.isIdentifier(declaration.name) || !declaration.initializer) return null;
  const initializer = unwrapExpression(declaration.initializer);
  if (!ts.isCallExpression(initializer) || !ts.isIdentifier(initializer.expression)) return null;
  if (
    initializer.expression.text !== "useTranslations" &&
    initializer.expression.text !== "getTranslations"
  ) {
    return null;
  }
  const namespace = initializer.arguments[0];
  if (!namespace || !ts.isStringLiteralLike(namespace)) return null;
  return { name: declaration.name.text, namespace: namespace.text };
}

function catalogHasPath(catalog: Catalog, keyPath: string): boolean {
  let current: unknown = catalog;
  for (const segment of keyPath.split(".")) {
    if (
      !current ||
      typeof current !== "object" ||
      Array.isArray(current) ||
      !Object.prototype.hasOwnProperty.call(current, segment)
    ) {
      return false;
    }
    current = (current as Record<string, unknown>)[segment];
  }
  return true;
}

function missingLiteralTranslationCalls(catalogs: Record<"en" | "zh", Catalog>) {
  const missing: Array<{
    file: string;
    line: number;
    key: string;
    missingIn: string[];
  }> = [];

  for (const file of sourceFilesUnder(SRC_ROOT)) {
    const sourceFile = ts.createSourceFile(
      file,
      readFileSync(file, "utf8"),
      ts.ScriptTarget.Latest,
      true,
      file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
    );
    const bindings: TranslatorBinding[] = [];

    const collectBindings = (node: ts.Node) => {
      if (ts.isVariableDeclaration(node)) {
        const binding = translationBinding(node);
        if (binding) {
          const scope = nearestTranslationScope(node);
          bindings.push({
            ...binding,
            declarationStart: node.getStart(sourceFile),
            scope,
            scopeDepth: nodeDepth(scope),
          });
        }
      }
      ts.forEachChild(node, collectBindings);
    };
    collectBindings(sourceFile);

    const inspectCalls = (node: ts.Node) => {
      if (
        ts.isCallExpression(node) &&
        ts.isIdentifier(node.expression) &&
        node.arguments[0] &&
        ts.isStringLiteralLike(node.arguments[0])
      ) {
        const calleeName = node.expression.text;
        const messageKey = node.arguments[0].text;
        const callStart = node.getStart(sourceFile);
        const binding = bindings
          .filter(
            (candidate) =>
              candidate.name === calleeName &&
              candidate.declarationStart <= callStart &&
              isDescendantOf(node, candidate.scope),
          )
          .sort(
            (left, right) =>
              right.scopeDepth - left.scopeDepth ||
              right.declarationStart - left.declarationStart,
          )[0];
        if (binding) {
          const key = `${binding.namespace}.${messageKey}`;
          const missingIn = (Object.keys(catalogs) as Array<keyof typeof catalogs>).filter(
            (locale) => !catalogHasPath(catalogs[locale], key),
          );
          if (missingIn.length) {
            missing.push({
              file: path.relative(WEB_ROOT, file),
              line: sourceFile.getLineAndCharacterOfPosition(callStart).line + 1,
              key,
              missingIn,
            });
          }
        }
      }
      ts.forEachChild(node, inspectCalls);
    };
    inspectCalls(sourceFile);
  }
  return missing;
}

function staticText(expression: ts.Expression | undefined): string | null {
  if (!expression) return null;
  if (ts.isStringLiteralLike(expression) || ts.isNoSubstitutionTemplateLiteral(expression)) {
    return expression.text;
  }
  if (ts.isTemplateExpression(expression)) {
    return [expression.head.text, ...expression.templateSpans.map((span) => span.literal.text)].join(
      "",
    );
  }
  return null;
}

/**
 * Keep this deliberately narrow: only text that is certainly rendered or used
 * as an accessible name is checked. Comments, regexes, compatibility strings,
 * identifiers, user data, and technical constants are outside this scan.
 */
function hardcodedHanInJsx(): HardcodedHanViolation[] {
  const roots = [path.join(SRC_ROOT, "app"), path.join(SRC_ROOT, "components")];
  const attributes = new Set(["alt", "aria-label", "placeholder", "title"]);
  const violations: HardcodedHanViolation[] = [];

  const record = (sourceFile: ts.SourceFile, node: ts.Node, kind: string, text: string) => {
    const normalized = text.replace(/\s+/g, " ").trim();
    if (!/[\u3400-\u9fff]/u.test(normalized)) return;
    violations.push({
      file: path.relative(WEB_ROOT, sourceFile.fileName),
      line: sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1,
      kind,
      text: normalized.length > 80 ? `${normalized.slice(0, 77)}...` : normalized,
    });
  };

  for (const file of roots.flatMap(sourceFilesUnder).filter((candidate) => candidate.endsWith(".tsx"))) {
    const sourceFile = ts.createSourceFile(
      file,
      readFileSync(file, "utf8"),
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TSX,
    );
    const visit = (node: ts.Node) => {
      if (ts.isJsxText(node)) record(sourceFile, node, "JSX text", node.getText(sourceFile));
      if (
        ts.isJsxExpression(node) &&
        !ts.isJsxAttribute(node.parent) &&
        node.expression
      ) {
        const text = staticText(node.expression);
        if (text !== null) record(sourceFile, node, "JSX expression", text);
      }
      if (
        ts.isJsxAttribute(node) &&
        ts.isIdentifier(node.name) &&
        attributes.has(node.name.text) &&
        node.initializer
      ) {
        const text = ts.isStringLiteral(node.initializer)
          ? node.initializer.text
          : ts.isJsxExpression(node.initializer)
            ? staticText(node.initializer.expression)
            : null;
        if (text !== null) record(sourceFile, node, node.name.text, text);
      }
      ts.forEachChild(node, visit);
    };
    visit(sourceFile);
  }
  return violations;
}

function hardcodedHanFailure(violations: HardcodedHanViolation[]): string {
  const grouped = new Map<string, HardcodedHanViolation[]>();
  for (const violation of violations) {
    const items = grouped.get(violation.file) || [];
    items.push(violation);
    grouped.set(violation.file, items);
  }
  const detail = [...grouped.entries()].flatMap(([file, items]) => [
    `${file}: ${items.length}`,
    ...items.slice(0, 8).map(
      (item) => `  L${item.line} ${item.kind}: ${JSON.stringify(item.text)}`,
    ),
    ...(items.length > 8 ? [`  ... ${items.length - 8} more`] : []),
  ]);
  return [
    `Found ${violations.length} hard-coded Han JSX strings in ${grouped.size} files.`,
    "Move system copy and accessible names into the locale catalogs.",
    ...detail,
  ].join("\n");
}

describe("i18n catalog integrity", () => {
  it("rejects duplicate keys at every catalog object level", () => {
    const duplicates = (Object.keys(CATALOG_PATHS) as Array<keyof typeof CATALOG_PATHS>)
      .flatMap((locale) =>
        duplicateKeysInCatalog(CATALOG_PATHS[locale]).map((item) => ({ locale, ...item })),
      );
    expect(duplicates).toEqual([]);
  });

  it("keeps English and Chinese keys and node types identical", () => {
    const enShape = catalogShape(readCatalog("en"));
    const zhShape = catalogShape(readCatalog("zh"));
    const missingInZh = [...enShape.keys()].filter((key) => !zhShape.has(key));
    const missingInEn = [...zhShape.keys()].filter((key) => !enShape.has(key));
    const typeMismatches = [...enShape.entries()].flatMap(([key, enType]) => {
      const zhType = zhShape.get(key);
      return zhType !== undefined && zhType !== enType ? [{ key, enType, zhType }] : [];
    });
    expect({ missingInZh, missingInEn, typeMismatches }).toEqual({
      missingInZh: [],
      missingInEn: [],
      typeMismatches: [],
    });
  });

  it("keeps ICU placeholder names identical across locales", () => {
    const enStrings = stringLeaves(readCatalog("en"));
    const zhStrings = stringLeaves(readCatalog("zh"));
    const mismatches = [...enStrings.entries()].flatMap(([key, enMessage]) => {
      const zhMessage = zhStrings.get(key);
      if (zhMessage === undefined) return [];
      const enPlaceholders = icuPlaceholders(enMessage);
      const zhPlaceholders = icuPlaceholders(zhMessage);
      return enPlaceholders.join("\0") === zhPlaceholders.join("\0")
        ? []
        : [{ key, enPlaceholders, zhPlaceholders }];
    });
    expect(mismatches).toEqual([]);
  });

  it("resolves literal useTranslations and getTranslations calls in both catalogs", () => {
    const catalogs = { en: readCatalog("en"), zh: readCatalog("zh") };
    expect(missingLiteralTranslationCalls(catalogs)).toEqual([]);
  });

  it("keeps enumerated dynamic translation families in both catalogs", () => {
    const expectedPaths = [
      "theme.dawn.name",
      "theme.dawn.description",
      "theme.midnight.name",
      "theme.midnight.description",
      ...["all", "candidate", "confirmed", "locked"].map(
        (state) => `projectUnderstanding.stateFilter.${state}`
      ),
      ...["all", "unverified", "active", "stale"].map(
        (validity) => `projectUnderstanding.validity.${validity}`
      ),
      ...["candidate", "confirmed", "locked"].map(
        (state) => `projectUnderstanding.editorState.${state}`
      ),
      ...[
        "project",
        "localDatabase",
        "remoteDatabase",
        "csv",
        "excel",
        "parquet",
        "json",
        "otherFile",
        "crossSource",
        "unresolved",
        "allLocalDatabases",
        "allRemoteDatabases",
        "allExcel",
        "allCsv",
        "allParquet",
        "allJson",
        "allOtherFiles",
      ].map((scope) => `projectUnderstanding.scope.${scope}`),
    ];
    const catalogs = { en: readCatalog("en"), zh: readCatalog("zh") };
    const missing = expectedPaths.flatMap((key) =>
      (Object.keys(catalogs) as Array<keyof typeof catalogs>).flatMap((locale) =>
        catalogHasPath(catalogs[locale], key) ? [] : [{ locale, key }]
      )
    );
    expect(missing).toEqual([]);
  });

  it("keeps static Han system copy out of JSX and accessible-name attributes", () => {
    const violations = hardcodedHanInJsx();
    if (violations.length) throw new Error(hardcodedHanFailure(violations));
  });
});
