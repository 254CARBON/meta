# Load & Scale Test Plan

Coordinates platform-wide load testing using the assets already checked into
the repository. The goal is to provide repeatable guidance for validating the
end-to-end stack after major contract or infrastructure changes.

## Existing Assets

- **Access Layer** – `access/performance/k6/*.js` (gateway + streaming smoke
  tests enforcing p95 latency budgets).
- **Analytics** – `analytics/performance/k6/curve_read_smoke.js` plus Kafka
  throughput harness in `analytics/performance/`.
- **Data Processing** – `data-processing/tests/load/k6_load_test.js` and
  `data-processing/scripts/run-performance-tests.sh` for pipeline stress.
- **ML Platform** – `ml/performance/benchmark.py` and supporting configs for
  embedding/search throughput.
- **Meta** – `meta/scripts/monitor_performance.py` to aggregate results and
  compare against historical baselines.

## Operating the Plan

1. **Provision**  
   - Start the unified dev stack via `make e2e-up` from repo root.  
   - Verify ClickHouse, Kafka, Redis, and gateway endpoints respond.

2. **Baseline Latency (Access)**  
   - Run `k6 run access/performance/k6/gateway_latency_smoke.js`.  
   - Run `k6 run access/performance/k6/streaming_latency_smoke.js`.  
   - Export results with `--summary-export` for later aggregation.

3. **Analytics Scenario & Curve Throughput**  
   - Execute `make -C analytics perf-smoke` to cover curve reads and Kafka
     producer throughput.  
   - For deeper analysis, use `analytics/performance/k6/curve_read_smoke.js`
     with higher VUs/duration.

4. **Data Processing Pipeline Load**  
   - Launch infra with `make -C data-processing start`.  
   - Run `k6 run data-processing/tests/load/k6_load_test.js` (or the shell
     wrapper under `scripts/`).  
   - Capture ClickHouse ingest lag metrics via Prometheus/Grafana.

5. **ML Inference & Indexing Scale**  
   - Execute `python ml/performance/benchmark.py --profile full` to stress
     embedding + search services.  
   - Optional: drive reindex pipeline via
     `ml/tests/integration/test_ml_pipeline.py` for regression guards.

6. **Aggregation & Reporting**  
   - Use `python meta/scripts/monitor_performance.py --component all` to collect
     latency/throughput snapshots.  
   - Store artefacts under `artifacts/` (already gitignored) for CI upload.

## Scheduling & Ownership

- **Trigger** – Nightly on `main` and during release candidates.  
- **Duration** – ~45 minutes end-to-end (dominated by data-processing + ML runs).  
- **Owner** – Platform Engineering; results posted to `#carbon-perf`.

## Next Steps

- Integrate the plan into CI once env spin-up time is acceptable (tracked in
  `infra/` roadmap).  
- Automate artefact collation with a meta `make perf-suite` target that chains
  the steps above and pushes summaries to object storage.
