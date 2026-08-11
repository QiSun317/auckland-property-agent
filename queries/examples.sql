-- Worked examples. Run one at a time:  python3 scripts/q.py -f queries/examples.sql
-- (q.py prints only the last statement's result, so paste the one you want.)

-- 1. Shortlist: budget, yield, and a liquid market
SELECT name, avg_house_value, round(est_gross_yield_pct, 1) AS yield_pct,
       median_weekly_rent, sold_last_12m, median_days_to_sell
FROM suburb_overview
WHERE avg_house_value BETWEEN 900000 AND 1200000
  AND est_gross_yield_pct > 3 AND sold_last_12m > 50
ORDER BY est_gross_yield_pct DESC;

-- 2. Everything within 1.5 km of a point, by walk-up distance.
--    Use ST_Distance_Sphere, NOT ST_Distance_Spheroid: the spheroid variants
--    return nan / always-false in duckdb-spatial 1.5.5.
SELECT s.name, count(*) AS units, median(r.cv_2024)::BIGINT AS cv_median
FROM rating_unit r JOIN suburb s USING (suburb_id)
WHERE ST_Distance_Sphere(r.geom, ST_Point(174.7645, -36.8443)) <= 1500
GROUP BY 1 ORDER BY units DESC;

-- 3. Street-level medians inside one suburb
SELECT trim(regexp_replace(split_part(address, ',', 1),
             '^[0-9]+[A-Za-z]?(/[0-9]+[A-Za-z]?)?\s*', '')) AS street,
       count(*) AS n, median(cv_2024)::BIGINT AS cv_median
FROM rating_unit r JOIN suburb s USING (suburb_id)
WHERE s.name = 'Remuera' AND cv_2024 IS NOT NULL
GROUP BY 1 HAVING count(*) >= 25
ORDER BY cv_median DESC;

-- 4. Which suburbs the 2021 -> 2024 revaluation hit hardest
SELECT s.name, count(*) AS units,
       round(median((cv_2024 - cv_2021) / cv_2021::DOUBLE) * 100, 1) AS pct_change
FROM rating_unit r JOIN suburb s USING (suburb_id)
WHERE cv_2021 > 0 AND cv_2024 > 0
GROUP BY 1 HAVING count(*) >= 300
ORDER BY pct_change;

-- 5. Land value per m2 on ordinary freehold sections
SELECT s.name, count(*) AS n, median(lv_2024 / land_area_m2)::INT AS lv_per_m2
FROM rating_unit r JOIN suburb s USING (suburb_id)
WHERE land_area_m2 BETWEEN 300 AND 1200 AND lv_2024 > 0
GROUP BY 1 HAVING count(*) >= 200
ORDER BY lv_per_m2 DESC;

-- 6. One property
SELECT address, land_area_m2, cv_2021, cv_2024,
       round((cv_2024 - cv_2021) / cv_2021::DOUBLE * 100, 1) AS pct_change
FROM rating_unit
WHERE address ILIKE '23 Coromandel Cres%';

-- 7. Everything known about one suburb, in one row
SELECT * FROM suburb_overview WHERE name = 'Titirangi';
