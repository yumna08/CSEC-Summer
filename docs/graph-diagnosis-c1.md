# Stage C1 graph diagnosis

## Comparison from the saved real reports

The reports are labeled `real Gemini model, 6 questions` and were captured
before the general-advice scoring correction. The only questions where the
saved graph report failed while the saved legacy report passed are:

| Question | Legacy evidence | Graph evidence | Proven failing node |
| --- | --- | --- | --- |
| `cal-01` | `behavior_correct: true`, `citation_correct: true`, `retrieved_count: 4`, `grounding_status: grounded`, `abstained: false` | `behavior_correct: false`, `citation_correct: false`, `retrieved_count: 1`, `grounding_status: grounded`, `abstained: false`, `failure_reasons: ["bad citation"]` | Not identifiable from the saved report |
| `reg-02` | `behavior_correct: true`, `citation_correct: true`, `retrieved_count: 3`, `grounding_status: grounded`, `abstained: false` | `behavior_correct: false`, `citation_correct: false`, `retrieved_count: 1`, `grounding_status: abstained`, `abstained: true`, `failure_reasons: ["wrong abstention", "bad citation"]` | Not identifiable from the saved report |

The saved report contains aggregate retrieval counts, grounding status, and
failure labels, but no classify/rewrite/tool/generate/verify/abstain trace. It
therefore does not prove whether the cause was a classifier route, tool result,
rewritten query, generated answer, citation verifier, or final abstention.
The lower retrieved counts are evidence of a difference in retrieved output,
not proof of the responsible node.

`adv-01` is not a graph-vs-legacy regression in the saved comparison: both
reports marked it false. Its retrieval/citation labels were caused by the
general-advice scoring bug, which is now fixed in the evaluator. A corrected
real rerun is still required.

## Diagnostic changes

The graph now records a non-sensitive `node_trace` in evaluator results. Each
entry contains only node names and facts such as classification, retrieval
mode, tool names/counts, chunk counts, grounding status, citation count, and
final outcome. It does not contain user messages, rewritten query text, API
keys, or model prompts. Retrieval traces distinguish normal retrieval, tool
retrieval, and fallback reasons such as malformed calls or empty tool results.

The evaluator also bounds each real Gemini HTTP request so quota or network
failure produces a failure result instead of hanging indefinitely. No
retrieval thresholds were changed, and `USE_GRAPH_PIPELINE` remains false by
default.

## 12-question rerun

A traced 12-question legacy run was attempted with a 1.5-second delay. Gemini
reported `429 RESOURCE_EXHAUSTED` for the primary model, while fallback calls
reported `503 UNAVAILABLE` and `504 DEADLINE_EXCEEDED`. The bounded attempt
completed with no questions and produced no 12-question metrics. The graph
12-question run was not started because the available quota was already
blocked; no estimates were made and no 12-question reports were created.

The next required rerun is both pipelines with available Gemini quota. The
trace will then identify the responsible node for `cal-01` and `reg-02`.
