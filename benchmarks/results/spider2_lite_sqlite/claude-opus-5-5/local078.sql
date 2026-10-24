WITH maxcomp AS (
  SELECT
    m.month_year,
    m.interest_id,
    m.composition,
    ROW_NUMBER() OVER (PARTITION BY m.interest_id ORDER BY m.composition DESC) AS rn
  FROM interest_metrics m
  WHERE m.interest_id IS NOT NULL
    AND m.month_year IS NOT NULL
),
best AS (
  SELECT month_year, interest_id, composition
  FROM maxcomp
  WHERE rn = 1
),
ranked AS (
  SELECT
    b.*,
    RANK() OVER (ORDER BY b.composition DESC) AS top_rank,
    RANK() OVER (ORDER BY b.composition ASC) AS bottom_rank
  FROM best b
)
SELECT
  r.month_year AS time_mm_yyyy,
  im.interest_name,
  r.composition
FROM ranked r
JOIN interest_map im ON im.id = r.interest_id
WHERE r.top_rank <= 10
   OR r.bottom_rank <= 10
ORDER BY r.composition DESC