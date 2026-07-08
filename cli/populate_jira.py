import os
import sys
import json
import time
import hashlib
import requests
from dotenv import load_dotenv

# Ensure safe Windows UTF-8 stdout printing
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

DUMMY_INCIDENTS = [
    {
        "key": "CR-101",
        "summary": "MemoryPoolExhaustedException during stmt_gen_eod batch run on reporting node 04",
        "precursor_condition": "JVM Heap Overflow triggered by unpaged statement generation batch during overnight reconciliation runs (`stmt_gen_eod`).",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Increase JVM heap allocation to -Xmx16g on reporting node 04.\n2. Enable pagination chunking (`max_records=5000`) in application.yml.\n3. Restart stmt_gen service via `systemctl restart stmt_gen.service` and verify heap metrics in Grafana.",
        "escalation_owner": "stmt-engine-team"
    },
    {
        "key": "CR-102",
        "summary": "HikariPool-1 - Connection is not available, request timed out after 30000ms",
        "precursor_condition": "Database connection pool deadlock caused by long-running reporting queries locking table `account_ledger_partition_2026_07`.",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Terminate blocking PID on primary PostgreSQL node via `SELECT pg_terminate_backend(pid)` for idle in transaction queries.\n2. Flush HikariCP connection pool via JMX endpoint (`/actuator/hikari/pool/flush`).\n3. Scale read replica traffic weighting to 70% to offload EOD ledger scans.",
        "escalation_owner": "db-infra-team"
    },
    {
        "key": "CR-103",
        "summary": "KafkaConsumerRebalanceException: Commit cannot be completed due to group rebalance",
        "precursor_condition": "Consumer heartbeat timeout (`session.timeout.ms=10000`) breached during high-throughput market open message surge.",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Increase consumer `max.poll.interval.ms` to `300000` and reduce `max.poll.records` to `100`.\n2. Trigger rolling restart of `trade-ingestion-consumer` pods across US-East cluster.\n3. Verify consumer group lag drops below 500 records via Kafka Manager.",
        "escalation_owner": "messaging-core-team"
    },
    {
        "key": "CR-104",
        "summary": "RedisCacheEvictionSpike: Out of memory error when caching customer portfolio snapshots",
        "precursor_condition": "Eviction policy (`volatile-lru`) exhausted due to unexpiring cache keys written by legacy portfolio sync job.",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Execute targeted key purging script for legacy namespace (`portfolio:snapshot:legacy:*`).\n2. Set explicit TTL (`EXPIRE 3600`) on all portfolio cache write operations.\n3. Temporarily scale Redis cluster memory buffer by +25% via cloud console.",
        "escalation_owner": "cache-platform-team"
    },
    {
        "key": "CR-105",
        "summary": "FXRateServiceTimeout: 504 Gateway Timeout when fetching EOD currency settlement rates",
        "precursor_condition": "Upstream liquidity provider API (`Bloomberg LP FX Feed`) latency spike exceeding 5.0s circuit breaker threshold.",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Force failover to secondary FX pricing provider (`Refinitiv FX API`) by updating feature flag `use_secondary_fx_feed=true` in Consul.\n2. Clear local FX rate cache (`/api/v1/fx/cache/evict`).\n3. Re-run failed statement settlement jobs with `--retry-fx` flag.",
        "escalation_owner": "settlement-ops-team"
    },
    {
        "key": "CR-106",
        "summary": "SwiftPaymentGatewayError: ISO 20022 PACs.008 message validation rejected due to schema mismatch",
        "precursor_condition": "XML namespace validation failure caused by unexpected currency code formatting (`USD_EXT`) sent from upstream wire transfer interface.",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Apply schema transformation patch on SWIFT gateway gateway-router-config.xml.\n2. Re-queue rejected PACs.008 wire payloads in dead-letter queue (`swift.pac008.dlq`).\n3. Notify treasury settlement desk that wire processing has resumed.",
        "escalation_owner": "payments-core-team"
    },
    {
        "key": "CR-107",
        "summary": "OrderBookSynchronizationException: Crossed market state detected in NASDAQ equities feed",
        "precursor_condition": "Out-of-order UDP multicast packet sequence numbers during market open liquidity flash.",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Switch order book reconstruction engine to TCP replay buffer for sequence synchronization.\n2. Purge stale L2 order book snapshot in shared memory segment `/dev/shm/nasdaq_l2`.\n3. Verify bid-ask spreads normalize across all monitored symbols.",
        "escalation_owner": "equities-trading-team"
    },
    {
        "key": "CR-108",
        "summary": "ReconciliationLedgerDrift: Out of balance exception (+$1.42M) between core banking and settlement rails",
        "precursor_condition": "Orphaned debit transactions created during ungraceful failover of core accounting database replica.",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Execute automated ledger reconciliation reconciliation-repair tool `--mode=auto-match --threshold=5.00`.\n2. Generate exception report for pending unposted journal entries (`/var/log/ledger/drift_report.csv`).\n3. Submit adjusting entries for sign-off via dual-authorization portal.",
        "escalation_owner": "reconciliation-team"
    },
    {
        "key": "CR-109",
        "summary": "JWTAuthenticationExpired: Token signing key rotation failed on OAuth IDP cluster US-East",
        "precursor_condition": "Key management service (`HashiCorp Vault`) connection timeout during scheduled midnight RSA-4096 key pair rotation.",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Rollback IDP signing key ring to previous active key ID `kid-2026-07-v1` via Vault CLI.\n2. Flush API Gateway (`Kong/Apigee`) edge authentication cache across all regions.\n3. Schedule manual key rotation window during low-traffic maintenance slot.",
        "escalation_owner": "identity-auth-team"
    },
    {
        "key": "CR-110",
        "summary": "PostgresLockWaitTimeoutException: Deadlock found when trying to get lock on table customer_margin_account",
        "precursor_condition": "Concurrent batch updates (`margin_call_calc` vs `intraday_deposit_sweep`) acquiring row locks in reverse primary key order.",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Terminate conflicting transaction batch via `SELECT pg_cancel_backend(pid)` for `intraday_deposit_sweep`.\n2. Update batch job scheduling cron to enforce strict serialization between margin calls and deposit sweeps.\n3. Re-run aborted margin calculation batch.",
        "escalation_owner": "db-infra-team"
    },
    {
        "key": "CR-111",
        "summary": "ConsulServiceDiscoveryOutage: 503 Service Unavailable when resolving pricing-engine-grpc.consul",
        "precursor_condition": "Consul leader election storm triggered by network split between primary and disaster recovery data centers.",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Force Consul raft cluster leadership bootstrap via `consul operator raft remove-peer` on unreachable nodes.\n2. Verify local Consul agents re-register all microservices.\n3. Restart `pricing-engine-grpc` client connection pool across front-end web apps.",
        "escalation_owner": "platform-sre-team"
    },
    {
        "key": "CR-112",
        "summary": "ElasticsearchCircuitBreakerException: Data too large, data for [http_request] would be [15.2GB/15GB]",
        "precursor_condition": "Fielddata memory allocation exceeded due to unindexed wildcard aggregations executed by custom Kibana dashboard.",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Clear Elasticsearch fielddata cache via `POST /_cache/clear?fielddata=true`.\n2. Disable high-memory wildcard aggregation widget on `Production Security Monitoring` Kibana dashboard.\n3. Increase `indices.breaker.fielddata.limit` to `75%` temporarily.",
        "escalation_owner": "observability-team"
    },
    {
        "key": "CR-113",
        "summary": "RiskCalculationGridCrash: Value-at-Risk (VaR) Monte Carlo simulation worker pool OOM killed by Kubernetes",
        "precursor_condition": "Container memory limit (`8Gi`) exceeded when simulating 100,000 market paths for complex exotic derivative portfolios.",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Patch Kubernetes deployment `var-simulation-worker` with memory limit `16Gi` and CPU requests `8000m`.\n2. Enable batch partitioning (`paths_per_job=10000`) in risk simulation orchestrator.\n3. Re-submit failed EOD risk simulation batches.",
        "escalation_owner": "risk-grid-team"
    },
    {
        "key": "CR-114",
        "summary": "BatchJobTimeoutException: EOD corporate action dividend payout batch (`corp_action_div`) exceeded 120m SLA",
        "precursor_condition": "Slow cursor fetching over unindexed corporate action entitlements table (`entitlements_history_tbl`).",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Create composite index `idx_entitlements_lookup (security_id, ex_date, status)` on primary database.\n2. Increase Spring Batch chunk size from `100` to `2500` in `dividendBatchJob.xml`.\n3. Resume aborted batch execution from last committed step (`STEP_CALCULATE_NET_PAYOUT`).",
        "escalation_owner": "asset-servicing-team"
    },
    {
        "key": "CR-115",
        "summary": "SftpTransferFailureError: Connection reset by peer when pushing regulatory MiFID II transaction reports to FINRA",
        "precursor_condition": "Upstream SFTP gateway firewall drop due to exceeding concurrent SFTP channel limit (`MaxSessions=10`).",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Reconfigure SFTP transfer client to use single persistent multiplexed connection (`ControlMaster=yes`).\n2. Clear connection backlog in local outbound transmission queue.\n3. Trigger manual resend of pending MiFID II XML transaction files.",
        "escalation_owner": "regulatory-reporting-team"
    },
    {
        "key": "CR-116",
        "summary": "FIXProtocolLogoutEvent: Session sequence number gap detected (>1000 msgs) with CME Market Data Gateway",
        "precursor_condition": "Network link flap between matching engine colocation rack and CME direct feed during market surge.",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Send FIX `SequenceReset-Reset (MsgType=4)` with `GapFillFlag=Y` to resynchronize session state.\n2. Request historical message replay for gap window (`BeginSeqNo=40500`, `EndSeqNo=41500`).\n3. Verify heartbeat exchange (`MsgType=0`) resumes normally.",
        "escalation_owner": "exchange-connectivity-team"
    },
    {
        "key": "CR-117",
        "summary": "S3BucketWriteRateLimitExceeded: 503 Slow Down error during automated nightly trade repository cold archiving",
        "precursor_condition": "Amazon S3 prefix hotspot caused by writing 50,000 files/min to single sequential date prefix (`/archive/2026-07-08/`).",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Modify S3 key generation logic to prepend random 4-character hex hash (`/archive/a8f2/2026-07-08/`) to distribute request load across partitions.\n2. Enable exponential backoff retry handler (`max_retries=5`, `base_delay=500ms`) in archive writer.\n3. Resume cold archiving pipeline.",
        "escalation_owner": "cloud-storage-team"
    },
    {
        "key": "CR-118",
        "summary": "CollateralManagementServiceException: Margin call shortfall calculation returned NaN during volatility surge",
        "precursor_condition": "Zero-division exception inside derivative yield curve interpolation routine triggered by negative short-term interest rates.",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Deploy hotfix patch `collateral-engine-v1.4.2` handling zero and negative rate bounds during yield curve bootstrapping.\n2. Invalidate cached yield curves in collateral computation service.\n3. Re-run morning margin calculation run (`/api/v1/collateral/compute-all`).",
        "escalation_owner": "credit-risk-team"
    },
    {
        "key": "CR-119",
        "summary": "GrpcDeadlineExceeded: 4s RPC timeout calling account-balance-service from mobile banking API gateway",
        "precursor_condition": "Upstream account balance service thread starvation due to blocking synchronous core banking ledger balance checks.",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Switch gRPC client deadline from `4000ms` to `6000ms` during morning balance inquiry rush.\n2. Scale `account-balance-service` deployment replicas from `10` to `25`.\n3. Enable Redis read-through balance cache for non-transactional balance checks.",
        "escalation_owner": "mobile-backend-team"
    },
    {
        "key": "CR-120",
        "summary": "RabbitMqQueueFullException: High-priority fraud alerting queue (`fraud_score_v2`) reached 100,000 message high-water mark",
        "precursor_condition": "Downstream fraud scoring ML inference consumers stalled due to CUDA GPU memory leak after model reload.",
        "resolution_narrative": "[INCIDENT_INTELLIGENCE_KB_ENTRY] 1. Restart all GPU inference pods (`kubectl rollout restart deployment/fraud-ml-inference`).\n2. Temporarily increase RabbitMQ `x-max-length` policy on `fraud_score_v2` to `250,000` messages.\n3. Verify consumer acknowledgment rate (`ack/s`) exceeds ingestion rate until queue drains.",
        "escalation_owner": "fraud-prevention-team"
    }
]

def populate_local_kb_store():
    """Seeds data/kb_store.json with clean 2am P1 dummy resolutions (`EC-2.1`, `EC-4.2`)."""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)
    kb_path = os.path.join(data_dir, "kb_store.json")
    
    records = []
    now = time.time() - (86400 * 3) # Spread over past 3 days for weekly summary (`Step 4.3`)
    
    for idx, inc in enumerate(DUMMY_INCIDENTS):
        sig = inc["summary"].lower().split(":")[0].replace(" ", "_")[:40]
        narrative = inc["resolution_narrative"]
        content_hash = hashlib.sha256(f"{sig}_{inc['precursor_condition']}_{narrative}".encode('utf-8')).hexdigest()
        
        records.append({
            "kb_id": inc["key"],
            "alert_signature": inc["summary"],
            "precursor_condition": inc["precursor_condition"],
            "resolution_narrative": narrative,
            "escalation_owner": inc["escalation_owner"],
            "created_timestamp": now + (idx * 10000),
            "sync_status": "SYNCED",
            "content_hash": content_hash
        })
        
    with open(kb_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    print(f"[SUCCESS] Successfully seeded {len(records)} realistic P1 dummy incidents into local data/kb_store.json.")

def populate_atlassian_cloud():
    """
    Attempts to create issues on Atlassian Jira Cloud portal (`https://amanshende652.atlassian.net/`).
    Requires JIRA_USER_EMAIL and JIRA_API_TOKEN (or valid Atlassian Basic/Bearer Auth).
    """
    cloud_url = os.getenv("ATLASSIAN_CLOUD_URL", "https://amanshende652.atlassian.net/").rstrip("/")
    email = os.getenv("JIRA_USER_EMAIL", os.getenv("ATLASSIAN_USER_EMAIL", "amanshende652@gmail.com"))
    api_token = os.getenv("JIRA_API_TOKEN", os.getenv("ATLASSIAN_CLIENT_SECRET", ""))
    project_key = os.getenv("JIRA_PROJECT_KEYS", "CR").split(",")[0].strip().replace('"', '')
    
    if not api_token or not email or not (api_token.startswith("ATATT") or api_token.startswith("AT")) or len(api_token) < 40:
        print("\n[INFO] Atlassian Cloud Direct Portal Sync Skipped (Missing/Invalid ATATT API Token).")
        return

    url = f"{cloud_url}/rest/api/3/issue"
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    auth = (email, api_token)
    
    print(f"\n[INFO] Attempting to create {len(DUMMY_INCIDENTS)} dummy issues on Atlassian Cloud [{cloud_url}] in project [{project_key}] as [{email}]...")
    
    success_count = 0
    for inc in DUMMY_INCIDENTS:
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": inc["summary"],
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": f"Precursor Condition: {inc['precursor_condition']}\n\n"},
                                {"type": "text", "text": inc["resolution_narrative"]}
                            ]
                        }
                    ]
                },
                "issuetype": {"name": "Support Issue"}
            }
        }
        try:
            res = requests.post(url, json=payload, auth=auth, headers=headers, timeout=10)
            if res.status_code in (201, 200):
                data = res.json()
                print(f"  [SUCCESS] Created Jira Cloud Issue: {data.get('key')} -> {inc['summary'][:55]}...")
                success_count += 1
            else:
                print(f"  [ERROR] Failed to create [{inc['summary'][:40]}...]: HTTP {res.status_code} - {res.text[:150]}")
        except Exception as e:
            print(f"  [ERROR] Network error connecting to Atlassian Cloud: {e}")
            break
            
    if success_count > 0:
        print(f"\n[SUCCESS] Successfully created {success_count} dummy issues directly on your Atlassian Jira Portal ({cloud_url})!")

if __name__ == "__main__":
    populate_local_kb_store()
    populate_atlassian_cloud()
