// The landing's only network call — the public discovery-booking submission.
// Uses the shared HTTP helper with `skipAuth` so no token is read or attached
// (the landing holds no session and belongs to neither auth realm).

import { api } from "../shared/api";

export interface BookingSubmission {
  full_name: string;
  work_email: string;
  company: string;
  industry: string;
  phone?: string;
  company_size?: string;
  preferred_at?: string;
  message?: string;
  /** Honeypot — always empty for real users; bots fill it and are dropped. */
  website?: string;
}

export async function submitBooking(payload: BookingSubmission): Promise<void> {
  await api("/public/discovery-bookings", {
    method: "POST",
    body: payload,
    skipAuth: true,
  });
}
