// Inventory module UI (docs/modules/INVENTORY.md). Stock is derived from the
// movement ledger — nothing here edits on_hand directly.

import { useState } from "react";
import { useLocation, useOutletContext } from "react-router-dom";
import type { ClientMe } from "../../shared/types";
import { LowStockSection } from "./LowStockSection";
import { MovementsSection } from "./MovementsSection";
import { ProductsSection } from "./ProductsSection";
import { StockSection } from "./StockSection";

const SECTIONS = [
  { key: "stock", label: "Stock" },
  { key: "products", label: "Products" },
  { key: "movements", label: "Movements" },
  { key: "low", label: "Low stock" },
] as const;

export function InventoryPage() {
  const me = useOutletContext<ClientMe>();
  const location = useLocation();
  // the dashboard's `inventory.adjust` quick action deep-links to /app/inventory/adjust
  const adjustDeepLink = location.pathname.endsWith("/adjust");
  const [section, setSection] = useState<string>("stock");
  const canWrite = (me.role.permissions["inventory"] ?? 0) >= 3;

  return (
    <>
      <div className="quick-actions">
        {SECTIONS.map((s) => (
          <button key={s.key}
            className={`btn ${section === s.key ? "btn-primary" : "btn-ghost"}`}
            onClick={() => setSection(s.key)}>
            {s.label}
          </button>
        ))}
      </div>
      {section === "stock" && (
        <StockSection canWrite={canWrite} openMove={adjustDeepLink} />
      )}
      {section === "products" && <ProductsSection canWrite={canWrite} />}
      {section === "movements" && <MovementsSection />}
      {section === "low" && <LowStockSection />}
    </>
  );
}
