# Progress log

This log uses the repository's commit history as its source of truth. Where a
phase commit did not record command output, the test result is explicitly
marked as not recorded rather than inferred.

## Phase 0 — baseline

- Built: the repository snapshot and a reproducible Phase 0 baseline were
  committed in `fa3fa8a` and `4acb207`.
- Learned: the project needed a reproducible starting point before feature
  work; this is the wording captured by the baseline commit.
- Test result: test output is not recorded in the phase commit history.
- Next step: establish the security and operational fixes represented by the
  following Phase 1 commits.

## Phase 1 — production fixes

- Built: admin authentication (`976af8a`), configurable API rate limits
  (`2adccbe`), restricted CORS (`44245cc`), and structured request logging
  (`ad180fb`).
- Learned: the production boundary needs explicit admin credentials and
  origins; those changes are recorded in the commit subjects and repository
  configuration.
- Test result: test output is not recorded in these phase commit messages.
- Next step: add persistent conversation memory.

## Phase 2 — conversation memory

- Built: persistent conversation memory (`4731d3f`) and frontend session
  persistence (`62a61c0`), including the chat-session deletion path.
- Learned: session identifiers must be client-carried but server-owned; the
  implementation and commit history record this session boundary.
- Test result: test output is not recorded in the phase commit messages.
- Next step: add optional graph orchestration and tool calling.

## Phase 3 — graph workflow and evaluation baseline

- Built: the Neon probe was removed from normal pytest collection (`33069d2`),
  a mocked RAG baseline was recorded (`846d772`), and the optional LangGraph
  tool workflow was added (`ae57f26`).
- Learned: the graph must wrap the established RAG and citation behavior; this
  is reflected in the graph commit and the committed architecture files.
- Test result: the committed baseline and graph evaluation artifacts are the
  recorded test/evaluation outputs for this phase.
- Next step: run a small real-model evaluation before deployment work.

## Stage A — real evaluation

- Built: the quota-safe real evaluator and separate legacy/graph reports were
  committed in `913d455`; the general-advice scoring correction was committed
  in `421b248`.
- Learned: the real run exercised the fallback chain and exposed both quota or
  high-demand responses and a scoring defect for citation-free study advice.
- Test result: the six-question artifacts record the measured legacy and graph
  metrics; a corrected real rerun was not possible after the observed quota
  exhaustion.
- Next step: finish container deployment and documentation, then rerun the
  corrected evaluation when model quota permits.

## Stage B — deployment and documentation

- Built: container deployment scaffolding was committed in `7988a80`; CI for
  backend tests, frontend checks, and Docker builds was committed in `3eb84d9`.
- Learned: the deployment boundary separates runtime secrets from build
  contexts and persists Chroma independently through a volume.
- Test result: local verification status is recorded in the final handoff; the
  phase commits themselves do not contain Docker command output.
- Next step: add any remaining MCP, research-agent, and tracing work, then
  perform a corrected real evaluation.

## Stage C2 — MCP server

- Built: the pinned official MCP SDK, read-only search tool, indexed-source
  catalog resource, direct tests, and Claude Desktop instructions were added in
  `9e34741`.
- Learned: MCP 2.x uses `MCPServer` and its `httpx2` dependency can conflict
  with the test harness alias; the test setup restores the real SDK dependency
  only for MCP tests.
- Test result: the commit was preceded by 155 passing backend tests from both
  repository locations, frontend lint, and TypeScript checks.
- Next step: implement the capped research-agent workflow.
