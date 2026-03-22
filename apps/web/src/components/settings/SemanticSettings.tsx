"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Loader2, Pencil, X, BookOpen } from "lucide-react";
import { api } from "@/lib/api/client";
import { useTranslations } from "next-intl";

interface SemanticTerm {
  id: string;
  term: string;
  expression: string;
  term_type: string;
  connection_id?: string;
  description?: string;
  examples: string[];
  is_active: boolean;
  created_at: string;
}

interface TermFormData {
  term: string;
  expression: string;
  term_type: string;
  connection_id: string;
  description: string;
  examples: string;
}

const initialFormData: TermFormData = {
  term: "",
  expression: "",
  term_type: "metric",
  connection_id: "",
  description: "",
  examples: "",
};

export function SemanticSettings() {
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formData, setFormData] = useState<TermFormData>(initialFormData);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const t = useTranslations("semantic");
  const tc = useTranslations("common");

  const TERM_TYPES = [
    { value: "metric", label: t("typeMetric"), description: t("typeMetricDesc") },
    { value: "dimension", label: t("typeDimension"), description: t("typeDimensionDesc") },
    { value: "filter", label: t("typeFilter"), description: t("typeFilterDesc") },
    { value: "alias", label: t("typeAlias"), description: t("typeAliasDesc") },
  ];

  const { data: terms, isLoading } = useQuery({
    queryKey: ["semantic-terms"],
    queryFn: async () => {
      const response = await api.get("/api/v1/config/semantic/terms");
      return response.data.data as SemanticTerm[];
    },
  });

  const { data: connections } = useQuery({
    queryKey: ["connections"],
    queryFn: async () => {
      const response = await api.get("/api/v1/config/connections");
      return response.data.data as { id: string; name: string }[];
    },
  });

  const addMutation = useMutation({
    mutationFn: async (data: TermFormData) => {
      const payload = {
        term: data.term,
        expression: data.expression,
        term_type: data.term_type,
        connection_id: data.connection_id || null,
        description: data.description || null,
        examples: data.examples ? data.examples.split("\n").filter(Boolean) : [],
      };
      const response = await api.post("/api/v1/config/semantic/terms", payload);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["semantic-terms"] });
      resetForm();
    },
    onError: (err) => {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(axiosErr.response?.data?.detail || t("addFailed"));
    },
  });

  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: TermFormData }) => {
      const payload = {
        term: data.term,
        expression: data.expression,
        term_type: data.term_type,
        connection_id: data.connection_id || null,
        description: data.description || null,
        examples: data.examples ? data.examples.split("\n").filter(Boolean) : [],
      };
      const response = await api.put(`/api/v1/config/semantic/terms/${id}`, payload);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["semantic-terms"] });
      resetForm();
    },
    onError: (err) => {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(axiosErr.response?.data?.detail || t("updateFailed"));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/v1/config/semantic/terms/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["semantic-terms"] });
    },
    onError: (err) => {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(axiosErr.response?.data?.detail || t("deleteFailed"));
    },
  });

  const resetForm = () => {
    setShowForm(false);
    setEditingId(null);
    setFormData(initialFormData);
    setError(null);
  };

  const handleEdit = (term: SemanticTerm) => {
    setEditingId(term.id);
    setFormData({
      term: term.term,
      expression: term.expression,
      term_type: term.term_type,
      connection_id: term.connection_id || "",
      description: term.description || "",
      examples: term.examples.join("\n"),
    });
    setShowForm(true);
    setError(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (editingId) {
      updateMutation.mutate({ id: editingId, data: formData });
    } else {
      addMutation.mutate(formData);
    }
  };

  const handleDelete = (id: string) => {
    if (confirm(t("confirmDelete"))) {
      deleteMutation.mutate(id);
    }
  };

  const isSubmitting = addMutation.isPending || updateMutation.isPending;

  const getTermTypeLabel = (type: string) => {
    return TERM_TYPES.find((tt) => tt.value === type)?.label || type;
  };

  const getTermTypeColor = (type: string) => {
    switch (type) {
      case "metric":
        return "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400";
      case "dimension":
        return "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400";
      case "filter":
        return "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400";
      case "alias":
        return "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400";
      default:
        return "bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400";
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-foreground">{t("title")}</h2>
          <p className="text-sm text-muted-foreground mt-1">
            {t("description")}
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors text-sm"
        >
          <Plus size={16} />
          {t("addTerm")}
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-destructive/10 border border-destructive/20 rounded-lg flex items-center justify-between">
          <span className="text-sm text-destructive">{error}</span>
          <button onClick={() => setError(null)} className="text-destructive/60 hover:text-destructive">
            <X size={16} />
          </button>
        </div>
      )}

      {showForm && (
        <form
          onSubmit={handleSubmit}
          className="mb-6 p-4 bg-secondary rounded-lg border border-border"
        >
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-medium text-foreground">
              {editingId ? t("editTerm") : t("addTerm")}
            </h3>
            <button type="button" onClick={resetForm} className="text-muted-foreground hover:text-foreground">
              <X size={18} />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                {t("termName")} *
              </label>
              <input
                type="text"
                value={formData.term}
                onChange={(e) => setFormData({ ...formData, term: e.target.value })}
                className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:ring-2 focus:ring-ring focus:border-transparent"
                placeholder={t("termNamePlaceholder")}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                {t("termType")}
              </label>
              <select
                value={formData.term_type}
                onChange={(e) => setFormData({ ...formData, term_type: e.target.value })}
                className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:ring-2 focus:ring-ring focus:border-transparent"
              >
                {TERM_TYPES.map((tt) => (
                  <option key={tt.value} value={tt.value}>
                    {tt.label} - {tt.description}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-span-2">
              <label className="block text-sm font-medium text-foreground mb-1">
                {t("sqlExpression")} *
              </label>
              <input
                type="text"
                value={formData.expression}
                onChange={(e) => setFormData({ ...formData, expression: e.target.value })}
                className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground font-mono text-sm focus:ring-2 focus:ring-ring focus:border-transparent"
                placeholder={t("sqlExpressionPlaceholder")}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                {t("linkedConnection")}
              </label>
              <select
                value={formData.connection_id}
                onChange={(e) => setFormData({ ...formData, connection_id: e.target.value })}
                className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:ring-2 focus:ring-ring focus:border-transparent"
              >
                <option value="">{t("globalAllConnections")}</option>
                {connections?.map((conn) => (
                  <option key={conn.id} value={conn.id}>
                    {conn.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                {t("descriptionOptional")}
              </label>
              <input
                type="text"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:ring-2 focus:ring-ring focus:border-transparent"
                placeholder={t("descriptionPlaceholder")}
              />
            </div>
            <div className="col-span-2">
              <label className="block text-sm font-medium text-foreground mb-1">
                {t("examplesOptional")}
              </label>
              <textarea
                value={formData.examples}
                onChange={(e) => setFormData({ ...formData, examples: e.target.value })}
                className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:ring-2 focus:ring-ring focus:border-transparent"
                placeholder={t("examplesPlaceholder")}
                rows={2}
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-4">
            <button
              type="button"
              onClick={resetForm}
              className="px-4 py-2 text-muted-foreground hover:bg-muted rounded-lg transition-colors text-sm"
            >
              {tc("cancel")}
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors text-sm"
            >
              {isSubmitting && <Loader2 size={16} className="animate-spin" />}
              {editingId ? tc("update") : tc("save")}
            </button>
          </div>
        </form>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="animate-spin text-muted-foreground" size={24} />
        </div>
      ) : terms && terms.length > 0 ? (
        <div className="space-y-3">
          {terms.map((term) => (
            <div
              key={term.id}
              className="p-4 bg-secondary rounded-lg border border-border"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-foreground">{term.term}</span>
                    <span className={`px-2 py-0.5 text-xs rounded-full ${getTermTypeColor(term.term_type)}`}>
                      {getTermTypeLabel(term.term_type)}
                    </span>
                  </div>
                  <code className="text-sm text-muted-foreground bg-muted px-2 py-1 rounded font-mono">
                    {term.expression}
                  </code>
                  {term.description && (
                    <p className="text-sm text-muted-foreground mt-2">{term.description}</p>
                  )}
                  {term.examples.length > 0 && (
                    <div className="flex items-center gap-1 mt-2 text-xs text-muted-foreground">
                      <BookOpen size={12} />
                      <span>{t("examples")}: {term.examples.slice(0, 2).join(", ")}</span>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-1 ml-4">
                  <button
                    onClick={() => handleEdit(term)}
                    className="p-2 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded-lg transition-colors"
                    title={tc("edit")}
                  >
                    <Pencil size={16} />
                  </button>
                  <button
                    onClick={() => handleDelete(term.id)}
                    disabled={deleteMutation.isPending}
                    className="p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors"
                    title={tc("delete")}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          <BookOpen size={48} className="mx-auto mb-4 opacity-50" />
          <p>{t("emptyState")}</p>
          <p className="text-sm mt-1">{t("emptyStateHint")}</p>
        </div>
      )}
    </div>
  );
}
