## Log line format (one per operation, JSON, single line)
```json
{"op":"build|run|switch|tag|revalidate|topology_write|...",
 "ts":"iso8601","actor":"human:<id>|engine:shadow|engine:live|engine:revalidator|system:<component>",
 "image":"<hash8>","from":"<state?>","to":"<state?>",
 "evidence":{...}|"pre_evidence":{...}|"persistence":{...},
 "latency_ms":n}
```
Upward tag moves REQUIRE `evidence`. Builds carry `pre_evidence`.
Re-validations carry `persistence`. Ops outside that family carry `op/ts/actor`
plus their own context keys - currently `closure_distribution`,
`cluster_stability`, `integrity_violation`, `detector_observing`,
`candidate_declined`, `revalidation_failed`.
A PR adding an operation without its log line is rejected.
