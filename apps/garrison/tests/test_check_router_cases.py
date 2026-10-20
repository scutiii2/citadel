from scripts.check_router_cases import CASES, evaluate, main


def test_offline_cases_cover_plumbing_and_abstention_without_claiming_accuracy(capsys):
    result = evaluate(live=False)
    assert result["mode"] == "offline_contract_fixtures"
    assert len(result["cases"]) == len(CASES)
    assert result["remote_calls"] == 0
    assert all(row["contract_ok"] for row in result["cases"])
    assert main(["--offline"]) == 0
    assert "offline_contract_fixtures" in capsys.readouterr().out
