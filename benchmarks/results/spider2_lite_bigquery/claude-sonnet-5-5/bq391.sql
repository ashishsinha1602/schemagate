WITH pats AS (
  SELECT p.id
  FROM `bigquery-public-data.fhir_synthea.patient` p
  WHERE p.deceased.dateTime IS NULL
    AND COALESCE(p.deceased.boolean, FALSE) = FALSE
    AND EXISTS (SELECT 1 FROM UNNEST(p.name) n WHERE n.family LIKE 'A%')
),
cond AS (
  SELECT c.subject.patientId AS pid,
         c.code.coding[SAFE_OFFSET(0)].code AS ccode,
         c.code.coding[SAFE_OFFSET(0)].display AS cdisplay
  FROM `bigquery-public-data.fhir_synthea.condition` c
  JOIN pats ON pats.id = c.subject.patientId
),
single AS (
  SELECT pid, ANY_VALUE(ccode) AS cond_code, ANY_VALUE(cdisplay) AS cond_display
  FROM cond
  GROUP BY pid
  HAVING COUNT(DISTINCT ccode) = 1
),
meds AS (
  SELECT m.subject.patientId AS pid, COUNT(DISTINCT mc.code) AS n
  FROM `bigquery-public-data.fhir_synthea.medication_request` m,
       UNNEST(m.medication.codeableConcept.coding) mc
  WHERE m.status = 'active'
  GROUP BY pid
)
SELECT s.cond_display AS condition, s.cond_code AS condition_code
FROM single s
JOIN meds ON meds.pid = s.pid
GROUP BY s.cond_code, s.cond_display
ORDER BY MAX(meds.n) DESC
LIMIT 8