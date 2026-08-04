"""Discovery-session bookings — leads captured from the public landing page.

Control-plane data (Blyns's own leads, not tenant data): a public unauthenticated
POST writes them; the admin portal reads and works them, gated on the `leads`
resource. See docs/LANDING_PAGE.md §4.
"""
