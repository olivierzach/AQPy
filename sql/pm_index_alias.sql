SET lock_timeout='2s';
SET statement_timeout='10s';
DO $$ BEGIN
 IF to_regclass('derived.pms_aqi') IS NOT NULL AND to_regclass('derived.pms_aqi_legacy_v1') IS NULL THEN
  EXECUTE 'CREATE VIEW derived.pms_aqi_legacy_v1 AS ' || pg_get_viewdef('derived.pms_aqi'::regclass,true);
 END IF;
END $$;

-- Preserve the original four column names/order; append explicit PM10/definition.
CREATE OR REPLACE VIEW derived.pms_aqi AS
SELECT t,pm25_st::integer,pm10_st::integer,
 derived.pm_index_v2(pm25_st,pm100_st) AS aqi_pm,
 pm100_st::integer,'instant_pm_index_epa2024_v2'::text AS aqi_definition FROM pi;
CREATE OR REPLACE VIEW pms_aqi AS SELECT * FROM derived.pms_aqi;
