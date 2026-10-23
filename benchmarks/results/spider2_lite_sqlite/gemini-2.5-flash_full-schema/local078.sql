WITH MaxCompositionPerInterest AS (
    SELECT
        im.interest_id,
        im.month_year,
        im.composition,
        ROW_NUMBER() OVER (PARTITION BY im.interest_id ORDER BY im.composition DESC, im.month_year ASC) as rn
    FROM
        main.interest_metrics AS im
),
RankedInterests AS (
    SELECT
        mci.month_year,
        ima.interest_name,
        mci.composition,
        RANK() OVER (ORDER BY mci.composition DESC) as top_rank,
        RANK() OVER (ORDER BY mci.composition ASC) as bottom_rank
    FROM
        MaxCompositionPerInterest AS mci
    JOIN
        main.interest_map AS ima
    ON
        mci.interest_id = ima.id
    WHERE
        mci.rn = 1
)
SELECT
    month_year,
    interest_name,
    composition
FROM
    RankedInterests
WHERE
    top_rank <= 10
UNION ALL
SELECT
    month_year,
    interest_name,
    composition
FROM
    RankedInterests
WHERE
    bottom_rank <= 10
ORDER BY
    composition DESC