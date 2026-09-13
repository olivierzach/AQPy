CREATE SCHEMA IF NOT EXISTS derived;

-- Instantaneous standard-mass proxy, capped at 500. Not daily AQI/NowCast.
CREATE OR REPLACE FUNCTION derived.pm_index_v2(pm25 double precision, pm10 double precision)
RETURNS integer LANGUAGE SQL IMMUTABLE AS $$
WITH concentrations(kind,c) AS (
 SELECT 'pm25',trunc(pm25::numeric,1) WHERE pm25>=0 AND pm25<'Infinity'::float8
 UNION ALL SELECT 'pm10',trunc(pm10::numeric,0) WHERE pm10>=0 AND pm10<'Infinity'::float8
), bands(kind,lo,hi,ilo,ihi) AS (VALUES
 ('pm25',0.0,9.0,0,50),('pm25',9.1,35.4,51,100),('pm25',35.5,55.4,101,150),
 ('pm25',55.5,125.4,151,200),('pm25',125.5,225.4,201,300),('pm25',225.5,325.4,301,500),
 ('pm10',0.0,54.0,0,50),('pm10',55.0,154.0,51,100),('pm10',155.0,254.0,101,150),
 ('pm10',255.0,354.0,151,200),('pm10',355.0,424.0,201,300),('pm10',425.0,604.0,301,500)
)
SELECT max(CASE WHEN b.lo IS NULL THEN 500 ELSE round(b.ilo+(c.c-b.lo)*(b.ihi-b.ilo)/(b.hi-b.lo))::integer END)
FROM concentrations c LEFT JOIN bands b ON b.kind=c.kind AND c.c BETWEEN b.lo AND b.hi;
$$;

CREATE OR REPLACE VIEW derived.pms_aqi_v2 AS
SELECT t,pm25_st,pm100_st,derived.pm_index_v2(pm25_st,pm100_st) AS aqi_pm,
 'instant_pm_index_epa2024_v2'::text AS aqi_definition FROM pi;
CREATE OR REPLACE VIEW pms_aqi_v2 AS SELECT * FROM derived.pms_aqi_v2;
