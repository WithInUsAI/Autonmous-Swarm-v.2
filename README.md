# GOD Swarm Command Center — V2
### Autonomous Tool-Using Recursive Swarm

V1 visualized a pipeline. V2 closes the loop: the Executor can request a
real tool, the Specialist validates the arguments, the Tool Registry runs
it in a sandbox, and the Critic can send the whole thing back to the
Reasoner for revision — up to `MAX_SWARM_CYCLES` (default 8) — instead of
ending the mission either way.

## What changed from V1, point by point

1. **Real tool loop.** `Executor → Specialist → ToolRegistry → observation
   → Critic` is now an actual call, not a description of one. See
   `swarm/tools.py`.
2. **Connection geometry fix.** Nodes now register their connections and
   call `prepareGeometryChange()` on them via `itemChange()` when moved —
   dragging no longer leaves stale line segments. See
   `ui/graph.py::_MovableNode`.
3. **Real cancellation.** `MissionWorker.stop_event` is checked *inside*
   the streaming loop, between tokens — since llama.cpp's stream is
   pull-based, breaking there means the next token is never requested.
   STOP now actually stops generation, not just the UI's opinion of it.
   See `swarm/engine.py::AgentRuntime.generate`.
4. **Per-model adapters.** `swarm/adapters.py` gives each model its own
   prompt construction and output parsing — FunctionGemma gets a rigid
   JSON-only schema instruction, the Executor gets the live tool schema
   appended to its system prompt, the Specialist gets the target tool's
   exact parameter schema. This is a seam, not a finished template
   audit — see the "Still worth doing" note below.
5. **Router is schema-first now.** `swarm/router.py` requires
   `{"route": "SIMPLE"|"COMPLEX", "confidence": ..., "reason": ...}` and
   defaults to `COMPLEX` (the safe direction) whenever the model's
   output doesn't parse — a substring check can no longer misfire on a
   hedge like *"looks simple, but it's actually COMPLEX."*
6. **Critic actually controls the loop.** `_parse_verdict()` looks for an
   explicit `VERDICT: PASS/REVISE` tag (falling back to a structured
   JSON verdict, defaulting to `REVISE` if neither parses — again, the
   safe direction). On `REVISE`, the Critic's full response becomes
   feedback injected into the next cycle's Reasoner prompt, and the
   mission loops until `PASS` or the cycle cap.

## Safety decisions (unchanged from the plan, worth restating)

- **No shell tool.** The registry exposes `read_file`, `write_file`,
  `list_directory`, `run_python`, `search_huggingface` — nothing that
  hands a model a raw shell. `run_python` still runs arbitrary code you
  told it to run, in a subprocess, with a timeout — it's the closest
  thing to a shell here, and it's off by a checkbox
  (**Allow run_python**, right panel) if you want the registry without it.
- **Filesystem sandbox.** `read_file` / `write_file` / `list_directory`
  resolve every path against `WORKSPACE_DIR` (default `./workspace`) and
  reject anything that resolves outside it — verified against a `../../`
  traversal attempt in testing.
- **Tool registry has a master switch** (**Enable tool registry**, left
  panel) — flip it off and the Executor/Specialist can still talk about
  tools, they just can't call them.

## New in the GUI

- **Cycle counter** on the Director node and top bar (`CYCLE n/8`).
- **Tool Activity panel** (left) — every `CALL` and its `OK`/`FAIL`
  result, separate from the general event stream.
- **Four pulse colors** on the graph edges instead of one: blue = THINK,
  orange = TOOL, red = VERIFY, green = SUCCESS (propagates across the
  whole graph on a PASS).
- **Tool permission toggles** (left panel), sandbox path shown so you
  always know where `run_python` and file tools are scoped to.

## Setup

```bash
pip install -r requirements.txt
```

`llama-cpp-python` needs a build toolchain; for GPU offload build it with
the matching backend flag, e.g. `CMAKE_ARGS="-DGGML_CUDA=on" pip install
llama-cpp-python`. `huggingface_hub` is optional — only `search_huggingface`
needs it, and that tool just reports "not installed" without it.

## Model files

Same five files as V1, in `./models/` (or set `SWARM_MODEL_DIR`):

| Role | File | Adapter |
|---|---|---|
| Router | `functiongemma-270m-it.Q4_K_M.gguf` | `FunctionGemmaAdapter` |
| Reasoner | `MiniCPM5-1B-Claude-Opus-Fable5-V2-Thinking-Q8_0.gguf` | `MiniCPMThinkingAdapter` |
| Executor | `MiniCPM5-1B-Agentic-Tooluse-v3.Q8_0.gguf` | `MiniCPMTooluseAdapter` |
| Specialist | `LFM2.5-1.2B-Nova-Function-Calling.Q5_K_M.gguf` | `LFMFunctionAdapter` |
| Critic | `MiniCPM5-1B-Claude-Opus-Fable5-V2-Thinking-heretic-Q5_K_M.gguf` | `MiniCPMThinkingAdapter` |

Any agent whose file is missing (or with no `llama-cpp-python` installed)
shows OFFLINE and the app runs fine — tick **Simulate** to exercise the
whole flow with fabricated text. Note: simulated text won't trigger real
tool calls, since the Executor's fake output never contains the
`{"tool": ...}` JSON the adapter looks for — simulate mode is for
checking the graph/UI, not the tool loop. Run against real models (or a
scripted fake, as in the test suite below) to see the tool loop fire.

## Run

```bash
python app.py
```

## Verified before hand-off

Everything below was run headlessly (`QT_QPA_PLATFORM=offscreen`) against
this exact code, not just read over:

- `ToolRegistry`: write → read → list → `run_python` → path-traversal
  rejection → unknown-tool rejection, all correct.
- `parse_route()` on the exact hedge case from the review
  (*"appears simple, but... COMPLEX"*) — correctly defaults to `COMPLEX`
  now that it requires real JSON instead of a substring match.
- Full closed loop with a scripted fake swarm: Router → COMPLEX →
  Executor requests `read_file` → Specialist structures it → Tool
  Registry executes it → Critic says `REVISE` → loop back to Reasoner
  with that feedback → cycle 2 → Critic says `PASS` → mission complete
  after 2 cycles, with the correct THINK/TOOL/VERIFY/SUCCESS pulses
  firing on the correct edges in order.
- Cancellation: a fake infinite token stream, `stop_event` set after the
  5th token — generation stopped at exactly 5, not after draining the
  stream.
- Connection geometry: dragged a node, confirmed all 3 attached
  connections' `boundingRect()` actually changed (this is the specific
  bug described in the review — it's fixed, not just refactored).

## Still worth doing (not in V2)

- **Chat-template verification per GGUF.** The adapters are the seam for
  this (`ModelAdapter.build_messages`), but I haven't inspected your
  actual five `.gguf` files' baked-in templates — I don't have them here
  to check. Worth doing before you trust FunctionGemma's JSON-only
  output rate in particular; if it's unreliable in practice, that's
  where to look first.
- **Concurrent agent execution.** Cycle steps are still sequential. Your
  models are small enough to plausibly run a couple simultaneously
  (e.g. Specialist structuring one call while Critic reviews the last
  cycle's output) — real speedup, but real added complexity in the
  Director's control flow. Worth it once the sequential version's
  behavior is trusted.
- **Memory across missions.** Nothing persists between EXECUTE runs yet.
- **Mission history panel.** Only the current mission's event stream is
  kept.
