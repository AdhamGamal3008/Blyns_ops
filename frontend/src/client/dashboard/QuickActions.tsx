// Quick System Actions (§1): the server returns only what this role may do,
// already ranked by role × recent behavior (Phase 1) and personalized by the
// user's own pins/hides (Phase 2). We lead with the top action, keep the next
// few inline, tuck any remainder into a "More" overflow, and offer a Customize
// control. Silent — the ranking is felt, not labelled.

import { ChevronDown, SlidersHorizontal } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../shared/api";
import type { QuickAction } from "../../shared/types";
import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Row,
} from "../../shared/ui";
import { CustomizeQuickActions } from "./CustomizeQuickActions";

const INLINE_LIMIT = 5; // shown inline; anything past this goes to the overflow menu

export function QuickActions() {
  const navigate = useNavigate();
  const [actions, setActions] = useState<QuickAction[] | null>(null);
  const [customizable, setCustomizable] = useState(false);
  const [customizing, setCustomizing] = useState(false);

  const load = useCallback(() => {
    api<QuickAction[]>("/dashboard/quick-actions")
      .then((res) => {
        setActions(res.data);
        setCustomizable(Boolean(res.meta?.customizable));
      })
      .catch(() => {
        setActions([]);
        setCustomizable(false);
      });
  }, []);

  useEffect(() => load(), [load]);

  if (!actions) return null; // still loading
  // Nothing permitted at all → render nothing. But if the user simply hid
  // everything, keep the Customize control reachable so they can bring actions back.
  if (actions.length === 0 && !customizable) return null;

  const inline = actions.slice(0, INLINE_LIMIT);
  const overflow = actions.slice(INLINE_LIMIT);

  return (
    <>
      <Row gap={2}>
        {inline.map((a, i) => (
          <Button
            key={a.key}
            // the server returns these in priority order, so lead with the first
            variant={i === 0 ? "primary" : "secondary"}
            onClick={() => navigate(a.target_route)}
          >
            {a.label}
          </Button>
        ))}

        {overflow.length > 0 && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="secondary" iconRight={<ChevronDown size={15} aria-hidden="true" />}>
                More
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              {overflow.map((a) => (
                <DropdownMenuItem key={a.key} onSelect={() => navigate(a.target_route)}>
                  {a.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        )}

        {customizable && (
          <Button
            variant="ghost"
            aria-label="Customize quick actions"
            onClick={() => setCustomizing(true)}
          >
            <SlidersHorizontal size={16} aria-hidden="true" />
          </Button>
        )}
      </Row>

      {customizing && (
        <CustomizeQuickActions
          onClose={() => setCustomizing(false)}
          onSaved={() => {
            setCustomizing(false);
            load();
          }}
        />
      )}
    </>
  );
}
