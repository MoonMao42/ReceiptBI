import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import ts from "typescript";

const root = path.resolve(import.meta.dirname, "..");
const ignoredDirectories = new Set([
  ".git",
  ".next",
  "coverage",
  "dist",
  "node_modules",
  "out",
  "target",
]);
const ignoredFiles = new Set([
  path.join(root, "scripts", "check-path-construction.mjs"),
  path.join(root, "scripts", "check-path-construction.test.mjs"),
  path.join(root, "crates", "semantic-node", "index.js"),
]);
const sourceExtensions = new Set([
  ".cjs",
  ".cts",
  ".js",
  ".jsx",
  ".mjs",
  ".mts",
  ".rs",
  ".ts",
  ".tsx",
]);
const typedScriptExtensions = new Set([
  ".cjs",
  ".cts",
  ".js",
  ".jsx",
  ".mjs",
  ".mts",
  ".ts",
  ".tsx",
]);

const violations = [];
const violationKeys = new Set();

function addViolation(file, content, offset, rule, message) {
  const before = content.slice(0, offset);
  const line = before.split(/\r?\n/u).length;
  const key = `${file}:${line}:${rule}`;
  if (violationKeys.has(key)) {
    return;
  }

  violationKeys.add(key);
  violations.push({
    file: path.relative(root, file),
    line,
    rule,
    message,
    source: content.split(/\r?\n/u)[line - 1]?.trim() ?? "",
  });
}

function hasSeparator(value) {
  return value.includes("/") || value.includes("\\");
}

function stringValue(node) {
  return ts.isStringLiteralLike(node) ? node.text : undefined;
}

function isPathSeparatorReference(node, sourceFile) {
  return (
    ts.isPropertyAccessExpression(node) &&
    node.name.text === "sep" &&
    /(?:^|\.)path(?:\.(?:posix|win32))?\.sep$/u.test(node.getText(sourceFile))
  );
}

function flattenPlus(node, parts) {
  if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.PlusToken) {
    flattenPlus(node.left, parts);
    flattenPlus(node.right, parts);
    return;
  }
  parts.push(node);
}

function checkTypedScript(file, content) {
  const extension = path.extname(file);
  const scriptKind =
    extension === ".tsx" || extension === ".jsx"
      ? ts.ScriptKind.TSX
      : extension === ".js" || extension === ".mjs" || extension === ".cjs"
        ? ts.ScriptKind.JS
        : ts.ScriptKind.TS;
  const sourceFile = ts.createSourceFile(
    file,
    content,
    ts.ScriptTarget.Latest,
    true,
    scriptKind,
  );

  function visit(node) {
    if (
      ts.isBinaryExpression(node) &&
      node.operatorToken.kind === ts.SyntaxKind.PlusToken &&
      !(
        ts.isBinaryExpression(node.parent) &&
        node.parent.operatorToken.kind === ts.SyntaxKind.PlusToken
      )
    ) {
      const parts = [];
      flattenPlus(node, parts);
      const hasDynamicPart = parts.some((part) => stringValue(part) === undefined);
      const hasSeparatorPart = parts.some((part) => {
        const value = stringValue(part);
        return value !== undefined
          ? hasSeparator(value)
          : isPathSeparatorReference(part, sourceFile);
      });

      if (hasDynamicPart && hasSeparatorPart) {
        addViolation(
          file,
          content,
          node.getStart(sourceFile),
          "separator-concatenation",
          "Use node:path join/resolve instead of constructing a path with +.",
        );
      }
    }

    if (ts.isTemplateExpression(node)) {
      const literalParts = [node.head.text, ...node.templateSpans.map((span) => span.literal.text)];
      if (literalParts.some(hasSeparator)) {
        addViolation(
          file,
          content,
          node.getStart(sourceFile),
          "template-path-construction",
          "Pass template values as separate node:path segments.",
        );
      }
    }

    if (
      ts.isCallExpression(node) &&
      ts.isPropertyAccessExpression(node.expression) &&
      node.expression.name.text === "concat"
    ) {
      const parts = [node.expression.expression, ...node.arguments];
      const hasDynamicPart = parts.some((part) => stringValue(part) === undefined);
      const hasSeparatorPart = parts.some((part) => {
        const value = stringValue(part);
        return value !== undefined
          ? hasSeparator(value)
          : isPathSeparatorReference(part, sourceFile);
      });
      if (hasDynamicPart && hasSeparatorPart) {
        addViolation(
          file,
          content,
          node.getStart(sourceFile),
          "separator-concat-call",
          "Use node:path join/resolve instead of String.concat for paths.",
        );
      }
    }

    if (
      ts.isCallExpression(node) &&
      ts.isPropertyAccessExpression(node.expression) &&
      node.expression.name.text === "join" &&
      node.arguments.some((argument) => {
        const value = stringValue(argument);
        return value === "/" || value === "\\" || isPathSeparatorReference(argument, sourceFile);
      })
    ) {
      addViolation(
        file,
        content,
        node.getStart(sourceFile),
        "separator-array-join",
        "Use node:path join/resolve instead of Array.join with a filesystem separator.",
      );
    }

    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
}

function checkRust(file, content) {
  const formatPatterns = [
    /\bformat!\s*\(\s*"((?:\\.|[^"\\])*)"/gmu,
    /\bformat!\s*\(\s*r(#+)"([\s\S]*?)"\1/gmu,
  ];

  for (const [patternIndex, pattern] of formatPatterns.entries()) {
    for (const match of content.matchAll(pattern)) {
      const template = match[patternIndex === 0 ? 1 : 2] ?? "";
      const hasPlaceholder = /\{[^}]*\}/u.test(template);
      const hasLiteralSeparator =
        template.includes("/") ||
        (patternIndex === 0 ? template.includes("\\\\") : template.includes("\\"));
      if (hasPlaceholder && hasLiteralSeparator) {
        addViolation(
          file,
          content,
          match.index,
          "rust-format-path",
          "Use PathBuf::push or Path::join instead of format! for paths.",
        );
      }
    }
  }

  const stringConcatenation = /(?:\+\s*"(?:\/|\\\\)[^"\n]*"|"[^"\n]*(?:\/|\\\\)"\s*\+)/gmu;
  for (const match of content.matchAll(stringConcatenation)) {
    addViolation(
      file,
      content,
      match.index,
      "rust-string-path",
      "Use PathBuf::push or Path::join instead of string concatenation for paths.",
    );
  }
}

async function collectFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    if (ignoredDirectories.has(entry.name)) {
      continue;
    }

    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await collectFiles(entryPath)));
      continue;
    }

    if (
      entry.isFile() &&
      sourceExtensions.has(path.extname(entry.name)) &&
      !ignoredFiles.has(entryPath)
    ) {
      files.push(entryPath);
    }
  }

  return files;
}

for (const file of await collectFiles(root)) {
  const content = await readFile(file, "utf8");
  if (typedScriptExtensions.has(path.extname(file))) {
    checkTypedScript(file, content);
  } else {
    checkRust(file, content);
  }
}

if (violations.length > 0) {
  for (const violation of violations) {
    process.stderr.write(
      `${violation.file}:${violation.line} [${violation.rule}] ${violation.message}\n`,
    );
    process.stderr.write(`  ${violation.source}\n`);
  }
  process.exitCode = 1;
} else {
  process.stdout.write("Path construction policy passed.\n");
}
