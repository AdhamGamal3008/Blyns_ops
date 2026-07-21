// Quick System Actions (§1): the server returns only what this role may do.

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../shared/api";
import type { QuickAction } from "../../shared/types";
import { Button, Card } from "../../shared/legacy-ui";

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
    <Card title="Quick actions">
      <div className="quick-actions">
        {actions.map((a) => (
          <Button key={a.key} variant="ghost"
            onClick={() => navigate(a.target_route.replace(/^\/app/, "/app"))}>
            {a.label}
          </Button>
        ))}
      </div>
    </Card>
  );
}
