// Per-tab CSV grant checks (docs/modules/SETTINGS.md §1.3), the frontend mirror
// of backend `app/shared/csv_access.py`. The rules are the same on both sides:
//
//   * a grant only takes effect above module READ (the floor);
//   * `approve_import` implies import, so an approver may import a tab even with
//     no explicit import grant;
//   * a role with no grants sees no CSV controls for that tab.
//
// The server re-checks every one of these — this only decides which buttons to
// render, never what is allowed.

import type { ClientMe } from "../types";

const READ = 2; // PermissionLevel.READ

export interface CsvGrants {
  canExport: boolean;
  /** Includes approve-implies-import. */
  canImport: boolean;
  canApprove: boolean;
}

export function csvKey(module: string, entity: string): string {
  return `${module}:${entity}`;
}

function hasModuleRead(me: ClientMe, module: string): boolean {
  return (me.role.permissions[module] ?? 0) >= READ;
}

/** What the current user may do with one tab's CSV. */
export function csvGrants(me: ClientMe, module: string, entity: string): CsvGrants {
  const read = hasModuleRead(me, module);
  const access = me.role.csv_access;
  if (!read || !access) {
    return { canExport: false, canImport: false, canApprove: false };
  }
  const key = csvKey(module, entity);
  const canApprove = access.approve_import.includes(key);
  return {
    canExport: access.export.includes(key),
    canImport: access.import.includes(key) || canApprove, // approve ⇒ import
    canApprove,
  };
}

function someTabIn(keys: string[] | undefined, module: string): boolean {
  return (keys ?? []).some((k) => k.startsWith(`${module}:`));
}

/** Can this user approve at least one tab in the module? Drives the inbox's
 *  visibility without needing the tab catalog. */
export function canApproveModule(me: ClientMe, module: string): boolean {
  if (!hasModuleRead(me, module)) return false;
  return someTabIn(me.role.csv_access?.approve_import, module);
}

/** Can this user import (directly or by staging) at least one tab in the module?
 *  Whoever can import may have requests of their own to track. */
export function canImportModule(me: ClientMe, module: string): boolean {
  if (!hasModuleRead(me, module)) return false;
  const access = me.role.csv_access;
  return someTabIn(access?.import, module) || someTabIn(access?.approve_import, module);
}
