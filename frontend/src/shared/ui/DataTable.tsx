import type { ReactNode } from "react";

export interface DataTableColumn<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
}

export interface DataTableProps<T> {
  columns: readonly DataTableColumn<T>[];
  rows: readonly T[];
  rowKey: (row: T) => string;
  empty?: ReactNode;
}

export default function DataTable<T>({ columns, rows, rowKey, empty }: DataTableProps<T>) {
  if (rows.length === 0 && empty) return <>{empty}</>;
  return (
    <div className="ui-table-wrap" role="region" tabIndex={0} aria-label="Data table">
      <table className="ui-table">
        <thead>
          <tr>{columns.map((column) => <th key={column.key} scope="col">{column.header}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => <td key={column.key}>{column.render(row)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
