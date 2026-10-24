WITH small AS (
  SELECT cmte_id, SUM(transaction_amt) AS total_small
  FROM `bigquery-public-data.fec.other_committee_tx_2016`
  WHERE entity_tp = 'IND'
    AND transaction_amt > 0
    AND transaction_amt < 200
  GROUP BY cmte_id
  HAVING SUM(transaction_amt) > 0
),
links AS (
  SELECT DISTINCT cmte_id, cand_id
  FROM `bigquery-public-data.fec.candidate_committee_2016`
  WHERE cand_id IS NOT NULL
),
cands AS (
  SELECT cand_id, MAX(cand_name) AS cand_name
  FROM `bigquery-public-data.fec.candidate_2016`
  GROUP BY cand_id
),
cm AS (
  SELECT cmte_id, MAX(cmte_nm) AS cmte_nm
  FROM `bigquery-public-data.fec.committee_2016`
  GROUP BY cmte_id
)
SELECT
  cm.cmte_nm AS committee_name,
  COUNT(DISTINCT l.cand_id) AS num_candidates_supported,
  STRING_AGG(DISTINCT c.cand_name, ', ' ORDER BY c.cand_name) AS candidate_names,
  s.total_small AS total_small_dollar_contributions
FROM small s
JOIN links l ON l.cmte_id = s.cmte_id
LEFT JOIN cands c ON c.cand_id = l.cand_id
LEFT JOIN cm ON cm.cmte_id = s.cmte_id
GROUP BY s.cmte_id, cm.cmte_nm, s.total_small