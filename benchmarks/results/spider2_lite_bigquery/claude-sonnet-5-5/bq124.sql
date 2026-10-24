WITH dx AS (
  SELECT DISTINCT c.patient.patientId AS pid
  FROM `bigquery-public-data.fhir_synthea.claim` c,
    UNNEST(c.diagnosis) d,
    UNNEST(d.diagnosis.codeableConcept.coding) cd
  WHERE LOWER(cd.display) LIKE '%diabetes%'
    OR LOWER(cd.display) LIKE '%hypertension%'
),
meds AS (
  SELECT mr.subject.patientId AS pid
  FROM `bigquery-public-data.fhir_synthea.medication_request` mr,
    UNNEST(mr.medication.codeableConcept.coding) mc
  WHERE mr.status = 'active'
  GROUP BY mr.subject.patientId
  HAVING COUNT(DISTINCT mc.code) >= 7
)
SELECT COUNT(DISTINCT p.id) AS patient_count
FROM `bigquery-public-data.fhir_synthea.patient` p
JOIN dx ON p.id = dx.pid
JOIN meds ON p.id = meds.pid
WHERE p.deceased.dateTime IS NULL