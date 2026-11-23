"""Capture real Allegro responses and write scrubbed test fixtures.

Usage: ALLEGRO_QXLSESSID=<cookie value> python3 scripts/capture.py

Raw bodies go to captures/ (gitignored, contain secrets). Scrubbed copies go
to tests/fixtures/. The cookie is read from the environment only and is never
written anywhere.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import string
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
CAPTURES = ROOT / "captures"
FIXTURES = ROOT / "tests" / "fixtures"

ENDPOINTS = {
    "users": (
        "https://api.allegro.pl/users",
        "application/vnd.allegro.public.v2+json",
    ),
    "myorders": (
        "https://api.allegro.pl/myorder-api/myorders?limit=25",
        "application/vnd.allegro.public.v3+json",
    ),
    "packages": (
        "https://edge.allegro.pl/packages",
        "application/vnd.allegro.internal.v1+json",
    ),
}

# Keys whose values are personal or secret, replaced with stable fakes.
SECRET_KEYS = {
    "code",
    "qrCode",
    "receiverPhoneNumber",
    "firstName",
    "lastName",
    "email",
    "phoneNumber",
    "street",
    "login",
}
# What was bought is purchase history, i.e. personal data: fake it too.
PURCHASE_KEYS = {
    "title",
    "description",
    "friendlyUrl",
    "imageUrl",
    "productId",
    "url",
    "totalCostLabel",
}
# Subtrees that describe a person, dropped wholesale.
PERSON_KEYS = {
    "buyer",
    "receiver",
    "invoice",
    "invoiceAddress",
    "deliveryAddress",
    "addresses",
    "company",
    "contacts",
    "person",
    # How the buyer paid (e.g. Allegro Pay credit).
    "payment",
    "secondary",
    "paymentType",
}
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# Offer links carry a per-buyer snapshot token.
SNAPSHOT = re.compile(r"snapshot=[^\"&]*")


def fake_leaves(node: object, key: str, fakes: dict[str, str]) -> object:
    """Keep the shape of a subtree, replacing every string with a stable fake."""
    if isinstance(node, dict):
        return {k: fake_leaves(v, k, fakes) for k, v in node.items()}
    if isinstance(node, list):
        return [fake_leaves(item, key, fakes) for item in node]
    if isinstance(node, str):
        fakes.setdefault(f"{key}:{node}", f"FAKE-{key}-{len(fakes)}")
        return fakes[f"{key}:{node}"]
    return node


def fake_uuid(real: str, key: bytes) -> str:
    """Map a UUID to a stable fake, so ids still join across files."""
    digest = _digest(real, key)
    return (
        f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"
    )


def fetch(cookie: str, url: str, accept: str) -> bytes:
    """GET one endpoint with the session cookie."""
    request = urllib.request.Request(
        url,
        headers={
            "Cookie": f"QXLSESSID={cookie}",
            "Referer": "https://allegro.pl/",
            "Accept": accept,
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def scrub_key() -> bytes:
    """Secret HMAC key kept in captures/ (gitignored), so fakes cannot be reversed."""
    path = CAPTURES / ".scrub-key"
    if not path.exists():
        path.write_bytes(secrets.token_bytes(32))
    return path.read_bytes()


def _digest(real: str, key: bytes) -> str:
    return hmac.new(key, real.encode(), hashlib.sha256).hexdigest()


def fake_waybill(real: str, key: bytes) -> str:
    """Map a waybill to a stable fake of the same length and character classes."""
    digest = _digest(real, key)
    out = []
    for index, char in enumerate(real):
        seed = int(
            digest[(index * 2) % len(digest) : (index * 2) % len(digest) + 2], 16
        )
        if char.isdigit():
            out.append(string.digits[seed % 10])
        elif char.isupper():
            out.append(string.ascii_uppercase[seed % 26])
        elif char.islower():
            out.append(string.ascii_lowercase[seed % 26])
        else:
            out.append(char)
    return "".join(out)


def collect_waybills(node: object, found: set[str]) -> None:
    """Find every waybill number in a response."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("waybill", "waybillId") and isinstance(value, str):
                found.add(value)
            collect_waybills(value, found)
    elif isinstance(node, list):
        for item in node:
            collect_waybills(item, found)


def scrub(node: object, fakes: dict[str, str]) -> object:
    """Replace secret values with stable fakes, recursively."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key in PERSON_KEYS:
                out[key] = {"FAKE": "removed"}
            elif key == "generalDelivery":
                # Pickup point names and addresses reveal where the buyer lives.
                out[key] = fake_leaves(value, key, fakes)
            elif key == "id" and isinstance(value, str) and value.isdigit():
                # Numeric ids are offers and sellers: each leads to what was bought.
                fakes.setdefault(f"id:{value}", str(900000 + len(fakes)))
                out[key] = fakes[f"id:{value}"]
            elif key == "amount" and isinstance(value, str):
                # What the buyer spent is personal too.
                out[key] = "0.00"
            elif key in (SECRET_KEYS | PURCHASE_KEYS) and isinstance(value, (str, int)):
                fakes.setdefault(f"{key}:{value}", f"FAKE-{key}-{len(fakes)}")
                out[key] = fakes[f"{key}:{value}"]
            else:
                out[key] = scrub(value, fakes)
        return out
    if isinstance(node, list):
        return [scrub(item, fakes) for item in node]
    return node


def main() -> int:
    # --offline re-scrubs the existing captures/ without calling Allegro.
    offline = "--offline" in sys.argv
    cookie = os.environ.get("ALLEGRO_QXLSESSID", "").strip()
    if not cookie and not offline:
        print("Set ALLEGRO_QXLSESSID to the QXLSESSID cookie value.", file=sys.stderr)
        return 2
    CAPTURES.mkdir(exist_ok=True)
    FIXTURES.mkdir(parents=True, exist_ok=True)

    bodies = {}
    for name, (url, accept) in ENDPOINTS.items():
        if offline:
            raw = (CAPTURES / f"{name}.json").read_bytes()
        else:
            try:
                raw = fetch(cookie, url, accept)
            except urllib.error.HTTPError as err:
                print(f"{name}: HTTP {err.code}", file=sys.stderr)
                return 1
            (CAPTURES / f"{name}.json").write_bytes(raw)
        try:
            bodies[name] = json.loads(raw)
        except ValueError:
            print(f"{name}: not JSON (bot protection page?)", file=sys.stderr)
            return 1

    waybills: set[str] = set()
    for body in bodies.values():
        collect_waybills(body, waybills)
    # Only the login is used from /users; keep nothing else (account id, dates).
    login = bodies["users"].get("accounts", {}).get("allegro", {}).get("login")
    bodies["users"] = {"accounts": {"allegro": {"login": login}}}
    key = scrub_key()
    fakes: dict[str, str] = {}
    for name, body in bodies.items():
        text = json.dumps(scrub(body, fakes), indent=2, ensure_ascii=False)
        # Waybills also appear inside tracking URLs, so replace them as text.
        for real in sorted(waybills, key=len, reverse=True):
            text = text.replace(real, fake_waybill(real, key))
        text = UUID.sub(lambda m: fake_uuid(m.group(0), key), text)
        text = SNAPSHOT.sub("snapshot=FAKE", text)
        if cookie and cookie in text:
            print(f"{name}: cookie found in output, aborting", file=sys.stderr)
            return 1
        (FIXTURES / f"{name}.json").write_text(text + "\n")

    orders = sum(
        len(g.get("myorders", [])) for g in bodies["myorders"].get("orderGroups", [])
    )
    print(f"orders={orders} packages={len(bodies['packages'].get('packages', []))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
