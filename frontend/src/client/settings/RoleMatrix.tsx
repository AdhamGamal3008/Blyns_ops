// The RBAC role matrix: resource rows × NONE/VIEW/READ/WRITE columns.
//
// Built on native radios so each row is a real radio group — Tab enters the
// grid at the checked cell and ←/→ move within a resource for free. We add
// ↑/↓ to cross resources, which native radios don't do, and colour the checked
// cell by level so the whole grant reads as one shape.

import { useRef } from "react";
import styles from "./RoleMatrix.module.css";

export const CLIENT_RESOURCES = [
  "dashboard", "calendar", "activity",
  "projects", "projects_analytics",
  "crm", "inventory", "finance", "settings",
];

export const LEVELS = ["None", "View", "Read", "Write"];

/** Humanize a resource key for display: `projects_analytics` → "Projects
 *  Analytics". Title-cased in JS (not just CSS) so it reads correctly and is
 *  assertable in tests. */
export const resourceLabel = (res: string): string =>
  res.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

/** Level → the swatch class that fills the checked cell. */
const LEVEL_CLASS = [styles.lvl0, styles.lvl1, styles.lvl2, styles.lvl3];

export interface RoleMatrixProps {
  value: Record<string, number>;
  onChange: (next: Record<string, number>) => void;
  resources?: string[];
  disabled?: boolean;
}

export function RoleMatrix({
  value,
  onChange,
  resources = CLIENT_RESOURCES,
  disabled,
}: RoleMatrixProps) {
  const gridRef = useRef<HTMLTableElement>(null);

  /** ↑/↓ move to the same level in the neighbouring resource, and select it —
   *  mirroring what ←/→ already do inside a row. */
  function onKeyDown(e: React.KeyboardEvent<HTMLTableElement>) {
    if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
    const target = e.target as HTMLElement;
    const res = target.dataset.resource;
    const lvl = target.dataset.level;
    if (res == null || lvl == null) return;

    const rowIndex = resources.indexOf(res);
    const next = resources[rowIndex + (e.key === "ArrowDown" ? 1 : -1)];
    if (!next) return;

    e.preventDefault();
    const el = gridRef.current?.querySelector<HTMLInputElement>(
      `input[data-resource="${next}"][data-level="${lvl}"]`,
    );
    el?.focus();
    el?.click();
  }

  function setAll(level: number) {
    onChange(Object.fromEntries(resources.map((r) => [r, level])));
  }

  return (
    <div className={styles.scroller}>
      <table ref={gridRef} className={styles.grid} onKeyDown={onKeyDown}>
        <caption className={styles.caption}>
          Pick one access level per resource. A resource left at None never appears
          in that role's navigation.
        </caption>
        <thead>
          <tr>
            <th scope="col" className={styles.resourceHead}>Resource</th>
            {LEVELS.map((label, level) => (
              <th key={label} scope="col" className={styles.levelHead}>
                <span className={styles.levelLabel}>{label}</span>
                {!disabled && (
                  <button
                    type="button"
                    className={styles.setAll}
                    onClick={() => setAll(level)}
                    // "set all" alone doesn't say which level, so name it fully
                    aria-label={`Set every resource to ${label}`}
                  >
                    set all
                  </button>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {resources.map((res) => {
            const current = value[res] ?? 0;
            return (
              <tr key={res}>
                <th scope="row" className={styles.resourceCell}>{resourceLabel(res)}</th>
                {LEVELS.map((label, level) => (
                  <td key={label} className={styles.cell}>
                    <label className={styles.swatchLabel}>
                      <input
                        type="radio"
                        className={styles.input}
                        name={`perm-${res}`}
                        value={level}
                        data-resource={res}
                        data-level={level}
                        disabled={disabled}
                        checked={current === level}
                        onChange={() => onChange({ ...value, [res]: level })}
                        aria-label={`${resourceLabel(res)}: ${label}`}
                      />
                      <span className={`${styles.swatch} ${LEVEL_CLASS[level]}`} aria-hidden="true" />
                    </label>
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

/** Read-only badge for one grant, used in the roles overview. */
export function LevelChip({ level }: { level: number }) {
  return (
    <span className={`${styles.chip} ${LEVEL_CLASS[level] ?? LEVEL_CLASS[0]}`}>
      {LEVELS[level] ?? LEVELS[0]}
    </span>
  );
}
