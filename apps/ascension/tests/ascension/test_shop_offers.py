from collections import Counter

from src.ascension.shop_offers import ShopOffers
from tests.ascension.env import CATALOG

ROTATION = 21600.0
NOW = 1_000_000.0


def offers(count=5):
    return ShopOffers(CATALOG, ROTATION, count)


def test_the_same_account_sees_the_same_window_within_a_rotation():
    first = offers().window("ann", NOW)
    again = offers().window("ann", NOW + 60)
    assert first == again
    assert first.rotation == int(NOW // ROTATION)
    assert first.refreshes_at == (first.rotation + 1) * ROTATION


def test_the_window_changes_with_the_rotation_and_the_account():
    base = offers().window("ann", NOW)
    later = offers().window("ann", NOW + ROTATION)
    other = offers().window("bob", NOW)
    assert later.rotation == base.rotation + 1 and later.offers != base.offers
    assert other.offers != base.offers


def test_offers_are_distinct_regular_ascended_with_stock_by_tier():
    window = offers().window("ann", NOW)
    ids = [o.ascended_id for o in window.offers]
    assert len(window.offers) == 5 and len(set(ids)) == 5
    assert [o.slot for o in window.offers] == [0, 1, 2, 3, 4]
    for offer in window.offers:
        assert not CATALOG.ascended(offer.ascended_id).forbidden
        assert offer.tier_id in CATALOG.shop.stock
        assert offer.stock == CATALOG.shop.stock[offer.tier_id]


def test_the_count_is_limited_by_the_number_of_regular_ascended():
    regular = [s for s in CATALOG.all_ascendeds() if not s.forbidden]
    assert len(offers(12).window("ann", NOW).offers) == min(12, len(regular))


def test_lower_tiers_are_offered_more_often():
    seen = Counter()
    for n in range(300):
        for offer in offers().window(f"player{n}", NOW).offers:
            seen[offer.tier_id] += 1
    assert seen["rare"] > seen["unique"] > seen["legendary"] > 0  # only the Ascended whose ladder reaches a tier are offered at it
