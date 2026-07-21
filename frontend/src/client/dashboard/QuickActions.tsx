// Quick System Actions (§1): the server returns only what this role may do.

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../shared/api";
import type { QuickAction } from "../../shared/types";
import { Button, Row } from "../../shared/ui";

export function QuickActions() {
  const navigate = useNavigate();
  const [actions, setActions] = useState<QuickAction[] | null>(null);

  useEffect(() => {
    api<QuickAction[]>("/dashboard/quick-actions")
      .then((res) => setActions(res.data))
      .catch(() => setActions([]));
  }, []);

  if (!actions || actions.length === 0) return null;

  return (
    <Row gap={2}>
      {actions.map((a, i) => (
        <Button
          key={a.key}
          // the server returns these in priority order, so lead with the first
          variant={i === 0 ? "primary" : "secondary"}
          onClick={() => navigate(a.target_route)}
        >
          {a.label}
        </Button>
      ))}
    </Row>
  );
}
