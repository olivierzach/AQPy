-- Additive: preserve legacy rows and the raw output behind future corrections.
SET lock_timeout = '2s';
SET statement_timeout = '10s';
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS raw_yhat DOUBLE PRECISION;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS output_policy TEXT NOT NULL DEFAULT 'legacy_unchecked';
