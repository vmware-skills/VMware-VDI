"""Server-side pagination for Horizon list endpoints.

Horizon paginates list responses (query params ``page`` 1-based + ``size``). A single
GET returns only the first page, so a bare fetch silently truncates a large estate and
makes the caller's ``truncated`` flag lie and blast-radius counts under-report (issue
#31 / recurring-shape #1). ``fetch_all`` loops until a short page, with a safety cap.
"""

from __future__ import annotations

from typing import Any

_PAGE_SIZE = 1000
_MAX_PAGES = 100


def fetch_all(client: Any, path: str, params: dict | None = None, *, page_size: int = _PAGE_SIZE) -> list[dict]:
    """Fetch every page of a Horizon collection, deduped by ``id``.

    Two independent stop conditions guard both a paginating and a *non*-paginating server:

    * ``len(page) < page_size`` — the normal last page.
    * ``added == 0`` — a page brought no row with a new ``id``. A server that ignores
      ``page``/``size`` re-returns its whole list every time; without this guard, a list
      of ≥``page_size`` rows would look "full" on every page and loop to the cap,
      returning the estate duplicated ~100× (which would inflate ``pool_push_image``'s
      blast-radius preview by the same factor). Dedup-by-id makes the result correct
      regardless, and this guard makes it cheap (2 GETs, not 100).

    ``_MAX_PAGES`` is a final backstop for the pathological case of ≥``page_size``
    id-less rows from a non-paginating server.
    """
    out: list[dict] = []
    seen_ids: set = set()
    page = 1
    while page <= _MAX_PAGES:
        p = dict(params or {})
        p["page"] = page
        p["size"] = page_size
        data = client.get(path, params=p)
        if isinstance(data, dict):
            data = data.get("results") or data.get("items") or []
        if not isinstance(data, list):
            data = []
        added = 0
        for row in data:
            rid = row.get("id") if isinstance(row, dict) else None
            if rid is not None:
                if rid in seen_ids:
                    continue
                seen_ids.add(rid)
            out.append(row)
            added += 1
        if len(data) < page_size or added == 0:
            break
        page += 1
    return out
