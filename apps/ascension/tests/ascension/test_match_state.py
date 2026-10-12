import pytest

from src.ascension.match_state import MatchReader, MoodConstants
from src.ascension.models import PLAYER, WILD, BattleState, FighterState
from tests.ascension.helpers import revealed_round as rnd, setup

reader = MatchReader(MoodConstants())
SETUP = setup()  # both fighters have 100 HP


def read(history, player_hp=100, wild_hp=100, side=PLAYER):
    state = BattleState(len(history) + 1, FighterState(player_hp), FighterState(wild_hp), tuple(history))
    return reader.read(SETUP, state, side)


def test_a_fresh_battle_reads_neutral():
    match, meters = read([])
    assert (match.own_hp, match.enemy_hp, match.lead, match.trend, match.round) == (1.0, 1.0, 0.0, 0.0, 1)
    assert (match.own_streak, match.own_last, match.enemy_last, match.hit_taken, match.enemy_low) == (0, None, None, 0.0, False)
    assert (meters.rage, meters.confidence, meters.nerves) == (0.0, 0.5, 0.0)


def test_rage_jumps_with_a_hit_and_halves_each_quiet_round():
    _, hit = read([rnd(1, hits=[(WILD, 10)])], player_hp=90)
    assert hit.rage == pytest.approx(0.4)
    _, quiet = read([rnd(1, hits=[(WILD, 10)]), rnd(2)], player_hp=90)
    assert quiet.rage == pytest.approx(0.2)
    _, big = read([rnd(1, hits=[(WILD, 40)])], player_hp=60)
    assert big.rage == 1.0  # clamped


def test_confidence_rises_when_the_lead_grows_and_falls_when_it_shrinks():
    _, up = read([rnd(1, hits=[(PLAYER, 30)])], wild_hp=70)
    assert up.confidence == pytest.approx(0.7)
    _, down = read([rnd(1, hits=[(PLAYER, 30)]), rnd(2, hits=[(WILD, 50)])], player_hp=50, wild_hp=70)
    assert down.confidence == pytest.approx(0.5)
    _, flat = read([rnd(1), rnd(2)])
    assert flat.confidence == 0.5


def test_nerves_follow_the_lead_and_low_hp():
    _, one = read([rnd(1, hits=[(WILD, 60)])], player_hp=40)
    assert one.nerves == pytest.approx(0.35)  # target 0.6 + 0.1, half way
    _, two = read([rnd(1, hits=[(WILD, 60)]), rnd(2)], player_hp=40)
    assert two.nerves == pytest.approx(0.525)
    _, winning = read([rnd(1, hits=[(PLAYER, 60)])], wild_hp=40)
    assert winning.nerves == 0.0


def test_match_state_reads_hp_lead_trend_streak_and_the_enemy():
    history = [
        rnd(1, player=("attack", "ATTACK"), wild=("attack", "ATTACK"), hits=[(PLAYER, 30)]),
        rnd(2, player=("ability:g", "DEFENSE"), wild=("ability:s", "SUPPORT"), hits=[(WILD, 20)]),
        rnd(3, player=("ability:g", "DEFENSE"), wild=("attack", "ATTACK")),
    ]
    match, _ = read(history, player_hp=80, wild_hp=70)
    assert (match.own_hp, match.enemy_hp) == (0.8, 0.7)
    assert match.lead == pytest.approx(0.1) and match.trend == pytest.approx(-0.2)  # leads 0, 0.3, 0.1, 0.1
    assert (match.own_last, match.own_streak, match.enemy_last, match.round) == ("DEFENSE", 2, "ATTACK", 4)
    assert match.hit_taken == 0.0  # nothing last round


def test_the_last_rounds_damage_is_the_hit_taken_and_a_low_enemy_is_flagged():
    match, _ = read([rnd(1, hits=[(WILD, 25)])], player_hp=75, wild_hp=20)
    assert match.hit_taken == pytest.approx(0.25) and match.enemy_low is True


def test_the_wild_side_reads_the_same_battle_from_its_own_seat():
    history = [rnd(1, hits=[(PLAYER, 30)])]
    mine, _ = read(history, wild_hp=70, side=PLAYER)
    theirs, meters = read(history, wild_hp=70, side=WILD)
    assert mine.lead == pytest.approx(0.3) and theirs.lead == pytest.approx(-0.3)
    assert theirs.hit_taken == pytest.approx(0.3) and meters.rage == 1.0  # 0.3 * 4 clamps


def test_reading_twice_gives_the_same_answer():
    history = [rnd(1, hits=[(WILD, 12)]), rnd(2, hits=[(PLAYER, 5)])]
    assert read(history, player_hp=88, wild_hp=95) == read(history, player_hp=88, wild_hp=95)


def test_bleed_ticks_count_as_damage_and_heals_as_recovery():
    from src.ascension.models import RevealedRound

    events = (
        {"type": "tick", "side": PLAYER, "kind": "bleed", "amount": 10, "hp": 90},
        {"type": "heal", "side": WILD, "amount": 15},
        {"type": "tick", "side": WILD, "kind": "regen", "amount": 5, "hp": 100},
    )
    first = RevealedRound(1, {PLAYER: ("attack", "ATTACK"), WILD: ("attack", "ATTACK")}, events)
    match, meters = read([first], player_hp=90, wild_hp=100)
    assert match.hit_taken == pytest.approx(0.1)
    assert meters.rage == pytest.approx(0.4)
    assert meters.confidence == pytest.approx(0.3)  # the lead shrank: own lost 10, the foe healed back to full
