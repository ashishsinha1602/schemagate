WITH
  LossRateStats AS (
    SELECT
      AVG([loss_rate_%]) AS avg_loss_rate,
      SQRT(AVG([loss_rate_%] * [loss_rate_%]) - (AVG([loss_rate_%])) * (AVG([loss_rate_%]))) AS stddev_loss_rate
    FROM main.veg_loss_rate_df
  )
SELECT
  lrs.avg_loss_rate AS average_loss_rate,
  SUM(
    CASE
      WHEN vlr.[loss_rate_%] < (lrs.avg_loss_rate - lrs.stddev_loss_rate)
      THEN 1
      ELSE 0
    END
  ) AS count_below_one_stddev,
  SUM(
    CASE
      WHEN vlr.[loss_rate_%] > (lrs.avg_loss_rate + lrs.stddev_loss_rate)
      THEN 1
      ELSE 0
    END
  ) AS count_above_one_stddev,
  SUM(
    CASE
      WHEN vlr.[loss_rate_%] >= (lrs.avg_loss_rate - lrs.stddev_loss_rate)
      AND vlr.[loss_rate_%] <= (lrs.avg_loss_rate + lrs.stddev_loss_rate)
      THEN 1
      ELSE 0
    END
  ) AS count_within_one_stddev
FROM main.veg_loss_rate_df AS vlr
CROSS JOIN LossRateStats AS lrs