# Aurora backend: agents + API + background loop (deploy on an always-on host, e.g. Railway)
FROM python:3.13-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend backend
COPY tenants tenants
# Customer data and the agents' cache are uploaded from the local machine at deploy time
# (never committed to git). The cache means 299 documents are not read (and paid for) again.
COPY data/current data/current
COPY data/snapshots/files_*.json data/snapshots/
COPY data/state seed/state
COPY start.sh start.sh
ENV PYTHONUNBUFFERED=1
CMD ["sh", "start.sh"]
