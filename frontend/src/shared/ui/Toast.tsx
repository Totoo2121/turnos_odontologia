import "./Toast.css";

export type ToastKind = "info" | "success" | "error";

interface ToastProps {
  message: string | null;
  kind?: ToastKind;
  onDismiss: () => void;
}

/** Un mensaje por vez; la cola (si se necesita) vive en cada feature. */
export function Toast({ message, kind = "info", onDismiss }: ToastProps): JSX.Element | null {
  return message === null ? null : (
    <div role="status" data-kind={kind} className="toast">
      <p className="toast-message">{message}</p>
      <button type="button" aria-label="Descartar" onClick={onDismiss}>
        ×
      </button>
    </div>
  );
}
