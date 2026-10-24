SELECT DISTINCT t.start_position
FROM `bigquery-public-data.gnomAD.v2_1_1_genomes__chr17` AS t,
  UNNEST(t.alternate_bases) AS a,
  UNNEST(a.vep) AS v
WHERE t.reference_bases = 'C'
  AND a.alt = 'T'
  AND v.SYMBOL = 'BRCA1'
  AND v.Consequence LIKE '%missense_variant%'
ORDER BY t.start_position