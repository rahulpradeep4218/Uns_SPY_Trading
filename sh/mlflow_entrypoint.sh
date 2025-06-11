#!/bin/bash

echo "Creating MLFlow database if they dont exist..."
echo "ML Flow Port : ${MLFLOW_PORT}"

PGPASSWORD=$POSTGRES_PASSWORD \
psql -U ${POSTGRES_USER} -d postgres -h postgres -f /tmp/init_dbs.sql
echo "Starting MLflow server..."
mlflow server \
  --backend-store-uri postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:${POSTGRES_PORT}/${MLFLOW_POSTGRES_DB} \
  --default-artifact-root /mlflow/artifacts \
  --host 0.0.0.0 \
  --port ${MLFLOW_PORT}