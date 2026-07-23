"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Check,
  Eraser,
  Loader2,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import type {
  DataRow,
  ProjectDataSource,
  VisualCleaningOperation,
  VisualCleaningSnapshot,
} from "@/lib/types/api";
import { useProjectStore } from "@/lib/stores/project";

export type VisualCleaningAction =
  | "trim_text"
  | "fill_missing"
  | "normalize_datetime"
  | "normalize_currency"
  | "drop_exact_duplicates";

type VisualCleaningTranslator = ReturnType<
  typeof useTranslations<"visualCleaning">
>;

export function buildVisualCleaningOperation(
  action: VisualCleaningAction,
  column?: string,
): VisualCleaningOperation | null {
  if (action === "drop_exact_duplicates") {
    return { operation: "drop_exact_duplicates" };
  }
  const selectedColumn = column?.trim();
  if (!selectedColumn) return null;
  if (action === "fill_missing") {
    return { operation: "fill_missing", column: selectedColumn, value: 0 };
  }
  return { operation: action, column: selectedColumn };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

interface SavedVisualCleaningState {
  operations: VisualCleaningOperation[];
  operationKeys: Set<string>;
  hasSavedOperations: boolean;
  hasUnsupportedOperations: boolean;
}

interface ReadonlyCleaningOperation {
  key: string;
  label: string;
}

function editableSavedOperation(value: unknown): VisualCleaningOperation | null {
  if (!isRecord(value) || typeof value.operation !== "string") return null;
  if (value.operation === "drop_exact_duplicates") {
    return { operation: "drop_exact_duplicates" };
  }
  if (typeof value.column !== "string" || !value.column.trim()) return null;
  const column = value.column.trim();
  if (value.operation === "fill_missing" && value.value === 0) {
    return { operation: "fill_missing", column, value: 0 };
  }
  if (
    value.operation === "trim_text" ||
    value.operation === "normalize_datetime" ||
    value.operation === "normalize_currency"
  ) {
    return { operation: value.operation, column };
  }
  return null;
}

function rawOperationKey(value: unknown): string | null {
  if (!isRecord(value) || typeof value.operation !== "string") return null;
  const operation = value.operation.trim();
  if (!operation || operation.startsWith("replay_") || operation === "reapply_recipe") {
    return null;
  }
  if (typeof value.column === "string" && value.column.trim()) {
    return `${operation}:${value.column.trim()}`;
  }
  if (typeof value.sheet === "string" && value.sheet.trim()) {
    return `${operation}:${value.sheet.trim()}`;
  }
  if (typeof value.row === "number" && Number.isFinite(value.row)) {
    return `${operation}:${value.row}`;
  }
  return `${operation}:all`;
}

function inspectSavedVisualCleaningOperations(
  value: unknown,
): SavedVisualCleaningState {
  if (value === null || value === undefined) {
    return {
      operations: [],
      operationKeys: new Set(),
      hasSavedOperations: false,
      hasUnsupportedOperations: false,
    };
  }
  if (!isRecord(value)) {
    return {
      operations: [],
      operationKeys: new Set(),
      hasSavedOperations: true,
      hasUnsupportedOperations: true,
    };
  }
  if (!("operations" in value)) {
    return {
      operations: [],
      operationKeys: new Set(),
      hasSavedOperations: false,
      hasUnsupportedOperations: false,
    };
  }
  if (!Array.isArray(value.operations)) {
    return {
      operations: [],
      operationKeys: new Set(),
      hasSavedOperations: true,
      hasUnsupportedOperations: true,
    };
  }
  const operations: VisualCleaningOperation[] = [];
  const editableKeys = new Set<string>();
  const operationKeys = new Set<string>();
  let hasUnsupportedOperations = false;
  value.operations.forEach((item) => {
    const rawKey = rawOperationKey(item);
    if (rawKey) operationKeys.add(rawKey);
    const operation = editableSavedOperation(item);
    if (!operation) {
      hasUnsupportedOperations = true;
      return;
    }
    const key = operationKey(operation);
    if (editableKeys.has(key)) {
      hasUnsupportedOperations = true;
      return;
    }
    editableKeys.add(key);
    operations.push(operation);
  });
  return {
    operations,
    operationKeys,
    hasSavedOperations: value.operations.length > 0,
    hasUnsupportedOperations,
  };
}

export function parseSavedVisualCleaningOperations(
  value: unknown,
): VisualCleaningOperation[] {
  return inspectSavedVisualCleaningOperations(value).operations;
}

function operationKey(operation: VisualCleaningOperation): string {
  return `${operation.operation}:${"column" in operation ? operation.column : "all"}`;
}

function operationLabel(
  operation: VisualCleaningOperation,
  t: VisualCleaningTranslator,
): string {
  const column = "column" in operation ? `“${operation.column}”` : "";
  switch (operation.operation) {
    case "trim_text":
      return t("trimLabel", { column });
    case "fill_missing":
      return t("fillZeroLabel", { column });
    case "normalize_datetime":
      return t("unifyDatesLabel", { column });
    case "normalize_currency":
      return t("unifyAmountsLabel", { column });
    case "drop_exact_duplicates":
      return t("removeDuplicatesLabel");
  }
}

function readonlyOperationLabel(
  value: Record<string, unknown>,
  t: VisualCleaningTranslator,
): string {
  const editable = editableSavedOperation(value);
  if (editable) return operationLabel(editable, t);
  const operation = value.operation;
  if (operation === "fill_missing" && typeof value.column === "string") {
    return t("fillNullLabel", { column: `“${value.column}”` });
  }
  if (operation === "select_sheet" && typeof value.sheet === "string") {
    return t("selectSheetLabel", { sheet: value.sheet });
  }
  if (operation === "select_header" && typeof value.row === "number") {
    return t("headerRowLabel", { row: value.row });
  }
  if (operation === "normalize_column_names") return t("cleanHeadersLabel");
  if (operation === "drop_empty") return t("removeEmptyLabel");
  if (operation === "exclude_summary_rows") return t("removeSummaryLabel");
  return t("otherStepLabel");
}

function readonlyRecipeOperations(
  recipeOperations: Record<string, unknown>[],
  manualOperationKeys: Set<string>,
  t: VisualCleaningTranslator,
): ReadonlyCleaningOperation[] {
  const seen = new Set<string>();
  return recipeOperations.flatMap((operation) => {
    const key = rawOperationKey(operation);
    if (!key || manualOperationKeys.has(key) || seen.has(key)) return [];
    seen.add(key);
    return [{ key, label: readonlyOperationLabel(operation, t) }];
  });
}

function sampleColumns(snapshot: VisualCleaningSnapshot): string[] {
  const columns = new Set<string>();
  snapshot.sample.forEach((row) =>
    Object.keys(row).forEach((column) => columns.add(column)),
  );
  return Array.from(columns).slice(0, 8);
}

function SampleTable({
  title,
  snapshot,
}: {
  title: string;
  snapshot: VisualCleaningSnapshot;
}) {
  const locale = useLocale();
  const t = useTranslations("visualCleaning");
  const columns = sampleColumns(snapshot);
  return (
    <section className="min-w-0">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h4 className="text-sm font-semibold text-foreground">{title}</h4>
        <span className="text-xs text-muted-foreground">
          {t("summaryCounts", {
            rows: snapshot.rows.toLocaleString(locale),
            columns: snapshot.columns,
          })}
        </span>
      </div>
      <div className="max-h-64 overflow-auto border border-border bg-background">
        {columns.length ? (
          <table className="w-full min-w-max border-collapse text-left text-xs">
            <thead className="sticky top-0 bg-muted">
              <tr>
                {columns.map((column) => (
                  <th
                    key={column}
                    scope="col"
                    className="border-b border-r border-border px-3 py-2 font-semibold text-foreground last:border-r-0"
                  >
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {snapshot.sample.map((row: DataRow, rowIndex) => (
                <tr key={rowIndex} className="border-b border-border last:border-b-0">
                  {columns.map((column) => (
                    <td
                      key={column}
                      className="max-w-48 truncate border-r border-border px-3 py-2 text-foreground last:border-r-0"
                      title={String(row[column] ?? "")}
                    >
                      {row[column] === null || row[column] === ""
                        ? t("emptyCell")
                        : String(row[column] ?? t("emptyCell"))}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="px-4 py-8 text-center text-xs text-muted-foreground">
            {t("noSample")}
          </div>
        )}
      </div>
    </section>
  );
}

interface VisualCleaningEditorProps {
  source: ProjectDataSource;
  columns: string[];
  recipeOperations?: Record<string, unknown>[];
  onClose: () => void;
}

export function VisualCleaningEditor({
  source,
  columns,
  recipeOperations = [],
  onClose,
}: VisualCleaningEditorProps) {
  const locale = useLocale();
  const t = useTranslations("visualCleaning");

  const COLUMN_ACTIONS: Array<{
    value: Exclude<VisualCleaningAction, "drop_exact_duplicates">;
    label: string;
    description: string;
  }> = [
    {
      value: "trim_text",
      label: t("trimWhitespace"),
      description: t("trimWhitespaceDesc"),
    },
    {
      value: "fill_missing",
      label: t("fillZero"),
      description: t("fillZeroDesc"),
    },
    {
      value: "normalize_datetime",
      label: t("unifyDates"),
      description: t("unifyDatesDesc"),
    },
    {
      value: "normalize_currency",
      label: t("unifyAmounts"),
      description: t("unifyAmountsDesc"),
    },
  ];

  const firstColumn = columns[0] || "";
  const savedState = inspectSavedVisualCleaningOperations(
    source.profile_data.visual_cleaning,
  );
  const savedOperations = savedState.operations;
  const readonlyOperations = readonlyRecipeOperations(
    recipeOperations,
    savedState.operationKeys,
    t,
  );
  const readonlyOperationKeys = new Set(
    readonlyOperations.map((operation) => operation.key),
  );
  const hasUnsupportedSavedOperations = savedState.hasUnsupportedOperations;
  const [selectedColumn, setSelectedColumn] = useState(firstColumn);
  const [operations, setOperations] =
    useState<VisualCleaningOperation[]>(savedOperations);
  const [initialHadOperations, setInitialHadOperations] = useState(
    savedState.hasSavedOperations,
  );
  const [feedback, setFeedback] = useState<string | null>(null);
  const preview = useProjectStore(
    (state) => state.cleaningPreviewBySource[source.id],
  );
  const cleaningAction = useProjectStore((state) => state.cleaningAction);
  const previewSourceCleaning = useProjectStore(
    (state) => state.previewSourceCleaning,
  );
  const clearSourceCleaningPreview = useProjectStore(
    (state) => state.clearSourceCleaningPreview,
  );
  const applySourceCleaning = useProjectStore(
    (state) => state.applySourceCleaning,
  );
  const busy = cleaningAction?.sourceId === source.id;
  const changedCells = useMemo(
    () => preview?.changes.reduce((total, change) => total + change.changed_count, 0) || 0,
    [preview],
  );

  useEffect(() => {
    const nextState = inspectSavedVisualCleaningOperations(
      source.profile_data.visual_cleaning,
    );
    setOperations(nextState.operations);
    setInitialHadOperations(nextState.hasSavedOperations);
    setSelectedColumn(firstColumn);
    setFeedback(null);
    clearSourceCleaningPreview(source.id);
  }, [
    clearSourceCleaningPreview,
    firstColumn,
    source.id,
    source.profile_data.visual_cleaning,
  ]);

  const changeOperations = (next: VisualCleaningOperation[]) => {
    setOperations(next);
    setFeedback(null);
    clearSourceCleaningPreview(source.id);
  };

  const closeEditor = () => {
    clearSourceCleaningPreview(source.id);
    onClose();
  };

  const addOperation = (action: VisualCleaningAction) => {
    if (hasUnsupportedSavedOperations) {
      setFeedback(t("lockedHint"));
      return;
    }
    const operation = buildVisualCleaningOperation(action, selectedColumn);
    if (!operation) {
      setFeedback(t("pickColumn"));
      return;
    }
    if (operations.some((item) => operationKey(item) === operationKey(operation))) {
      setFeedback(t("stepAlreadyAdded"));
      return;
    }
    if (readonlyOperationKeys.has(operationKey(operation))) {
      setFeedback(t("stepDoneAtImport"));
      return;
    }
    changeOperations([...operations, operation]);
  };

  const handlePreview = async () => {
    if (hasUnsupportedSavedOperations) {
      setFeedback(t("lockedHint"));
      return;
    }
    setFeedback(null);
    try {
      await previewSourceCleaning(source.id, operations);
    } catch {
      setFeedback(t("previewFailed"));
    }
  };

  const canPreview =
    !hasUnsupportedSavedOperations &&
    (operations.length > 0 || initialHadOperations);

  const handleApply = async () => {
    if (hasUnsupportedSavedOperations) {
      setFeedback(t("lockedHint"));
      return;
    }
    setFeedback(null);
    try {
      await applySourceCleaning(source.id, operations);
      onClose();
    } catch {
      setFeedback(t("staleSnapshot"));
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/20"
      role="dialog"
      aria-modal="true"
      aria-labelledby="visual-cleaning-title"
    >
      <div className="flex h-full w-full max-w-[820px] flex-col bg-card shadow-2xl">
        <header className="flex items-start justify-between border-b border-border px-6 py-5">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-xs font-semibold text-primary">
              <Eraser size={15} />
              {t("sectionTitle")}
            </div>
            <h2 id="visual-cleaning-title" className="mt-1 truncate text-xl font-semibold text-foreground">
              {source.name}
            </h2>
          </div>
          <button
            type="button"
            onClick={closeEditor}
            className="p-2 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label={t("closeEditorAria")}
          >
            <X size={19} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          <section>
            <h3 className="text-sm font-semibold text-foreground">{t("addStep")}</h3>
            <div className="mt-3 grid gap-3 md:grid-cols-[minmax(180px,240px)_1fr]">
              <label className="text-xs font-medium text-muted-foreground">
                {t("selectColumn")}
                <select
                  aria-label={t("selectColumnAria")}
                  value={selectedColumn}
                  onChange={(event) => setSelectedColumn(event.target.value)}
                  className="mt-1.5 w-full border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none focus:border-primary"
                >
                  {columns.map((column) => (
                    <option key={column} value={column}>
                      {column}
                    </option>
                  ))}
                </select>
              </label>
              <div className="grid gap-2 sm:grid-cols-2">
                {COLUMN_ACTIONS.map((action) => (
                  <button
                    key={action.value}
                    type="button"
                    disabled={!columns.length || busy || hasUnsupportedSavedOperations}
                    onClick={() => addOperation(action.value)}
                    className="border border-border bg-background px-3 py-2 text-left hover:border-primary/60 hover:bg-primary/5 disabled:opacity-50"
                  >
                    <span className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
                      <Plus size={13} />
                      {action.label}
                    </span>
                    <span className="mt-0.5 block text-[11px] leading-4 text-muted-foreground">
                      {action.description}
                    </span>
                  </button>
                ))}
              </div>
            </div>
            <button
              type="button"
              disabled={busy || hasUnsupportedSavedOperations}
              onClick={() => addOperation("drop_exact_duplicates")}
              className="mt-3 inline-flex items-center gap-1.5 border border-border bg-background px-3 py-2 text-xs font-semibold text-foreground hover:border-primary/60 hover:bg-primary/5 disabled:opacity-50"
            >
              <Plus size={13} />
              {t("removeDuplicatesButton")}
            </button>
          </section>

          {hasUnsupportedSavedOperations && (
            <div
              role="alert"
              className="mt-4 border border-warning/30 bg-warning/[0.06] px-3 py-2 text-xs text-warning"
            >
              {t("readonlyNotice")}
            </div>
          )}

          <section className="mt-6 border-y border-border py-4">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-semibold text-foreground">
                {t("stepsSectionTitle")}
                {operations.length + readonlyOperations.length
                  ? ` · ${t("stepsSectionCount", { count: operations.length + readonlyOperations.length })}`
                  : ""}
              </h3>
              {canPreview && !preview && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void handlePreview()}
                  className="inline-flex items-center gap-1.5 bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground disabled:opacity-50"
                >
                  {busy && cleaningAction?.kind === "preview" ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <ArrowRight size={13} />
                  )}
                  {t("previewChanges")}
                </button>
              )}
            </div>
            {operations.length || readonlyOperations.length ? (
              <ol className="mt-3 divide-y divide-border border-y border-border">
                {operations.map((operation, index) => (
                  <li key={operationKey(operation)} className="flex items-center gap-3 py-2.5">
                    <span className="w-6 font-mono text-xs text-muted-foreground">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span className="min-w-0 flex-1 text-sm text-foreground">
                      {operationLabel(operation, t)}
                    </span>
                    <button
                      type="button"
                      disabled={busy || hasUnsupportedSavedOperations}
                      onClick={() =>
                        changeOperations(
                          operations.filter((_, operationIndex) => operationIndex !== index),
                        )
                      }
                      className="p-1.5 text-muted-foreground hover:text-destructive disabled:opacity-50"
                      aria-label={t("removeStepAria", { step: operationLabel(operation, t) })}
                    >
                      <Trash2 size={14} />
                    </button>
                  </li>
                ))}
                {readonlyOperations.map((operation, index) => (
                  <li key={operation.key} className="flex items-center gap-3 py-2.5">
                    <span className="w-6 font-mono text-xs text-muted-foreground">
                      {String(operations.length + index + 1).padStart(2, "0")}
                    </span>
                    <span className="min-w-0 flex-1 text-sm text-foreground">
                      {operation.label}
                    </span>
                    <span className="shrink-0 text-[11px] text-muted-foreground">
                      {t("importedNote")}
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="mt-3 text-xs text-muted-foreground">
                {hasUnsupportedSavedOperations
                  ? t("stepsKept")
                  : initialHadOperations
                  ? t("stepsCleared")
                  : t("stepsPlaceholder")}
              </p>
            )}
          </section>

          {preview && (
            <section className="mt-6" aria-label={t("previewAria")}>
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-foreground">{t("previewTitle")}</h3>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t("previewChangedCells", {
                      count: changedCells.toLocaleString(locale),
                    })}
                    {preview.before.rows !== preview.after.rows
                      ? t("previewRowsChange", {
                          before: preview.before.rows.toLocaleString(locale),
                          after: preview.after.rows.toLocaleString(locale),
                        })
                      : t("previewRowsUnchanged")}
                    {preview.before.columns !== preview.after.columns
                      ? t("previewColumnsChange", {
                          before: preview.before.columns,
                          after: preview.after.columns,
                        })
                      : t("previewColumnsUnchanged")}
                  </p>
                </div>
                {preview.can_apply && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void handleApply()}
                    className="inline-flex items-center gap-1.5 bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground disabled:opacity-50"
                  >
                    {busy && cleaningAction?.kind === "apply" ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Check size={14} />
                    )}
                    {t("applyButton")}
                  </button>
                )}
              </div>
              {preview.changes.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {preview.changes.map((change) => (
                    <span
                      key={change.column}
                      className="bg-success/[0.06] px-2.5 py-1 text-xs text-success"
                    >
                      {t("columnChangeLabel", {
                        column: change.column,
                        count: change.changed_count.toLocaleString(locale),
                      })}
                    </span>
                  ))}
                </div>
              )}
              <div className="mt-4 grid gap-5 xl:grid-cols-2">
                <SampleTable title={t("beforeLabel")} snapshot={preview.before} />
                <SampleTable title={t("afterLabel")} snapshot={preview.after} />
              </div>
            </section>
          )}

          {feedback && (
            <div role="alert" className="mt-4 border border-destructive/30 bg-destructive/[0.06] px-3 py-2 text-xs text-destructive">
              {feedback}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
