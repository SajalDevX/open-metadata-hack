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


def test_pick_test_case_ignores_cross_entity_direct_match():
    entity_fqn = "svc.db.customer_profiles"
    test_case_hint = "tc-null-ratio"
    direct_cross_entity = {
        "name": test_case_hint,
        "fullyQualifiedName": "svc.db.other_table.tc-null-ratio",
    }
    listed_for_entity = {
        "name": test_case_hint,
        "fullyQualifiedName": f"{entity_fqn}.tc-null-ratio",
    }
    responses = {
        (
            f"/v1/dataQuality/testCases/name/{test_case_hint}",
            (("fields", "testCaseResult,testDefinition,owners,tags"),),
        ): direct_cross_entity,
        (
            "/v1/dataQuality/testCases",
            (("entityFQN", entity_fqn), ("fields", "testCaseResult,testDefinition,owners,tags"), ("limit", 25)),
        ): {"data": [listed_for_entity]},
    }
    client = FakeClient(responses, raise_on_missing=True)

    picked = client._pick_test_case(test_case_hint, entity_fqn)

    assert picked is not None
    assert picked["fullyQualifiedName"] == f"{entity_fqn}.tc-null-ratio"


def test_test_case_belongs_to_entity_checks_fqn_prefix():
    client = FakeClient({})
    entity_fqn = "svc.db.customer_profiles"

    assert client._test_case_belongs_to_entity(
        {"fullyQualifiedName": "svc.db.customer_profiles.tc-null-ratio"},
        entity_fqn,
    )
    assert not client._test_case_belongs_to_entity(
        {"fullyQualifiedName": "svc.db.other_table.tc-null-ratio"},
        entity_fqn,
    )
    assert not client._test_case_belongs_to_entity({}, entity_fqn)
