SELECT County_of_Residence, AVG(Ave_Number_of_Prenatal_Wks) AS avg_prenatal_wks
FROM `bigquery-public-data.sdoh_cdc_wonder_natality.county_natality`
WHERE EXTRACT(YEAR FROM Year) = 2018
  AND County_of_Residence LIKE '%, WI'
GROUP BY County_of_Residence