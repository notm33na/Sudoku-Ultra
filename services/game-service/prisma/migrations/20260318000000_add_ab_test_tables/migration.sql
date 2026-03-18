-- Migration: add_ab_test_tables
-- Adds ab_test_config and ab_test_result for ML model A/B experiments.

CREATE TABLE "ab_test_config" (
    "id"               TEXT    NOT NULL,
    "experiment_name"  TEXT    NOT NULL,
    "model_name"       TEXT    NOT NULL,
    "control_variant"  TEXT    NOT NULL,
    "treatment_variant" TEXT   NOT NULL,
    "traffic_split"    DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    "status"           TEXT    NOT NULL DEFAULT 'active',
    "description"      TEXT    NOT NULL DEFAULT '',
    "start_date"       TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "end_date"         TIMESTAMP(3),
    "created_at"       TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at"       TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ab_test_config_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "ab_test_config_experiment_name_key"
    ON "ab_test_config"("experiment_name");

CREATE TABLE "ab_test_result" (
    "id"               TEXT    NOT NULL,
    "experiment_name"  TEXT    NOT NULL,
    "user_id"          TEXT    NOT NULL,
    "variant"          TEXT    NOT NULL,
    "metric_name"      TEXT    NOT NULL,
    "metric_value"     DOUBLE PRECISION NOT NULL,
    "recorded_at"      TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ab_test_result_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "ab_test_result_experiment_name_variant_idx"
    ON "ab_test_result"("experiment_name", "variant");

CREATE INDEX "ab_test_result_user_id_idx"
    ON "ab_test_result"("user_id");

ALTER TABLE "ab_test_result"
    ADD CONSTRAINT "ab_test_result_experiment_name_fkey"
    FOREIGN KEY ("experiment_name")
    REFERENCES "ab_test_config"("experiment_name")
    ON DELETE CASCADE ON UPDATE CASCADE;

-- updated_at trigger for ab_test_config
CREATE OR REPLACE FUNCTION update_ab_test_config_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER ab_test_config_updated_at
    BEFORE UPDATE ON "ab_test_config"
    FOR EACH ROW EXECUTE PROCEDURE update_ab_test_config_updated_at();
