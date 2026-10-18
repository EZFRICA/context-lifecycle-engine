## 1. What you need

* A Google Cloud project with billing enabled and the BigQuery API on.
* The **Vertex AI API** enabled in that project. The embedding benches call
  `ML.GENERATE_EMBEDDING`, which reaches Vertex through a connection.
* `gcloud` authenticated: `gcloud auth application-default login`.
* The measurement extras: `uv pip install -e ".[measure]"`.

Region matters and is not cosmetic. A US table is invisible to an EU query, and
the connection, the dataset and the models must agree. The published figures
were produced in **EU**; if you use another region, use it everywhere.
