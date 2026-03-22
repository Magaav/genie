FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    ripgrep \
    tini \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /local

COPY bash /local/bash
COPY docs /local/docs

RUN chmod +x \
  /local/bash/local_llm.sh \
  /local/bash/local_memory.py \
  /local/bash/local_agent.py \
  /local/bash/local_agent_http.py

ENV LOCAL_LLM_DIR=/var/lib/freewiller
ENV FREEWILLER_LOG_DIR=/var/log/freewiller
ENV LOCAL_AGENT_HTTP_HOST=0.0.0.0
ENV LOCAL_AGENT_HTTP_PORT=18790

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python3", "/local/bash/local_agent_http.py"]
