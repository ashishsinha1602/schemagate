WITH patients AS (
  SELECT DISTINCT ParticipantBarcode
  FROM `isb-cgc-bq.pancancer_atlas.TCGA_CDR`
  WHERE Study = 'PAAD'
),
mut AS (
  SELECT
    m.ParticipantBarcode,
    MAX(IF(m.Hugo_Symbol = 'KRAS', 1, 0)) AS kras,
    MAX(IF(m.Hugo_Symbol = 'TP53', 1, 0)) AS tp53
  FROM `isb-cgc-bq.pancancer_atlas.Filtered_MC3_MAF_V5_one_per_tumor_sample` m
  WHERE m.Study = 'PAAD'
    AND m.Hugo_Symbol IN ('KRAS', 'TP53')
    AND NOT EXISTS (
      SELECT 1
      FROM `isb-cgc-bq.pancancer_atlas.merged_sample_quality_annotations` q
      WHERE q.aliquot_barcode = m.Tumor_AliquotBarcode
        AND q.Do_not_use = 'True'
    )
  GROUP BY m.ParticipantBarcode
),
flags AS (
  SELECT
    p.ParticipantBarcode,
    IFNULL(mu.kras, 0) AS kras,
    IFNULL(mu.tp53, 0) AS tp53
  FROM patients p
  LEFT JOIN mut mu ON mu.ParticipantBarcode = p.ParticipantBarcode
),
counts AS (
  SELECT
    COUNTIF(kras = 1 AND tp53 = 1) AS a,
    COUNTIF(kras = 1 AND tp53 = 0) AS b,
    COUNTIF(kras = 0 AND tp53 = 1) AS c,
    COUNTIF(kras = 0 AND tp53 = 0) AS d
  FROM flags
)
SELECT
  SAFE_DIVIDE(
    (a + b + c + d) * POW(a * d - b * c, 2),
    (a + b) * (c + d) * (a + c) * (b + d)
  ) AS chi_squared
FROM counts