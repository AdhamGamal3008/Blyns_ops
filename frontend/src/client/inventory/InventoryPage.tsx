// Inventory module UI (docs/modules/INVENTORY.md). Stock is derived from the
// movement ledger — nothing here edits on_hand directly.

import { useLocation, useOutletContext } from "react-router-dom";
import { csvGrants } from "../../shared/csv/access";
import { ImportApprovals } from "../../shared/csv/ImportApprovals";
import { PageHeader } from "../../shared/shell";
import type { ClientMe } from "../../shared/types";
import { Stack, Tabs, TabsContent, TabsList, TabsTrigger } from "../../shared/ui";
import { InventoryAnalytics } from "./InventoryAnalytics";
import { LowStockSection } from "./LowStockSection";
import { MovementsSection } from "./MovementsSection";
import { ProductsSection } from "./ProductsSection";
import { StockSection } from "./StockSection";

export function InventoryPage() {
  const me = useOutletContext<ClientMe>();
  const { pathname } = useLocation();
  const canWrite = (me.role.permissions["inventory"] ?? 0) >= 3;
  const canAnalytics = (me.role.permissions["inventory_analytics"] ?? 0) >= 1;
  const csv = (entity: string) => csvGrants(me, "inventory", entity);

  // Dashboard quick actions deep-link here: /adjust opens the stock-move modal
  // (stock tab); /products/new opens the new-product modal (products tab).
  const tab = pathname.startsWith("/app/inventory/products") ? "products"
    : pathname.startsWith("/app/inventory/movements") ? "movements"
    : pathname.startsWith("/app/inventory/low") ? "low"
    : "stock";
  const adjustDeepLink = pathname.endsWith("/adjust");
  const newProduct = tab === "products" && pathname.endsWith("/new");

  return (
    <Stack>
      <PageHeader title="Inventory" description="Stock, products, and the movement ledger behind them" />

      <ImportApprovals me={me} module="inventory" />

      <Tabs defaultValue={tab}>
        <TabsList>
          <TabsTrigger value="stock">Stock</TabsTrigger>
          <TabsTrigger value="products">Products</TabsTrigger>
          <TabsTrigger value="movements">Movements</TabsTrigger>
          <TabsTrigger value="low">Low stock</TabsTrigger>
          {canAnalytics && <TabsTrigger value="analytics">Analytics</TabsTrigger>}
        </TabsList>

        <TabsContent value="stock">
          <StockSection canWrite={canWrite} csv={csv("stock-levels")} openMove={adjustDeepLink} />
        </TabsContent>
        <TabsContent value="products">
          <ProductsSection canWrite={canWrite} csv={csv("products")} openNew={newProduct} />
        </TabsContent>
        <TabsContent value="movements">
          <MovementsSection canWrite={canWrite} csv={csv("movements")} />
        </TabsContent>
        <TabsContent value="low"><LowStockSection /></TabsContent>
        {canAnalytics && (
          <TabsContent value="analytics"><InventoryAnalytics /></TabsContent>
        )}
      </Tabs>
    </Stack>
  );
}
