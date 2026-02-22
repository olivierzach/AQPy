CREATE TABLE IF NOT EXISTS pi (
    t TIMESTAMPTZ NOT NULL DEFAULT now(),
    pm10_st INTEGER,
    pm25_st INTEGER,
    pm100_st INTEGER,
    pm10_en INTEGER,
    pm25_en INTEGER,
    pm100_en INTEGER,
    p1 INTEGER,
    p2 INTEGER,
    p3 INTEGER,
    p4 INTEGER,
    p5 INTEGER,
    p6 INTEGER
);

CREATE INDEX IF NOT EXISTS idx_pms_pi_t_desc ON pi (t DESC);
