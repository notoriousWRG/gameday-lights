

from app.config import BulbConfig, Config, GeneralConfig, TeamConfig
from app.effects import EffectConfig
from tests.support import (
    Down,
    cfg,
    client,
    make,
    page_text,
)


def test_setup_items_for_a_fresh_install_a_healthy_one_and_trouble():
    from app.web.status import setup_items

    empty = Config(GeneralConfig(True, "x.db"), (), (), EffectConfig())
    todo = {i["id"] for i in setup_items(empty, {}, False) if not i["done"]}
    assert todo == {"bulb", "team"}

    assert [i for i in setup_items(cfg(), {"lamp": 12.0}, False) if not i["done"]] == []

    trouble = {i["id"]: i for i in setup_items(cfg(), {"lamp": None}, True)}
    assert trouble["reach:lamp"]["fix"] == "#/bulbs"
    assert "dispatch_enabled" in trouble["live"]["hint"] and trouble["live"]["fix"] is None


def test_setup_flags_a_bulb_no_team_uses():
    from app.web.status import setup_items

    config = Config(GeneralConfig(True, "x.db"),
                    (BulbConfig("lamp", "1.1.1.1"), BulbConfig("spare", "1.1.1.2")),
                    (TeamConfig("nfl", "9", "GB", ("lamp",)),), EffectConfig())
    todo = {i["id"] for i in setup_items(config, {"lamp": 1.0, "spare": 1.0}, False)
            if not i["done"]}
    assert todo == {"unused:spare"}


async def test_setup_endpoint_and_page_card():
    async with client(make(Down("lamp"))) as c:
        items = (await c.get("/api/setup")).json()["items"]
        html = await page_text(c)
    assert any(i["id"] == "reach:lamp" for i in items)
    assert 'id="setup-card"' in html and "api/setup" in html
