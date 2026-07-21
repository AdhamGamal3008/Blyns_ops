// The sign-in frame shared by both auth realms (docs/AUTH_RBAC.md §4). The
// realm badge is the visible reminder that admins and employees are separate
// pools — you can see which door you are standing at.

import type { ReactNode } from "react";
import { Banner, Card, Stack } from "../ui";
import { errorText } from "../ui";
import styles from "./LoginLayout.module.css";

export interface LoginLayoutProps {
  realm: string;
  lede: ReactNode;
  error?: unknown;
  children: ReactNode;
  /** Link to the other realm's sign-in. */
  footer?: ReactNode;
}

export function LoginLayout({ realm, lede, error, children, footer }: LoginLayoutProps) {
  return (
    <div className={styles.wrap}>
      <div className={styles.box}>
        <div className={styles.brand}>
          <h1 className={styles.wordmark}>Blyns ERP</h1>
          <span className={styles.realm}>{realm}</span>
        </div>

        <Card className={styles.card}>
          <Stack gap={4}>
            <p className={styles.lede}>{lede}</p>
            {error != null && (
              <Banner tone="danger" title="Sign-in failed">{errorText(error)}</Banner>
            )}
            {children}
          </Stack>
        </Card>

        {footer && <p className={styles.switch}>{footer}</p>}
      </div>
    </div>
  );
}
