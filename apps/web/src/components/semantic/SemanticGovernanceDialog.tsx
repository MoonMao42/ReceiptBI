"use client";

import { Database, FileSpreadsheet, Loader2, Sparkles, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useLocale, useTranslations } from "next-intl";
import { api } from "@/lib/api/client";
import { useModalFocus } from "@/lib/use-modal-focus";
import { normalizeSemanticInventoryJob } from "@/components/semantic/semantic-inventory";
import {
  UserFacingError,
  type DataSourceRelationIndex,
  type ProjectDataSource,
  type RelationIndexRefreshResult,
  type SemanticInventoryDepth,
  type SemanticInventoryJob,
  type SemanticInventoryJobRequest,
  type SemanticRecommendationRequest,
  type SemanticRecommendationResult,
  type SemanticRecommendationScope,
} from "@/lib/types/api";

type Translate = (key: string, values?: Record<string, string | number>) => string;

interface SemanticGovernanceDialogProps {
  open: boolean;
  projectId: string;
  sources: ProjectDataSource[];
  modelId?: string | null;
  limit?: number;
  onClose: () => void;
  onGenerated?: (result: SemanticRecommendationResult) => void;
  onInventoryStarted?: (jobs: SemanticInventoryJob[]) => void;
  onCatalogRefreshed?: (source: ProjectDataSource) => void | Promise<void>;
}

type DatabaseMode = "all" | "selected";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function nonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

interface SourceTableOption {
  name: string;
  businessName: string;
  summary: string | null;
}

function qualifiedRelationName(record: Record<string, unknown>): string | null {
  const name = nonEmptyString(record.name);
  if (!name) return null;
  const schema = nonEmptyString(record.schema);
  return schema ? `${schema}.${name}` : name;
}

function relationIdentity(record: Record<string, unknown>): string | null {
  const name = nonEmptyString(record.name);
  if (!name) return null;
  return `${nonEmptyString(record.schema) || ""}\u0000${name}`;
}

function relationIndexForSource(source: ProjectDataSource): Record<string, unknown> {
  const preanalysis = isRecord(source.profile_data.preanalysis)
    ? source.profile_data.preanalysis
    : {};
  return isRecord(source.profile_data.relation_index)
    ? source.profile_data.relation_index
    : isRecord(preanalysis.relation_index)
      ? preanalysis.relation_index
      : {};
}

function mergedTableRecords(source: ProjectDataSource): Record<string, unknown>[] {
  const relationIndex = relationIndexForSource(source);
  const profiledTables = Array.isArray(source.profile_data.tables)
    ? source.profile_data.tables.filter(isRecord)
    : [];
  const indexedRelations = Array.isArray(relationIndex.relations)
    ? relationIndex.relations.filter(isRecord)
    : [];
  if (!indexedRelations.length) return profiledTables;

  const profilesByIdentity = new Map(
    profiledTables.flatMap((table) => {
      const identity = relationIdentity(table);
      return identity ? [[identity, table] as const] : [];
    })
  );
  const profilesByName = new Map<string, Record<string, unknown>[]>();
  for (const table of profiledTables) {
    const name = nonEmptyString(table.name);
    if (!name) continue;
    profilesByName.set(name, [...(profilesByName.get(name) || []), table]);
  }
  const indexedNameCounts = new Map<string, number>();
  for (const relation of indexedRelations) {
    const name = nonEmptyString(relation.name);
    if (name) indexedNameCounts.set(name, (indexedNameCounts.get(name) || 0) + 1);
  }

  const matchedProfiles = new Set<Record<string, unknown>>();
  const mergedRelations = indexedRelations.map((relation) => {
    const identity = relationIdentity(relation);
    const name = nonEmptyString(relation.name);
    const sameNamedProfiles = name ? profilesByName.get(name) || [] : [];
    const profile =
      (identity ? profilesByIdentity.get(identity) : undefined) ||
      (name && indexedNameCounts.get(name) === 1 && sameNamedProfiles.length === 1
        ? sameNamedProfiles[0]
        : undefined);
    if (profile) matchedProfiles.add(profile);
    return profile ? { ...profile, ...relation } : relation;
  });

  if (relationIndex.complete !== false) return mergedRelations;
  return [
    ...mergedRelations,
    ...profiledTables.filter((table) => !matchedProfiles.has(table)),
  ];
}

function sourceBusinessName(source: ProjectDataSource): string {
  const presentation = isRecord(source.profile_data.presentation)
    ? source.profile_data.presentation
    : {};
  return (
    nonEmptyString(source.profile_data.business_name) ||
    nonEmptyString(source.profile_data.display_name) ||
    nonEmptyString(presentation.business_name) ||
    source.name
  );
}

function tableDisplayName(value: string, locale: string): string {
  const relationName = value.split(".").at(-1) || value;
  if (locale === "en") {
    return relationName
      .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
      .split(/[^a-zA-Z0-9\u3400-\u9fff]+/)
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
  }
  const tokens = relationName
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .split(/[^a-zA-Z0-9\u3400-\u9fff]+/)
    .filter(Boolean);
  const year = tokens.find((token) => /^(?:19|20)\d{2}$/.test(token));
  const ignored = new Set(["d", "dim", "f", "fact", "info", "new", "tbl", "table", "v", "view"]);
  const labels: Record<string, string> = {
    center: "中心",
    cust: "客户",
    customer: "客户",
    customers: "客户",
    dict: "字典",
    order: "订单",
    orders: "订单",
    prd: "商品",
    product: "商品",
    products: "商品",
    refund: "退款",
    refunds: "退款",
    region: "地区",
    sales: "销售",
    sku: "商品",
    store: "门店",
    stores: "门店",
  };
  const rendered = tokens
    .filter((token) => token !== year && !ignored.has(token.toLowerCase()))
    .map((token) => {
      if (/[\u3400-\u9fff]/u.test(token)) return token;
      return labels[token.toLowerCase()] || token.toUpperCase();
    })
    .join("");
  if (year && rendered) return `${year} 年${rendered}资料`;
  return rendered ? `${rendered}资料` : "数据表";
}

function sourceTableOptions(source: ProjectDataSource, locale: string): SourceTableOption[] {
  if (source.kind !== "connection") return [];
  const seen = new Set<string>();
  return mergedTableRecords(source).flatMap((table) => {
    const name = qualifiedRelationName(table);
    if (!name || seen.has(name)) return [];
    seen.add(name);
    const documentedName =
      nonEmptyString(table.business_name) ||
      nonEmptyString(table.display_name) ||
      nonEmptyString(table.comment);
    return [
      {
        name,
        businessName: documentedName || tableDisplayName(name, locale),
        summary:
          nonEmptyString(table.description) ||
          nonEmptyString(table.business_topic) ||
          (documentedName === nonEmptyString(table.comment)
            ? null
            : nonEmptyString(table.comment)),
      },
    ];
  });
}

function parseRelationIndexRefresh(value: unknown): RelationIndexRefreshResult | null {
  if (!isRecord(value) || typeof value.source_id !== "string") return null;
  if (!isRecord(value.relation_index) || !Array.isArray(value.relation_index.relations)) {
    return null;
  }
  return value as unknown as RelationIndexRefreshResult;
}

function withRelationIndex(
  source: ProjectDataSource,
  relationIndex: DataSourceRelationIndex
): ProjectDataSource {
  const profile = source.profile_data;
  const preanalysis = isRecord(profile.preanalysis) ? profile.preanalysis : {};
  return {
    ...source,
    profile_data: {
      ...profile,
      relation_index: relationIndex,
      preanalysis: {
        ...preanalysis,
        relation_index: relationIndex,
      },
    },
  };
}

export function SemanticGovernanceDialog({
  open,
  projectId,
  sources,
  modelId,
  limit = 20,
  onClose,
  onGenerated,
  onInventoryStarted,
  onCatalogRefreshed,
}: SemanticGovernanceDialogProps) {
  const locale = useLocale();
  const t = useTranslations("projectUnderstanding.governanceDialog") as Translate;
  const [dialogSources, setDialogSources] = useState<ProjectDataSource[]>(sources);
  const readySources = useMemo(
    () => dialogSources.filter((source) => source.status === "ready"),
    [dialogSources]
  );
  const [selectedSourceIds, setSelectedSourceIds] = useState<Set<string>>(new Set());
  const [selectedTables, setSelectedTables] = useState<Record<string, string[]>>({});
  const [databaseModeBySource, setDatabaseModeBySource] = useState<
    Record<string, DatabaseMode>
  >({});
  const [depthBySource, setDepthBySource] = useState<
    Record<string, SemanticInventoryDepth>
  >({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [catalogRefreshBySource, setCatalogRefreshBySource] = useState<
    Record<string, "loading" | "ready" | "failed">
  >({});
  const dialogRef = useRef<HTMLElement>(null);
  const firstSourceRef = useRef<HTMLInputElement>(null);
  const sourcesRef = useRef(sources);
  const onCatalogRefreshedRef = useRef(onCatalogRefreshed);

  useEffect(() => {
    sourcesRef.current = sources;
    if (!open) setDialogSources(sources);
  }, [open, sources]);

  useEffect(() => {
    onCatalogRefreshedRef.current = onCatalogRefreshed;
  }, [onCatalogRefreshed]);

  useEffect(() => {
    if (!open) return;
    const initialSources = sourcesRef.current;
    const connections = initialSources.filter(
      (source) => source.kind === "connection" && source.status === "ready"
    );
    let active = true;
    setDialogSources(initialSources);
    setSelectedSourceIds(new Set());
    setSelectedTables({});
    setDatabaseModeBySource({});
    setDepthBySource({});
    setError(null);
    setCatalogRefreshBySource(
      Object.fromEntries(connections.map((source) => [source.id, "loading" as const]))
    );

    for (const source of connections) {
      void api
        .post(`/api/v1/projects/${projectId}/sources/${source.id}/relation-index`)
        .then((response) => {
          if (!active) return;
          const result = parseRelationIndexRefresh(response.data.data);
          if (!result || result.source_id !== source.id) throw new Error("invalid relation index");
          const refreshedSource = withRelationIndex(source, result.relation_index);
          setDialogSources((current) =>
            current.map((item) => (item.id === source.id ? refreshedSource : item))
          );
          setCatalogRefreshBySource((current) => ({ ...current, [source.id]: "ready" }));
          void Promise.resolve(onCatalogRefreshedRef.current?.(refreshedSource)).catch(
            () => undefined
          );
        })
        .catch(() => {
          if (!active) return;
          setCatalogRefreshBySource((current) => ({ ...current, [source.id]: "failed" }));
        });
    }

    return () => {
      active = false;
    };
  }, [open, projectId]);

  useModalFocus({
    active: open,
    containerRef: dialogRef,
    onClose,
    initialFocusRef: firstSourceRef,
  });

  const selectedSources = readySources.filter((source) => selectedSourceIds.has(source.id));
  const connectionWithoutTable = selectedSources.some(
    (source) =>
      source.kind === "connection" &&
      (databaseModeBySource[source.id] || "all") === "selected" &&
      !(selectedTables[source.id] || []).length
  );
  const canSubmit = selectedSources.length > 0 && !connectionWithoutTable && !submitting;

  if (!open) return null;

  const toggleSource = (source: ProjectDataSource) => {
    const removing = selectedSourceIds.has(source.id);
    setSelectedSourceIds((current) => {
      const next = new Set(current);
      if (next.has(source.id)) next.delete(source.id);
      else next.add(source.id);
      return next;
    });
    if (removing) {
      setSelectedTables((tables) => {
        const copy = { ...tables };
        delete copy[source.id];
        return copy;
      });
      setDatabaseModeBySource((modes) => {
        const copy = { ...modes };
        delete copy[source.id];
        return copy;
      });
      setDepthBySource((depths) => {
        const copy = { ...depths };
        delete copy[source.id];
        return copy;
      });
    } else if (source.kind === "connection") {
      setDatabaseModeBySource((current) => ({ ...current, [source.id]: "all" }));
      setDepthBySource((current) => ({ ...current, [source.id]: "structure" }));
    }
    setError(null);
  };

  const setDatabaseMode = (sourceId: string, mode: DatabaseMode) => {
    setDatabaseModeBySource((current) => ({ ...current, [sourceId]: mode }));
    setError(null);
  };

  const setInventoryDepth = (sourceId: string, depth: SemanticInventoryDepth) => {
    setDepthBySource((current) => ({ ...current, [sourceId]: depth }));
    setError(null);
  };

  const toggleTable = (sourceId: string, tableName: string) => {
    setSelectedTables((current) => {
      const selected = new Set(current[sourceId] || []);
      if (selected.has(tableName)) selected.delete(tableName);
      else selected.add(tableName);
      return { ...current, [sourceId]: Array.from(selected) };
    });
    setError(null);
  };

  const selectAllTables = (source: ProjectDataSource) => {
    const tables = sourceTableOptions(source, locale).map((table) => table.name);
    setSelectedTables((current) => ({
      ...current,
      [source.id]: (current[source.id] || []).length === tables.length ? [] : tables,
    }));
    setError(null);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) {
      setError(
        selectedSources.length === 0
          ? t("errors.sourceRequired")
          : t("errors.databaseTableRequired")
      );
      return;
    }
    const requestLocale = locale === "en" ? "en" : "zh";
    const databaseSources = selectedSources.filter(
      (source) => source.kind === "connection"
    );
    const fileSources = selectedSources.filter((source) => source.kind === "file");
    setSubmitting(true);
    setError(null);
    try {
      const databaseRequests = databaseSources.map(async (source) => {
        const mode = databaseModeBySource[source.id] || "all";
        const payload: SemanticInventoryJobRequest = {
          locale: requestLocale,
          tables: mode === "all" ? [] : selectedTables[source.id] || [],
          depth: mode === "all" ? "structure" : depthBySource[source.id] || "structure",
          ...(modelId ? { model_id: modelId } : {}),
        };
        const response = await api.post(
          `/api/v1/projects/${projectId}/sources/${source.id}/semantic-inventory-jobs`,
          payload
        );
        const job = normalizeSemanticInventoryJob(response.data.data);
        if (!job) throw new UserFacingError(t("errors.startFailed"));
        return job;
      });

      const fileRequest = fileSources.length
        ? (async () => {
            const scopes: SemanticRecommendationScope[] = fileSources.map((source) => ({
              source_id: source.id,
              tables: [],
            }));
            const payload: SemanticRecommendationRequest = {
              locale: requestLocale,
              scopes,
              limit,
              ...(modelId ? { model_id: modelId } : {}),
            };
            const response = await api.post(
              `/api/v1/projects/${projectId}/knowledge/recommendations`,
              payload
            );
            return response.data.data as SemanticRecommendationResult;
          })()
        : null;

      const [databaseResults, fileResult] = await Promise.all([
        Promise.allSettled(databaseRequests),
        fileRequest ? Promise.allSettled([fileRequest]) : Promise.resolve([]),
      ]);
      const startedJobs = databaseResults.flatMap((result) =>
        result.status === "fulfilled" ? [result.value] : []
      );
      const firstFileResult = fileResult[0];
      const fileRecommendation =
        firstFileResult?.status === "fulfilled" ? firstFileResult.value : undefined;
      const failedCount =
        databaseResults.filter((result) => result.status === "rejected").length +
        fileResult.filter((result) => result.status === "rejected").length;
      if (!startedJobs.length && !fileRecommendation) {
        const firstFailure = [...databaseResults, ...fileResult].find(
          (result) => result.status === "rejected"
        );
        throw firstFailure && firstFailure.status === "rejected"
          ? firstFailure.reason
          : new UserFacingError(t("errors.startFailed"));
      }

      if (startedJobs.length) onInventoryStarted?.(startedJobs);
      if (fileRecommendation) onGenerated?.(fileRecommendation);

      if (failedCount) {
        const failedSourceIds = new Set<string>();
        databaseResults.forEach((result, index) => {
          if (result.status === "rejected") failedSourceIds.add(databaseSources[index].id);
        });
        if (firstFileResult?.status === "rejected") {
          fileSources.forEach((source) => failedSourceIds.add(source.id));
        }
        // Keep only the failed selections active so a retry cannot create a
        // duplicate run for a source that has already started successfully.
        setSelectedSourceIds(failedSourceIds);
        setError(t("errors.partialStart", { count: failedCount }));
        return;
      }
      onClose();
    } catch {
      setError(t("errors.startFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/25 p-4">
      <section
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="semantic-governance-title"
        tabIndex={-1}
        className="flex max-h-[min(760px,calc(100dvh-2rem))] w-full max-w-2xl flex-col overflow-hidden bg-background shadow-2xl"
      >
        <div className="flex shrink-0 items-start justify-between border-b border-border px-5 py-5 sm:px-6">
          <div className="min-w-0 pr-4">
            <h2 id="semantic-governance-title" className="text-xl font-semibold">
              {t("title")}
            </h2>
          </div>
          <button
            type="button"
            aria-label={t("close")}
            onClick={onClose}
            className="p-2 text-muted-foreground hover:text-foreground"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-6">
            <div className="flex items-center justify-between gap-4">
              <h3 className="text-sm font-semibold">{t("scopeTitle")}</h3>
              <span className="shrink-0 text-xs text-muted-foreground">
                {t("readyCount", { count: readySources.length })}
              </span>
            </div>

            {readySources.length ? (
              <div className="mt-4 divide-y divide-border border-y border-border">
                {readySources.map((source, sourceIndex) => {
                  const selected = selectedSourceIds.has(source.id);
                  const tables = sourceTableOptions(source, locale);
                  const selectedForSource = selectedTables[source.id] || [];
                  const catalogRefresh = catalogRefreshBySource[source.id];
                  const catalogRefreshing = catalogRefresh === "loading";
                  const displayName = sourceBusinessName(source);
                  const databaseMode = databaseModeBySource[source.id] || "all";
                  const inventoryDepth = depthBySource[source.id] || "structure";
                  return (
                    <div key={source.id} className="py-4">
                      <label className="flex cursor-pointer items-start gap-3">
                        <input
                          ref={sourceIndex === 0 ? firstSourceRef : undefined}
                          type="checkbox"
                          aria-label={t("selectSource", { name: displayName })}
                          checked={selected}
                          disabled={submitting}
                          onChange={() => toggleSource(source)}
                          className="mt-1 accent-primary disabled:opacity-40"
                        />
                        <span className="flex min-w-0 flex-1 gap-3">
                          {source.kind === "connection" ? (
                            <Database size={17} className="mt-0.5 shrink-0 text-muted-foreground" />
                          ) : (
                            <FileSpreadsheet
                              size={17}
                              className="mt-0.5 shrink-0 text-muted-foreground"
                            />
                          )}
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-medium">
                              {displayName}
                            </span>
                            <span className="mt-1 block text-xs text-muted-foreground">
                              {source.kind === "file"
                                ? t("wholeFile")
                                : catalogRefreshing
                                  ? t("catalogRefreshing")
                                  : t("databaseTableCount", { count: tables.length })}
                            </span>
                            {source.kind === "connection" && catalogRefresh === "failed" ? (
                              <span
                                role="alert"
                                className="mt-1 block text-xs leading-5 text-warning"
                              >
                                {t("catalogRefreshFailed", { count: tables.length })}
                              </span>
                            ) : null}
                          </span>
                        </span>
                      </label>

                      {source.kind === "connection" && selected ? (
                        <div className="ml-7 mt-4 border-l border-border pl-5">
                          <fieldset>
                            <legend className="text-xs font-medium text-muted-foreground">
                              {t("databaseScope")}
                            </legend>
                            <div className="mt-2 grid gap-2 sm:grid-cols-2">
                              <label className="flex cursor-pointer items-start gap-2 border border-border px-3 py-3">
                                <input
                                  type="radio"
                                  name={`database-mode-${source.id}`}
                                  aria-label={t("wholeDatabase", { count: tables.length })}
                                  checked={databaseMode === "all"}
                                  disabled={submitting}
                                  onChange={() => setDatabaseMode(source.id, "all")}
                                  className="mt-0.5 accent-primary"
                                />
                                <span>
                                  <span className="block text-xs font-medium">
                                    {t("wholeDatabase", { count: tables.length })}
                                  </span>
                                  <span className="mt-1 block text-[11px] leading-4 text-muted-foreground">
                                    {t("wholeDatabaseHint")}
                                  </span>
                                </span>
                              </label>
                              <label className="flex cursor-pointer items-start gap-2 border border-border px-3 py-3">
                                <input
                                  type="radio"
                                  name={`database-mode-${source.id}`}
                                  aria-label={t("selectedTables")}
                                  checked={databaseMode === "selected"}
                                  disabled={submitting}
                                  onChange={() => setDatabaseMode(source.id, "selected")}
                                  className="mt-0.5 accent-primary"
                                />
                                <span>
                                  <span className="block text-xs font-medium">
                                    {t("selectedTables")}
                                  </span>
                                  <span className="mt-1 block text-[11px] leading-4 text-muted-foreground">
                                    {t("selectedTablesHint")}
                                  </span>
                                </span>
                              </label>
                            </div>
                          </fieldset>

                          {databaseMode === "selected" ? (
                            <>
                              <fieldset className="mt-4">
                                <legend className="text-xs font-medium text-muted-foreground">
                                  {t("organizeDepth")}
                                </legend>
                                <div className="mt-2 flex flex-wrap gap-x-5 gap-y-2 text-xs">
                                  <label className="inline-flex cursor-pointer items-center gap-2">
                                    <input
                                      type="radio"
                                      name={`inventory-depth-${source.id}`}
                                      aria-label={t("structureOnly")}
                                      checked={inventoryDepth === "structure"}
                                      disabled={submitting}
                                      onChange={() => setInventoryDepth(source.id, "structure")}
                                      className="accent-primary"
                                    />
                                    {t("structureOnly")}
                                  </label>
                                  <label className="inline-flex cursor-pointer items-center gap-2">
                                    <input
                                      type="radio"
                                      name={`inventory-depth-${source.id}`}
                                      aria-label={t("sampled")}
                                      checked={inventoryDepth === "sampled"}
                                      disabled={submitting}
                                      onChange={() => setInventoryDepth(source.id, "sampled")}
                                      className="accent-primary"
                                    />
                                    {t("sampled")}
                                  </label>
                                </div>
                              </fieldset>

                              <fieldset className="mt-4">
                                <legend className="flex w-full items-center justify-between gap-3 text-xs font-medium text-muted-foreground">
                                  <span>{t("chooseTables")}</span>
                                  {tables.length ? (
                                    <button
                                      type="button"
                                      disabled={submitting}
                                      onClick={() => selectAllTables(source)}
                                      className="text-primary hover:underline disabled:opacity-40"
                                    >
                                      {selectedForSource.length === tables.length
                                        ? t("clearTables")
                                        : t("selectAllTables")}
                                    </button>
                                  ) : null}
                                </legend>
                                {tables.length ? (
                                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                                    {tables.map((table) => (
                                      <label
                                        key={table.name}
                                        className="flex min-w-0 cursor-pointer items-center gap-2 border border-border px-3 py-2 text-sm"
                                      >
                                        <input
                                          type="checkbox"
                                          aria-label={t("selectTable", {
                                            source: displayName,
                                            table: table.businessName,
                                          })}
                                          checked={selectedForSource.includes(table.name)}
                                          disabled={submitting}
                                          onChange={() => toggleTable(source.id, table.name)}
                                          className="shrink-0 accent-primary"
                                        />
                                        <span className="min-w-0">
                                          <span className="block truncate text-xs font-medium">
                                            {table.businessName}
                                          </span>
                                          {table.summary ? (
                                            <span className="mt-0.5 line-clamp-2 block text-[11px] leading-4 text-muted-foreground">
                                              {table.summary}
                                            </span>
                                          ) : null}
                                        </span>
                                      </label>
                                    ))}
                                  </div>
                                ) : (
                                  <p className="mt-2 text-xs text-warning">
                                    {catalogRefreshing
                                      ? t("catalogRefreshing")
                                      : t("noProfiledTables")}
                                  </p>
                                )}
                                {!selectedForSource.length && tables.length ? (
                                  <p className="mt-2 text-xs text-warning">
                                    {t("databaseTableRequired")}
                                  </p>
                                ) : null}
                              </fieldset>
                            </>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="mt-4 border border-border px-4 py-8 text-center text-sm text-muted-foreground">
                {t("noReadySources")}
              </div>
            )}

            {error && (
              <div role="alert" className="mt-4 bg-destructive/[0.06] px-3 py-2 text-sm text-destructive">
                {error}
              </div>
            )}
          </div>

          <div className="flex shrink-0 flex-col-reverse gap-2 border-t border-border px-5 py-4 sm:flex-row sm:items-center sm:justify-end sm:px-6">
            <button
              type="button"
              onClick={onClose}
              className="h-10 px-4 text-sm text-muted-foreground hover:text-foreground"
            >
              {t("cancel")}
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              className="inline-flex h-10 items-center justify-center gap-2 bg-primary px-5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-45"
            >
              {submitting ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
              {submitting ? t("starting") : t("start")}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
