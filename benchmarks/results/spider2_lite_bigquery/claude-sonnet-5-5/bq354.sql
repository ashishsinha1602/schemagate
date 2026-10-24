WITH roots AS (
  SELECT
    c.concept_code,
    c2.concept_id AS standard_concept_id
  FROM `bigquery-public-data.cms_synthetic_patient_data_omop.concept` c
  JOIN `bigquery-public-data.cms_synthetic_patient_data_omop.concept_relationship` r
    ON r.concept_id_1 = c.concept_id
   AND r.relationship_id = 'Maps to'
  JOIN `bigquery-public-data.cms_synthetic_patient_data_omop.concept` c2
    ON c2.concept_id = r.concept_id_2
   AND c2.standard_concept = 'S'
  WHERE c.vocabulary_id = 'ICD10CM'
    AND c.concept_code IN ('L70', 'L20', 'L40', 'L80')
),
descendants AS (
  SELECT
    ro.concept_code,
    ca.descendant_concept_id
  FROM roots ro
  JOIN `bigquery-public-data.cms_synthetic_patient_data_omop.concept_ancestor` ca
    ON ca.ancestor_concept_id = ro.standard_concept_id
),
counts AS (
  SELECT
    CASE concept_code
      WHEN 'L70' THEN 'Acne'
      WHEN 'L20' THEN 'Atopic dermatitis'
      WHEN 'L40' THEN 'Psoriasis'
      WHEN 'L80' THEN 'Vitiligo'
    END AS condition_name,
    COUNT(DISTINCT descendant_concept_id) AS concept_count
  FROM descendants
  GROUP BY concept_code
)
SELECT
  condition_name,
  100 * SAFE_DIVIDE(concept_count, SUM(concept_count) OVER ()) AS percentage
FROM counts