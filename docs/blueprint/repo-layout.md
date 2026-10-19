## 2. Repo layout

```
cle/
  store/        # objects.py (content_hash, Block), commits.py (SourceSpec,
                # Image, TriggerSpec, evidence types), backends.py
                # (Protocol, InMemory, File, Sqlite, all local)
  detect/       # episodes.py (segmentation: silence + explicit markers for v1)
                # clusters.py (incremental intent clustering, per-user baseline)
                # embedders.py (Embedder impls + provenance + vector cache)
                # signals.py (reformulation vs recurrence classification)
                # stability.py (intra-cluster divergence classification)
  build/        # resolver.py, replay.py (validation stage), assembler.py
  runtime/      # container.py, mounts.py, metrics_volume.py
  lifecycle/    # tags.py, engine.py (shadow mode), topology.py, revalidator.py
                # reasons.py (the closed vocabulary, see 7b)
  batch_guard.py# guards against calls that return without working (see 8)
  cli/          # main.py (typer)
tests/          # property/ + unit/, hypothesis for invariants
```
