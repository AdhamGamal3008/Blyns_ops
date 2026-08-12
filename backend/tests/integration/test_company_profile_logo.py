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


async def test_logo_is_stored_and_surfaced_to_every_user(client_client):
    res = await client_client.patch("/api/v1/settings/company", json={"logo_ref": PNG})
    assert res.status_code == 200, res.text
    assert res.json()["data"]["logo_ref"] == PNG

    assert (await client_client.get(
        "/api/v1/settings/company")).json()["data"]["logo_ref"] == PNG

    # /auth/me carries it so the shell can render it without Settings access
    me = (await client_client.get("/api/v1/auth/me")).json()["data"]
    assert me["company"]["logo_ref"] == PNG


async def test_logo_rejects_non_image_and_oversized(client_client):
    res = await client_client.patch("/api/v1/settings/company",
        json={"logo_ref": "data:text/html;base64,PHNjcmlwdD4="})
    assert res.status_code == 422, res.text

    big = "data:image/png;base64," + "A" * 400_000
    res = await client_client.patch("/api/v1/settings/company", json={"logo_ref": big})
    assert res.status_code == 422, res.text
