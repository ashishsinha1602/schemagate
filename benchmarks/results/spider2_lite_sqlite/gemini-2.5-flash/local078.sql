WITH InterestMaxComposition AS (
    SELECT
        im.interest_name,
        imi.month_year,
        imi.composition,
        ROW_NUMBER() OVER (PARTITION BY im.id ORDER BY imi.composition DESC, imi.month_year ASC) as rn_per_interest
    FROM main.interest_metrics AS imi
    JOIN main.interest_map AS im
        ON imi.interest_id = im.id
),
FilteredMaxComposition AS (
    SELECT
        interest_name,
        month_year,
        composition
    FROM InterestMaxComposition
    WHERE rn_per_interest = 1
),
RankedOverall AS (
    SELECT
        interest_name,
        month_year,
        composition,
        RANK() OVER (ORDER BY composition DESC) as rnk_desc,
        RANK() OVER (ORDER BY composition ASC) as rnk_asc
    FROM FilteredMaxComposition
)
SELECT
    month_year,
    interest_name,
    composition
FROM RankedOverall
WHERE rnk_desc <= 10 OR rnk_asc <= 10
ORDER BY composition DESC