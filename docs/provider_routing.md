# LLM Provider Routing

VinSOC uses OpenAI as the primary provider and pins
`inclusionai/ling-3.0-flash-vl:free` as the OpenRouter operational fallback. Fallback
is a runtime availability feature, not part of the scientific comparison.

The pinned fallback was verified against the OpenRouter catalog on 2026-09-18. Its
[official model page](https://openrouter.ai/inclusionai/ling-3.0-flash-vl:free)
lists zero token cost and support for `tools`/`tool_choice`. It does not support
`response_format`; VinSOC therefore relies on tool schemas and its local validators.

## Modes

| Mode | Fallback policy |
|---|---|
| `evaluation` | Disabled. Provider failure is part of the evaluation result. |
| `development` | Enabled only for budget exhaustion, rate limits, timeouts, or provider outage. |
| `demo` | Same controlled fallback policy as development. |

Invalid requests, context/schema failures, moderation refusals, and output validation
failures never trigger fallback. These failures must remain visible.

OpenRouter supports provider ordering and provider fallback controls. VinSOC disables
OpenRouter's upstream provider fallback by default and requires support for every
requested parameter. See the official [OpenRouter provider routing documentation](https://openrouter.ai/docs/guides/routing/provider-selection).

## Configuration

Set secrets in environment variables rather than command history:

```bash
export OPENAI_API_KEY="..."
export OPENROUTER_API_KEY="..."
```

Evaluation run with no fallback:

```bash
python -m cli.main scenario case_001 \
  --provider routed \
  --model gpt-5.6-luna \
  --fallback-model inclusionai/ling-3.0-flash-vl:free \
  --run-mode evaluation \
  --monthly-budget-usd 4.5
```

Development/demo run with controlled fallback:

```bash
python -m cli.main scenario case_001 \
  --provider routed \
  --model gpt-5.6-luna \
  --fallback-model inclusionai/ling-3.0-flash-vl:free \
  --run-mode development \
  --monthly-budget-usd 4.5
```

The fallback model is pinned rather than delegated to OpenRouter's auto-router. The
provider adapter rejects model IDs without the `:free` suffix and sends
`max_price: {prompt: 0, completion: 0}`. According to the official
[provider-routing documentation](https://openrouter.ai/docs/guides/routing/provider-selection),
`max_price` prevents execution when no endpoint satisfies the configured price.

Free endpoints are still subject to availability and rate limits. If the pinned model
is removed or stops supporting tool calls, the fallback fails visibly; it does not
silently select a paid model.

## Budget accounting

The OpenAI monthly ledger defaults to `.vinsoc/openai_budget.json`. It is excluded from
Git and resets logically when the UTC billing month changes. The guard requires a known
pricing snapshot for the selected model; otherwise startup fails rather than pretending
that the budget is enforced.

The built-in `gpt-5.6-luna` and `gpt-5.6-terra` rates are a snapshot checked on
2026-09-18 against the official [OpenAI API pricing page](https://developers.openai.com/api/docs/pricing).
Refresh or explicitly override pricing before a later experiment.

The ledger is an application-side safety control, not a replacement for the billing
limit configured in the provider account.

## Recorded metadata

Each investigation records `metadata.llm_run`, including:

- requested and actual provider/model;
- whether fallback occurred and why;
- input, output, and total tokens;
- estimated cost and pricing snapshot;
- latency and normalized provider failure category;
- monthly budget state.

OpenRouter charges for the model ultimately used and returns that model in the response.
See the official [model fallback documentation](https://openrouter.ai/docs/guides/routing/model-fallbacks).
