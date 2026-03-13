-- ──────────────────────────────────────────────────────────────────────────────
-- PostgreSQL initialization script
-- Runs once on first container start (via docker-entrypoint-initdb.d)
-- Creates the 'airflow' metadata database for the Airflow scheduler.
-- ──────────────────────────────────────────────────────────────────────────────

CREATE DATABASE airflow;
GRANT ALL PRIVILEGES ON DATABASE airflow TO sudoku;
