from __future__ import annotations

from src.services.forge.routing import Member, TurnRouter

CLAUDE, CODEX = Member(1, "claude"), Member(2, "codex")
BOTH = [CLAUDE, CODEX]
router = TurnRouter()


def test_a_mention_picks_the_worker_ignoring_case() -> None:
    assert router.target_for_user("@Codex review this", BOTH, None) == CODEX
    assert router.target_for_user("hey @claude, hi", BOTH, 2) == CLAUDE


def test_the_first_known_mention_wins_and_unknown_ones_are_skipped() -> None:
    assert router.target_for_user("@bob then @codex then @claude", BOTH, None) == CODEX


def test_an_email_address_is_not_a_mention() -> None:
    assert router.target_for_user("mail me at a@claude.com", BOTH, None) is None


def test_a_longer_handle_does_not_match_a_shorter_label() -> None:
    assert router.target_for_user("@codex-review go", BOTH, None) is None


def test_no_mention_goes_to_the_last_addressed_worker() -> None:
    assert router.target_for_user("keep going", BOTH, 2) == CODEX


def test_no_mention_and_no_last_goes_to_the_only_worker() -> None:
    assert router.target_for_user("hello", [CLAUDE], None) == CLAUDE
    assert router.target_for_user("hello", BOTH, None) is None
    assert router.target_for_user("hello", [], None) is None


def test_a_last_addressed_worker_that_left_is_ignored() -> None:
    assert router.target_for_user("hello", [CLAUDE], 99) == CLAUDE


def test_handoff_reads_the_last_line_of_a_reply() -> None:
    reply = "I fixed the bug.\n\n@codex please review the patch"

    assert router.handoff(reply, BOTH, current_worker_id=1) == (CODEX, "please review the patch")


def test_handoff_with_nothing_after_the_mention_asks_to_continue() -> None:
    assert router.handoff("done\n@codex", BOTH, 1) == (CODEX, "Please continue.")
    assert router.handoff("done\n@codex:", BOTH, 1) == (CODEX, "Please continue.")


def test_handoff_ignores_mentions_that_are_not_the_start_of_the_last_line() -> None:
    assert router.handoff("ping @codex first\nthen I stop", BOTH, 1) is None
    assert router.handoff("see you, @codex", BOTH, 1) is None


def test_a_worker_cannot_hand_off_to_itself_or_a_stranger() -> None:
    assert router.handoff("ok\n@claude again", BOTH, 1) is None
    assert router.handoff("ok\n@nobody hi", BOTH, 1) is None
    assert router.handoff("", BOTH, 1) is None


def test_the_depth_cap_is_configurable() -> None:
    assert router.max_relay_depth == 3
    assert TurnRouter(max_relay_depth=1).max_relay_depth == 1
