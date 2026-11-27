import React from "react";
import { AlertTriangle, ChevronDown, ChevronUp, RefreshCw } from "lucide-react";
import { captureFrontendError } from "../lib/errorMonitor";

interface ErrorBoundaryProps {
  sectionName: string;
  children: React.ReactNode;
  onReset?: () => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  componentStack: string;
  showDetails: boolean;
}

export default class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      componentStack: "",
      showDetails: false,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    const componentStack = info.componentStack || "";
    this.setState({ componentStack });
    captureFrontendError({
      category: "react_render",
      module: `ErrorBoundary:${this.props.sectionName}`,
      message: error.message || "Component rendering failure",
      severity: "critical",
      stack_trace: [error.stack || "", componentStack].filter(Boolean).join("\n"),
      context: { section: this.props.sectionName },
    });
  }

  handleRecover = (): void => {
    this.setState({ hasError: false, error: null, componentStack: "", showDetails: false });
    this.props.onReset?.();
  };

  render(): React.ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className="flex-1 min-h-0 flex items-center justify-center p-6 bg-app text-primary">
        <div className="w-full max-w-lg bg-card border border-danger/50 rounded-sm p-5 flex flex-col gap-3">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-xs bg-danger-bg border border-danger/40 text-danger flex items-center justify-center shrink-0">
              <AlertTriangle className="w-4 h-4" strokeWidth={1.8} />
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-semibold text-primary">
                {this.props.sectionName} encountered a rendering error
              </h2>
              <p className="text-xs text-secondary mt-1 break-words">
                {this.state.error?.message || "An unexpected UI error occurred."} The error has been
                logged to Error Intelligence.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={this.handleRecover}
              className="btn-primary h-8 px-3 text-xs"
            >
              <RefreshCw className="w-3.5 h-3.5" strokeWidth={1.7} />
              <span>Recover Section</span>
            </button>
            <button
              type="button"
              onClick={() => this.setState(s => ({ showDetails: !s.showDetails }))}
              className="btn-neutral h-8 px-3 text-xs"
            >
              {this.state.showDetails ? (
                <ChevronUp className="w-3.5 h-3.5" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5" />
              )}
              <span>{this.state.showDetails ? "Hide Stack" : "Inspect Stack"}</span>
            </button>
          </div>

          {this.state.showDetails && (
            <pre className="p-2.5 bg-input border border-subtle rounded-xs text-[11px] font-mono text-secondary overflow-auto max-h-48 whitespace-pre-wrap select-text">
              {this.state.error?.stack || "No stack trace available."}
              {this.state.componentStack}
            </pre>
          )}
        </div>
      </div>
    );
  }
}
