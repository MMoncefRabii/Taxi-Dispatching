import {
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type KeyboardEvent,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger";
}) {
  const variantClass = variant === "primary" ? "btn" : `btn secondary${variant === "danger" ? " danger-button" : ""}`;
  return <button {...props} className={`${variantClass} ${className}`.trim()} />;
}

export function Field({
  label,
  id,
  className = "",
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; id: string }) {
  return (
    <div className={`form-field ${className}`.trim()}>
      <label htmlFor={id}>{label}</label>
      <input id={id} {...props} />
    </div>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "online" | "stale" | "offline" | "active" | "inactive" | "self" | "neutral";
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function Table({
  children,
  label,
}: {
  children: ReactNode;
  label: string;
}) {
  return (
    <div className="table-scroll">
      <table aria-label={label}>{children}</table>
    </div>
  );
}

export function ErrorBanner({ children }: { children: ReactNode }) {
  if (!children) return null;
  return <p className="error" role="alert" aria-live="polite">{children}</p>;
}

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

export function Dialog({
  open,
  title,
  onClose,
  children,
  className = "",
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  className?: string;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      dialog.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)?.focus();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  function trapFocus(event: KeyboardEvent<HTMLDialogElement>) {
    if (event.key !== "Tab") return;
    const dialog = dialogRef.current;
    if (!dialog) return;
    const focusable = [...dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)];
    if (!focusable.length) {
      event.preventDefault();
      dialog.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className={`shared-dialog ${className}`.trim()}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onKeyDown={trapFocus}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section className="dialog-box">
        <h2 id={titleId}>{title}</h2>
        {children}
      </section>
    </dialog>
  );
}

export interface SecretEntry {
  label: string;
  value: string;
  copyLabel: string;
}

export function OneTimeSecretDialog({
  open,
  title,
  warning,
  entries,
  onClose,
}: {
  open: boolean;
  title: string;
  warning: string;
  entries: SecretEntry[];
  onClose: () => void;
}) {
  const [copyMessage, setCopyMessage] = useState("");
  const visibleEntries = open ? entries : [];

  function closeAndClear() {
    setCopyMessage("");
    onClose();
  }

  async function copyEntry(entry: SecretEntry) {
    try {
      await navigator.clipboard.writeText(entry.value);
      setCopyMessage(`${entry.copyLabel} copied.`);
    } catch {
      setCopyMessage(`Could not copy ${entry.label.toLowerCase()}. Select it and copy manually.`);
    }
  }

  return (
    <Dialog open={open} title={title} onClose={closeAndClear} className="secret-dialog">
      <p className="token-warning">{warning}</p>
      {visibleEntries.map((entry) => (
        <div className="secret-entry" key={entry.label}>
          <p className="secret-label">{entry.label}</p>
          <code className="token-value">
            {entry.value}
          </code>
          <Button type="button" variant="secondary" onClick={() => void copyEntry(entry)}>
            Copy {entry.copyLabel}
          </Button>
        </div>
      ))}
      <ErrorBanner>{copyMessage}</ErrorBanner>
      <div className="dialog-actions">
        <Button type="button" onClick={closeAndClear}>Close</Button>
      </div>
    </Dialog>
  );
}
