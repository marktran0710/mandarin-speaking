import { Component, ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        this.props.fallback ?? (
          <div
            style={{
              padding: "40px 24px",
              textAlign: "center",
              fontFamily: "var(--font-sans, system-ui, sans-serif)",
              color: "var(--clay-ink, #1c1a17)",
            }}
          >
            <div style={{ fontSize: "2.5rem", marginBottom: "12px" }}>⚠️</div>
            <h2 style={{ margin: "0 0 8px", fontSize: "1.2rem" }}>
              Something went wrong
            </h2>
            <p style={{ color: "var(--clay-muted, #8a8275)", marginBottom: "20px", fontSize: "14px" }}>
              {this.state.error.message}
            </p>
            <button
              type="button"
              onClick={() => this.setState({ error: null })}
              style={{
                padding: "8px 20px",
                background: "var(--seal, #b3312c)",
                color: "#fff",
                border: "none",
                borderRadius: "10px",
                cursor: "pointer",
                fontSize: "14px",
              }}
            >
              Try again
            </button>
          </div>
        )
      );
    }
    return this.props.children;
  }
}
