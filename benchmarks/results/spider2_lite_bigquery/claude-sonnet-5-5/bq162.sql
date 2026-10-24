WITH l2 AS (
  SELECT DISTINCT Imaging_Assay_Type, HTAN_Data_File_ID
  FROM `isb-cgc-bq.HTAN_versioned.imaging_level2_metadata_r2`
  WHERE HTAN_Center = 'HTAN WUSTL'
    AND Component IS NOT NULL
    AND Component NOT LIKE '%Auxiliary%'
    AND Component NOT LIKE '%OtherAssay%'
    AND Imaging_Assay_Type IS NOT NULL
    AND LOWER(Imaging_Assay_Type) NOT LIKE '%electron%'
),
derived AS (
  SELECT DISTINCT
    l2.Imaging_Assay_Type,
    CASE
      WHEN p.Component LIKE '%Level3%' THEN 'Level3'
      WHEN p.Component LIKE '%Level4%' THEN 'Level4'
    END AS data_level
  FROM l2
  JOIN `isb-cgc-bq.HTAN_versioned.id_provenance_r4` p
    ON l2.HTAN_Data_File_ID IN UNNEST(SPLIT(REPLACE(p.HTAN_Parent_Data_File_ID, ' ', ''), ','))
  WHERE p.Component IS NOT NULL
    AND p.Component NOT LIKE '%Auxiliary%'
    AND p.Component NOT LIKE '%OtherAssay%'
    AND (p.Component LIKE '%Level3%' OR p.Component LIKE '%Level4%')
),
all_levels AS (
  SELECT DISTINCT Imaging_Assay_Type, 'Level2' AS data_level FROM l2
  UNION DISTINCT
  SELECT Imaging_Assay_Type, data_level FROM derived
)
SELECT
  Imaging_Assay_Type,
  STRING_AGG(data_level, ', ' ORDER BY data_level) AS available_data_levels
FROM all_levels
GROUP BY Imaging_Assay_Type
ORDER BY Imaging_Assay_Type