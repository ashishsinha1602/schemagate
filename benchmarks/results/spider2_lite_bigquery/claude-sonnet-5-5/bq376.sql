WITH s AS (
  SELECT n.neighborhood, COUNT(*) AS station_count
  FROM `bigquery-public-data.san_francisco_neighborhoods.boundaries` n
  JOIN `bigquery-public-data.san_francisco_bikeshare.bikeshare_station_info` b
    ON ST_CONTAINS(n.neighborhood_geom, b.station_geom)
  GROUP BY n.neighborhood
),
c AS (
  SELECT n.neighborhood, COUNT(*) AS incident_count
  FROM `bigquery-public-data.san_francisco_neighborhoods.boundaries` n
  JOIN `bigquery-public-data.san_francisco_sfpd_incidents.sfpd_incidents` i
    ON ST_CONTAINS(n.neighborhood_geom, ST_GEOGPOINT(i.longitude, i.latitude))
  WHERE i.longitude IS NOT NULL AND i.latitude IS NOT NULL
  GROUP BY n.neighborhood
)
SELECT s.neighborhood, s.station_count, c.incident_count
FROM s
JOIN c USING (neighborhood)