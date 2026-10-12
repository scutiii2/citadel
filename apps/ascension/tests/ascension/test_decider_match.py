import pytest

from src.ascension.decider import ActionDecider
from src.ascension.engine import BattleEngine
from src.ascension.models import PLAYER, WILD, BattleState, FighterState, PersonalityInstance
from src.ascension.policy import ActionPolicy, Mood
from src.ascension.situation import HeuristicSituationReader, SituationViewBuilder
from tests.ascension.env import CATALOG, run
from tests.ascension.helpers import ScriptedPolicy, ScriptedRandom, revealed_round, setup

engine = BattleEngine(CATALOG)
views = SituationViewBuilder(engine)
reader = HeuristicSituationReader(CATALOG.policy.default_aggression)
SETUP = setup()
STATE = BattleState(2, FighterState(70), FighterState(100), (revealed_round(1, hits=[(WILD, 30)]),))
AGGRESSIVE = (PersonalityInstance("p1", "AGGRESSIVE", 2),)


def decider(policy=None):
    return ActionDecider(CATALOG, engine, policy or ActionPolicy(CATALOG.policy), Mood(CATALOG), reader, views)


def test_the_audit_records_the_match_the_mood_and_the_categories():
    decision = run(decider().decide(SETUP, STATE, PLAYER, AGGRESSIVE, ScriptedRandom(0.0, 0.0), can_collect=False))
    audit = decision.audit
    assert audit["match"]["own_hp"] == 0.7 and audit["match"]["lead"] == pytest.approx(-0.3, abs=1e-3)
    assert audit["match"]["hit_taken"] == pytest.approx(0.3, abs=1e-3) and audit["match"]["own_last"] == "ATTACK"
    assert set(audit["mood_meters"]) == {"rage", "confidence", "nerves"} and audit["mood_meters"]["rage"] == 1.0
    assert audit["fired"] == [] and set(audit["categories"]) == {"ATTACK", "FEAR"}
    assert audit["mood"] == "p1" and audit["chosen"] in audit["probabilities"]


def test_it_still_draws_only_for_the_mood_and_the_choice():
    random = ScriptedRandom(0.5, 0.5)
    run(decider().decide(SETUP, STATE, PLAYER, AGGRESSIVE, random, can_collect=False))
    assert random.used == 2
    random = ScriptedRandom(0.5)
    run(decider().decide(SETUP, STATE, PLAYER, (), random, can_collect=False))
    assert random.used == 1


def test_a_scripted_policy_without_details_still_gets_an_audit():
    decision = run(decider(ScriptedPolicy(player=["flee"])).decide(SETUP, STATE, PLAYER, AGGRESSIVE, ScriptedRandom(0.0, 0.0), can_collect=False))
    assert decision.action.key == "flee" and decision.audit["fired"] == [] and decision.audit["categories"] == {}
    assert "match" in decision.audit and "mood_meters" in decision.audit


def test_the_wild_side_reads_its_own_seat():
    decision = run(decider().decide(SETUP, STATE, WILD, (), ScriptedRandom(0.0), can_collect=False))
    assert decision.audit["match"]["lead"] == pytest.approx(0.3, abs=1e-3) and decision.audit["match"]["hit_taken"] == 0.0
