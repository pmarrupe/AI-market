import { Component } from "react";

/**
 * Top-level error boundary so a thrown error in any child renders a fallback
 * UI instead of leaving the user with a blank white page. Logs the error +
 * stack so we can see what blew up in the browser console.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary] caught:", error, info);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="error-boundary">
        <div className="error-boundary__card">
          <h2>Something broke while rendering.</h2>
          <p className="detail-meta">
            The page hit a JavaScript error. Check the browser console for the
            stack trace, then click <strong>Try again</strong>. If it keeps
            happening, copy the console error and tell us.
          </p>
          <pre className="error-boundary__stack">
            {String(this.state.error?.message || this.state.error)}
          </pre>
          <div className="error-boundary__actions">
            <button type="button" onClick={this.reset}>Try again</button>
            <button type="button" onClick={() => window.location.reload()}>Hard reload</button>
          </div>
        </div>
      </div>
    );
  }
}
