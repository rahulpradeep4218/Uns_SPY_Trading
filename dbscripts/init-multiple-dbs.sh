#!/bin/bash
set -e
echo "Creating additional databases..."

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS(
            SELECT FROM pg_database WHERE datname = '${DAGSTER_POSTGRES_DB}'
        ) THEN
            EXECUTE 'CREATE DATABASE ${DAGSTER_POSTGRES_DB}';
        END IF;

        IF NOT EXISTS(
            SELECT FROM pg_database WHERE datname = '${MLFLOW_POSTGRES_DB}'
        ) THEN
            EXECUTE 'CREATE DATABASE ${MLFLOW_POSTGRES_DB}';
        END IF;
    END
    \$\$;
EOSQL