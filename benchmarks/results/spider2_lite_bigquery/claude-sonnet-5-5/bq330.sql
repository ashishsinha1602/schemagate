WITH overlaps AS (
  SELECT
    z.zip_code,
    b.geo_id,
    SAFE_DIVIDE(
      ST_AREA(ST_INTERSECTION(z.zip_code_geom, b.blockgroup_geom)),
      ST_AREA(b.blockgroup_geom)
    ) AS overlap_ratio
  FROM `bigquery-public-data.geo_us_boundaries.zip_codes` z
  JOIN `bigquery-public-data.geo_census_blockgroups.us_blockgroups_national` b
    ON ST_INTERSECTS(z.zip_code_geom, b.blockgroup_geom)
  WHERE z.state_code = 'CO'
    AND b.state_name = 'Colorado'
)
SELECT
  zip_code
FROM overlaps
GROUP BY zip_code
ORDER BY SUM(overlap_ratio) DESC
LIMIT 1