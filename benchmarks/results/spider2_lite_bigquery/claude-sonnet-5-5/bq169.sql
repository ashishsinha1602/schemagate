SELECT DISTINCT
  c13.RefNo,
  c13.CaseNo,
  c13.InvNo,
  c13.Clone,
  c13.ChrOrd AS Chr13_ChrOrd,
  c13.Start AS Chr13_Start,
  c13.End AS Chr13_End,
  c17.ChrOrd AS Chr17_ChrOrd,
  c17.Start AS Chr17_Start,
  c17.End AS Chr17_End,
  c11.ChrOrd AS Chr11_ChrOrd,
  c11.Start AS Chr11_Start,
  c11.End AS Chr11_End,
  k.CloneShort
FROM `mitelman-db.prod.CytoConverted` c13
JOIN `mitelman-db.prod.CytoConverted` c17
  ON c13.RefNo = c17.RefNo AND c13.CaseNo = c17.CaseNo AND c13.InvNo = c17.InvNo AND c13.Clone = c17.Clone
JOIN `mitelman-db.prod.CytoConverted` c11
  ON c13.RefNo = c11.RefNo AND c13.CaseNo = c11.CaseNo AND c13.InvNo = c11.InvNo AND c13.Clone = c11.Clone
JOIN `mitelman-db.prod.KaryClone` k
  ON k.RefNo = c13.RefNo AND k.CaseNo = c13.CaseNo AND k.InvNo = c13.InvNo AND k.CloneNo = c13.Clone
WHERE c13.ChrOrd = 13 AND c13.Type = 'Loss' AND c13.Start <= 48303751 AND c13.End >= 48481890
  AND c17.ChrOrd = 17 AND c17.Type = 'Loss' AND c17.Start <= 7668421 AND c17.End >= 7687490
  AND c11.ChrOrd = 11 AND c11.Type = 'Gain' AND c11.Start <= 108223067 AND c11.End >= 108369102