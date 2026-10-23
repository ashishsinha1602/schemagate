WITH btc_buy_transactions_with_price AS (
    SELECT
        bm.region,
        CAST(SUBSTR(bt.txn_date, 1, 4) AS INTEGER) AS year,
        bt.quantity,
        bp.price
    FROM
        main.bitcoin_transactions AS bt
    JOIN
        main.bitcoin_prices AS bp
        ON bt.ticker = bp.ticker AND bt.txn_date = bp.market_date
    JOIN
        main.bitcoin_members AS bm
        ON bt.member_id = bm.member_id
    WHERE
        bt.ticker = 'BTC' AND bt.txn_type = 'BUY'
),
annual_region_purchase_summary AS (
    SELECT
        region,
        year,
        SUM(quantity) AS total_quantity,
        SUM(quantity * price) AS total_cost,
        SUM(quantity * price) * 1.0 / SUM(quantity) AS avg_purchase_price
    FROM
        btc_buy_transactions_with_price
    GROUP BY
        region,
        year
    HAVING
        SUM(quantity) > 0
),
region_first_year AS (
    SELECT
        region,
        year,
        avg_purchase_price,
        MIN(year) OVER (PARTITION BY region) AS first_year_for_region
    FROM
        annual_region_purchase_summary
),
filtered_annual_data AS (
    SELECT
        region,
        year,
        avg_purchase_price
    FROM
        region_first_year
    WHERE
        year > first_year_for_region
),
ranked_and_lagged_data AS (
    SELECT
        region,
        year,
        avg_purchase_price,
        RANK() OVER (PARTITION BY year ORDER BY avg_purchase_price ASC) AS region_rank,
        LAG(avg_purchase_price, 1, NULL) OVER (PARTITION BY region ORDER BY year) AS prev_year_avg_purchase_price
    FROM
        filtered_annual_data
)
SELECT
    region,
    year,
    avg_purchase_price,
    region_rank,
    CASE
        WHEN prev_year_avg_purchase_price IS NOT NULL AND prev_year_avg_purchase_price != 0
        THEN (avg_purchase_price - prev_year_avg_purchase_price) * 100.0 / prev_year_avg_purchase_price
        ELSE NULL
    END AS annual_percentage_change
FROM
    ranked_and_lagged_data
ORDER BY
    year,
    region_rank