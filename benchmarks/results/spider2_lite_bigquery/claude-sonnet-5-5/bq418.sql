WITH targets AS (
  SELECT DISTINCT i.target_uniprotID AS uniprot_id
  FROM `isb-cgc-bq.targetome_versioned.interactions_v1` i
  JOIN `isb-cgc-bq.targetome_versioned.experiments_v1` e
    ON i.expID = e.expID
  WHERE LOWER(i.drugName) = 'sorafenib'
    AND i.targetSpecies = 'Homo sapiens'
    AND e.exp_assayValueMedian <= 100
    AND (e.exp_assayValueLow IS NULL OR e.exp_assayValueLow <= 100)
    AND (e.exp_assayValueHigh IS NULL OR e.exp_assayValueHigh <= 100)
    AND i.target_uniprotID IS NOT NULL
),
pairs AS (
  SELECT DISTINCT pe.uniprot_id, p.pathway_stable_id
  FROM `isb-cgc-bq.reactome_versioned.physical_entity_v77` pe
  JOIN `isb-cgc-bq.reactome_versioned.pe_to_pathway_v77` p
    ON pe.stable_id = p.pe_stable_id
  JOIN `isb-cgc-bq.reactome_versioned.pathway_v77` pw
    ON pw.stable_id = p.pathway_stable_id
  WHERE p.evidence_code = 'TAS'
    AND pw.lowest_level = TRUE
    AND pw.species = 'Homo sapiens'
    AND pe.uniprot_id IS NOT NULL
),
totals AS (
  SELECT
    COUNT(DISTINCT uniprot_id) AS n_total,
    COUNT(DISTINCT IF(uniprot_id IN (SELECT uniprot_id FROM targets), uniprot_id, NULL)) AS t_total
  FROM pairs
),
per_pw AS (
  SELECT
    pathway_stable_id,
    COUNT(DISTINCT uniprot_id) AS n_pw,
    COUNT(DISTINCT IF(uniprot_id IN (SELECT uniprot_id FROM targets), uniprot_id, NULL)) AS a
  FROM pairs
  GROUP BY pathway_stable_id
),
calc AS (
  SELECT
    pp.pathway_stable_id,
    pp.a AS targets_in_pathway,
    t.t_total - pp.a AS targets_outside_pathway,
    pp.n_pw - pp.a AS non_targets_in_pathway,
    t.n_total - t.t_total - (pp.n_pw - pp.a) AS non_targets_outside_pathway,
    t.n_total AS n_total
  FROM per_pw pp
  CROSS JOIN totals t
)
SELECT
  c.pathway_stable_id,
  pw.name,
  SAFE_DIVIDE(
    c.n_total * POW(c.targets_in_pathway * c.non_targets_outside_pathway - c.targets_outside_pathway * c.non_targets_in_pathway, 2),
    (c.targets_in_pathway + c.targets_outside_pathway) * (c.non_targets_in_pathway + c.non_targets_outside_pathway) * (c.targets_in_pathway + c.non_targets_in_pathway) * (c.targets_outside_pathway + c.non_targets_outside_pathway)
  ) AS chi_squared,
  c.targets_in_pathway,
  c.targets_outside_pathway,
  c.non_targets_in_pathway,
  c.non_targets_outside_pathway
FROM calc c
JOIN `isb-cgc-bq.reactome_versioned.pathway_v77` pw
  ON pw.stable_id = c.pathway_stable_id
WHERE SAFE_DIVIDE(
    c.n_total * POW(c.targets_in_pathway * c.non_targets_outside_pathway - c.targets_outside_pathway * c.non_targets_in_pathway, 2),
    (c.targets_in_pathway + c.targets_outside_pathway) * (c.non_targets_in_pathway + c.non_targets_outside_pathway) * (c.targets_in_pathway + c.non_targets_in_pathway) * (c.targets_outside_pathway + c.non_targets_outside_pathway)
  ) IS NOT NULL
ORDER BY chi_squared DESC
LIMIT 3