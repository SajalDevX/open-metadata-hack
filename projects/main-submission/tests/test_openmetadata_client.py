import os
from unittest.mock import patch

from incident_copilot.openmetadata_client import OpenMetadataClient, OpenMetadataClientError, OpenMetadataSettings


class FakeClient(OpenMetadataClient):
    def __init__(self, responses, raise_on_missing=False):
        super().__init__(OpenMetadataSettings(base_url="http://localhost:8585/api", token=None, entity_type="table", timeout_seconds=1))
        self.responses = responses
        self.raise_on_missing = raise_on_missing
        self.called_paths = []

    def _json_get(self, path, query=None):  # noqa: D401 - intentional test override
        key = (path, tuple(sorted((query or {}).items())))
        self.called_paths.append(path)
        if key not in self.responses:
            if self.raise_on_missing:
                raise OpenMetadataClientError(f"missing mock for {path}")
            return {}
        return self.responses[key]

    def _get_table(self, fqn):
        key = f"table::{fqn}"
        return self.responses.get(key)


def test_fetch_incident_context_builds_expected_shape():
    entity_fqn = "svc.db.customer_profiles"
    test_case = {
        "name": "tc-null-ratio",
        "fullyQualifiedName": "svc.db.customer_profiles.tc-null-ratio",
        "testDefinition": {"name": "tableColumnCountToEqual"},
        "testCaseResult": {"result": "null ratio exceeded"},
    }
    lineage = {
        "entity": {"id": "root", "fullyQualifiedName": entity_fqn, "type": "table"},
        "nodes": [{"id": "n1", "fullyQualifiedName": "svc.db.customer_curated", "type": "table"}],
        "downstreamEdges": [{"fromEntity": "root", "toEntity": "n1"}],
    }

    responses = {
        ("/v1/dataQuality/testCases/name/tc-null-ratio", (("fields", "testCaseResult,testDefinition,owners,tags"),)): test_case,
        (
            "/v1/dataQuality/testCases/testCaseResults/search/list",
            (("limit", 1), ("offset", 0), ("sortField", "timestamp"), ("sortType", "desc"), ("testCaseFQN", "svc.db.customer_profiles.tc-null-ratio")),
        ): {"data": [{"result": "latest failure"}]},
        ("/v1/lineage/table/name/svc.db.customer_profiles", (("downstreamDepth", 2), ("upstreamDepth", 2))): lineage,
        f"table::{entity_fqn}": {"owners": [{"type": "user", "name": "dre-oncall"}], "domains": [], "tags": []},
        "table::svc.db.customer_curated": {"owners": [], "domains": [], "tags": [{"tagFQN": "PII.Sensitive"}]},
    }

    client = FakeClient(responses)
    out = client.fetch_incident_context({"entity_fqn": entity_fqn, "test_case_id": "tc-null-ratio"}, max_depth=2)

    assert out["failed_test"]["name"] == "tc-null-ratio"
    assert out["owners"]["asset_owner"] == "dre-oncall"
    assert out["lineage"][0]["fqn"] == "svc.db.customer_curated"
    assert out["classifications"]["svc.db.customer_curated"] == ["PII.Sensitive"]


def test_fetch_incident_context_maps_fixture_fqn_to_service_prefixed_fqn():
    original_fqn = "customer_analytics.raw.customer_profiles"
    mapped_fqn = "demo_mysql.customer_analytics.raw.customer_profiles"
    test_case = {
        "name": "tc-null-ratio",
        "fullyQualifiedName": f"{mapped_fqn}.tc-null-ratio",
        "testDefinition": {"name": "tableColumnCountToEqual"},
        "testCaseResult": {"result": "null ratio exceeded"},
    }
    lineage = {
        "entity": {"id": "root", "fullyQualifiedName": mapped_fqn, "type": "table"},
        "nodes": [{"id": "n1", "fullyQualifiedName": "demo_mysql.customer_analytics.curated.customer_curated", "type": "table"}],
        "downstreamEdges": [{"fromEntity": "root", "toEntity": "n1"}],
    }

    responses = {
        ("/v1/dataQuality/testCases/name/tc-null-ratio", (("fields", "testCaseResult,testDefinition,owners,tags"),)): test_case,
        (
            "/v1/dataQuality/testCases/testCaseResults/search/list",
            (("limit", 1), ("offset", 0), ("sortField", "timestamp"), ("sortType", "desc"), ("testCaseFQN", f"{mapped_fqn}.tc-null-ratio")),
        ): {"data": [{"result": "latest failure"}]},
        (f"/v1/lineage/table/name/{mapped_fqn}", (("downstreamDepth", 2), ("upstreamDepth", 2))): lineage,
        f"table::{mapped_fqn}": {"owners": [{"type": "user", "name": "dre-oncall"}], "domains": [], "tags": []},
        "table::demo_mysql.customer_analytics.curated.customer_curated": {
            "owners": [],
            "domains": [],
            "tags": [{"tagFQN": "PII.Sensitive"}],
        },
    }

    client = FakeClient(responses, raise_on_missing=True)
    with patch.dict(os.environ, {"OPENMETADATA_FQN_SERVICE_HINTS": "demo_mysql"}, clear=False):
        out = client.fetch_incident_context({"entity_fqn": original_fqn, "test_case_id": "tc-null-ratio"}, max_depth=2)

    assert out["owners"]["asset_owner"] == "dre-oncall"
    assert out["lineage"][0]["fqn"] == "demo_mysql.customer_analytics.curated.customer_curated"
    assert f"/v1/lineage/table/name/{original_fqn}" in client.called_paths
    assert f"/v1/lineage/table/name/{mapped_fqn}" in client.called_paths
