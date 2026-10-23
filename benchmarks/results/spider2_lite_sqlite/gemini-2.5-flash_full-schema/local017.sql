WITH YearlyFactors AS (
  SELECT
    ci.db_year,
    c.primary_collision_factor,
    COUNT(*) AS factor_count
  FROM main.collisions AS c
  JOIN main.case_ids AS ci
    ON c.case_id = ci.case_id
  WHERE
    c.primary_collision_factor IS NOT NULL
  GROUP BY
    ci.db_year,
    c.primary_collision_factor
), RankedFactors AS (
  SELECT
    db_year,
    primary_collision_factor,
    factor_count,
    ROW_NUMBER() OVER (PARTITION BY db_year ORDER BY factor_count DESC, primary_collision_factor ASC) AS rnk
  FROM YearlyFactors
), TopTwoFactorsPerYear AS (
  SELECT
    db_year,
    primary_collision_factor
  FROM RankedFactors
  WHERE
    rnk <= 2
), YearlyFactorPairs AS (
  SELECT
    db_year,
    GROUP_CONCAT(primary_collision_factor ORDER BY primary_collision_factor) AS top_factors_pair
  FROM TopTwoFactorsPerYear
  GROUP BY
    db_year
)
SELECT
  yfp.db_year
FROM YearlyFactorPairs AS yfp
GROUP BY
  yfp.top_factors_pair
HAVING
  COUNT(yfp.db_year) = 1