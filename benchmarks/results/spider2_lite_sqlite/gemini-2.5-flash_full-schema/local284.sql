WITH
  AvgLossRate AS (
    SELECT
      AVG("loss_rate_%") AS avg_lr
    FROM main.veg_loss_rate_df
  ),
  StdDevNumerator AS (
    SELECT
      SUM(POWER(T."loss_rate_%" - A.avg_lr, 2)) AS sum_sq_diff,
      COUNT(T."loss_rate_%") AS count_lr
    FROM main.veg_loss_rate_df AS T, AvgLossRate AS A
  ),
  Stats AS (
    SELECT
      A.avg_lr AS avg_loss_rate,
      CASE
        WHEN S.count_lr > 1
        THEN SQRT(S.sum_sq_diff / (S.count_lr - 1))
        ELSE 0.0
      END AS stddev_loss_rate
    FROM AvgLossRate AS A, StdDevNumerator AS S
  )
SELECT
  S.avg_loss_rate,
  SUM(
    CASE
      WHEN V."loss_rate_%" < (S.avg_loss_rate - S.stddev_loss_rate)
      THEN 1
      ELSE 0
    END
  ) AS below_avg_count,
  SUM(
    CASE
      WHEN V."loss_rate_%" BETWEEN (S.avg_loss_rate - S.stddev_loss_rate) AND (
        S.avg_loss_rate + S.stddev_loss_rate
      )
      THEN 1
      ELSE 0
    END
  ) AS within_avg_count,
  SUM(
    CASE
      WHEN V."loss_rate_%" > (S.avg_loss_rate + S.stddev_loss_rate)
      THEN 1
      ELSE 0
    END
  ) AS above_avg_count
FROM main.veg_loss_rate_df AS V,
  Stats AS S