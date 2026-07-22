// Modal + <form> + error banner + submit/cancel footer. Every "create / edit"
// dialog in the app is this shape, so screens describe only their fields.

import { useId, type FormEvent, type ReactNode } from "react";
import { useIsPhone } from "../_internal/useMediaQuery";
import { Banner } from "../Banner/Banner";
import { Button } from "../Button/Button";
import { Modal } from "../Dialog/Dialog";
import { Stack } from "../Layout/Layout";
import { Sheet } from "../Sheet/Sheet";

/** Best-effort human message from an API rejection or thrown Error. */
export function errorText(error: unknown): string {
  if (!error) return "";
  if (error instanceof Error) return error.message;
  if (typeof error === "object") {
    const e = error as { message?: unknown; detail?: unknown };
    if (typeof e.message === "string") return e.message;
    if (typeof e.detail === "string") return e.detail;
  }
  return String(error);
}

export interface FormModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  /** Fired on form submit; call preventDefault in the handler. */
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
  error?: unknown;
  /** Headline shown above the error body. */
  errorTitle?: string;
  busy?: boolean;
  submitLabel?: string;
  busyLabel?: string;
  submitDisabled?: boolean;
  destructive?: boolean;
  size?: "sm" | "md" | "lg";
  children: ReactNode;
}

export function FormModal({
  open,
  onOpenChange,
  title,
  description,
  onSubmit,
  error,
  errorTitle = "That didn’t go through",
  busy,
  submitLabel = "Save",
  busyLabel = "Saving…",
  submitDisabled,
  destructive,
  size = "md",
  children,
}: FormModalProps) {
  // useId embeds delimiters (":r0:" / "«r0»"); strip them so the id is a safe
  // target for the footer button's `form` attribute.
  const formId = `form-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  // On a phone a centre-anchored dialog fights the on-screen keyboard, which
  // pushes the submit button off the bottom of the viewport. A bottom sheet is
  // anchored to the edge the keyboard grows from, so the actions stay reachable.
  const phone = useIsPhone();

  const footer = (
    <>
      <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
        Cancel
      </Button>
      <Button
        type="submit"
        form={formId}
        variant={destructive ? "danger" : "primary"}
        disabled={busy || submitDisabled}
      >
        {busy ? busyLabel : submitLabel}
      </Button>
    </>
  );

  const body = (
    <form id={formId} onSubmit={onSubmit}>
      <Stack gap={4}>
        {error != null && (
          <Banner tone="danger" title={errorTitle}>
            {errorText(error)}
          </Banner>
        )}
        {children}
      </Stack>
    </form>
  );

  if (phone) {
    return (
      <Sheet
        open={open}
        onOpenChange={onOpenChange}
        side="bottom"
        title={title}
        description={description}
        footer={footer}
      >
        {body}
      </Sheet>
    );
  }

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      size={size}
      footer={footer}
    >
      {body}
    </Modal>
  );
}
