# DeepSeek adapter

This branch targets DeepSeek through Codex's Responses API integration. The shared generator, evidence ledger, gates, and generic volume builder remain unchanged.

## Model choice

Use `deepseek-flash` (currently DeepSeek-V4.1-Flash) for this project. It supports native image input, tool calls, Responses API, and a 1M context. `deepseek-v4-pro` does not support vision and is being phased out/routed to Flash in the current official deployment. Older distilled local models are appropriate only for constrained text/data edits with human-supplied photo measurements.

Official references:

- [Models and pricing](https://api-docs.deepseek.com/quick_start/pricing/)
- [Vision input and limits](https://api-docs.deepseek.com/guides/vision/)
- [Codex integration](https://api-docs.deepseek.com/quick_start/agent_integrations/codex/)
- [Thinking and tool calls](https://api-docs.deepseek.com/guides/thinking_mode/)
- [V4.1-Flash deployment](https://api-docs.deepseek.com/news/news260910/)

## Codex setup

Use the official DeepSeek setup or manual configuration linked above. Do not paste an API key into project files, TASK.md, logs, or README. Review any downloaded setup script before executing it. Restart Codex after changing provider configuration and confirm that the startup model is `deepseek-flash`.

The kit does not run the setup script automatically and does not upload photos automatically.

## Reasoning policy

Get the machine-readable policy for the current task:

```bash
python tools/agent.py deepseek-policy --project P --task data --json
python tools/agent.py deepseek-policy --project P --task edit --json
python tools/agent.py deepseek-policy --project P --task geometry --json
python tools/agent.py deepseek-policy --project P --task vision --json
python tools/agent.py deepseek-policy --project P --task review --json
```

- `data`: non-thinking; edit only allowed values.
- `edit`: low reasoning; fix one reported error group.
- `geometry`, `vision`, `review`: high reasoning.
- Do not use the 1M context as a reason to load every document or log. Keep `--brief` and `next_action`.

For a custom tool-calling client, preserve `reasoning_content` and tool-call IDs in subsequent requests. The official documentation warns that missing reasoning content can produce a 400 error. Prefer the official Codex integration over writing a new loop.

## Photo preparation and privacy

DeepSeek resizes images before inference and charges image tokens by dimensions. Contact sheets are for photo classification, not fine measurement. Use a wall or detail crop for windows, rails, louvers, and colors.

```bash
python tools/agent.py vision --project P \
  --photo photos/front.jpg --box=100,200,1200,1400 \
  --wall-id main:front --json
```

To redact people, plates, or other sensitive rectangles in original-photo pixels:

```bash
python tools/agent.py vision --project P \
  --photo photos/front.jpg --box=100,200,1200,1400 \
  --redact=300,500,420,650 --out previews/vision/front_detail.jpg --json
```

The tool:

- never changes the source photo;
- keeps derived files under `previews/`;
- records source/derived hashes, crop, size, wall ID, and redaction count;
- uses `detail=original` as the recommendation and never uploads the image itself.

Inspect the derived image before explicitly sending it to an external API. If image input or external upload is unavailable, use supplied measurements and `NEEDS_HUMAN_REVIEW`.

## Completion gate

There is no automatic stop hook in this branch. An external runner or the agent must call:

```bash
python tools/agent.py require-final --project P --json
```

PASS requires a final gate PASS, FBX PASS, and visual review PASS. Missing state is NOT_CHECKED; failed gates remain FAIL; unfinished review is INCOMPLETE. Do not convert these into a successful completion report.

## Verification status

The local tools and a generic final asset were exercised, but no DeepSeek API call was made during implementation. Measure completion rate, runtime, tokens, wrong geometry edits, and photo hallucinations before selecting a different model or changing the policy.
