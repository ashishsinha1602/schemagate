SELECT p.port_name
FROM `bigquery-public-data.geo_international_ports.world_port_index` AS p
JOIN `bigquery-public-data.geo_us_boundaries.states` AS s
  ON ST_WITHIN(p.port_geom, s.state_geom)
WHERE p.region_number = '6585'
ORDER BY p.port_name
LIMIT 1