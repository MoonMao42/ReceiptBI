"use client";

import { Component, ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

interface ErrorFallbackProps {
  error: Error | null;
  onReset: () => void;
  onReload: () => void;
}

function ErrorFallback({ error, onReset, onReload }: ErrorFallbackProps) {
  const t = useTranslations("errors");

  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] p-8 bg-background">
      <div className="flex flex-col items-center max-w-md text-center">
        <div className="w-16 h-16 rounded-full bg-destructive/10 flex items-center justify-center mb-4">
          <AlertTriangle className="w-8 h-8 text-destructive" />
        </div>

        <h2 className="text-xl font-semibold text-foreground mb-2">
          {t("somethingWrong")}
        </h2>

        <p className="text-muted-foreground mb-6">
          {t("unexpectedError")}
        </p>

        {process.env.NODE_ENV === "development" && error && (
          <details className="w-full mb-6 text-left">
            <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">
              {t("viewDetails")}
            </summary>
            <pre className="mt-2 p-4 bg-secondary rounded-lg text-xs text-destructive overflow-auto max-h-40">
              {error.message}
              {"\n\n"}
              {error.stack}
            </pre>
          </details>
        )}

        <div className="flex gap-3">
          <button
            onClick={onReset}
            className="px-4 py-2 text-sm font-medium text-foreground bg-secondary hover:bg-muted rounded-lg transition-colors"
          >
            {t("retry")}
          </button>
          <button
            onClick={onReload}
            className="px-4 py-2 text-sm font-medium text-primary-foreground bg-primary hover:bg-primary/90 rounded-lg transition-colors flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            {t("refreshPage")}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * React Error Boundary component
 * Catches JavaScript errors in child component tree and displays a fallback UI
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    // Log errors to error reporting service here
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null });
  };

  handleReload = (): void => {
    window.location.reload();
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <ErrorFallback
          error={this.state.error}
          onReset={this.handleReset}
          onReload={this.handleReload}
        />
      );
    }

    return this.props.children;
  }
}

/**
 * Wraps an async component with an Error Boundary
 */
export function withErrorBoundary<P extends object>(
  WrappedComponent: React.ComponentType<P>,
  fallback?: ReactNode
): React.FC<P> {
  return function WithErrorBoundary(props: P) {
    return (
      <ErrorBoundary fallback={fallback}>
        <WrappedComponent {...props} />
      </ErrorBoundary>
    );
  };
}
