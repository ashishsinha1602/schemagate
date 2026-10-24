SELECT
  a.consecutive_number,
  a.county,
  a.type_of_intersection,
  a.light_condition,
  a.atmospheric_conditions_1,
  a.hour_of_crash,
  a.functional_system,
  a.related_factors_crash_level_1 AS related_factors,
  IF(a.hour_of_ems_arrival_at_hospital BETWEEN 0 AND 23, a.hour_of_ems_arrival_at_hospital - a.hour_of_crash, NULL) AS delay_to_hospital,
  IF(a.hour_of_arrival_at_scene BETWEEN 0 AND 23, a.hour_of_arrival_at_scene - a.hour_of_crash, NULL) AS delay_to_scene,
  p.age,
  p.person_type,
  p.seating_position,
  CASE SAFE_CAST(p.restraint_system_helmet_use AS INT64)
    WHEN 0 THEN 0
    WHEN 1 THEN 0.33
    WHEN 2 THEN 0.67
    WHEN 3 THEN 1.0
    ELSE 0.5
  END AS restraint,
  IF(SAFE_CAST(p.injury_severity AS INT64) = 4, 1, 0) AS survived,
  IF(CAST(v.rollover AS STRING) IN ('0', 'No Rollover'), 0, 1) AS rollover,
  IF(SAFE_CAST(p.air_bag_deployed AS INT64) BETWEEN 1 AND 9, 1, 0) AS airbag,
  IF(CONTAINS_SUBSTR(p.police_reported_alcohol_involvement, 'Yes'), 1, 0) AS alcohol,
  IF(CONTAINS_SUBSTR(p.police_reported_drug_involvement, 'Yes'), 1, 0) AS drugs,
  p.related_factors_person_level1,
  v.travel_speed,
  IF(CONTAINS_SUBSTR(v.speeding_related, 'Yes'), 1, 0) AS speeding_related,
  v.extent_of_damage,
  v.body_type,
  v.vehicle_removal,
  IF(a.manner_of_collision > 11, 11, a.manner_of_collision) AS manner_of_collision,
  IF(v.roadway_surface_condition > 11, 8, v.roadway_surface_condition) AS roadway_surface_condition,
  IF(a.first_harmful_event < 90, a.first_harmful_event, 0) AS first_harmful_event,
  IF(v.most_harmful_event < 90, v.most_harmful_event, 0) AS most_harmful_event
FROM `bigquery-public-data.nhtsa_traffic_fatalities.accident_2015` a
JOIN `bigquery-public-data.nhtsa_traffic_fatalities.vehicle_2015` v
  ON a.consecutive_number = v.consecutive_number
JOIN `bigquery-public-data.nhtsa_traffic_fatalities.person_2015` p
  ON a.consecutive_number = p.consecutive_number
 AND v.vehicle_number = p.vehicle_number