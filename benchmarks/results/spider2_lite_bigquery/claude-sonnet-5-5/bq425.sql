SELECT molregno, trade_name, approval_date
FROM (
  SELECT
    s.molregno AS molregno,
    p.trade_name AS trade_name,
    p.approval_date AS approval_date,
    ROW_NUMBER() OVER (PARTITION BY s.molregno ORDER BY p.approval_date DESC) AS rn
  FROM `bigquery-public-data.ebi_chembl.molecule_synonyms_23` s
  JOIN `bigquery-public-data.ebi_chembl.research_companies_23` c
    ON s.res_stem_id = c.res_stem_id
  JOIN `bigquery-public-data.ebi_chembl.products_23` p
    ON UPPER(s.synonyms) = UPPER(p.trade_name)
  WHERE c.company = 'SanofiAventis'
)
WHERE rn = 1