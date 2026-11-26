/**
 * Keeps one page's failure inside that page.
 *
 * Without a boundary a render error anywhere in a workspace unmounts the whole app and leaves a
 * blank white screen with no way back but a reload (seen on the demo's Network page when the
 * map could not start). The boundary shows what happened in plain words, names the page, and
 * offers Try again (re-mount the page) and Reload; the top bar and navigation stay usable, so
 * the user can move on to another page. The technical message is kept behind Details for a
 * support request, never as the headline.
 */
import { Component, type ErrorInfo, type ReactNode } from "react";

type Translate = (key: string, options?: Record<string, unknown>) => string;

interface Props {
  t: Translate;
  /** Changes when the user navigates: a new page gets a fresh try. */
  resetKey: string;
  children: ReactNode;
}

interface State {
  error: Error | null;
  key: string;
}

export class PanelErrorBoundary extends Component<Props, State> {
  state: State = { error: null, key: this.props.resetKey };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  static getDerivedStateFromProps(
    props: Props,
    state: State,
  ): Partial<State> | null {
    // Moving to another page clears the failure, so one broken page never blocks the rest.
    if (props.resetKey !== state.key)
      return { error: null, key: props.resetKey };
    return null;
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(
      "Workspace page failed to render",
      error,
      info.componentStack,
    );
  }

  private retry = () => this.setState({ error: null });

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    const { t } = this.props;
    return (
      <section
        className="panel-error"
        role="alert"
        aria-live="assertive"
        data-panel-error="true"
      >
        <h2 className="panel-error__title">{t("panel_error.title")}</h2>
        <p className="panel-error__body">{t("panel_error.body")}</p>
        <div className="panel-error__actions">
          <button type="button" className="button-primary" onClick={this.retry}>
            {t("panel_error.retry")}
          </button>
          <button type="button" onClick={() => window.location.reload()}>
            {t("panel_error.reload")}
          </button>
        </div>
        <details className="panel-error__details">
          <summary>{t("panel_error.details")}</summary>
          <code>{error.message || String(error)}</code>
        </details>
      </section>
    );
  }
}
