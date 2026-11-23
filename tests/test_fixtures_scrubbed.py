"""The committed Allegro fixtures must carry no personal or secret data."""

import json
from pathlib import Path
import re

FIXTURES = Path(__file__).parent / "fixtures"
SECRET_KEYS = ("code", "qrCode", "receiverPhoneNumber", "login", "street")


def _values_of(key: str, node: object):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key and isinstance(v, str):
                yield v
            yield from _values_of(key, v)
    elif isinstance(node, list):
        for item in node:
            yield from _values_of(key, item)


def test_fixtures_contain_no_secrets():
    bodies = [json.loads(p.read_text()) for p in FIXTURES.glob("*.json")]
    assert len(bodies) == 3
    for body in bodies:
        for key in SECRET_KEYS:
            for value in _values_of(key, body):
                assert value.startswith("FAKE"), (key, value[:2])
    text = "".join(p.read_text() for p in FIXTURES.glob("*.json"))
    assert "QXLSESSID" not in text
    assert not re.search(r"snapshot=(?!FAKE)", text)


def test_purchase_history_is_fake():
    """What was bought, from whom, for how much and how it was paid is personal."""
    orders = json.loads((FIXTURES / "myorders.json").read_text())
    packages = json.loads((FIXTURES / "packages.json").read_text())
    for group in orders["orderGroups"]:
        for order in group["myorders"]:
            assert "payment" not in order or order["payment"] == {"FAKE": "removed"}
            assert order["seller"]["login"].startswith("FAKE")
            for offer in order["offers"]:
                assert offer["title"].startswith("FAKE")
                assert int(offer["id"]) >= 900000
                assert offer["unitPrice"]["amount"] == "0.00"
    for package in packages["packages"]:
        assert package["content"]["description"].startswith("FAKE")


def test_users_fixture_keeps_only_the_fake_login():
    users = json.loads((FIXTURES / "users.json").read_text())
    assert users == {"accounts": {"allegro": {"login": "FAKE-login-0"}}}


def test_pickup_points_are_fake():
    orders = json.loads((FIXTURES / "myorders.json").read_text())
    for group in orders["orderGroups"]:
        for order in group["myorders"]:
            point = order["delivery"].get("generalDelivery")
            if point:
                assert point["name"].startswith("FAKE")
                assert point["address"]["city"].startswith("FAKE")
