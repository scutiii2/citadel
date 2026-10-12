from src.ascension.models import PassiveSpec
from src.ascension.passives import CombinedPassive, PassiveFactory

FACTORY = PassiveFactory()


def both(*specs):
    return FACTORY.create_all(specs)


def test_one_spec_is_that_passive_and_none_is_neutral():
    assert both().attack_bonus(100, 50, 100, False) == 0.0
    assert both(PassiveSpec("battle_start_speed", {"power_fraction": 0.5})).start_buffs(20) == [("speed", 10)]


def test_bonuses_add_and_multipliers_multiply():
    combined = both(PassiveSpec("low_hp_attack_bonus", {"hp_below": 0.5, "power_fraction": 0.25}),
                    PassiveSpec("attack_bonus_vs_defense", {"power_fraction": 0.2}))
    assert isinstance(combined, CombinedPassive)
    assert combined.attack_bonus(100, 10, 100, True) == 45.0
    assert combined.attack_bonus(100, 90, 100, True) == 20.0
    heals = both(PassiveSpec("heal_bonus", {"fraction": 0.5}), PassiveSpec("heal_bonus", {"fraction": 0.2}))
    assert abs(heals.heal_multiplier(10, 100) - 1.8) < 1e-9


def test_buffs_and_ratings_combine_and_defense_takes_the_best_of_each_limit():
    combined = both(PassiveSpec("defense_extension", {"protected_attacks": 2, "rounds": 1}),
                    PassiveSpec("defense_extension", {"protected_attacks": 1, "rounds": 3}),
                    )
    assert combined.defense_limits() == (2, 3)
    mixed = both(PassiveSpec("defense_rating_bonus", {"power_fraction": 0.3}), PassiveSpec("defense_rating_bonus", {"power_fraction": 0.1}))
    assert abs(mixed.defense_rating_bonus(100) - 40.0) < 1e-9
    support = both(PassiveSpec("support_duration_bonus", {"rounds": 1}), PassiveSpec("support_duration_bonus", {"rounds": 2}))
    assert support.support_extra_rounds() == 3


def test_cooldown_reductions_chain():
    combined = both(PassiveSpec("cooldown_reduction", {"rounds": 1, "minimum": 1}), PassiveSpec("cooldown_reduction", {"rounds": 1, "minimum": 1}))
    assert combined.cooldown(4) == 2 and combined.cooldown(2) == 1


def test_marked_bonus_adds():
    combined = both(PassiveSpec("attack_bonus_vs_marked", {"mark": "prey", "power_fraction": 0.3}),
                    PassiveSpec("attack_bonus_vs_marked", {"mark": "soaked", "power_fraction": 0.1}))
    assert abs(combined.marked_bonus(100, frozenset({"prey", "soaked"})) - 40.0) < 1e-9
    assert combined.marked_bonus(100, frozenset({"prey"})) == 30.0
