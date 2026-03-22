# Freewiller

Freewiller is a bootstrapable local orchestration node for:

- host hardening
- Docker and Ollama setup
- a small local LLM worker
- local memory and retrieval
- a containerized local-agent HTTP service

This repo is meant to be spawned onto a brand new Ubuntu VM and rebuilt from Git.

## What A Fresh Spawn Creates

After a successful bootstrap, the VM will have:

- hardened SSH config
  - `PasswordAuthentication no`
  - `PermitRootLogin no`
- `ufw` enabled with `OpenSSH` allowed
- `fail2ban` enabled for SSH
- Docker installed and running
- Ollama installed and running
- local models pulled
  - `qwen3:0.6b`
  - `nomic-embed-text`
- the Freewiller local-agent container running on:
  - `http://127.0.0.1:18790`

Runtime state is stored under `/local`, but outside Git tracking:

- `/local/state/freewiller`
- `/local/log/freewiller`
- `/local/feed`
- `/local/backups`

These paths live under `/local` so you can inspect and evolve the running node from the same workspace, but they are still ignored by Git.

## Requirements

- a brand new Ubuntu VM
- SSH key access to that VM before bootstrap starts

Important:

- `init.sh` hardens SSH and disables password authentication.
- Do not rely on password login for recovery.
- Make sure your cloud VM already has a valid SSH public key installed before running the bootstrap.

Tested flow:

- Ubuntu 24.04
- Oracle ARM64 VM

## Fastest Spawn

On the new VM, run:

```bash
sudo bash -lc 'mkdir -p /local && curl -fsSL https://raw.githubusercontent.com/Magaav/freewiller/master/init.sh | bash'
```

That is the default public-repo path. No GitHub deploy key is required.

To restore memory from a prior backup during spawn:

```bash
sudo RESTORE_BACKUP_URL='https://example.com/freewiller-daily-2026-03-22.tar.gz' \
  bash -lc 'mkdir -p /local && curl -fsSL https://raw.githubusercontent.com/Magaav/freewiller/master/init.sh | bash'
```

You can also restore from a file already present on the VM:

```bash
sudo RESTORE_BACKUP_PATH=/tmp/freewiller-daily-2026-03-22.tar.gz \
  bash -lc 'mkdir -p /local && curl -fsSL https://raw.githubusercontent.com/Magaav/freewiller/master/init.sh | bash'
```

## What `init.sh` Does

`init.sh` will:

1. install minimal bootstrap packages
2. clone or update this repo into `/local`
3. run host hardening
4. install Docker
5. install Ollama
6. pull the default local models
7. optionally restore compact memory from a prior Freewiller backup
8. install hourly and daily backup cron jobs
9. build and start the `freewiller-local-agent` container

## After Bootstrap

Open a new shell so the `ubuntu` user picks up Docker group membership:

```bash
newgrp docker
```

Then verify the instance:

```bash
docker ps
ollama list
curl -s http://127.0.0.1:18790/health
curl -s http://127.0.0.1:18790/policy
bash /local/bash/backup_freewiller.sh list
```

Expected service:

- container: `freewiller-local-agent`
- health endpoint: `http://127.0.0.1:18790/health`

## Optional Modes

If you want only the hardened base host and repo sync, without the local LLM stack:

```bash
sudo INSTALL_LOCAL_LLM=0 INSTALL_LOCAL_AGENT_SERVICE=0 bash /local/init.sh
```

If you want to override the repo URL:

```bash
sudo REPO_URL=https://github.com/Magaav/freewiller.git bash /local/init.sh
```

If you want to use SSH cloning instead of public HTTPS, provide one of:

- `DEPLOY_KEY_B64`
- `DEPLOY_KEY_CONTENT`
- `DEPLOY_KEY_PATH`

Example:

```bash
sudo REPO_URL=git@github.com:Magaav/freewiller.git \
  DEPLOY_KEY_B64='BASE64_OF_PRIVATE_KEY' \
  bash /local/init.sh
```

## Gateway Configuration

Bootstrap does not configure a remote gateway token by default.

If you want Freewiller to dispatch packaged requests to a remote OpenClaw-compatible gateway, edit:

```bash
/local/state/freewiller/freewiller-gateway.env
```

Then restart the local-agent service:

```bash
bash /local/bash/install_local_agent_service.sh
```

## Backups And Respawn Memory

Bootstrap installs two root cron jobs by default:

- hourly snapshot at `HH:05`
- daily snapshot at `03:17 UTC`

Backups are stored in:

- `/local/backups/hourly`
- `/local/backups/daily`

Retention is intentionally small:

- keep the last `3` hourly backups
- keep the last `1` daily backup

Each archive contains a compact recovery bundle:

- `local-llm.env`
- `freewiller-gateway.env` if present
- compact memory export with summaries, facts, TODOs, and constraints
- `manifest.json`

On restore, embeddings are rebuilt locally from the compact memory export so a respawn can recover its prior memory state without carrying the full raw runtime tree.

Manual commands:

```bash
bash /local/bash/backup_freewiller.sh save hourly
bash /local/bash/backup_freewiller.sh save daily
bash /local/bash/backup_freewiller.sh list
bash /local/bash/backup_freewiller.sh restore /local/backups/daily/freewiller-daily-YYYY-MM-DD.tar.gz
```

## Recover Old Agent Progress

If you have a backup from an older Freewiller node and want this instance to inherit that prior memory:

1. Drop the archive into `/local/feed`.
2. Restore it into the live state directory.
3. Restart the local-agent service.
4. Continue talking to the agent with the recovered memory now present on disk.

Example:

```bash
mkdir -p /local/feed
cp /path/to/freewiller-daily-YYYY-MM-DD.tar.gz /local/feed/
bash /local/bash/backup_freewiller.sh restore /local/feed/freewiller-daily-YYYY-MM-DD.tar.gz --force
bash /local/bash/install_local_agent_service.sh
```

After that, the prior memory is restored into:

- `/local/state/freewiller/memory/entries.jsonl`

So if you then ask the agent to integrate or continue from its old progress, it is already operating on the recovered memory base.

If you want to do this during the very first spawn instead of after the machine is already up, use `RESTORE_BACKUP_PATH` or `RESTORE_BACKUP_URL` with `init.sh` as shown above.

## Local Runtime

Current default local worker:

- `qwen3:0.6b`

Current embedding model:

- `nomic-embed-text`

That model choice is intentional for this class of small CPU VM. Larger local models were too slow for routing and summarization on this hardware.

## Main Files

- [`init.sh`](init.sh)
- [`docs/local_memory_flow.md`](docs/local_memory_flow.md)
- [`bash/local_llm.sh`](bash/local_llm.sh)
- [`bash/local_memory.py`](bash/local_memory.py)
- [`bash/local_agent.py`](bash/local_agent.py)
- [`bash/local_agent_http.py`](bash/local_agent_http.py)
- [`bash/backup_freewiller.sh`](bash/backup_freewiller.sh)
- [`bash/cronjob_freewiller.sh`](bash/cronjob_freewiller.sh)
- [`docker-compose.local-agent.yml`](docker-compose.local-agent.yml)

## Troubleshooting

If bootstrap completes but Docker commands fail for `ubuntu`, open a new shell or run:

```bash
newgrp docker
```

If the local-agent container is not healthy:

```bash
docker compose -f /local/docker-compose.local-agent.yml logs -f local-agent
```

If Ollama is not responding:

```bash
systemctl status ollama --no-pager
curl -s http://127.0.0.1:11434/api/tags
```
