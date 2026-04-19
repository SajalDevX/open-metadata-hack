import json
import os
import re
from collections import deque
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request


class OpenMetadataClientError(RuntimeError):
    pass


_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_BUSINESS_TAG_HINTS = ("tier.tier1", "business", "critical")


def _is_uuid_like(value: str) -> bool:
    return bool(_UUID_RE.match(value or ""))


def _normalize_base_url(value: str | None) -> str:
    raw = (value or "http://localhost:8585/api").rstrip("/")
    parsed = parse.urlparse(raw)
    path = parsed.path or ""

    if path.endswith("/api/v1"):
        path = path[:-3]
    elif path in ("", "/"):
        path = "/api"
    elif not path.endswith("/api"):
        # Accept custom reverse-proxy prefixes, but still keep /api semantics.
        path = f"{path}/api"

    return parse.urlunparse((parsed.scheme or "http", parsed.netloc, path.rstrip("/"), "", "", ""))


@dataclass(frozen=True)
class OpenMetadataSettings:
    base_url: str
    token: str | None
    entity_type: str
    timeout_seconds: float


class OpenMetadataClient:
    def __init__(self, settings: OpenMetadataSettings):
        self.settings = settings

    @classmethod
    def from_env(cls) -> "OpenMetadataClient":
        return cls(
            OpenMetadataSettings(
                base_url=_normalize_base_url(os.environ.get("OPENMETADATA_BASE_URL")),
                token=os.environ.get("OPENMETADATA_JWT_TOKEN") or None,
                entity_type=(os.environ.get("OPENMETADATA_ENTITY_TYPE") or "table").strip() or "table",
                timeout_seconds=float(os.environ.get("OPENMETADATA_TIMEOUT_SECONDS", "3")),
            )
        )

    def _json_get(self, path: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.settings.base_url}{path}"
        if query:
            encoded = parse.urlencode({k: v for k, v in query.items() if v is not None and v != ""})
            if encoded:
                url = f"{url}?{encoded}"

        headers = {"Accept": "application/json"}
        if self.settings.token:
            headers["Authorization"] = f"Bearer {self.settings.token}"

        req = request.Request(url, headers=headers, method="GET")
        try:
            with request.urlopen(req, timeout=self.settings.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
                return json.loads(payload) if payload else {}
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OpenMetadataClientError(f"OpenMetadata HTTP {exc.code} for {url}: {detail}") from exc
        except error.URLError as exc:
            raise OpenMetadataClientError(f"OpenMetadata connection error for {url}: {exc.reason}") from exc

    def _quote(self, value: str) -> str:
        return parse.quote(value, safe="")

    def _get_test_case_by_name(self, fqn_or_name: str) -> dict[str, Any] | None:
        if not fqn_or_name:
            return None
        try:
            return self._json_get(
                f"/v1/dataQuality/testCases/name/{self._quote(fqn_or_name)}",
                query={"fields": "testCaseResult,testDefinition,owners,tags"},
            )
        except OpenMetadataClientError:
            return None

    def _get_test_case_by_id(self, test_case_id: str) -> dict[str, Any] | None:
        if not test_case_id:
            return None
        try:
            return self._json_get(
                f"/v1/dataQuality/testCases/{self._quote(test_case_id)}",
                query={"fields": "testCaseResult,testDefinition,owners,tags"},
            )
        except OpenMetadataClientError:
            return None

    def _list_test_cases_for_entity(self, entity_fqn: str, limit: int = 25) -> list[dict[str, Any]]:
        if not entity_fqn:
            return []
        payload = self._json_get(
            "/v1/dataQuality/testCases",
            query={
                "entityFQN": entity_fqn,
                "fields": "testCaseResult,testDefinition,owners,tags",
                "limit": limit,
            },
        )
        return payload.get("data") or []

    def _get_latest_test_result(self, test_case_fqn: str) -> dict[str, Any] | None:
        if not test_case_fqn:
            return None
        payload = self._json_get(
            "/v1/dataQuality/testCases/testCaseResults/search/list",
            query={
                "testCaseFQN": test_case_fqn,
                "limit": 1,
                "offset": 0,
                "sortField": "timestamp",
                "sortType": "desc",
            },
        )
        rows = payload.get("data") or []
        return rows[0] if rows else None

    def _get_lineage(self, fqn: str, max_depth: int) -> dict[str, Any]:
        return self._json_get(
            f"/v1/lineage/{self._quote(self.settings.entity_type)}/name/{self._quote(fqn)}",
            query={"upstreamDepth": max_depth, "downstreamDepth": max_depth},
        )

    def _get_table(self, fqn: str) -> dict[str, Any] | None:
        if not fqn:
            return None
        try:
            return self._json_get(
                f"/v1/tables/name/{self._quote(fqn)}",
                query={"fields": "owners,tags,domains"},
            )
        except OpenMetadataClientError:
            return None

    def _test_case_belongs_to_entity(self, test_case: dict[str, Any] | None, entity_fqn: str) -> bool:
        if not test_case or not entity_fqn:
            return False
        case_fqn = test_case.get("fullyQualifiedName") or ""
        return case_fqn.startswith(f"{entity_fqn}.")

    def _pick_test_case(self, test_case_hint: str, entity_fqn: str) -> dict[str, Any] | None:
        direct = self._get_test_case_by_name(test_case_hint)
        if self._test_case_belongs_to_entity(direct, entity_fqn):
            return direct

        if _is_uuid_like(test_case_hint):
            by_id = self._get_test_case_by_id(test_case_hint)
            if self._test_case_belongs_to_entity(by_id, entity_fqn):
                return by_id

        listed = self._list_test_cases_for_entity(entity_fqn)
        if not listed:
            return None

        if test_case_hint:
            lowered = test_case_hint.lower()
            for case in listed:
                if lowered in (case.get("name") or "").lower() or lowered in (
                    case.get("fullyQualifiedName") or ""
                ).lower():
                    return case

        return listed[0]

    def _extract_classifications(self, tags: list[dict[str, Any]] | None) -> list[str]:
        if not tags:
            return []
        return [tag.get("tagFQN", "") for tag in tags if tag.get("tagFQN")]

    def _is_business_facing(self, tags: list[dict[str, Any]] | None) -> bool:
        lowered_tags = [tag.lower() for tag in self._extract_classifications(tags)]
        return any(any(hint in tag for hint in _BUSINESS_TAG_HINTS) for tag in lowered_tags)

    def _extract_failed_test(
        self,
        test_case: dict[str, Any] | None,
        latest_result: dict[str, Any] | None,
        test_case_hint: str,
    ) -> dict[str, Any]:
        case_result = (test_case or {}).get("testCaseResult") or {}
        message = (
            case_result.get("result")
            or (latest_result or {}).get("result")
            or "OpenMetadata test case reported a failure."
        )
        return {
            "name": (test_case or {}).get("name") or test_case_hint or "unknown_test_case",
            "message": message,
            "testType": ((test_case or {}).get("testDefinition") or {}).get("name") or "unknown",
        }

    def _build_lineage_assets(
        self,
        lineage: dict[str, Any],
        root_fqn: str,
        max_depth: int,
    ) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
        root = lineage.get("entity") or {}
        root_id = root.get("id")

        refs: dict[str, dict[str, Any]] = {}
        if root_id:
            refs[root_id] = root
        for node in lineage.get("nodes") or []:
            node_id = node.get("id")
            if node_id:
                refs[node_id] = node

        adjacency: dict[str, list[str]] = {}
        for edge in lineage.get("downstreamEdges") or []:
            src = edge.get("fromEntity")
            dst = edge.get("toEntity")
            if not src or not dst:
                continue
            adjacency.setdefault(src, []).append(dst)

        distances: dict[str, int] = {}
        if root_id:
            queue = deque([(root_id, 0)])
            while queue:
                current, depth = queue.popleft()
                for neighbor in adjacency.get(current, []):
                    if neighbor in distances:
                        continue
                    distances[neighbor] = depth + 1
                    queue.append((neighbor, depth + 1))

        impacted_assets: list[dict[str, Any]] = []
        classifications_map: dict[str, list[str]] = {}

        for node_id, distance in distances.items():
            if distance > max_depth:
                continue
            ref = refs.get(node_id) or {}
            fqn = ref.get("fullyQualifiedName") or ref.get("name")
            if not fqn or fqn == root_fqn:
                continue

            table_data = self._get_table(fqn) if (ref.get("type") or "table") == "table" else None
            tags = (table_data or {}).get("tags") or []
            classifications = self._extract_classifications(tags)
            classifications_map[fqn] = classifications

            impacted_assets.append(
                {
                    "fqn": fqn,
                    "distance": distance,
                    "business_facing": self._is_business_facing(tags),
                    "downstream_count": len(adjacency.get(node_id, [])),
                    "classifications": classifications,
                }
            )

        return impacted_assets, classifications_map

    def _fqn_service_hints(self) -> list[str]:
        raw = (
            os.environ.get("OPENMETADATA_FQN_SERVICE_HINTS")
            or os.environ.get("OPENMETADATA_SERVICE_NAME")
            or ""
        )
        return [part.strip() for part in raw.split(",") if part.strip()]

    def _candidate_entity_fqns(self, entity_fqn: str) -> list[str]:
        candidates = [entity_fqn]
        # Fixture events may provide 3-part FQNs; OpenMetadata usually expects service.database.schema.table.
        if entity_fqn and entity_fqn.count(".") == 2:
            for hint in self._fqn_service_hints():
                mapped = f"{hint}.{entity_fqn}"
                if mapped not in candidates:
                    candidates.append(mapped)
        return candidates

    def fetch_recent_test_case_results(
        self, since_ms: int = 0, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Fetch recent testCaseResults for polling mode.

        Queries `/v1/dataQuality/testCases/testCaseResults` (OpenMetadata 1.x).
        Returns a flat list of entries shaped `{testCase: {...}, testCaseResult: {...}}`.
        """
        try:
            payload = self._json_get(
                "/v1/dataQuality/testCases/testCaseResults",
                query={
                    "startTs": since_ms if since_ms > 0 else None,
                    "limit": limit,
                    "fields": "testCase,testCaseResult",
                },
            )
        except OpenMetadataClientError:
            return []

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return []
        return data

    def fetch_incident_context(self, envelope: dict[str, Any], max_depth: int = 2) -> dict[str, Any]:
        original_entity_fqn = envelope.get("entity_fqn") or ""
        test_case_hint = envelope.get("test_case_id") or ""
        if not original_entity_fqn:
            raise OpenMetadataClientError("entity_fqn is required for OpenMetadata context resolution")

        selected_entity_fqn = original_entity_fqn
        lineage = None
        last_error = None
        for candidate in self._candidate_entity_fqns(original_entity_fqn):
            try:
                lineage = self._get_lineage(candidate, max_depth)
                selected_entity_fqn = candidate
                break
            except OpenMetadataClientError as exc:
                last_error = exc

        if lineage is None:
            if last_error is not None:
                raise last_error
            raise OpenMetadataClientError("Unable to resolve lineage from OpenMetadata")

        test_case = self._pick_test_case(test_case_hint, selected_entity_fqn)
        latest_result = None
        if test_case and test_case.get("fullyQualifiedName"):
            latest_result = self._get_latest_test_result(test_case.get("fullyQualifiedName"))

        impacted_assets, classifications = self._build_lineage_assets(lineage, selected_entity_fqn, max_depth)

        root_table = self._get_table(selected_entity_fqn) or {}
        owners = root_table.get("owners") or []

        owner_map = {
            "asset_owner": next((o.get("name") for o in owners if o.get("type") == "user"), None),
            "domain_owner": next((d.get("name") for d in (root_table.get("domains") or [])), None),
            "team_owner": next((o.get("name") for o in owners if o.get("type") == "team"), None),
        }

        return {
            "failed_test": self._extract_failed_test(test_case, latest_result, test_case_hint),
            "lineage": impacted_assets,
            "owners": owner_map,
            "classifications": classifications,
        }
