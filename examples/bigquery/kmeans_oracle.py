"""k-means as an ORACLE, never as the detector.

STATUS, repeated because it matters: this is a SECOND detector, used as a point
of comparison. It does not replace the CLE's detector and it writes nothing. A
BigQuery clustering that quietly became the detector would be an architecture
change nobody decided.

The question it answers: do questions from the same 90-day window land in the
same cluster, or do clusters follow the user's technical stack regardless of
period? If a cluster gathers all of a user's `laravel` questions across years,
the recurrence signal in this corpus is vocabulary. If it gathers a window and
separates periods, it is intent.
"""
import sys, time
from google.cloud import bigquery

import bqconfig
P = bqconfig.dataset()
c = bigquery.Client(project=bqconfig.project())
KS = [int(x) for x in (sys.argv[1:] or ["16", "48"])]

for k in KS:
    t0 = time.perf_counter()
    j = c.query(f"""CREATE OR REPLACE MODEL `{P}.km_c_{k}`
        OPTIONS(model_type='kmeans', num_clusters={k}, distance_type='COSINE',
                standardize_features=FALSE) AS
        SELECT v FROM `{P}.r23_c_emb`""", location="EU")
    j.result()
    e = list(c.query(f"SELECT * FROM ML.EVALUATE(MODEL `{P}.km_c_{k}`)",
                     location="EU").result())[0]
    print(f"k={k:<4} davies_bouldin={e.davies_bouldin_index:.4f} "
          f"mean_sq_dist={e.mean_squared_distance:.4f} "
          f"{time.perf_counter()-t0:.0f}s {(j.total_bytes_billed or 0)/1e9:.3f}Go")
