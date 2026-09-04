"""Corpus C — 90-day recurrence windows.

Sampling is EXPLICITLY random (`ORDER BY RAND()`), not `LIMIT` alone: a bare
LIMIT returns whatever the scan happens to reach first, which is a property of
storage layout, not of the population. The prior 21-user measurement was not
randomised.

Qualifying user = has at least MIN_Q questions inside some 90-day window. The
window itself is computed with a range window function rather than by
enumerating windows, so a user qualifies once and is sampled once.
"""
import sys
from google.cloud import bigquery

import bqconfig
DS = f"`{bqconfig.dataset()}`"
MIN_Q, USERS = 5, 300
DRY = "--dry" in sys.argv

Q = f"""
WITH q AS (
  SELECT id, owner_user_id, title, tags, creation_date
  FROM {DS}.posts_questions
  WHERE owner_user_id IS NOT NULL
),
windowed AS (
  SELECT owner_user_id, id,
         COUNT(*) OVER (
           PARTITION BY owner_user_id ORDER BY UNIX_SECONDS(creation_date)
           RANGE BETWEEN CURRENT ROW AND {90 * 24 * 3600} FOLLOWING
         ) AS in_window
  FROM q
),
qualifying AS (
  SELECT DISTINCT owner_user_id FROM windowed WHERE in_window >= {MIN_Q}
),
sampled AS (
  SELECT owner_user_id FROM qualifying ORDER BY RAND() LIMIT {USERS}
)
SELECT q.owner_user_id, q.id, q.title, q.tags, q.creation_date
FROM q JOIN sampled s USING (owner_user_id)
ORDER BY q.owner_user_id, q.creation_date
"""

c = bigquery.Client(project=bqconfig.project())
if DRY:
    j = c.query(Q, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
    print(f"corpus C dry-run : {j.total_bytes_processed/1e9:.2f} Go "
          f"(~${j.total_bytes_processed/1e12*6.25:.2f})")
    raise SystemExit
job = c.query(Q)
df = job.result().to_dataframe()
df.to_parquet("examples/bigquery/data/corpus_c_windows.parquet")
print(f"corpus C : {len(df):,} questions | {df.owner_user_id.nunique()} utilisateurs "
      f"| {job.total_bytes_billed/1e9:.2f} Go facturés")
