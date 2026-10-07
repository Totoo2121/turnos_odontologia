/** RED — task 4.2: Form/Field + Toast controlados. Datos ficticios. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Field, Form } from "./Form";
import { Toast } from "./Toast";

describe("shared/ui Form+Toast (RED 4.2)", () => {
  beforeEach(() => {
    cleanup();
  });

  it("Field muestra el error con el texto exacto", () => {
    render(
      <Form onSubmit={() => {}}>
        <Field htmlFor="f-email" label="Email" error="El email ficticio es obligatorio">
          <input id="f-email" name="email" />
        </Field>
      </Form>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("El email ficticio es obligatorio");
  });

  it("TRIANGULATE: Field sin error no muestra alerta", () => {
    render(
      <Field htmlFor="f-email" label="Email">
        <input id="f-email" name="email" />
      </Field>,
    );

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("Toast muestra el mensaje y descartar llama onDismiss una vez", () => {
    const onDismiss = vi.fn();
    render(<Toast message="Turno ficticio guardado" kind="success" onDismiss={onDismiss} />);

    expect(screen.getByRole("status")).toHaveTextContent("Turno ficticio guardado");
    fireEvent.click(screen.getByRole("button", { name: /descartar/i }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("TRIANGULATE: Toast sin mensaje no renderiza nada", () => {
    const onDismiss = vi.fn();
    const { container } = render(<Toast message={null} onDismiss={onDismiss} />);

    expect(container).toBeEmptyDOMElement();
    expect(onDismiss).not.toHaveBeenCalled();
  });
});
