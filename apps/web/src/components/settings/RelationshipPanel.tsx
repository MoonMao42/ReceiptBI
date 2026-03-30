"use client";

import { Lightbulb, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import type {
  RelationshipSuggestion,
  TableRelationship,
} from "@/lib/types/schema";

interface RelationshipPanelProps {
  suggestions: RelationshipSuggestion[];
  relationships: TableRelationship[];
  isLoading: boolean;
  onApplySuggestion: (suggestion: RelationshipSuggestion) => void;
  onDeleteRelationship: (id: string) => void;
}

export function RelationshipPanel({
  suggestions,
  relationships,
  isLoading,
  onApplySuggestion,
  onDeleteRelationship,
}: RelationshipPanelProps) {
  const t = useTranslations("schema");

  if (suggestions.length === 0 && relationships.length === 0) {
    return null;
  }

  return (
    <div className="space-y-4 mb-4">
      {/* Suggestions Panel */}
      {suggestions.length > 0 && (
        <div className="p-3 bg-primary/5 border border-primary/20 rounded-lg">
          <div className="flex items-center gap-2 text-primary text-sm font-medium mb-2">
            <Lightbulb size={14} />
            {t("detectedRelationships")}
          </div>
          <div className="flex flex-wrap gap-2">
            {suggestions.slice(0, 5).map((suggestion, index) => (
              <button
                key={index}
                onClick={() => onApplySuggestion(suggestion)}
                disabled={isLoading}
                className="px-2 py-1 text-xs bg-background border border-border rounded hover:border-primary transition-colors disabled:opacity-50"
                title={`Confidence: ${(suggestion.confidence * 100).toFixed(0)}%`}
              >
                {suggestion.source_table}.{suggestion.source_column} → {suggestion.target_table}.
                {suggestion.target_column}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Existing Relationships */}
      {relationships.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {relationships.map((rel) => (
            <div
              key={rel.id}
              className="flex items-center gap-2 px-2 py-1 text-xs bg-primary/10 text-primary rounded"
            >
              <span>
                {rel.source_table}.{rel.source_column} → {rel.target_table}.{rel.target_column}
              </span>
              <button
                onClick={() => onDeleteRelationship(rel.id)}
                disabled={isLoading}
                className="hover:text-destructive disabled:opacity-50"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
