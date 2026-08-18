"""Company profile + logo (Settings profile tab + sidebar brand).

The four profile fields round-trip through the existing PATCH; the logo is stored
on company_profile.logo_ref (as a small inline data URI), surfaced in /auth/me for
every authenticated user, and the data-URI form is validated (image only, capped).
"""

from __future__ import annotations

# a 1×1 transparent PNG
PNG = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAA"
    "C0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


async def test_company_profile_reflects_the_core_fields(client_client):
    res = await client_client.patch("/api/v1/settings/company", json={
        "name": "Acme Fabrication", "timezone": "Europe/London",
        "currency": "GBP", "fiscal_year_start": "04-01",
    })
    assert res.status_code == 200, res.text
    data = (await client_client.get("/api/v1/settings/company")).json()["data"]
    assert data["name"] == "Acme Fabrication"
    assert data["timezone"] == "Europe/London"
    assert data["currency"] == "GBP"
    assert data["fiscal_year_start"] == "04-01"

    # currency reaches /auth/me so the SPA formats every money value in the
    # tenant's currency without granting Settings access to everyone
    me = (await client_client.get("/api/v1/auth/me")).json()["data"]
    assert me["company"]["currency"] == "GBP"


async def test_logo_is_stored_and_surfaced_to_every_user(client_client):
    res = await client_client.patch("/api/v1/settings/company", json={"logo_ref": PNG})
    assert res.status_code == 200, res.text
    assert res.json()["data"]["logo_ref"] == PNG

    assert (await client_client.get(
        "/api/v1/settings/company")).json()["data"]["logo_ref"] == PNG

    # /auth/me carries it so the shell can render it without Settings access
    me = (await client_client.get("/api/v1/auth/me")).json()["data"]
    assert me["company"]["logo_ref"] == PNG


async def test_logo_can_be_removed(client_client):
    # set a logo, then clear it with an explicit null — a partial PATCH must be
    # able to remove a field, not just add or replace it.
    await client_client.patch("/api/v1/settings/company", json={"logo_ref": PNG})
    res = await client_client.patch("/api/v1/settings/company", json={"logo_ref": None})
    assert res.status_code == 200, res.text
    assert res.json()["data"]["logo_ref"] is None

    assert (await client_client.get(
        "/api/v1/settings/company")).json()["data"]["logo_ref"] is None
    me = (await client_client.get("/api/v1/auth/me")).json()["data"]
    assert me["company"]["logo_ref"] is None


async def test_unsent_fields_are_left_untouched(client_client):
    # a PATCH that only sets the logo must not wipe the other profile fields
    await client_client.patch("/api/v1/settings/company", json={
        "name": "Kept Co", "currency": "EUR"})
    await client_client.patch("/api/v1/settings/company", json={"logo_ref": PNG})
    data = (await client_client.get("/api/v1/settings/company")).json()["data"]
    assert data["name"] == "Kept Co" and data["currency"] == "EUR"
    assert data["logo_ref"] == PNG


async def test_logo_rejects_non_image_and_oversized(client_client):
    res = await client_client.patch("/api/v1/settings/company",
        json={"logo_ref": "data:text/html;base64,PHNjcmlwdD4="})
    assert res.status_code == 422, res.text

    big = "data:image/png;base64," + "A" * 400_000
    res = await client_client.patch("/api/v1/settings/company", json={"logo_ref": big})
    assert res.status_code == 422, res.text


async def test_blank_optional_fields_do_not_break_the_save(client_client):
    """A profile whose fiscal-year (or any optional constrained field) is blank
    must still save — the form re-sends every field, so an empty one used to 422
    the whole PATCH and, when the user was changing currency, looked like a
    currency error."""
    res = await client_client.patch("/api/v1/settings/company", json={
        "currency": "EGP", "fiscal_year_start": "", "legal_name": "",
    })
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["currency"] == "EGP"           # the change the user wanted lands
    assert data.get("fiscal_year_start") in (None, "")  # blank normalised, not rejected
