from unittest.mock import MagicMock

from incident_copilot.om_poller import poll_once


def _sample_test_case_result(test_case_id: str, status: str = "Failed") -> dict:
    return {
        "testCase": {"id": test_case_id, "fullyQualifiedName": f"svc.db.t.{test_case_id}"},
        "testCaseResult": {
            "testCaseStatus": status,
            "result": "null ratio exceeded",
            "timestamp": 1713436800000,
        },
    }


def test_poller_fetches_and_dispatches_failed_results():
    om_client = MagicMock()
    om_client.fetch_recent_test_case_results.return_value = [
        _sample_test_case_result("tc-1", "Failed"),
        _sample_test_case_result("tc-2", "Failed"),
    ]
    dispatch = MagicMock(return_value={"incident_id": "inc-x"})

    result = poll_once(om_client=om_client, dispatch_fn=dispatch, cursor=0)
    assert result["fetched"] == 2
    assert result["dispatched"] == 2
    assert dispatch.call_count == 2


def test_poller_skips_non_failed_results():
    om_client = MagicMock()
    om_client.fetch_recent_test_case_results.return_value = [
        _sample_test_case_result("tc-1", "Success"),
        _sample_test_case_result("tc-2", "Failed"),
    ]
    dispatch = MagicMock(return_value={"incident_id": "inc-x"})

    result = poll_once(om_client=om_client, dispatch_fn=dispatch, cursor=0)
    assert result["fetched"] == 2
    assert result["dispatched"] == 1


def test_poller_advances_cursor_to_latest_timestamp():
    om_client = MagicMock()
    om_client.fetch_recent_test_case_results.return_value = [
        {"testCase": {"id": "tc-1"}, "testCaseResult": {"testCaseStatus": "Failed", "result": "x", "timestamp": 1000}},
        {"testCase": {"id": "tc-2"}, "testCaseResult": {"testCaseStatus": "Failed", "result": "y", "timestamp": 2000}},
    ]
    dispatch = MagicMock(return_value={"incident_id": "inc-x"})
    result = poll_once(om_client=om_client, dispatch_fn=dispatch, cursor=0)
    assert result["new_cursor"] == 2000


def test_poller_handles_om_fetch_failure():
    om_client = MagicMock()
    om_client.fetch_recent_test_case_results.side_effect = Exception("om unreachable")
    dispatch = MagicMock()
    result = poll_once(om_client=om_client, dispatch_fn=dispatch, cursor=0)
    assert result["fetched"] == 0
    assert result["dispatched"] == 0
    assert "error" in result
    dispatch.assert_not_called()


def test_poller_handles_empty_result():
    om_client = MagicMock()
    om_client.fetch_recent_test_case_results.return_value = []
    dispatch = MagicMock()
    result = poll_once(om_client=om_client, dispatch_fn=dispatch, cursor=1000)
    assert result["fetched"] == 0
    assert result["dispatched"] == 0
    assert result["new_cursor"] == 1000  # unchanged


def test_poller_tolerates_dispatch_failure_per_event():
    om_client = MagicMock()
    om_client.fetch_recent_test_case_results.return_value = [
        _sample_test_case_result("tc-1", "Failed"),
        _sample_test_case_result("tc-2", "Failed"),
    ]
    dispatch = MagicMock(side_effect=[Exception("bad"), {"incident_id": "ok"}])
    result = poll_once(om_client=om_client, dispatch_fn=dispatch, cursor=0)
    assert result["fetched"] == 2
    assert result["dispatched"] == 1
    assert result["dispatch_errors"] == 1
