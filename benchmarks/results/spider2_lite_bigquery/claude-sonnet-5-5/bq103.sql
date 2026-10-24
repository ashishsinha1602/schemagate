WITH variants AS (
  SELECT
    COUNT(*) AS num_variants,
    SUM((SELECT SUM(a.AC) FROM UNNEST(alternate_bases) AS a)) AS total_allele_count,
    SUM(AN) AS total_number_of_alleles
  FROM `bigquery-public-data.gnomAD.v3_genomes__chr1`
  WHERE start_position BETWEEN 55039447 AND 55064852
),
genes AS (
  SELECT ARRAY_AGG(DISTINCT vep.SYMBOL IGNORE NULLS) AS gene_symbols
  FROM `bigquery-public-data.gnomAD.v3_genomes__chr1` AS t,
    UNNEST(t.alternate_bases) AS a,
    UNNEST(a.vep) AS vep
  WHERE t.start_position BETWEEN 55039447 AND 55064852
)
SELECT
  v.num_variants,
  v.total_allele_count,
  v.total_number_of_alleles,
  g.gene_symbols,
  SAFE_DIVIDE(55064852 - 55039447, v.num_variants) AS mutation_density
FROM variants AS v
CROSS JOIN genes AS g