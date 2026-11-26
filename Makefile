PYTHON ?= /opt/homebrew/bin/python3.12
.PHONY: doctor audit-images cluster-start cluster-stop sock-shop-deploy sock-shop-forward smoke dependencies monitoring-forward telemetry-check collector-forward gemini-probe rag-index ui qdrant-start collector-deploy observability-deploy chaos-install test dataset-plan dataset-test benchmark-check alert-test stability evaluate-pilot scenario-render scenario-validate-all review-queue admission-preview admission-apply
doctor:
	bash scripts/doctor.sh
audit-images:
	$(PYTHON) scripts/audit_images.py
cluster-start:
	bash scripts/start_cluster.sh
cluster-stop:
	bash scripts/stop_cluster.sh
sock-shop-deploy:
	bash scripts/deploy_sock_shop.sh
sock-shop-forward:
	bash scripts/port_forward.sh
smoke:
	$(PYTHON) traffic/run.py --profile checkout --journeys 2 --output results/environment/smoke-checkout.json
dependencies:
	bash scripts/check_dependencies.sh
monitoring-forward:
	bash scripts/forward_monitoring.sh
telemetry-check:
	$(PYTHON) scripts/verify_telemetry.py
collector-forward:
	bash scripts/forward_collector.sh
gemini-probe:
	.venv/bin/python scripts/gemini_probe.py
rag-index:
	.venv/bin/python scripts/index_knowledge.py
ui:
	bash scripts/run_ui.sh
qdrant-start:
	bash scripts/start_qdrant.sh
collector-deploy:
	bash scripts/deploy_collector.sh
observability-deploy:
	bash scripts/install_observability.sh
chaos-install:
	bash scripts/install_chaos.sh
test:
	.venv/bin/python -m unittest discover -s tests -v
dataset-plan:
	.venv/bin/python experiments/generate_plan.py
	.venv/bin/python experiments/audit_plan.py experiments/scenario-plan.json --output results/evaluation/scenario-plan-audit.json
stability:
	bash -c 'source scripts/common.sh; caffeinate -di .venv/bin/python scripts/check_stability.py --seconds 600'
evaluate-pilot:
	.venv/bin/python experiments/evaluate.py experiments/pilot-evaluation.json --output results/evaluation/pilot-B3.json
scenario-render:
	bash -c 'source scripts/common.sh; .venv/bin/python scripts/run_scenario.py --render-all --server-dry-run'
scenario-validate-all:
	bash -c 'source scripts/common.sh; .venv/bin/python scripts/run_scenario.py --render-all --server-dry-run-all'
dataset-test:
	.venv/bin/python scripts/test_dataset.py
alert-test:
	bash -c 'source scripts/common.sh; .venv/bin/python scripts/test_alert_rules.py'
baseline:
	.venv/bin/python scripts/run_baseline.py

benchmark-check:
	.venv/bin/python scripts/check_benchmark_readiness.py

review-queue:
	.venv/bin/python scripts/export_review_queue.py
admission-preview:
	.venv/bin/python scripts/apply_admission_batch.py
admission-apply:
	.venv/bin/python scripts/apply_admission_batch.py --apply
dataset-labels:
	.venv/bin/python scripts/export_dataset_labels.py
grafana-dashboard:
	bash scripts/deploy_grafana_dashboard.sh
case-memory-preview:
	.venv/bin/python scripts/index_case_memory.py
thesis:
	.venv/bin/python scripts/build_thesis_figures.py
	.venv/bin/python scripts/build_thesis_docx.py
