import * as RadixDialog from "@radix-ui/react-dialog";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { cn } from "../ui/_internal/cn";
import type { CommandItem } from "./types";
import styles from "./CommandPalette.module.css";

export interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  commands: CommandItem[];
  placeholder?: string;
}

function groupCommands(items: CommandItem[]): { name: string; items: CommandItem[] }[] {
  const map = new Map<string, CommandItem[]>();
  for (const it of items) {
    const g = it.group ?? "";
    if (!map.has(g)) map.set(g, []);
    map.get(g)!.push(it);
  }
  return Array.from(map, ([name, groupItems]) => ({ name, items: groupItems }));
}

export function CommandPalette({
  open,
  onOpenChange,
  commands,
  placeholder = "Search or jump to…",
}: CommandPaletteProps) {
  const reduce = useReducedMotion();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) =>
      `${c.label} ${c.keywords ?? ""} ${c.hint ?? ""} ${c.group ?? ""}`.toLowerCase().includes(q),
    );
  }, [commands, query]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
    }
  }, [open]);

  useEffect(() => {
    setActive((a) => Math.min(a, Math.max(filtered.length - 1, 0)));
  }, [filtered.length]);

  function choose(cmd?: CommandItem) {
    if (!cmd) return;
    onOpenChange(false);
    cmd.onSelect();
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(filtered[active]);
    }
  }

  const groups = useMemo(() => groupCommands(filtered), [filtered]);

  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <RadixDialog.Portal forceMount>
            <RadixDialog.Overlay asChild forceMount>
              <motion.div
                className={styles.overlay}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: reduce ? 0 : 0.16 }}
              />
            </RadixDialog.Overlay>
            <div className={styles.positioner}>
              <RadixDialog.Content
                asChild
                forceMount
                onOpenAutoFocus={(e) => {
                  e.preventDefault();
                  inputRef.current?.focus();
                }}
              >
                <motion.div
                  className={styles.panel}
                  initial={reduce ? { opacity: 0 } : { opacity: 0, y: -8, scale: 0.98 }}
                  animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
                  exit={reduce ? { opacity: 0 } : { opacity: 0, y: -8, scale: 0.98 }}
                  transition={{ duration: reduce ? 0 : 0.18, ease: [0.2, 0, 0, 1] }}
                >
                  <RadixDialog.Title className={styles.srOnly}>Command palette</RadixDialog.Title>
                  <div className={styles.searchRow}>
                    <Search size={18} className={styles.searchIcon} aria-hidden="true" />
                    <input
                      ref={inputRef}
                      className={styles.search}
                      placeholder={placeholder}
                      value={query}
                      onChange={(e) => {
                        setQuery(e.target.value);
                        setActive(0);
                      }}
                      onKeyDown={onKeyDown}
                    />
                    <kbd className={styles.kbd}>Esc</kbd>
                  </div>
                  <div className={styles.list} role="listbox">
                    {filtered.length === 0 ? (
                      <div className={styles.empty}>No results for “{query}”.</div>
                    ) : (
                      groups.map((group) => (
                        <div key={group.name || "_"} className={styles.group}>
                          {group.name && <div className={styles.groupLabel}>{group.name}</div>}
                          {group.items.map((cmd) => {
                            const idx = filtered.indexOf(cmd);
                            return (
                              <button
                                key={cmd.id}
                                type="button"
                                role="option"
                                aria-selected={idx === active}
                                className={cn(styles.item, idx === active && styles.itemActive)}
                                onMouseEnter={() => setActive(idx)}
                                onClick={() => choose(cmd)}
                              >
                                {cmd.icon && (
                                  <span className={styles.itemIcon} aria-hidden="true">
                                    {cmd.icon}
                                  </span>
                                )}
                                <span className={styles.itemLabel}>{cmd.label}</span>
                                {cmd.hint && <span className={styles.itemHint}>{cmd.hint}</span>}
                              </button>
                            );
                          })}
                        </div>
                      ))
                    )}
                  </div>
                </motion.div>
              </RadixDialog.Content>
            </div>
          </RadixDialog.Portal>
        )}
      </AnimatePresence>
    </RadixDialog.Root>
  );
}
