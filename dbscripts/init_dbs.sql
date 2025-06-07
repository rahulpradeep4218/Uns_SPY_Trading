-- Create Trading_Dagster_DB if it doesn't exist
SELECT 'CREATE DATABASE "Trading_Dagster_DB"'
WHERE NOT EXISTS (
  SELECT FROM pg_database WHERE datname = 'Trading_Dagster_DB'
)\gexec

-- Create MLFlow_DB if it doesn't exist
SELECT 'CREATE DATABASE "MLFlow_DB"'
WHERE NOT EXISTS (
  SELECT FROM pg_database WHERE datname = 'MLFlow_DB'
)\gexec