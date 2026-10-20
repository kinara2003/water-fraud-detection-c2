# NWSDB WaterGuard (Component 2) -- Final University Submission Index

**Project Title:** AI-Driven Network-Level Water Theft & Fraud Surveillance Engine under Intermittent Water Supply (IWS)  
**Utility Partner:** National Water Supply and Drainage Board (NWSDB), Western Production Division, Sri Lanka  
**Pilot Study Zone:** Kaduwela Distribution Scheme (DMA 01: Industrial/Commercial Corridor & DMA 02: Residential Control)  
**Academic Degree:** Master of Science / Postgraduate Research Defense  
**Core Innovation:** First hybrid physics-informed machine learning surveillance platform designed specifically for intermittent municipal water distribution networks in the Global South.

---

## 1. Evaluator's Navigation Map & Directory Architecture

```
water_fraud_c2/
├── app/                                 # Production FastAPI Backend & Telemetry Server
│   ├── main.py                          # REST API routes, WebSocket /ws/telemetry, Exception Handlers
│   ├── models.py                        # Pydantic v2 schemas for telemetry, risk scores, and audit records
│   └── config.py                        # Centralized application environment configurations
│
├── src/                                 # Core Analytical & Machine Learning Engine
│   ├── features.py                      # Physics-guided hydraulic feature engineering & spatial gradients
│   ├── scorer.py                        # 100-point multi-criteria fraud risk engine & IWS refill filter
│   ├── pipeline.py                      # Two-stage inference pipeline (Isolation Forest + Random Forest)
│   ├── scenario_runner.py               # 4-phase physical scenario generator (Baseline, Refill, Theft, C1)
│   ├── benchmark_models.py              # Comparative benchmark evaluator (Models A, B, C, D)
│   ├── edge_gateway_sim.py              # Edge gateway simulator with deadband filtering & SQLite buffer
│   ├── resilience_tester.py             # Degraded IoT network simulator (packet loss, latency, stuck sensor)
│   ├── audit_logger.py                  # Immutable field inspection audit ledger & live PPV tracker
│   └── export_network_geojson.py        # WGS84 GIS GeoJSON exporter (3,904 junctions & 4,279 pipes)
│
├── frontend/                            # Decision-Support Operator Dashboard (React 18 + TypeScript + Vite)
│   ├── src/
│   │   ├── pages/
│   │   │   ├── NetworkOverview.tsx      # Macro DMA surveillance, Leaflet GIS map, real-time pressure curves
│   │   │   ├── ZoneAnalysis.tsx         # Hydraulic residual profiles, spatial delta, sensor health chips
│   │   │   ├── EdgeGatewayMonitor.tsx   # Edge gateway battery, RSSI, deadband suppression, buffer status
│   │   │   ├── ModelDiagnostics.tsx     # Confusion matrix, ROC/PR curves, feature importance ranking
│   │   │   └── AlertInvestigation.tsx   # Evidence checklist, Google Maps dispatch, inspector audit verification
│   │   ├── services/
│   │   │   ├── api.ts                   # Axios REST client with mock fallback capability
│   │   │   └── telemetrySocket.ts       # Resilient reconnecting WebSocket hook (ws://localhost:8000/ws/telemetry)
│   │   └── App.tsx                      # Main routing, telemetry polling, and theme container
│   ├── public/data/                     # WGS84 GeoJSON layers (kaduwela_junctions.geojson, kaduwela_pipes.geojson)
│   ├── Dockerfile                       # Multi-stage Dockerfile (Node 20 build -> Nginx static serving)
│   └── package.json                     # Vite, React 18, Leaflet, Lucide icons, Recharts dependencies
│
├── data/
│   ├── networks/
│   │   └── kaduwela_2dma_clean_East_side.inp # Calibrated EPANET 2.2 / WNTR hydraulic digital twin model
│   └── processed/
│       ├── training_features.csv        # Synthesized and calibrated hydraulic feature training dataset
│       ├── evaluation_metrics.csv       # Multiclass precision, recall, F1, and false positive rate tables
│       ├── kaduwela_nodes_geo.json      # WGS84 geodetic lookup table with landmark metadata
│       └── field_inspections_ledger.json# Immutable field verification audit trail with live PPV
│
├── models/
│   ├── isolation_forest.joblib          # Stage 1: Unsupervised hydraulic departure detector
│   ├── random_forest.joblib             # Stage 2: Supervised root-cause classifier (Bypass vs. Leak)
│   └── random_forest_v2.joblib          # Calibrated secondary root-cause model
│
├── reports/
│   ├── Component2_Viva_Presentation.pptx # 12-slide widescreen oral viva defense presentation deck
│   ├── EXECUTIVE_DEFENSE_SUMMARY.md     # Consolidated executive summary with methodology & metrics
│   ├── model_comparison_benchmark.csv   # Quantitative comparison across 4 paradigms (Models A, B, C, D)
│   ├── resilience_benchmark.md          # Telemetry packet loss & sensor freeze benchmark report
│   └── figures/                         # High-resolution 300 DPI publication charts
│       ├── fig1_iws_refill_vs_theft.png # Panel comparison: 06:00 refill transient vs. 0.06 LPS bypass
│       ├── fig2_spatial_delta_dma.png   # Differential spatial gradient between DMA 01 and DMA 02
│       ├── fig3_roc_pr_curves.png       # Receiver Operating Characteristic & Precision-Recall curves
│       ├── fig4_feature_importance.png  # Random Forest Gini feature importances (>75% residual/spatial)
│       ├── confusion_matrix.png         # Multiclass confusion matrix (Normal, Leak, Partial Bypass)
│       └── model_benchmark_comparison.png# Comparative bar chart across Models A, B, C, D
│
├── scripts/
│   ├── generate_slides.py               # Automated 12-slide python-pptx presentation deck generator
│   ├── prepare_viva_package.py          # Prerequisite validator & viva package assembler
│   ├── run_viva_rehearsal.py            # Automated 2-minute live rehearsal script with performance grading
│   ├── backup_and_restore.py            # Automated application state backup, hash verification & restore engine
│   ├── backup_and_restore.bat           # Windows Command Prompt / PowerShell wrapper
│   ├── backup_and_restore.sh            # POSIX Bash / Linux / macOS wrapper
│   └── package_final_submission.py      # University final submission packaging script
│
├── tests/                               # 83 Unit and Integration Pytest Test Suites
│   ├── test_pipeline.py                 # Pipeline feature extraction and risk scoring tests
│   ├── test_benchmark_models.py         # Comparative benchmark evaluation tests
│   ├── test_edge_gateway.py             # Deadband, SQLite buffer, and battery telemetry tests
│   ├── test_resilience_tester.py        # Packet loss imputation and stuck sensor tests
│   ├── test_audit_logger.py             # Inspection ledger and PPV calculation tests
│   ├── test_slide_generator.py          # 12-slide presentation deck validation tests
│   ├── test_backup_and_restore.py       # Backup archive, checksum, and pickle validation tests
│   ├── test_viva_package.py             # Viva package assembly verification tests
│   ├── test_viva_rehearsal.py           # 4-phase demonstration rehearsal verification tests
│   ├── test_websocket_stream.py         # Real-time WebSocket connection and broadcast tests
│   ├── test_geo_converter.py            # Coordinates translation and WGS84 validation tests
│   └── test_export_network_geojson.py   # GeoJSON generation and topology tests
│
├── verify_full_system.py                # Automated 5/5 end-to-end full platform sanity check
├── Dockerfile.backend                   # Python 3.11-slim production backend container
├── docker-compose.yml                   # Multi-container orchestration (FastAPI backend + Vite/React frontend)
├── RESEARCH_DEFENSE.md                  # Comprehensive academic research monograph
├── VIVA_PREP.md                         # Viva examination questions & high-scoring answers guide
├── DEFENSE_FAQ.md                       # Detailed technical defense monograph addressing 6 examiner questions
├── requirements.txt                     # Pinned Python dependencies
└── SUBMISSION_INDEX.md                  # This file
```

---

## 2. Key Academic & Operational Highlights

### A. Core Mathematical Formulation
The feature vector $\mathbf{x}_i(t) \in \mathbb{R}^6$ transforms raw SCADA telemetry into physics-guided hydraulic deficit features:
$$\mathbf{x}_i(t) = \left[ P_{\text{act}, i}(t),\, \Delta P_i(t),\, \frac{dP_i}{dt},\, \mu_{\Delta P, i}(t),\, \sigma_{\Delta P, i}(t),\, \delta_{\text{spatial}, i}(t) \right]$$

- **Hydraulic Residual:** $\Delta P_i(t) = P_{\text{exp}, i}(t) - P_{\text{act}, i}(t)$ (head deficit relative to the EPANET digital twin).
- **Spatial Gradient Mismatch:** $\delta_{\text{spatial}, i}(t) = \Delta P_i(t) - \frac{1}{|\mathcal{N}_i|} \sum_{j \in \mathcal{N}_i} \Delta P_j(t)$ (isolates local off-takes from widespread diurnal demand swings).
- **Transient Rate of Change:** $\frac{dP_i}{dt}$ (discriminates sudden valve openings from gradual reservoir head decline).

### B. 100-Point Multi-Criteria Fraud Risk Engine
Implemented in [`src/scorer.py`](file:///c:/Users/kinara%20sadasi/OneDrive/Desktop/water_fraud_c2/src/scorer.py):
$$\text{Risk Score} = S_{\text{anomaly}} (20\text{ pts}) + S_{\text{severity}} (25\text{ pts}) + S_{\text{persistence}} (15\text{ pts}) + S_{\text{confidence}} (25\text{ pts}) + S_{\text{spatial}} (15\text{ pts})$$

- **IWS Refill Dampening Filter:** When distribution mains re-pressurize at $06:00\text{ AM}$, friction surges cause head losses exceeding $8.0\text{ m}$. The dampening filter caps scores to $\le 40\%$ during the initial 60 minutes, suppressing false alarms while preserving sensitivity if persistence and localized spatial mismatch are confirmed.

### C. Quantitative Benchmark Performance

| Metric | Model A (Static Rule) | Model B (Single SVM) | Model C (Deep MLP) | Model D (Proposed Two-Stage) |
| :--- | :---: | :---: | :---: | :---: |
| **Precision (Bypass)** | $0.9500$ | $\mathbf{1.0000}$ | $\mathbf{1.0000}$ | $0.8944$ |
| **Recall (Bypass)** | $0.0266$ | $0.0266$ | $0.0266$ | $\mathbf{0.6886}$ |
| **F1-Score (Bypass)** | $0.0518$ | $0.0519$ | $0.0519$ | $\mathbf{0.7781}$ |
| **Overall Accuracy** | $0.3906$ | $0.3298$ | $0.3911$ | $\mathbf{0.7743}$ |
| **Refill Transient FPR** | $51.37\%$ | $87.67\%$ | $68.49\%$ | $\mathbf{0.0\% \text{ (100% reduction)}}$ |
| **Inference Latency** | $\mathbf{0.0002\text{ ms}}$ | $0.2718\text{ ms}$ | $0.0012\text{ ms}$ | $\mathbf{0.0088\text{ ms (sub-millisecond)}}$ |

---

## 3. Cross-Component Interoperability Contracts

| Partner Component | Contract Endpoint | Data Exchange & Operational Synchronization |
| :--- | :--- | :--- |
| **Component 1 (Acoustic Leaks)** | `POST /api/v1/c1-leak-feedback` | Ingests acoustic correlation scores ($P_{\text{leak}} > 0.70$). Suppresses fraud risk by $40\%-80\%$, preventing false accusations and redirecting dispatches to pipe repair clamp squads. |
| **Component 3 (Storage Forecasting)** | `GET /api/v1/c3-water-loss/{zone}` | Translates detected head loss into volumetric water loss rate ($0.06\text{ LPS} \approx 1,892\text{ m}^3/\text{year}$). Feeds municipal storage reservoir depletion curves and pumping schedules. |
| **Component 4 (Water Quality Intrusion)** | `GET /api/v1/c4-pressure-drop-events` | Monitors severe depressurization ($\Delta P \ge 5.0\text{ m}$) creating negative gauge pressure back-siphonage risk, alerting water quality teams for immediate pathogen sampling. |

---

## 4. Key Quickstart Commands for Evaluators

### A. Run System Sanity Verification (5/5 Modules)
```bash
python verify_full_system.py
```

### B. Run Complete Pytest Suite (83 Tests)
```bash
pytest tests/ -v
```

### C. Run 2-Minute Live Viva Rehearsal
```bash
python scripts/run_viva_rehearsal.py
```

### D. Generate 12-Slide Viva Presentation Deck
```bash
python scripts/generate_slides.py
```

### E. Launch Full-Stack System via Docker Compose
```bash
docker compose up --build
```
- **Operator Dashboard:** [http://localhost:5173](http://localhost:5173)
- **FastAPI OpenAPI Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **WebSocket Streaming Endpoint:** `ws://localhost:8000/ws/telemetry`

---

## 5. Defense & Documentation Reference Library

1. **[`RESEARCH_DEFENSE.md`](file:///c:/Users/kinara%20sadasi/OneDrive/Desktop/water_fraud_c2/RESEARCH_DEFENSE.md)**: Academic technical monograph detailing the hydraulic digital twin formulation, Wagner PDD equations, and evaluation benchmarks.
2. **[`VIVA_PREP.md`](file:///c:/Users/kinara%20sadasi/OneDrive/Desktop/water_fraud_c2/VIVA_PREP.md)**: Comprehensive viva defense guide covering high-scoring answers to core examiner questions.
3. **[`DEFENSE_FAQ.md`](file:///c:/Users/kinara%20sadasi/OneDrive/Desktop/water_fraud_c2/DEFENSE_FAQ.md)**: Detailed technical defense answering 6 critical examiner questions (industrial draw vs. theft, $0.02\text{ LPS}$ physical limit, Hazen-Williams degradation, Random Forest vs. DBSCAN, post-meter plumbing, privacy safeguards).
4. **[`reports/EXECUTIVE_DEFENSE_SUMMARY.md`](file:///c:/Users/kinara%20sadasi/OneDrive/Desktop/water_fraud_c2/reports/EXECUTIVE_DEFENSE_SUMMARY.md)**: Executive summary detailing NWSDB business ROI and engineering impacts.
