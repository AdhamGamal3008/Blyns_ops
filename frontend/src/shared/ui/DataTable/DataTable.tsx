import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  type SortingState,
  useReactTable,
} from "@tanstack/react-table";
import { ChevronDown, ChevronsUpDown, ChevronUp, Search } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { cn } from "../_internal/cn";
import { Checkbox } from "../Checkbox/Checkbox";
import { Input } from "../Input/Input";
import { Pagination } from "../Pagination/Pagination";
import styles from "./DataTable.module.css";

interface ColMeta {
  numeric?: boolean;
  label?: string;
}

export interface DataTableColumn<T> {
  key: string;
  header: string;
  /** Custom cell render. Defaults to row[key]. */
  accessor?: (row: T) => ReactNode;
  sortable?: boolean;
  /** Right-align + tabular figures. */
  numeric?: boolean;
  /** Value used for sorting/filtering when the cell renders a node. */
  sortValue?: (row: T) => string | number;
}

export interface DataTableProps<T> {
  data: T[];
  columns: DataTableColumn<T>[];
  getRowId?: (row: T, index: number) => string;
  pageSize?: number;
  selectable?: boolean;
  searchable?: boolean;
  searchPlaceholder?: string;
  onSelectionChange?: (ids: string[]) => void;
  /** Makes rows activatable by click, Enter, or Space (e.g. open a detail view). */
  onRowClick?: (row: T) => void;
  emptyText?: string;
}

export function DataTable<T>({
  data,
  columns,
  getRowId,
  pageSize = 10,
  selectable,
  searchable = true,
  searchPlaceholder = "Search…",
  onSelectionChange,
  onRowClick,
  emptyText = "No results.",
}: DataTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState("");
  const [rowSelection, setRowSelection] = useState({});

  const columnDefs = useMemo<ColumnDef<T>[]>(() => {
    const defs: ColumnDef<T>[] = [];
    if (selectable) {
      defs.push({
        id: "__select",
        enableSorting: false,
        header: ({ table }) => (
          <Checkbox
            checked={
              table.getIsAllRowsSelected()
                ? true
                : table.getIsSomeRowsSelected()
                  ? "indeterminate"
                  : false
            }
            onCheckedChange={(v) => table.toggleAllRowsSelected(!!v)}
            aria-label="Select all rows"
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            checked={row.getIsSelected()}
            onCheckedChange={(v) => row.toggleSelected(!!v)}
            aria-label="Select row"
          />
        ),
      });
    }
    for (const col of columns) {
      defs.push({
        id: col.key,
        accessorFn: (row) =>
          col.sortValue ? col.sortValue(row) : (row as Record<string, unknown>)[col.key],
        header: col.header,
        cell: (ctx) => (col.accessor ? col.accessor(ctx.row.original) : (ctx.getValue() as ReactNode)),
        enableSorting: col.sortable ?? false,
        meta: { numeric: col.numeric, label: col.header } satisfies ColMeta,
      });
    }
    return defs;
  }, [columns, selectable]);

  const table = useReactTable({
    data,
    columns: columnDefs,
    state: { sorting, globalFilter, rowSelection },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    onRowSelectionChange: setRowSelection,
    enableRowSelection: Boolean(selectable),
    getRowId,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize } },
  });

  const selectedCount = table.getSelectedRowModel().rows.length;

  useEffect(() => {
    onSelectionChange?.(table.getSelectedRowModel().rows.map((r) => r.id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rowSelection]);

  const rows = table.getRowModel().rows;
  const pageCount = table.getPageCount();
  const columnCount = table.getAllLeafColumns().length;

  return (
    <div className={styles.root}>
      {searchable && (
        <div className={styles.toolbar}>
          <div className={styles.search}>
            <Input
              inputSize="compact"
              iconLeft={<Search />}
              placeholder={searchPlaceholder}
              value={globalFilter}
              onChange={(e) => setGlobalFilter(e.target.value)}
            />
          </div>
          {selectable && selectedCount > 0 && (
            <span className={styles.selectedCount}>{selectedCount} selected</span>
          )}
        </div>
      )}

      <div className={styles.scroll}>
        <table className={styles.table}>
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((header) => {
                  const meta = header.column.columnDef.meta as ColMeta | undefined;
                  const isSelect = header.column.id === "__select";
                  const canSort = header.column.getCanSort();
                  const sorted = header.column.getIsSorted();
                  return (
                    <th
                      key={header.id}
                      className={cn(meta?.numeric && styles.numeric, isSelect && styles.selectCell)}
                      aria-sort={
                        sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined
                      }
                    >
                      {header.isPlaceholder ? null : canSort ? (
                        <button
                          type="button"
                          className={styles.sortBtn}
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          <span className={styles.sortIcon} aria-hidden="true">
                            {sorted === "asc" ? (
                              <ChevronUp size={14} />
                            ) : sorted === "desc" ? (
                              <ChevronDown size={14} />
                            ) : (
                              <ChevronsUpDown size={14} />
                            )}
                          </span>
                        </button>
                      ) : (
                        flexRender(header.column.columnDef.header, header.getContext())
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td className={styles.empty} colSpan={columnCount}>
                  {emptyText}
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr
                  key={row.id}
                  className={cn(
                    row.getIsSelected() && styles.selectedRow,
                    onRowClick && styles.clickableRow,
                  )}
                  tabIndex={onRowClick ? 0 : undefined}
                  onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                  onKeyDown={
                    onRowClick
                      ? (e) => {
                          if (e.target !== e.currentTarget) return; // let cell controls win
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            onRowClick(row.original);
                          }
                        }
                      : undefined
                  }
                >
                  {row.getVisibleCells().map((cell) => {
                    const meta = cell.column.columnDef.meta as ColMeta | undefined;
                    const isSelect = cell.column.id === "__select";
                    return (
                      <td
                        key={cell.id}
                        data-label={isSelect ? "" : (meta?.label ?? "")}
                        className={cn(meta?.numeric && styles.numeric, isSelect && styles.selectCell)}
                      >
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    );
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {pageCount > 1 && (
        <div className={styles.footer}>
          <span className={styles.count}>{table.getFilteredRowModel().rows.length} rows</span>
          <Pagination
            page={table.getState().pagination.pageIndex + 1}
            pageCount={pageCount}
            onPageChange={(p) => table.setPageIndex(p - 1)}
          />
        </div>
      )}
    </div>
  );
}
