SELECT
  AVG(c.coloc_log2_h4_h3) AS avg_log2_h4_h3,
  VARIANCE(c.coloc_log2_h4_h3) AS variance_log2_h4_h3,
  MAX(c.coloc_log2_h4_h3) - MIN(c.coloc_log2_h4_h3) AS max_min_diff,
  ARRAY_AGG(c.right_study ORDER BY c.coloc_log2_h4_h3 DESC LIMIT 1)[OFFSET(0)] AS qtl_source_of_max
FROM `open-targets-genetics.genetics.variant_disease_coloc` c
WHERE c.right_gene_id = 'ENSG00000169174'
  AND c.coloc_h4 > 0.8
  AND c.coloc_h3 < 0.02
  AND c.left_study IN (
    SELECT DISTINCT d.study_id
    FROM `open-targets-genetics.genetics.variant_disease` d
    WHERE d.trait_reported LIKE '%lesterol levels%'
  )
  AND c.right_bio_feature = 'IPSC'
  AND c.left_chrom = '1'
  AND c.left_pos = 55029009
  AND c.left_ref = 'C'
  AND c.left_alt = 'T'