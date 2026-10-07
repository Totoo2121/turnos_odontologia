import type { ReactNode } from "react";
import "./Table.css";

export interface TableColumn {
  key: string;
  header: string;
  render?: (row: TableRow) => ReactNode;
}

export type TableRow = Record<string, unknown> & { id: string };

interface TableProps {
  columns: TableColumn[];
  rows: TableRow[];
  emptyText: string;
}

function cellText(row: TableRow, key: string): string {
  const value = row[key];
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

/** Tabla controlada: refleja exactamente columns/rows; sin filas muestra emptyText. */
export function Table({ columns, rows, emptyText }: TableProps): JSX.Element {
  if (rows.length === 0) {
    return <p className="table-empty">{emptyText}</p>;
  }
  return (
    <table className="table">
      <thead>
        <tr>
          {columns.map((column) => (
            <th key={column.key} scope="col">
              {column.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            {columns.map((column) =>
              column.render !== undefined ? (
                <td key={column.key}>{column.render(row)}</td>
              ) : (
                <td key={column.key}>{cellText(row, column.key)}</td>
              ),
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
