WITH pop AS (
  SELECT zipcode, SUM(population) AS population
  FROM `bigquery-public-data.census_bureau_usa.population_by_zip_2010`
  WHERE gender IN ('male', 'female')
    AND minimum_age IS NULL
    AND maximum_age IS NULL
  GROUP BY zipcode
)
SELECT
  z.zipcode_geom,
  z.area_land_meters,
  z.area_water_meters,
  z.latitude,
  z.longitude,
  z.state_code,
  z.state_name,
  z.city,
  z.county,
  p.population
FROM `bigquery-public-data.utility_us.zipcode_area` AS z
JOIN pop AS p
  ON z.zipcode = p.zipcode
WHERE ST_DWITHIN(ST_GEOGFROMTEXT(z.zipcode_geom), ST_GEOGPOINT(-122.3321, 47.6062), 10000)