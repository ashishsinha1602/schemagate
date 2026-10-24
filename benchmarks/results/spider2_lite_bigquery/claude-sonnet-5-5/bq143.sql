WITH prot AS (
  SELECT DISTINCT m.sample_submitter_id, p.gene_symbol, p.protein_abundance_log2ratio
  FROM `isb-cgc-bq.CPTAC.quant_proteome_CPTAC_CCRCC_discovery_study_pdc_current` p
  JOIN `isb-cgc-bq.PDC_metadata.aliquot_to_case_mapping_current` m
    ON p.aliquot_id = m.aliquot_id
),
rna AS (
  SELECT sample_barcode, gene_name, sample_type_name, fpkm_unstranded
  FROM `isb-cgc-bq.CPTAC.RNAseq_hg38_gdc_current`
  WHERE project_short_name = 'CPTAC-3'
    AND primary_site = 'Kidney'
    AND sample_type_name IN ('Primary Tumor', 'Solid Tissue Normal')
),
joined AS (
  SELECT
    r.sample_type_name AS sample_type,
    p.gene_symbol,
    p.protein_abundance_log2ratio AS protein_abundance,
    LOG10(r.fpkm_unstranded + 1) AS log_fpkm
  FROM prot p
  JOIN rna r
    ON p.sample_submitter_id = r.sample_barcode
   AND p.gene_symbol = r.gene_name
),
gene_corr AS (
  SELECT sample_type, gene_symbol, CORR(protein_abundance, log_fpkm) AS correlation
  FROM joined
  GROUP BY sample_type, gene_symbol
)
SELECT sample_type, AVG(correlation) AS avg_correlation
FROM gene_corr
WHERE correlation IS NOT NULL AND ABS(correlation) > 0.5
GROUP BY sample_type