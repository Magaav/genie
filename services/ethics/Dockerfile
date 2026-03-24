FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY app.py /app/app.py
COPY control_plane.py /app/control_plane.py
COPY workcell_support.py /app/workcell_support.py

EXPOSE 18791

CMD ["python3", "/app/app.py"]
