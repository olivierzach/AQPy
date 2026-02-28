CREATE SCHEMA IF NOT EXISTS derived;

CREATE OR REPLACE VIEW derived.pms_aqi AS
WITH src AS (
    SELECT
        t,
        pm25_st::double precision AS pm25_st,
        pm10_st::double precision AS pm10_st
    FROM pi
    WHERE pm25_st IS NOT NULL OR pm10_st IS NOT NULL
),
subidx AS (
    SELECT
        t,
        pm25_st,
        pm10_st,
        CASE
            WHEN pm25_st IS NULL THEN NULL
            WHEN floor(pm25_st * 10) / 10 <= 12.0 THEN ((50 - 0) / (12.0 - 0.0)) * ((floor(pm25_st * 10) / 10) - 0.0) + 0
            WHEN floor(pm25_st * 10) / 10 <= 35.4 THEN ((100 - 51) / (35.4 - 12.1)) * ((floor(pm25_st * 10) / 10) - 12.1) + 51
            WHEN floor(pm25_st * 10) / 10 <= 55.4 THEN ((150 - 101) / (55.4 - 35.5)) * ((floor(pm25_st * 10) / 10) - 35.5) + 101
            WHEN floor(pm25_st * 10) / 10 <= 150.4 THEN ((200 - 151) / (150.4 - 55.5)) * ((floor(pm25_st * 10) / 10) - 55.5) + 151
            WHEN floor(pm25_st * 10) / 10 <= 250.4 THEN ((300 - 201) / (250.4 - 150.5)) * ((floor(pm25_st * 10) / 10) - 150.5) + 201
            WHEN floor(pm25_st * 10) / 10 <= 350.4 THEN ((400 - 301) / (350.4 - 250.5)) * ((floor(pm25_st * 10) / 10) - 250.5) + 301
            WHEN floor(pm25_st * 10) / 10 <= 500.4 THEN ((500 - 401) / (500.4 - 350.5)) * ((floor(pm25_st * 10) / 10) - 350.5) + 401
            ELSE 500
        END AS aqi_pm25,
        CASE
            WHEN pm10_st IS NULL THEN NULL
            WHEN floor(pm10_st) <= 54 THEN ((50 - 0) / (54.0 - 0.0)) * (floor(pm10_st) - 0.0) + 0
            WHEN floor(pm10_st) <= 154 THEN ((100 - 51) / (154.0 - 55.0)) * (floor(pm10_st) - 55.0) + 51
            WHEN floor(pm10_st) <= 254 THEN ((150 - 101) / (254.0 - 155.0)) * (floor(pm10_st) - 155.0) + 101
            WHEN floor(pm10_st) <= 354 THEN ((200 - 151) / (354.0 - 255.0)) * (floor(pm10_st) - 255.0) + 151
            WHEN floor(pm10_st) <= 424 THEN ((300 - 201) / (424.0 - 355.0)) * (floor(pm10_st) - 355.0) + 201
            WHEN floor(pm10_st) <= 504 THEN ((400 - 301) / (504.0 - 425.0)) * (floor(pm10_st) - 425.0) + 301
            WHEN floor(pm10_st) <= 604 THEN ((500 - 401) / (604.0 - 505.0)) * (floor(pm10_st) - 505.0) + 401
            ELSE 500
        END AS aqi_pm10
    FROM src
)
SELECT
    t,
    pm25_st::integer AS pm25_st,
    pm10_st::integer AS pm10_st,
    greatest(coalesce(round(aqi_pm25), 0), coalesce(round(aqi_pm10), 0))::integer AS aqi_pm
FROM subidx;

CREATE OR REPLACE VIEW pms_aqi AS
SELECT t, pm25_st, pm10_st, aqi_pm
FROM derived.pms_aqi;
