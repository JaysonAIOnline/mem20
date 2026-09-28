import React from "react";

export function ErrorBanner({ title = "Request failed", error, onRetry, onDismiss, children }) {
  if (!error && !children) return null;
  const status = error && error.status ? `HTTP ${error.status}` : error && error.timedOut ? "timed out" : "error";
  return (
    <div className="banner banner-error" role="alert">
      <div className="banner-head">
        <strong>{title}</strong>
        <span className="banner-tag">{status}</span>
        {onRetry ? (
          <button type="button" className="btn btn-small" onClick={onRetry}>
            retry
          </button>
        ) : null}
        {onDismiss ? (
          <button type="button" className="btn btn-small" onClick={onDismiss}>
            dismiss
          </button>
        ) : null}
      </div>
      {error ? <div className="banner-msg">{error.message}</div> : null}
      {error && error.url ? <div className="banner-sub">endpoint: {error.url}</div> : null}
      {children}
    </div>
  );
}

export function NoticeBanner({ tone = "info", title, children, onDismiss }) {
  if (!children && !title) return null;
  return (
    <div className={`banner banner-${tone}`}>
      <div className="banner-head">
        {title ? <strong>{title}</strong> : null}
        {onDismiss ? (
          <button type="button" className="btn btn-small" onClick={onDismiss}>
            dismiss
          </button>
        ) : null}
      </div>
      <div className="banner-msg">{children}</div>
    </div>
  );
}

export function IdleNotice({ what, onLoad, loaded }) {
  return (
    <div className="banner banner-idle">
      <div className="banner-head">
        <strong>{what} not loaded</strong>
        {onLoad ? (
          <button type="button" className="btn btn-small" onClick={onLoad}>
            load
          </button>
        ) : null}
      </div>
      <div className="banner-msg">
        {loaded
          ? "No rows returned by the API for this view."
          : "This view has not requested data yet — nothing is shown because nothing has been fetched."}
      </div>
    </div>
  );
}
