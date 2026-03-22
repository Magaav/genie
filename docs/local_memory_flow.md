# Local Memory Flow

This machine uses a guarded local utility layer before remote escalation.

## Roles

- `bash/local_llm.sh`
  - local routing
  - local summarization
  - local extraction
  - local embeddings passthrough
- `bash/local_memory.py`
  - persistent memory store
  - embedding-backed retrieval
  - context assembly for remote prompts

## Storage

Runtime state lives outside the repo:

- config: `/var/lib/openclaw-local-llm/local-llm.env`
- memory db: `/var/lib/openclaw-local-llm/memory/entries.jsonl`

Each memory entry stores:

- `id`
- `created_at`
- `kind`
- `source`
- `tags`
- `summary`
- `text`
- `facts`
- `todo`
- `constraints`
- `embedding`

## Task Flow

1. New input arrives.
2. Run `bash/local_llm.sh route "<task>"`.
3. If route says `REMOTE`, skip local reasoning and escalate immediately.
4. If route says `LOCAL`, allow only:
   - summarization
   - extraction
   - cleanup
   - formatting
   - retrieval preparation
5. Store useful outputs with:
   - `python3 /local/bash/local_memory.py add ...`
6. Before remote escalation, assemble relevant context with:
   - `python3 /local/bash/local_memory.py context --query ...`
7. Send only:
   - current task
   - top retrieved memory
   - compressed recent context
   - required file/tool data

## Operational Rules

- Local model is not the default deep reasoner on this host.
- If local route/summarize/extract exceeds its timeout, fail closed.
- Long or architecture-grade tasks should skip local deliberation.
- Retrieval should use memory summaries and structured facts, not raw logs.

## Example Commands

Add memory:

```bash
python3 /local/bash/local_memory.py add \
  --kind decision \
  --source session \
  --tags local,llm,memory \
  --text "Use qwen3:8b for local routing and nomic-embed-text for retrieval."
```

Search memory:

```bash
python3 /local/bash/local_memory.py search \
  --query "Which local model are we using for routing?" \
  --limit 3
```

Build remote context:

```bash
python3 /local/bash/local_memory.py context \
  --query "local llm routing policy and embeddings" \
  --limit 3
```
