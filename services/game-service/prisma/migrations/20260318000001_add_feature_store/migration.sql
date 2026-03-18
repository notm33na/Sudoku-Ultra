-- Migration: add_feature_store
-- Adds feature_store (versioned feature snapshots) and feature_lineage
-- (data provenance records) for the ML feature store.

CREATE TABLE "feature_store" (
    "id"               TEXT    NOT NULL,
    "entity_id"        TEXT    NOT NULL,
    "entity_type"      TEXT    NOT NULL,
    "feature_group"    TEXT    NOT NULL,
    "feature_version"  INTEGER NOT NULL,
    "features"         JSONB   NOT NULL,
    "is_current"       BOOLEAN NOT NULL DEFAULT true,
    "pipeline_name"    TEXT    NOT NULL,
    "pipeline_run_id"  TEXT,
    "computed_at"      TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "feature_store_pkey" PRIMARY KEY ("id")
);

-- Enforce one record per (entity, group, version)
CREATE UNIQUE INDEX "feature_store_entity_group_version_key"
    ON "feature_store"("entity_id", "entity_type", "feature_group", "feature_version");

-- Fast lookup of the current feature vector for a given entity
CREATE INDEX "feature_store_entity_current_idx"
    ON "feature_store"("entity_id", "entity_type", "feature_group", "is_current");

-- Time-ordered scan per feature group (used by backfill detection)
CREATE INDEX "feature_store_group_time_idx"
    ON "feature_store"("feature_group", "computed_at" DESC);

CREATE TABLE "feature_lineage" (
    "id"             TEXT    NOT NULL,
    "feature_id"     TEXT    NOT NULL,
    "source_table"   TEXT    NOT NULL,
    "source_filter"  JSONB   NOT NULL,
    "row_count"      INTEGER,
    "computed_at"    TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "feature_lineage_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "feature_lineage_feature_id_idx"
    ON "feature_lineage"("feature_id");

ALTER TABLE "feature_lineage"
    ADD CONSTRAINT "feature_lineage_feature_id_fkey"
    FOREIGN KEY ("feature_id")
    REFERENCES "feature_store"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;
