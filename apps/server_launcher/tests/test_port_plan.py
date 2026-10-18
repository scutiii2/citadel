"""The port plan: ranges, reservations, free-port choice and the file form."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.port_plan import (
    FALLBACK_RANGE, PortPlan, PortPlanError, PortRange, assign_ports, default_plan, load_plan, save_plan,
)


def plan_with(*reserved: tuple[str, int]) -> PortPlan:
    return PortPlan(
        [PortRange("Web", 5170, 5179), PortRange("Api", 8030, 8039), PortRange(FALLBACK_RANGE, 8100, 8104)],
        dict(reserved),
    )


def nothing_busy(_port: int) -> bool:
    return False


class RangeTests(unittest.TestCase):
    def test_ranges_may_not_overlap_repeat_a_name_or_run_backwards(self) -> None:
        plan = plan_with()

        with self.assertRaisesRegex(PortPlanError, "overlaps Api"):
            plan.add_range("Other", 8035, 8050)
        with self.assertRaisesRegex(PortPlanError, "already a range called Api"):
            plan.add_range("Api", 9000, 9001)
        with self.assertRaisesRegex(PortPlanError, "cannot end before"):
            plan.add_range("Back", 9010, 9000)
        with self.assertRaisesRegex(PortPlanError, "needs a name"):
            plan.add_range("  ", 9000, 9001)
        with self.assertRaisesRegex(PortPlanError, "Ports run from"):
            plan.add_range("Big", 1, 70000)

        self.assertEqual([r.name for r in plan.ranges], ["Web", "Api", FALLBACK_RANGE])

    def test_resizing_keeps_every_reservation_inside_and_may_overlap_itself(self) -> None:
        plan = plan_with(("ember_api", 8030), ("db", 8037))

        plan.update_range("Api", "Backend", 8030, 8039)  # a rename alone is fine
        with self.assertRaisesRegex(PortPlanError, "db would fall outside"):
            plan.update_range("Backend", "Backend", 8030, 8035)
        with self.assertRaisesRegex(PortPlanError, "overlaps"):
            plan.update_range("Backend", "Backend", 8030, 8150)

        self.assertEqual(plan.range_named("Backend"), PortRange("Backend", 8030, 8039))

    def test_a_range_with_reservations_and_the_fallback_range_cannot_be_removed(self) -> None:
        plan = plan_with(("ember_api", 8030))

        with self.assertRaisesRegex(PortPlanError, "ember_api still reserve"):
            plan.remove_range("Api")
        with self.assertRaisesRegex(PortPlanError, "Keep it"):
            plan.remove_range(FALLBACK_RANGE)
        plan.remove_range("Web")

        self.assertIsNone(plan.range_named("Web"))


class ReservationTests(unittest.TestCase):
    def test_a_port_belongs_to_one_server_and_must_sit_in_a_range(self) -> None:
        plan = plan_with(("ember_web", 5173))

        with self.assertRaisesRegex(PortPlanError, "already reserved for ember_web"):
            plan.reserve("ember_admin", 5173)
        with self.assertRaisesRegex(PortPlanError, "not inside any range"):
            plan.reserve("ember_admin", 7000)
        plan.reserve("ember_web", 5174)  # moving a server's own reservation is fine

        self.assertEqual(plan.port_for("ember_web"), 5174)
        self.assertIsNone(plan.owner_of(5173))
        self.assertEqual(plan.conflict("ember_admin", 5174), "Port 5174 is reserved for ember_web.")
        self.assertIsNone(plan.conflict("ember_web", 5174))

    def test_release_frees_the_port(self) -> None:
        plan = plan_with(("ember_web", 5173))

        plan.release("ember_web")
        plan.release("never_reserved")

        self.assertIsNone(plan.port_for("ember_web"))


class FreePortTests(unittest.TestCase):
    def test_the_desired_port_is_used_when_free(self) -> None:
        self.assertEqual(plan_with(("ember_web", 5173)).free_port("ember_web", 5173, nothing_busy), 5173)

    def test_a_busy_port_moves_inside_its_range_and_skips_other_servers_ports(self) -> None:
        plan = plan_with(("ember_web", 5173), ("ember_admin", 5170), ("pdf_web", 5171))
        busy = {5173}.__contains__

        # the next port up is free
        self.assertEqual(plan.free_port("ember_web", 5173, busy), 5174)
        # a taken 5174 is skipped too, and a reserved port is never used
        self.assertEqual(plan.free_port("ember_web", 5173, {5173, 5174}.__contains__), 5175)
        # at the top of the range it wraps to the start, skipping the reserved 5170 and 5171
        self.assertEqual(plan.free_port("ember_web", 5179, {5179}.__contains__), 5172)

    def test_a_port_reserved_for_another_server_is_never_taken(self) -> None:
        plan = plan_with(("ember_web", 5173), ("ember_admin", 5176))

        self.assertNotEqual(plan.free_port("ember_web", 5176, nothing_busy), 5176)

    def test_a_busy_port_outside_every_range_goes_to_the_fallback_range(self) -> None:
        plan = plan_with()

        self.assertEqual(plan.free_port("thing", 3000, {3000, 8100}.__contains__), 8101)

    def test_a_full_range_is_an_error_not_a_neighbouring_port(self) -> None:
        plan = plan_with()

        with self.assertRaisesRegex(PortPlanError, "No free port in Unassigned"):
            plan.free_port("thing", 3000, lambda port: port == 3000 or 8100 <= port <= 8104)

    def test_allocate_reserves_the_preferred_port_when_it_is_open_else_a_fallback_port(self) -> None:
        plan = plan_with(("ember_api", 8030))

        self.assertEqual(plan.allocate("a", nothing_busy, preferred=8031), 8031)
        self.assertEqual(plan.allocate("b", nothing_busy, preferred=8030), 8100)  # taken: fallback
        self.assertEqual(plan.allocate("c", nothing_busy, preferred=8000), 8101)  # outside every range
        self.assertEqual(plan.allocate("d", nothing_busy), 8102)
        self.assertEqual(plan.port_for("c"), 8101)


class AssignTests(unittest.TestCase):
    def test_every_server_gets_a_reserved_port_and_nothing_defaults_to_8000(self) -> None:
        plan = plan_with(("ember_api", 8030))
        servers = [
            SimpleNamespace(key="ember_api", default_port=8000),
            SimpleNamespace(key="worker", default_port=8000),
            SimpleNamespace(key="web", default_port=5176),
        ]

        changed = assign_ports(plan, servers, nothing_busy, lambda template: template.default_port)

        self.assertTrue(changed)
        self.assertEqual([s.default_port for s in servers], [8030, 8100, 5176])
        self.assertFalse(assign_ports(plan, servers, nothing_busy, lambda template: template.default_port))


class FileTests(unittest.TestCase):
    def test_the_plan_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "port_plan.json"
            save_plan(plan_with(("ember_web", 5173)), path)

            loaded = load_plan(path)

        self.assertEqual(loaded.to_dict(), plan_with(("ember_web", 5173)).to_dict())

    def test_a_missing_or_broken_file_gives_the_default_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "port_plan.json"
            self.assertEqual(load_plan(path).to_dict(), default_plan().to_dict())
            for text in ("{not json", "[]", json.dumps({"ranges": [{"name": "a", "start": 9, "end": 1}]})):
                path.write_text(text, encoding="utf-8")
                self.assertEqual(load_plan(path).to_dict(), default_plan().to_dict(), text)

    def test_the_default_plan_keeps_todays_ports_and_has_no_overlap(self) -> None:
        plan = default_plan()

        self.assertEqual(plan.port_for("chess"), 8070)
        self.assertEqual(plan.port_for("db_gateway"), 8071)
        self.assertEqual([plan.port_for(k) for k in ("ember_web", "pdf_merger_web", "video_downloader_web", "ember_admin")],
                         [5173, 5174, 5175, 5176])
        # a second chess instance can no longer land on db_gateway's port
        self.assertEqual(plan.free_port("chess", 8070, {8070}.__contains__), 8072)


if __name__ == "__main__":
    unittest.main()
