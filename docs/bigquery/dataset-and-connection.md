## 2. Dataset and connection

```bash
export CLE_BQ_PROJECT=your-project
export CLE_BQ_DATASET=cle                # any name; the corpus tables live here
export CLE_BQ_REGION=eu                  # lowercase, as the connection path wants
export CLE_BQ_CONNECTION=vertex_eu       # created below

bq --location=EU mk --dataset "${CLE_BQ_PROJECT}:${CLE_BQ_DATASET}"

bq mk --connection --location=EU --project_id="${CLE_BQ_PROJECT}" \
      --connection_type=CLOUD_RESOURCE "${CLE_BQ_CONNECTION}"
```

The connection runs as its own service account, and that account, not you, is
what calls Vertex. Read its id and grant it Vertex AI User, or every
`ML.GENERATE_EMBEDDING` fails with a permission error that names the connection
rather than you:

```bash
SA=$(bq show --format=prettyjson --connection \
     "${CLE_BQ_PROJECT}.${CLE_BQ_REGION}.${CLE_BQ_CONNECTION}" \
     | uv run python -c 'import json,sys;print(json.load(sys.stdin)["cloudResource"]["serviceAccountId"])')

gcloud projects add-iam-policy-binding "${CLE_BQ_PROJECT}" \
  --member="serviceAccount:${SA}" --role=roles/aiplatform.user
```

Put the four variables in `.env` as well, so the scripts pick them up without an
export in every shell. `.env` is gitignored.
