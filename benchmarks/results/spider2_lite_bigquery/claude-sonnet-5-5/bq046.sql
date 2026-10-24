WITH a AS (
  SELECT DISTINCT
    case_barcode,
    category AS categoryName,
    classification AS classificationName
  FROM `isb-cgc.TCGA_bioclin_v0.Annotations`
  WHERE entity_type = 'Patient'
    AND (category = 'History of unacceptable prior treatment related to a prior/other malignancy'
         OR classification = 'Redaction')
),
c AS (
  SELECT DISTINCT case_barcode
  FROM `isb-cgc.TCGA_bioclin_v0.clinical_v1`
  WHERE disease_code = 'BRCA'
    AND age_at_diagnosis <= 30
    AND gender = 'FEMALE'
),
j AS (
  SELECT
    COALESCE(c.case_barcode, a.case_barcode) AS case_barcode,
    a.categoryName,
    a.classificationName
  FROM a
  FULL JOIN c
    ON a.case_barcode = c.case_barcode
  WHERE a.categoryName IS NULL
    AND a.classificationName IS NULL
)
SELECT
  j.case_barcode,
  u.file_gdc_url
FROM j
JOIN `isb-cgc.GDC_metadata.rel14_caseData` cd
  ON cd.case_barcode = j.case_barcode
JOIN `isb-cgc.GDC_metadata.rel14_fileData_current` fd
  ON fd.case_gdc_id = cd.case_gdc_id
JOIN `isb-cgc.GDC_metadata.rel14_GDCfileID_to_GCSurl_NEW` u
  ON u.file_gdc_id = fd.file_gdc_id