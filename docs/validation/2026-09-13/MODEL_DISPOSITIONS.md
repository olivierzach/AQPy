# Verified model dispositions

Each repair run passed independent source, coverage, causal-fit, recursive-prediction, actual-alignment, policy, score, export and publication checks.

| Model | Source | Snapshot | Repaired | Added | Unresolved | Served / raw / persistence MAE | Disposition |
|---|---|---:|---:|---:|---:|---|---|
| aqpy_ar_aqi_pm | pms.pms_aqi_v2.aqi_pm | 1047 | 996 | 0 | 0 | 3.856 / 3.856 / 4.168 (n=996) | verified repair |
| aqpy_ar_humidity | bme.pi.humidity | 26095 | 84 | 84 | 4 | 0.402 / 0.402 / 0.3655 (n=84) | verified repair; unavailable source explicitly recorded |
| aqpy_ar_p1 | pms.pi.p1 | 26095 | 84 | 84 | 4 | 19.57 / 19.57 / 24.9 (n=84) | verified repair; unavailable source explicitly recorded |
| aqpy_ar_p2 | pms.pi.p2 | 26096 | 84 | 84 | 5 | 18.63 / 18.63 / 23.69 (n=84) | verified repair; unavailable source explicitly recorded |
| aqpy_ar_p3 | pms.pi.p3 | 26096 | 84 | 84 | 5 | 7.185 / 7.185 / 12.06 (n=84) | verified repair; unavailable source explicitly recorded |
| aqpy_ar_p4 | pms.pi.p4 | 26096 | 88 | 84 | 5 | 1.433 / 1.433 / 1.898 (n=88) | verified repair; unavailable source explicitly recorded |
| aqpy_ar_p5 | pms.pi.p5 | 26096 | 1954 | 84 | 5 | 0.06198 / 0.06349 / 0.1003 (n=1954) | verified repair; unavailable source explicitly recorded |
| aqpy_ar_p6 | pms.pi.p6 | 26096 | 2438 | 84 | 5 | 0.05024 / 0.05129 / 0.1206 (n=2438) | verified repair; unavailable source explicitly recorded |
| aqpy_ar_pm100_en | pms.pi.pm100_en | 1047 | 25452 | 25452 | 0 | 0.3118 / 0.3119 / 0.3516 (n=25452) | verified repair |
| aqpy_ar_pm100_st | pms.pi.pm100_st | 1047 | 25452 | 25452 | 0 | 0.3118 / 0.3119 / 0.3516 (n=25452) | verified repair |
| aqpy_ar_pm10_en | pms.pi.pm10_en | 1047 | 25452 | 25452 | 0 | 0.07369 / 0.07407 / 0.08636 (n=25452) | verified repair |
| aqpy_ar_pm10_st | pms.pi.pm10_st | 1047 | 25452 | 25452 | 0 | 0.07369 / 0.07407 / 0.08636 (n=25452) | verified repair |
| aqpy_ar_pm25_en | pms.pi.pm25_en | 1047 | 25452 | 25452 | 0 | 0.2864 / 0.2867 / 0.3213 (n=25452) | verified repair |
| aqpy_ar_pm25_st | pms.pi.pm25_st | 1047 | 25452 | 25452 | 0 | 0.2864 / 0.2867 / 0.3213 (n=25452) | verified repair |
| aqpy_ar_pressure | bme.pi.pressure | 26095 | 86 | 84 | 4 | 0.1335 / 0.1335 / 0.07881 (n=86) | verified repair; unavailable source explicitly recorded |
| aqpy_ar_temperature | bme.pi.temperature | 26095 | 114 | 84 | 5 | 0.4577 / 0.4577 / 0.396 (n=114) | verified repair; unavailable source explicitly recorded |
| aqpy_nn_aqi_pm | pms.pms_aqi_v2.aqi_pm | 1047 | 996 | 0 | 0 | 3.795 / 3.795 / 4.168 (n=996) | verified repair |
| aqpy_nn_humidity | bme.pi.humidity | 26095 | 111 | 84 | 4 | 1.482 / 365.8 / 1.5 (n=111) | verified repair; unavailable source explicitly recorded |
| aqpy_nn_p1 | pms.pi.p1 | 26095 | 169 | 84 | 4 | 40.58 / 317.6 / 18.68 (n=169) | verified repair; unavailable source explicitly recorded |
| aqpy_nn_p2 | pms.pi.p2 | 26095 | 85 | 84 | 4 | 17.44 / 17.44 / 23.46 (n=85) | verified repair; unavailable source explicitly recorded |
| aqpy_nn_p3 | pms.pi.p3 | 26096 | 88 | 84 | 5 | 7.12 / 7.14 / 11.9 (n=88) | verified repair; unavailable source explicitly recorded |
| aqpy_nn_p4 | pms.pi.p4 | 26096 | 103 | 84 | 5 | 1.319 / 1.33 / 1.854 (n=103) | verified repair; unavailable source explicitly recorded |
| aqpy_nn_p5 | pms.pi.p5 | 26096 | 85 | 84 | 5 | 0.107 / 0.107 / 0.04706 (n=85) | verified repair; unavailable source explicitly recorded |
| aqpy_nn_p6 | pms.pi.p6 | 26096 | 87 | 84 | 6 | 0.08326 / 0.08332 / 0.04598 (n=87) | verified repair; unavailable source explicitly recorded |
| aqpy_nn_pm100_en | pms.pi.pm100_en | 26095 | 5028 | 84 | 5 | 0.047 / 0.08455 / 0.0533 (n=5028) | verified repair; unavailable source explicitly recorded |
| aqpy_nn_pm100_st | pms.pi.pm100_st | 26095 | 5562 | 84 | 4 | 0.03697 / 23.27 / 0.04081 (n=5562) | verified repair; unavailable source explicitly recorded |
| aqpy_nn_pm10_en | pms.pi.pm10_en | 26095 | 8637 | 84 | 4 | 0.009012 / 30.39 / 0.009957 (n=8637) | verified repair; unavailable source explicitly recorded |
| aqpy_nn_pm10_st | pms.pi.pm10_st | 26095 | 8393 | 84 | 4 | 0.01303 / 0.03443 / 0.0143 (n=8393) | verified repair; unavailable source explicitly recorded |
| aqpy_nn_pm25_en | pms.pi.pm25_en | 26095 | 7513 | 84 | 4 | 0.05817 / 30.11 / 0.06855 (n=7513) | verified repair; unavailable source explicitly recorded |
| aqpy_nn_pm25_st | pms.pi.pm25_st | 26095 | 5905 | 84 | 4 | 0.04877 / 10.87 / 0.05368 (n=5905) | verified repair; unavailable source explicitly recorded |
| aqpy_nn_pressure | bme.pi.pressure | 26095 | 86 | 84 | 4 | 0.08473 / 0.08473 / 0.07805 (n=86) | verified repair; unavailable source explicitly recorded |
| aqpy_nn_temperature | bme.pi.temperature | 26095 | 90 | 84 | 4 | 0.2844 / 0.2844 / 0.4803 (n=90) | verified repair; unavailable source explicitly recorded |
| aqpy_rnn_aqi_pm | pms.pms_aqi_v2.aqi_pm | 1047 | 996 | 0 | 0 | 4.061 / 4.064 / 4.168 (n=996) | verified repair |
| aqpy_rnn_humidity | bme.pi.humidity | 26095 | 84 | 84 | 4 | 0.4386 / 0.4386 / 0.3655 (n=84) | verified repair; unavailable source explicitly recorded |
| aqpy_rnn_p1 | pms.pi.p1 | 26095 | 85 | 84 | 4 | 18.91 / 18.91 / 24.64 (n=85) | verified repair; unavailable source explicitly recorded |
| aqpy_rnn_p2 | pms.pi.p2 | 26096 | 86 | 84 | 5 | 17.65 / 17.65 / 23.23 (n=86) | verified repair; unavailable source explicitly recorded |
| aqpy_rnn_p3 | pms.pi.p3 | 26096 | 89 | 84 | 5 | 7.358 / 7.358 / 11.62 (n=89) | verified repair; unavailable source explicitly recorded |
| aqpy_rnn_p4 | pms.pi.p4 | 26096 | 87 | 84 | 5 | 1.436 / 1.442 / 2.057 (n=87) | verified repair; unavailable source explicitly recorded |
| aqpy_rnn_p5 | pms.pi.p5 | 26096 | 86 | 84 | 5 | 0.09454 / 0.09458 / 0.05814 (n=86) | verified repair; unavailable source explicitly recorded |
| aqpy_rnn_p6 | pms.pi.p6 | 26096 | 85 | 84 | 5 | 0.0828 / 0.08286 / 0.05882 (n=85) | verified repair; unavailable source explicitly recorded |
| aqpy_rnn_pm100_en | pms.pi.pm100_en | 26095 | 967 | 84 | 4 | 0.1898 / 0.233 / 0.1417 (n=967) | verified repair; unavailable source explicitly recorded |
| aqpy_rnn_pm100_st | pms.pi.pm100_st | 26095 | 963 | 84 | 4 | 0.1921 / 0.2359 / 0.1475 (n=963) | verified repair; unavailable source explicitly recorded |
| aqpy_rnn_pm10_en | pms.pi.pm10_en | 26095 | 1077 | 84 | 4 | 0.1366 / 0.2151 / 0.08542 (n=1077) | verified repair; unavailable source explicitly recorded |
| aqpy_rnn_pm10_st | pms.pi.pm10_st | 26095 | 1093 | 84 | 4 | 0.1339 / 0.215 / 0.08234 (n=1093) | verified repair; unavailable source explicitly recorded |
| aqpy_rnn_pm25_en | pms.pi.pm25_en | 26095 | 558 | 84 | 4 | 0.4907 / 0.5664 / 0.2796 (n=558) | verified repair; unavailable source explicitly recorded |
| aqpy_rnn_pm25_st | pms.pi.pm25_st | 26095 | 605 | 84 | 4 | 0.4621 / 0.5325 / 0.2678 (n=605) | verified repair; unavailable source explicitly recorded |
| aqpy_rnn_pressure | bme.pi.pressure | 26095 | 86 | 84 | 4 | 0.07064 / 0.07064 / 0.07846 (n=86) | verified repair; unavailable source explicitly recorded |
| aqpy_rnn_temperature | bme.pi.temperature | 26095 | 92 | 84 | 4 | 0.3851 / 0.3851 / 0.473 (n=92) | verified repair; unavailable source explicitly recorded |
