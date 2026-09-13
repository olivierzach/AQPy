# Versioned instantaneous particle index

`pms_aqi_v2` and `derived.pms_aqi_v2` use **pm25_st for PM2.5 and pm100_st for
PM10**. In this ingestion schema `pm10_st` is PM1.0, not PM10. The earlier derived
view used that wrong PM10 input. `aqi_definition` identifies
`instant_pm_index_epa2024_v2`.

The version uses current PM breakpoints from the
[EPA AQI reference table](https://aqs.epa.gov/aqsweb/documents/codetables/aqi_breakpoints.html).
PM2.5 is truncated to 0.1 and PM10 to whole ug/m3; interpolated component values
round half up, and the larger component is used. Missing/invalid concentrations
are not fabricated as zero. This application caps the proxy at 500.

**This is an instantaneous index proxy, not official daily AQI or NowCast.** It
uses the PMS standard-mass readings directly without the temporal averaging
required for those products. AirNow describes daily PM forecasts as 24-hour
concentrations and current reporting as NowCast:
[AirNow: Using the AQI](https://www.airnow.gov/aqi/aqi-basics/using-air-quality-index/).
This distinction belongs in the dashboard, not just implementation notes.

Models use the explicit `pms_aqi_v2` source and start fresh when their source
definition changes. Artifacts carry `target_definition`; old prediction rows
retain their original source/version. Historical repairs must use the corrected
frozen target and label reconstructed outputs. The old view definition is
preserved as `derived.pms_aqi_legacy_v1` when the compatibility alias is migrated.

`sql/pm_index_v2.sql` installs the new source alongside the old one. Transition
models first, then apply `sql/pm_index_alias.sql` to switch existing raw dashboard
queries to the corrected index. `sql/derived_schema_pms.sql` includes both for
new installations. The alias keeps its original four columns and appends PM10
and definition metadata for compatibility.
