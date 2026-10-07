import { useEffect, useRef, type ReactNode } from "react";
import "./Modal.css";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}

/** Diálogo controlado por `open` (ternario, nunca `&&`): Escape y botón cierran. */
export function Modal({ open, onClose, title, children }: ModalProps): JSX.Element | null {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    dialogRef.current?.focus();
    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open, onClose]);

  return open ? (
    <div className="modal-overlay">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} className="modal-dialog">
        <div className="modal-header">
          <h2>{title}</h2>
          <button type="button" aria-label="Cerrar" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  ) : null;
}
