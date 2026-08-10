// The discovery-booking form is the landing's one functional feature. What
// matters: required fields reach the public endpoint as a trimmed payload with an
// empty honeypot, a success swaps to the confirmation, and a failure keeps the
// form for retry. The network call is mocked — this is the form's contract, not
// the endpoint's (that is covered by the backend booking tests).

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { submitBooking } from "../landing/api";
import { BookingForm } from "../landing/sections/BookingForm";

vi.mock("../landing/api", () => ({ submitBooking: vi.fn() }));
const mockSubmit = vi.mocked(submitBooking);

function fillRequired() {
  fireEvent.change(screen.getByLabelText(/full name/i), { target: { value: "  Ada Lovelace  " } });
  fireEvent.change(screen.getByLabelText(/work email/i), { target: { value: "  ada@studio.co  " } });
  fireEvent.change(screen.getByLabelText(/company \*/i), { target: { value: "Analytical Engines" } });
  fireEvent.change(screen.getByLabelText(/your field/i), { target: { value: "flooring" } });
}

function submitForm() {
  const form = document.querySelector("form");
  if (!form) throw new Error("form not rendered");
  fireEvent.submit(form);
}

describe("BookingForm", () => {
  beforeEach(() => mockSubmit.mockReset());

  it("posts a trimmed payload with an empty honeypot, then confirms", async () => {
    mockSubmit.mockResolvedValueOnce(undefined);
    render(<BookingForm />);

    fillRequired();
    submitForm();

    await waitFor(() => expect(mockSubmit).toHaveBeenCalledTimes(1));
    expect(mockSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        full_name: "Ada Lovelace",
        work_email: "ada@studio.co",
        company: "Analytical Engines",
        industry: "flooring",
        website: "",
      }),
    );

    expect(await screen.findByText(/your request is in/i)).toBeInTheDocument();
    // the form is replaced by the confirmation
    expect(document.querySelector("form")).toBeNull();
  });

  it("keeps a honeypot field in the DOM but out of the a11y tree", () => {
    render(<BookingForm />);
    const honeypot = document.querySelector('[aria-hidden="true"] input');
    expect(honeypot).not.toBeNull();
    expect(honeypot).toHaveAttribute("tabindex", "-1");
  });

  it("surfaces an error and keeps the form for retry when the post fails", async () => {
    mockSubmit.mockRejectedValueOnce(new Error("Network down"));
    render(<BookingForm />);

    fillRequired();
    submitForm();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    // still on the form (not the confirmation)
    expect(document.querySelector("form")).not.toBeNull();
    expect(screen.queryByText(/your request is in/i)).toBeNull();
  });
});
