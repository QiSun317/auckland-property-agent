-- Worked examples. Run one at a time:  python3 scripts/q.py -f queries/examples.sql
-- (q.py prints only the last statement's result, so paste the one you want.)

-- 1. Shortlist: budget, yield, and a liquid market
SELECT name, avg_house_value, round(est_gross_yield_pct, 1) AS yield_pct,
       median_weekly_rent, sold_last_12m, median_days_to_sell
FROM suburb_overview
WHERE avg_house_value BETWEEN 900000 AND 1200000
  AND est_gross_yield_pct > 3 AND sold_last_12m > 50
ORDER BY est_gross_yield_pct DESC;

-- 2. Everything within 1.5 km of a point.
--    Project to NZTM (metres) rather than using ST_Distance_Sphere /
--    ST_Distance_Spheroid: those follow EPSG:4326's declared (lat, lon) axis
--    order, so passing the (lon, lat) points stored here returns nan, or worse,
--    a plausible-looking wrong number. always_xy pins the input order.
WITH nztm AS (SELECT 'EPSG:4326' AS src, 'EPSG:2193' AS dst)
SELECT s.name, count(*) AS units, median(v.cv)::BIGINT AS cv_median
FROM rating_unit_current v JOIN suburb s USING (suburb_id)
JOIN rating_unit r USING (ru_id), nztm
WHERE ST_Distance(
        ST_Transform(r.geom, src, dst, always_xy := true),
        ST_Transform(ST_Point(174.7645, -36.8443), src, dst, always_xy := true)
      ) <= 1500
GROUP BY 1 ORDER BY units DESC;

-- 3. Street-level medians inside one suburb
SELECT trim(regexp_replace(split_part(address, ',', 1),
             '^[0-9]+[A-Za-z]?(/[0-9]+[A-Za-z]?)?\s*', '')) AS street,
       count(*) AS n, median(cv)::BIGINT AS cv_median
FROM rating_unit_current r JOIN suburb s USING (suburb_id)
WHERE s.name = 'Remuera' AND cv IS NOT NULL
GROUP BY 1 HAVING count(*) >= 25
ORDER BY cv_median DESC;

-- 4. Which suburbs the 2021 -> 2024 revaluation hit hardest.
--    Two rounds means two rows of `valuation` per unit, so comparing them is a
--    self-join on ru_id rather than two columns. Naming both dates as literals
--    keeps each side an equality filter, and it runs in ~16 ms.
SELECT s.name, count(*) AS units,
       round(median((b.cv - a.cv) / a.cv::DOUBLE) * 100, 1) AS pct_change
FROM valuation a
JOIN valuation b ON a.ru_id = b.ru_id
                AND a.valuation_date = DATE '2021-06-01'
                AND b.valuation_date = DATE '2024-05-01'
JOIN rating_unit r ON r.ru_id = a.ru_id
JOIN suburb s USING (suburb_id)
WHERE a.cv > 0 AND b.cv > 0
GROUP BY 1 HAVING count(*) >= 300
ORDER BY pct_change;

-- 5. Land value per m2 on ordinary freehold sections.
--    Only the latest round is wanted, which is what rating_unit_current is for.
SELECT s.name, count(*) AS n, median(lv / land_area_m2)::INT AS lv_per_m2
FROM rating_unit_current r JOIN suburb s USING (suburb_id)
WHERE land_area_m2 BETWEEN 300 AND 1200 AND lv > 0
GROUP BY 1 HAVING count(*) >= 200
ORDER BY lv_per_m2 DESC;

-- 6. One property, and what the revaluation did to it
SELECT c.address, c.land_area_m2, a.cv AS cv_2021,
       c.cv AS cv_current, c.valuation_date,
       round((c.cv - a.cv) / a.cv::DOUBLE * 100, 1) AS pct_change
FROM rating_unit_current c
JOIN valuation a ON a.ru_id = c.ru_id AND a.valuation_date = DATE '2021-06-01'
WHERE c.address ILIKE '23 Coromandel Cres%';

-- 7. Everything known about one suburb, in one row
SELECT * FROM suburb_overview WHERE name = 'Titirangi';
