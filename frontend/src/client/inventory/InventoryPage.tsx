// Inventory module UI (docs/modules/INVENTORY.md). Stock is derived from the
// movement ledger — nothing here edits on_hand directly.

import { useLocation, useOutletContext } from "react-router-dom";
import { PageHeader } from "../../shared/shell";
import type { ClientMe } from "../../shared/types";
import { Stack, Tabs, TabsContent, TabsList, TabsTrigger } from "../../shared/ui";
import { LowStockSection } from "./LowStockSection";
import { MovementsSection } from "./MovementsSection";
import { ProductsSection } from "./ProductsSection";
import { StockSection } from "./StockSection";

export function InventoryPage() {
  const me = useOutletContext<ClientMe>();
  const location = useLocation();
  // the dashboard's `inventory.adjust` quick action deep-links to /app/inventory/adjust
  const adjustDeepLink = location.pathname.endsWith("/adjust");
  const canWrite = (me.role.permissions["inventory"] ?? 0) >= 3;

  return (
    <Stack>
      <PageHeader title="Inventory" description="Stock, products, and the movement ledger behind them" />

      <Tabs defaultValue="stock">
        <TabsList>
          <TabsTrigger value="stock">Stock</TabsTrigger>
          <TabsTrigger value="products">Products</TabsTrigger>
          <TabsTrigger value="movements">Movements</TabsTrigger>
          <TabsTrigger value="low">Low stock</TabsTrigger>
        </TabsList>

        <TabsContent value="stock">
          <StockSection canWrite={canWrite} openMove={adjustDeepLink} />
        </TabsContent>
        <TabsContent value="products"><ProductsSection canWrite={canWrite} /></TabsContent>
        <TabsContent value="movements"><MovementsSection /></TabsContent>
        <TabsContent value="low"><LowStockSection /></TabsContent>
      </Tabs>
    </Stack>
  );
}
