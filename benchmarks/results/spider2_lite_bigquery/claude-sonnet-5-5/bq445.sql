WITH region AS (
  SELECT MIN(t.start_position) AS min_start, MAX(t.end_position) AS max_end
  FROM `bigquery-public-data.gnomAD.v2_1_1_genomes__chr17` AS t,
    UNNEST(t.alternate_bases) AS ab,
    UNNEST(ab.vep) AS v
  WHERE v.SYMBOL = 'BRCA1'
)
SELECT v.Protein_position
FROM `bigquery-public-data.gnomAD.v2_1_1_genomes__chr17` AS t,
  UNNEST(t.alternate_bases) AS ab,
  UNNEST(ab.vep) AS v,
  region AS r
WHERE t.start_position >= r.min_start
  AND t.end_position <= r.max_end
  AND v.Consequence LIKE '%missense_variant%'
  AND v.Protein_position IS NOT NULL
  AND v.Protein_position != ''
ORDER BY v.Protein_position ASC
LIMIT 1