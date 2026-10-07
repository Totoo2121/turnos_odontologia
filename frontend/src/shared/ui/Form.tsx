import type { FormEvent, ReactNode } from "react";
import "./Form.css";

interface FormProps {
  onSubmit: () => void;
  children: ReactNode;
}

/** Form minimal: previene el submit nativo y delega en `onSubmit`. */
export function Form({ onSubmit, children }: FormProps): JSX.Element {
  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    onSubmit();
  }

  return <form onSubmit={handleSubmit}>{children}</form>;
}

interface FieldProps {
  htmlFor: string;
  label: string;
  error?: string;
  children: ReactNode;
}

/** Field presenta label + control + error por prop (la validación vive en cada feature). */
export function Field({ htmlFor, label, error, children }: FieldProps): JSX.Element {
  const showError = error !== undefined && error !== "";
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {showError ? <p role="alert" className="field-error">{error}</p> : null}
    </div>
  );
}
