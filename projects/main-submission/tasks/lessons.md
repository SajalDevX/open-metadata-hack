# Project Lessons

- When parsing MCP or FastMCP tool responses, prefer `result.structuredContent` first and keep legacy `result.content` / top-level `content` parsing only as compatibility fallback.
- When a Slack brief is user-supplied, treat any non-dict payload as malformed and return `False` instead of assuming dict-like access.
- For live OpenMetadata validation from constrained harness environments, confirm service health with an unsandboxed check before treating localhost connection failures as real runtime outages.
- For OpenMetadata fixtures using 3-part FQNs, support an explicit service-prefix hint (`OPENMETADATA_FQN_SERVICE_HINTS` / `OPENMETADATA_SERVICE_NAME`) to avoid false HTTP-to-fixture fallback during live replay validation.
- For OpenMetadata create APIs, reference fields like `service`, `database`, and `databaseSchema` may require string FQNs rather than object refs; validate payload shape against live API error messages before finalizing bootstrap scripts.
