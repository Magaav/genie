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

Runtime state is stored outside the repo:

- `/var/lib/freewiller`
- `/var/log/freewiller`

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
sudo mkdir -p /local
curl -fsSL https://raw.githubusercontent.com/Magaav/freewiller/master/init.sh -o /tmp/freewiller-init.sh
sudo install -m 755 /tmp/freewiller-init.sh /local/init.sh
sudo bash /local/init.sh
```

That is the default public-repo path. No GitHub deploy key is required.

## What `init.sh` Does

`init.sh` will:

1. install minimal bootstrap packages
2. clone or update this repo into `/local`
3. run host hardening
4. install Docker
5. install Ollama
6. pull the default local models
7. build and start the `freewiller-local-agent` container

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
/var/lib/freewiller/freewiller-gateway.env
```

Then restart the local-agent service:

```bash
bash /local/bash/install_local_agent_service.sh
```

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
