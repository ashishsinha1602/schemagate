WITH cohort AS (
  SELECT DISTINCT RefNo, CaseNo
  FROM `mitelman-db.prod.Cytogen`
  WHERE Morph = '3111' AND Topo = '0401'
),
events AS (
  SELECT DISTINCT cc.RefNo, cc.CaseNo, cc.Chr, cc.Start, cc.End, LOWER(cc.Type) AS Type
  FROM `mitelman-db.prod.CytoConverted` cc
  JOIN cohort co ON co.RefNo = cc.RefNo AND co.CaseNo = cc.CaseNo
),
total AS (
  SELECT COUNT(DISTINCT CONCAT(CAST(RefNo AS STRING), '_', CaseNo)) AS n
  FROM events
)
SELECT
  b.chromosome,
  b.cytoband_name,
  b.hg38_start,
  b.hg38_stop,
  COUNT(DISTINCT IF(e.Type = 'amplification', CONCAT(CAST(e.RefNo AS STRING), '_', e.CaseNo), NULL)) AS amplification_count,
  ROUND(SAFE_DIVIDE(100 * COUNT(DISTINCT IF(e.Type = 'amplification', CONCAT(CAST(e.RefNo AS STRING), '_', e.CaseNo), NULL)), ANY_VALUE(t.n)), 2) AS amplification_pct,
  COUNT(DISTINCT IF(e.Type = 'gain', CONCAT(CAST(e.RefNo AS STRING), '_', e.CaseNo), NULL)) AS gain_count,
  ROUND(SAFE_DIVIDE(100 * COUNT(DISTINCT IF(e.Type = 'gain', CONCAT(CAST(e.RefNo AS STRING), '_', e.CaseNo), NULL)), ANY_VALUE(t.n)), 2) AS gain_pct,
  COUNT(DISTINCT IF(e.Type = 'loss', CONCAT(CAST(e.RefNo AS STRING), '_', e.CaseNo), NULL)) AS loss_count,
  ROUND(SAFE_DIVIDE(100 * COUNT(DISTINCT IF(e.Type = 'loss', CONCAT(CAST(e.RefNo AS STRING), '_', e.CaseNo), NULL)), ANY_VALUE(t.n)), 2) AS loss_pct,
  COUNT(DISTINCT IF(e.Type = 'homozygous loss', CONCAT(CAST(e.RefNo AS STRING), '_', e.CaseNo), NULL)) AS homozygous_deletion_count,
  ROUND(SAFE_DIVIDE(100 * COUNT(DISTINCT IF(e.Type = 'homozygous loss', CONCAT(CAST(e.RefNo AS STRING), '_', e.CaseNo), NULL)), ANY_VALUE(t.n)), 2) AS homozygous_deletion_pct
FROM `mitelman-db.prod.CytoBands_hg38` b
CROSS JOIN total t
LEFT JOIN events e
  ON e.Chr = b.chromosome
  AND e.Start < b.hg38_stop
  AND e.End > b.hg38_start
GROUP BY b.chromosome, b.cytoband_name, b.hg38_start, b.hg38_stop
ORDER BY
  CASE REPLACE(b.chromosome, 'chr', '')
    WHEN 'X' THEN 23
    WHEN 'Y' THEN 24
    ELSE SAFE_CAST(REPLACE(b.chromosome, 'chr', '') AS INT64)
  END,
  b.hg38_start,
  b.hg38_stop