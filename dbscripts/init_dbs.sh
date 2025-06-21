#!/bin/bash

echo "Waiting for PostgreSQL to be ready..."
until pg_isready -h postgres -p ${POSTGRES_PORT:-5432} -U ${POSTGRES_USER:-postgres}; do sleep 1; done

# Create DBs if not exist
for DB in "Trading_Dagster_DB" "MLFlow_DB" "INF_DB"; do
  echo "Checking $DB..."
  psql -h postgres -U ${POSTGRES_USER:-postgres} -d postgres -tc "SELECT 1 FROM pg_database WHERE datname = '$DB'" | grep -q 1 || \
    psql -h postgres -U ${POSTGRES_USER:-postgres} -d postgres -c "CREATE DATABASE \"$DB\""
done

# Run the SQL init on INF_DB
psql -h postgres -U ${POSTGRES_USER:-postgres} -d INF_DB -f /init_sql.sql

echo "✅ All databases ensured."