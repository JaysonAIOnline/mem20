import React from "react";

export function TabBar({ tabs, active, onChange, label = "views" }) {
  return (
    <div className="tabbar" role="tablist" aria-label={label}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={active === tab.id}
          className={`tab${active === tab.id ? " tab-active" : ""}`}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
          {tab.badge !== undefined && tab.badge !== null ? <span className="tab-badge">{tab.badge}</span> : null}
        </button>
      ))}
    </div>
  );
}

export function Panel({ title, subtitle, actions, children, className = "", scroll = false }) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <header className="panel-head">
          <div className="panel-titles">
            {title ? <h2>{title}</h2> : null}
            {subtitle ? <span className="panel-sub">{subtitle}</span> : null}
          </div>
          {actions ? <div className="panel-actions">{actions}</div> : null}
        </header>
      )}
      <div className={scroll ? "panel-body panel-scroll" : "panel-body"}>{children}</div>
    </section>
  );
}

export function Section({ title, children, actions }) {
  return (
    <div className="block">
      <div className="block-head">
        <h3>{title}</h3>
        {actions ? <div className="block-actions">{actions}</div> : null}
      </div>
      {children}
    </div>
  );
}

export function Row({ label, children, mono = false }) {
  return (
    <div className="row">
      <span className="row-label">{label}</span>
      <span className={`row-value${mono ? " mono" : ""}`}>{children}</span>
    </div>
  );
}

export function Grid({ items, columns = 4 }) {
  return (
    <div className="grid" style={{ "--cols": columns }}>
      {items.map((item) => (
        <div className="cell" key={item.label}>
          <span className="cell-label">{item.label}</span>
          {/* A cell is a summary line, not a data structure. Rendering a raw
              object or array here throws away the whole React tree, and the
              failure names neither the component nor the field - so values are
              stringified here, exactly as `Table` already does for its cells. */}
          <span className={`cell-value ${item.tone ? `tone-${item.tone}` : ""}`}>{cellText(item.value)}</span>
          {item.hint ? <span className="cell-hint">{item.hint}</span> : null}
        </div>
      ))}
    </div>
  );
}

function cellText(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") {
    if (Array.isArray(value)) return value.length ? `${value.length} item(s)` : "—";
    return `${Object.keys(value).length} field(s)`;
  }
  return String(value);
}

export function Chips({ values, empty = "none reported" }) {
  if (!Array.isArray(values) || values.length === 0) {
    return <span className="muted">{empty}</span>;
  }
  return (
    <span className="chips">
      {values.map((value, index) => (
        <code className="chip" key={`${String(value)}-${index}`}>
          {String(value)}
        </code>
      ))}
    </span>
  );
}

export function Mono({ value, className = "" }) {
  if (value === null || value === undefined || value === "") {
    return <span className="muted">not reported</span>;
  }
  return <span className={`mono ${className}`}>{String(value)}</span>;
}

export function YesNo({ value }) {
  // A boolean data field is not a health signal: render it neutrally. Colour here
  // would imply a fault the API never reported.
  if (value === true) return <span className="bool">yes</span>;
  if (value === false) return <span className="bool">no</span>;
  return <span className="muted">not reported</span>;
}

export function Json({ value, empty = "no data" }) {
  if (value === null || value === undefined) {
    return <pre className="json empty">{empty}</pre>;
  }
  let text;
  try {
    text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  } catch {
    text = String(value);
  }
  return <pre className="json">{text}</pre>;
}

export function Table({ columns, rows, empty = "no rows returned by the API", rowKey, onRowClick, selectedKey }) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return <div className="table-empty">{empty}</div>;
  }
  return (
    <div className="table-wrap">
      <table className="grid-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} style={column.width ? { width: column.width } : undefined}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const key = rowKey ? rowKey(row, index) : index;
            return (
              <tr
                key={key}
                className={`${onRowClick ? "clickable" : ""} ${selectedKey !== undefined && selectedKey === key ? "selected" : ""}`}
                onClick={onRowClick ? () => onRowClick(row, index) : undefined}
              >
                {columns.map((column) => (
                  <td key={column.key} className={column.className || ""}>
                    {column.render ? column.render(row, index) : row[column.key] === undefined ? <span className="muted">—</span> : String(row[column.key])}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
