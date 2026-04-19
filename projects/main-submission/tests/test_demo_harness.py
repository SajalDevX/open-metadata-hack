from incident_copilot.demo_harness import run_demo_once, run_replay_command


def test_replay_mode_is_deterministic():
    replay = {
        "incident_id": "inc-replay",
        "entity_fqn": "svc.db.customer_profiles",
        "test_case_id": "tc-1",
        "severity": "high",
        "occurred_at": "2026-04-18T00:00:00Z",
        "raw_ref": "evt-1",
    }
    om_data = {"failed_test": {"message": "null ratio high"}, "lineage": [], "owners": {}, "classifications": {}}
    a = run_demo_once(live_event=None, replay_event=replay, om_data=om_data)
    b = run_demo_once(live_event=None, replay_event=replay, om_data=om_data)
    assert a["brief"] == b["brief"]


def test_cli_entrypoint_writes_reproducible_output(tmp_path):
    replay = {
        "incident_id": "inc-2",
        "entity_fqn": "svc.db.customer_profiles",
        "test_case_id": "tc-1",
        "severity": "high",
        "occurred_at": "2026-04-18T00:00:00Z",
        "raw_ref": "evt-1",
    }
    om_data = {"failed_test": {"message": "x"}, "lineage": [], "owners": {}, "classifications": {}}
    out1 = run_replay_command(replay, om_data, str(tmp_path / "latest_brief.json"))
    out2 = run_replay_command(replay, om_data, str(tmp_path / "latest_brief.json"))
    assert out1["brief"] == out2["brief"]
