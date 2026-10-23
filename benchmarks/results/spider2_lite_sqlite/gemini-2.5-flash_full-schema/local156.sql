WITH TransactionDetails AS (
    SELECT
        strftime('%Y', bt.txn_date) AS txn_year,
        bm.region,
        bt.quantity,
        bp.price,
        (bt.quantity * bp.price) AS spent_amount
    FROM
        main.bitcoin_transactions AS bt
    JOIN
        main.bitcoin_members AS bm
        ON bt.member_id = bm.member_id
    JOIN
        main.bitcoin_prices AS bp
        ON bt.ticker = bp.ticker AND bt.txn_date = bp.market_date
    WHERE
        bt.txn_type = 'BUY'
),
AnnualRegionAggregates AS (
    SELECT
        txn_year,
        region,
        SUM(quantity) AS total_quantity,
        SUM(spent_amount) AS total_spent,
        SUM(spent_amount) * 1.0 / SUM(quantity) AS avg_purchase_price
    FROM
        TransactionDetails
    GROUP BY
        txn_year,
        region
),
RegionFirstYear AS (
    SELECT
        region,
        MIN(txn_year) AS first_year
    FROM
        AnnualRegionAggregates
    GROUP BY
        region
),
FilteredAnnualData AS (
    SELECT
        ara.txn_year,
        ara.region,
        ara.avg_purchase_price
    FROM
        AnnualRegionAggregates AS ara
    JOIN
        RegionFirstYear AS rfy
        ON ara.region = rfy.region
    WHERE
        ara.txn_year > rfy.first_year
),
RankedData AS (
    SELECT
        txn_year,
        region,
        avg_purchase_price,
        RANK() OVER (PARTITION BY txn_year ORDER BY avg_purchase_price ASC) AS region_rank,
        LAG(avg_purchase_price, 1) OVER (PARTITION BY region ORDER BY txn_year) AS previous_year_price
    FROM
        FilteredAnnualData
)
SELECT
    txn_year,
    region,
    avg_purchase_price,
    region_rank,
    CASE
        WHEN previous_year_price IS NULL OR previous_year_price = 0 THEN NULL
        ELSE ((avg_purchase_price - previous_year_price) * 100.0 / previous_year_price)
    END AS annual_percentage_change
FROM
    RankedData
ORDER BY
    txn_year,
    region_rank