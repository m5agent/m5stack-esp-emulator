#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import unittest

from _docs_contract_support import DocsContractBase, ROOT, DOCS


class DocsNetworkWorkerContractTests(DocsContractBase):
    def test_ipv6_test_build_evidence_is_reconciled(self) -> None:
        evidence = json.loads(
            (
                ROOT
                / "tests/network/ipv6_end_to_end/"
                "evidence-2026-10-24-guest-ipv6-direct-test-build-pass.json"
            ).read_text()
        )
        patch = (
            ROOT
            / "tests/network/ipv6_end_to_end/"
            "uiflow2-sticks3-ipv6-test-build.patch"
        ).read_text()
        fixture_readme = (
            ROOT / "tests/network/ipv6_end_to_end/README.md"
        ).read_text()
        namespace_evidence = json.loads(
            (
                ROOT
                / "tests/network/ipv6_end_to_end/"
                "evidence-2026-10-25-ipv6-namespace-aaaa-http-pass.json"
            ).read_text()
        )
        status = (DOCS / "project-status.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        workstreams = (DOCS / "workstreams.md").read_text()
        validation_ledger = (DOCS / "validation-ledger.md").read_text()
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(evidence["scope"], "virtual-device-not-physical-rf")
        self.assertEqual(evidence["runtime"]["machine"], "m5sticks3")
        self.assertEqual(
            evidence["runtime"]["network"]["isolation"],
            "trusted-host",
        )
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(
            evidence["http_requests"],
            [{"path": "/ipv6", "host": "allowed.lab.test"}],
        )
        self.assertEqual(evidence["dns_requests"], [])
        destinations = evidence["pcap"]["destinations"]
        self.assertEqual(len(destinations), 1)
        self.assertEqual(destinations[0]["address"], "fec0::2")
        self.assertEqual(destinations[0]["port"], 18095)
        self.assertEqual(destinations[0]["scope"], "site-local")
        self.assertEqual(destinations[0]["protocols"], ["TCP"])
        self.assertEqual(destinations[0]["packets"], 6)
        test_build = evidence["test_build"]
        self.assertEqual(
            test_build["kind"],
            "uiflow2-sticks3-ipv6-linklocal",
        )
        self.assertEqual(
            test_build["patch_sha256"],
            "cfab27ea15065ad19617ab6671bc1f70c820953177a54bb58588ef5afd269514",
        )
        self.assertIn(
            "CONFIG_LWIP_IPV6_AUTOCONFIG=y",
            patch,
        )
        self.assertIn(
            "esp_netif_create_ip6_linklocal",
            patch,
        )
        self.assertIn("ports/esp32/modsocket.c", patch)
        self.assertIn("addrinfo_objs[4] = mp_obj_new_tuple(4", patch)
        self.assertIn("network_wlan_ip_event_handler", patch)
        self.assertIn("IPV6_WIFI_SCAN <redacted>", evidence["serial_tail"])
        self.assertNotRegex(
            json.dumps(evidence),
            r"\b[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}\b",
        )
        self.assertIn("stock StickS3 UIFlow2 image", fixture_readme)
        self.assertIn("controlled AAAA", fixture_readme)
        self.assertEqual(namespace_evidence["status"], "PASS")
        self.assertEqual(
            namespace_evidence["runtime"]["network"]["isolation"],
            "namespace",
        )
        self.assertTrue(
            all(value == "PASS" for value in namespace_evidence["checks"].values())
        )
        self.assertEqual(
            [item["port"] for item in namespace_evidence["pcap_destinations"]],
            [18095, 18096],
        )
        self.assertIn("测试构建", status)
        self.assertIn("原厂 UIFlow2", status)
        self.assertNotIn("NET-06", backlog)
        self.assertIn("同 guest IPv6 TCP/HTTP", workstreams)
        self.assertIn("NET-06", workstreams)
        self.assertIn(
            "evidence-2026-10-24-guest-ipv6-direct-test-build-pass.json",
            validation_ledger,
        )
        self.assertIn(
            "evidence-2026-10-25-ipv6-namespace-aaaa-http-pass.json",
            validation_ledger,
        )

    def test_worker_generation_pointer_migration_is_reconciled(self):
        status = (DOCS / "project-status.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        workstreams = (DOCS / "workstreams.md").read_text()
        ledger = (DOCS / "validation-ledger.md").read_text()
        api = (DOCS / "device-service-api.md").read_text()
        tls_readme = (
            ROOT / "tests/network/worker_tls/README.md"
        ).read_text()
        worker_code = (ROOT / "platform/tools/worker_agent.py").read_text()
        executor_readme = (
            ROOT / "tests/network/worker_executor/README.md"
        ).read_text()
        evidence = json.loads(
            (
                ROOT
                / "tests/network/worker_tls/"
                "evidence-2026-10-24-fleet-credential-migration-pass.json"
            ).read_text()
        )

        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(len(evidence["fleet"]["workers"]), 2)
        self.assertEqual(
            set(evidence["fleet"]["receipts"]),
            set(evidence["fleet"]["workers"]),
        )
        self.assertIsNone(evidence["rotation"]["worker_reload_signal"])
        self.assertEqual(
            evidence["rotation"]["worker_credential_commit"],
            "atomic-generation-pointer-replacement",
        )
        self.assertTrue(
            all(value == "PASS" for value in evidence["checks"].values())
        )

        for text in (status, backlog, workstreams, api, tls_readme):
            self.assertIn("generation", text.lower())
        self.assertIn("secret-free receipt", ledger)
        self.assertIn("cross-subnet/NAT unicast seed discovery", status)
        self.assertIn("active-token multicast discovery", status)
        self.assertIn(
            "--credential-generation-file",
            api,
        )
        self.assertIn(
            "run_fleet_migration_test.py",
            tls_readme,
        )
        self.assertIn("runtime_api", worker_code)
        self.assertIn("--runtime-service-url", worker_code)
        self.assertIn("--advertise-endpoint", worker_code)
        self.assertIn("--runtime-service-url", api)
        self.assertIn("control/execution URL split", executor_readme)
        self.assertIn("worker-local", status)
        self.assertIn("worker-local StickS3 QEMU", status)
        self.assertIn("本地 runtime API", workstreams)
        endpoint_evidence = json.loads(
            (
                ROOT
                / "tests/network/worker_cross_netns/"
                "evidence-2026-10-25-endpoint-advertisement-smoke.json"
            ).read_text()
        )
        self.assertEqual(endpoint_evidence["status"], "PASS")
        self.assertEqual(len(endpoint_evidence["checks"]), 14)
        self.assertTrue(
            endpoint_evidence["result"]["advertised_endpoint_present"]
        )
        worker_local_evidence = json.loads(
            (
                ROOT
                / "tests/network/worker_cross_netns/"
                "evidence-2026-10-25-worker-local-qemu-cross-netns-pass.json"
            ).read_text()
        )
        self.assertEqual(worker_local_evidence["status"], "PASS")
        self.assertEqual(len(worker_local_evidence["checks"]), 18)
        self.assertTrue(
            all(worker_local_evidence["checks"].values())
        )
        self.assertEqual(
            worker_local_evidence["result"]["execution_plane"],
            "worker-local",
        )
        self.assertIn(
            "cross-host QEMU execution",
            worker_local_evidence["not_claimed"],
        )
        self.assertIn("worker-local StickS3 QEMU", status)
        self.assertIn("worker-local QEMU", workstreams)
        self.assertIn("worker-local StickS3 QEMU", api)
        discovery_evidence = json.loads(
            (
                ROOT
                / "tests/network/worker_discovery/"
                "evidence-2026-10-25-discovery-rotation-pass.json"
            ).read_text()
        )
        self.assertEqual(discovery_evidence["status"], "PASS")
        self.assertEqual(len(discovery_evidence["checks"]), 17)
        self.assertTrue(all(discovery_evidence["checks"].values()))
        self.assertTrue(
            discovery_evidence["authentication"][
                "wrong_token_worker_registered"
            ]
            is False
        )
        self.assertTrue(
            discovery_evidence["authentication"][
                "old_token_worker_registered"
            ]
            is False
        )
        restart_evidence = json.loads(
            (
                ROOT
                / "tests/network/worker_control_restart/"
                "evidence-2026-10-25-central-restart-pass.json"
            ).read_text()
        )
        self.assertEqual(restart_evidence["status"], "PASS")
        self.assertEqual(len(restart_evidence["checks"]), 13)
        self.assertTrue(all(restart_evidence["checks"].values()))
        self.assertEqual(restart_evidence["job"]["status"], "completed")
        self.assertEqual(restart_evidence["job"]["result_state"], "PASS")
        initial_restart_failure = json.loads(
            (
                ROOT
                / "tests/network/worker_control_restart/"
                "evidence-2026-10-25-initial-runtime-qemu-failure.json"
            ).read_text()
        )
        self.assertEqual(initial_restart_failure["status"], "FAIL")
        self.assertIn(
            "cannot access local variable 'nic'",
            initial_restart_failure["failure"]["first_error"],
        )
        self.assertEqual(
            initial_restart_failure["root_cause_fix"]["successor_evidence"],
            "evidence-2026-10-25-central-restart-pass.json",
        )
        runtime_restart_evidence = json.loads(
            (
                ROOT
                / "tests/network/worker_runtime_restart/"
                "evidence-2026-10-25-runtime-restart-pass.json"
            ).read_text()
        )
        self.assertEqual(runtime_restart_evidence["status"], "PASS")
        self.assertEqual(len(runtime_restart_evidence["checks"]), 15)
        self.assertTrue(all(runtime_restart_evidence["checks"].values()))
        self.assertTrue(
            runtime_restart_evidence["runtime_restart"]["same_pid"]
        )
        self.assertTrue(
            runtime_restart_evidence["runtime_restart"][
                "reattached_process"
            ]
        )
        create_idempotency_evidence = json.loads(
            (
                ROOT
                / "tests/network/session_idempotency/"
                "evidence-2026-10-25-session-create-idempotency-pass.json"
            ).read_text()
        )
        self.assertEqual(create_idempotency_evidence["status"], "PASS")
        self.assertEqual(
            len(create_idempotency_evidence["checks"]),
            12,
        )
        self.assertTrue(
            all(create_idempotency_evidence["checks"].values())
        )
        self.assertEqual(
            create_idempotency_evidence["idempotency"]["session_count"],
            1,
        )
        self.assertEqual(
            create_idempotency_evidence["idempotency"]["conflict_status"],
            409,
        )
        self.assertIn("--control-reconnect-timeout", worker_code)
        self.assertIn("--runtime-reconnect-timeout", worker_code)
        self.assertIn("--control-reconnect-timeout", api)
        self.assertIn("--runtime-reconnect-timeout", api)
        openapi = (DOCS / "device-service.openapi.yaml").read_text()
        self.assertIn("WorkerJobStoredResult:", openapi)
        self.assertIn("lease_id:", openapi)
        self.assertIn("idempotency_key:", openapi)
        self.assertIn("idempotent_replay:", openapi)
        self.assertIn("claim_idempotency_key:", openapi)
        self.assertIn("claim_idempotent_replay:", openapi)
        self.assertIn("session_idempotency_conflict", api)

    def test_worker_claim_response_loss_idempotency(self):
        evidence = json.loads(
            (
                ROOT
                / "tests/network/worker_claim_idempotency/"
                "evidence-2026-10-29-worker-claim-idempotency-pass.json"
            ).read_text()
        )
        api = (DOCS / "device-service-api.md").read_text()
        openapi = (DOCS / "device-service.openapi.yaml").read_text()
        queue = (ROOT / "platform/tools/worker_queue.py").read_text()
        agent = (ROOT / "platform/tools/worker_agent.py").read_text()
        queue_tests = (
            ROOT / "platform/tests/test_worker_queue.py"
        ).read_text()
        agent_tests = (
            ROOT / "platform/tests/test_worker_agent.py"
        ).read_text()
        self.assertIn("claim_idempotency", queue)
        self.assertIn("claim_idempotency_conflict", queue)
        self.assertIn("claim_idempotency_stale", queue)
        self.assertIn("claim_idempotency_key", agent)
        self.assertIn(
            "test_claim_idempotency_replays_same_lease_across_restart",
            queue_tests,
        )
        self.assertIn("recovered_claim", agent_tests)
        self.assertIn("claim_idempotency_key:", openapi)
        self.assertIn("claim_idempotent_replay", openapi)
        self.assertIn("Empty no-job polls are not", api)
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(len(evidence["checks"]), 11)
        self.assertTrue(all(evidence["checks"].values()))
        self.assertTrue(evidence["service_restart"]["same_job"])
        self.assertTrue(evidence["service_restart"]["same_lease"])
        self.assertEqual(
            evidence["source_sha256"]["openapi"],
            "9027209dd5659d5845759638eb9d4ff212b700b5d2d8525199ffb27a4d0a1490",
        )

    def test_worker_lease_ownership_fencing_is_reconciled(self):
        status = (DOCS / "project-status.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        workstreams = (DOCS / "workstreams.md").read_text()
        ledger = (DOCS / "validation-ledger.md").read_text()
        api = (DOCS / "device-service-api.md").read_text()
        openapi = (DOCS / "device-service.openapi.yaml").read_text()
        agent = (ROOT / "platform/tools/worker_agent.py").read_text()
        queue = (ROOT / "platform/tools/worker_queue.py").read_text()
        agent_tests = (
            ROOT / "platform/tests/test_worker_agent.py"
        ).read_text()
        queue_tests = (
            ROOT / "platform/tests/test_worker_queue.py"
        ).read_text()
        service_tests = (
            ROOT / "platform/tests/test_device_service.py"
        ).read_text()

        self.assertIn("class WorkerLeaseLostError", agent)
        self.assertIn("lease_fence.wait(float(evidence_delay))", agent)
        self.assertIn("the stale result was not reported", agent)
        self.assertIn("job lease ownership changed", agent_tests)
        self.assertIn(
            "test_reclaimed_job_fences_the_previous_lease_result",
            queue_tests,
        )
        self.assertIn(
            "test_reclaimed_lease_rejects_the_previous_worker_result",
            service_tests,
        )
        self.assertIn("job_lease_mismatch", queue)
        for text in (status, backlog, workstreams, ledger, api):
            self.assertIn("fenc", text.lower())
        self.assertIn("job_lease_mismatch", api)
        self.assertIn("job_lease_mismatch", openapi)
        self.assertIn(
            "真实 QEMU PID reap",
            status,
        )
        self.assertIn("NOT RUN", ledger)

    def test_runtime_companion_continuity_is_reconciled(self):
        evidence = json.loads(
            (
                ROOT
                / "tests/network/worker_runtime_restart/"
                "evidence-2026-10-25-runtime-companion-continuity-pass.json"
            ).read_text()
        )
        status = (DOCS / "project-status.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        workstreams = (DOCS / "workstreams.md").read_text()
        ledger = (DOCS / "validation-ledger.md").read_text()
        code_map = (DOCS / "code-map.md").read_text()
        api = (DOCS / "device-service-api.md").read_text()
        openapi = (DOCS / "device-service.openapi.yaml").read_text()
        network_plan = (DOCS / "network-simulation-plan.md").read_text()

        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(len(evidence["checks"]), 26)
        self.assertTrue(all(evidence["checks"].values()))
        self.assertTrue(evidence["runtime_restart"]["same_pid"])
        self.assertEqual(
            evidence["runtime_restart"]["recovery_scope"],
            "qemu-control-plane+companions",
        )
        continuity = evidence["companion_continuity"]
        self.assertTrue(continuity["before_restart"]["ble_probe"]["required"])
        self.assertEqual(
            continuity["after_restart"]["http_fixture"]["generation"],
            2,
        )
        self.assertEqual(
            continuity["after_restart"]["ble_probe"]["state"],
            "adopted",
        )
        self.assertEqual(
            [
                request["fixture_generation"]
                for request in continuity["http_fixture_requests"]
            ],
            [1, 2],
        )
        self.assertTrue(continuity["ble_continuity_cycle_observed"])
        self.assertTrue(continuity["guest_http_recheck_observed"])
        self.assertEqual(continuity["network_evidence_status"], "PASS")
        self.assertEqual(
            evidence["firmware"]["sha256"],
            "04b008c60cf54d1e9fc52b8c9a1c2c4738a7ee046a64000779bebc8de9074c9d",
        )
        for text in (status, backlog, workstreams, code_map, api, network_plan):
            self.assertIn("companion", text.lower())
        self.assertIn("trusted-host", status)
        self.assertIn("generation 1", ledger)
        self.assertIn("generation 2", ledger)
        self.assertIn("qemu-control-plane+companions", api)
        self.assertIn("ble_post_pass_continuity", api)
        self.assertIn("ble_post_pass_continuity:", openapi)
        self.assertIn("CompanionState:", openapi)
        self.assertIn("evidence_delay_seconds", openapi)
        self.assertIn(
            "namespace-managed/Tab5/cross-host companion",
            backlog,
        )
        self.assertIn(
            "runtime-companion-continuity-pass.json",
            (DOCS / "validation-ledger.md").read_text(),
        )

    def test_controlled_dns_cname_lifecycle_is_reconciled(self) -> None:
        evidence = json.loads(
            (
                ROOT
                / "tests/network/dns_cname_chain/"
                "evidence-2026-10-25-controlled-cname-chain.json"
            ).read_text()
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(
            evidence["validation"],
            "resolver-data-plane validation",
        )
        self.assertTrue(evidence["checks"])
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(
            evidence["fixture"]["cname"],
            [
                "api.example.test -> edge.example.test",
                "edge.example.test -> origin.example.test",
            ],
        )
        self.assertTrue(evidence["checks"]["domain_suffix_terminal_resolves"])
        self.assertEqual(len(evidence["negative_cases"]), 5)
        self.assertIn(
            "guest firmware DNS lifecycle",
            evidence["not_claimed"],
        )
        guest_evidence = json.loads(
            (
                ROOT
                / "tests/network/cname_guest_lifecycle/"
                "evidence-2026-10-25-cname-guest-lifecycle-3x.json"
            ).read_text()
        )
        self.assertEqual(guest_evidence["status"], "PASS")
        self.assertEqual(
            guest_evidence["validation"],
            "virtual-device validation",
        )
        self.assertEqual(guest_evidence["runtime"]["lease_count"], 3)
        self.assertTrue(all(guest_evidence["checks"].values()))
        self.assertEqual(len(guest_evidence["runs"]), 3)
        self.assertEqual(
            len(
                {
                    run["session_id_sha256"]
                    for run in guest_evidence["runs"]
                }
            ),
            3,
        )
        self.assertEqual(
            len(
                {
                    run["evidence_zip_sha256"]
                    for run in guest_evidence["runs"]
                }
            ),
            3,
        )
        for run in guest_evidence["runs"]:
            self.assertEqual(run["status"], "PASS")
            self.assertTrue(run["cleanup"]["cleanup_completed"])
            self.assertTrue(run["cleanup"]["qemu_process_reaped"])
            self.assertTrue(run["cleanup"]["dns_closed"])
            self.assertTrue(run["cleanup"]["http_closed"])
        self.assertEqual(
            {
                failure["stage"]
                for failure in guest_evidence["diagnostic_failures"]
            },
            {
                "sandbox_dns_record_renormalization",
                "qemu_rom_directory_missing_machine_rom",
            },
        )
        status = (DOCS / "project-status.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        workstreams = (DOCS / "workstreams.md").read_text()
        code_map = (DOCS / "code-map.md").read_text()
        network_plan = (DOCS / "network-simulation-plan.md").read_text()
        network_index = (ROOT / "tests/network/README.md").read_text()
        api = (DOCS / "device-service-api.md").read_text()
        openapi = (DOCS / "device-service.openapi.yaml").read_text()
        ledger = (DOCS / "validation-ledger.md").read_text()
        for text in (
            status,
            workstreams,
            code_map,
            network_plan,
            network_index,
            api,
            openapi,
        ):
            self.assertIn("CNAME", text)
        self.assertNotIn("`NET-07`", backlog)
        self.assertNotIn("`NOT RUN` (`NET-07`)", api)
        self.assertIn("同 guest CNAME", status)
        self.assertIn("同 guest CNAME", network_plan)
        self.assertIn("cname_guest_lifecycle", network_index)
        self.assertIn("cname_guest_lifecycle", code_map)
        self.assertIn("cname-guest-lifecycle-3x.json", ledger)
        self.assertIn("cname_records:", openapi)
        self.assertIn("dns_requests:", openapi)
        self.assertIn("http_fixture_requests:", openapi)
        self.assertIn("isolation:", openapi)
        self.assertIn("dns_cname_chain", network_index)
        self.assertIn("controlled-cname-chain.json", ledger)
        sandbox = (ROOT / "platform/tools/network_sandbox.py").read_text()
        self.assertIn("MAX_CNAME_CHAIN = 8", sandbox)
        self.assertIn("def resolve_cname", sandbox)
        self.assertIn("conflicts with a domain suffix answer", sandbox)
        service = (ROOT / "platform/tools/device_service.py").read_text()
        network_service = (
            ROOT / "platform/tools/device_service_network.py"
        ).read_text()
        self.assertIn("from device_service_network import", service)
        self.assertIn("def parse_network_policy", network_service)
        self.assertIn("def parse_dns_cname_records", network_service)
        self.assertIn("validate_cname_record_bindings", network_service)
        self.assertIn("network_isolation_path", service)
        self.assertIn("termination_timeout = 20", service)
        self.assertIn("network/dns-requests.json", service)
        self.assertIn("network/http-fixture.json", service)
        self.assertIn("network/isolation.json", service)

    def test_cross_container_worker_qemu_is_reconciled(self) -> None:
        evidence = json.loads(
            (
                ROOT
                / "tests/network/worker_cross_container/"
                "evidence-2026-10-25-cross-container-qemu-3x.json"
            ).read_text()
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(
            evidence["validation"],
            "virtual-device validation",
        )
        self.assertEqual(evidence["environment"]["lease_count"], 3)
        self.assertTrue(evidence["checks"])
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(len(evidence["runs"]), 3)
        self.assertIn(
            "not-physical-hosts",
            evidence["scope"],
        )
        self.assertEqual(
            {
                failure["stage"]
                for failure in evidence["diagnostic_failures"]
            },
            {
                "central_service_unreachable_from_worker_container",
                "host_absolute_qemu_path_used_inside_container",
            },
        )
        self.assertIn(
            "physically separate hosts",
            evidence["not_claimed"],
        )
        status = (DOCS / "project-status.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        workstreams = (DOCS / "workstreams.md").read_text()
        code_map = (DOCS / "code-map.md").read_text()
        network_plan = (DOCS / "network-simulation-plan.md").read_text()
        network_index = (ROOT / "tests/network/README.md").read_text()
        ledger = (DOCS / "validation-ledger.md").read_text()
        for text in (
            status,
            workstreams,
            code_map,
            network_plan,
            network_index,
        ):
            self.assertIn("container", text.lower())
        self.assertIn("物理跨主机", status)
        self.assertIn("物理跨主机", backlog)
        self.assertIn("物理跨主机", workstreams)
        self.assertIn("`NET-04`", backlog)
        self.assertIn("worker_cross_container", network_index)
        self.assertIn("cross-container-qemu-3x.json", ledger)
        runner = (
            ROOT / "tests/network/worker_cross_container/run_test.py"
        ).read_text()
        self.assertIn('"network", "create"', runner)
        self.assertIn('"docker", "start", "-a"', runner)
        self.assertIn('"/workspace/" + inside_workspace', runner)
        self.assertIn('"HTTP_PROXY="', runner)
        dockerfile = (
            ROOT / "tests/network/worker_cross_container/Dockerfile"
        ).read_text()
        self.assertIn(
            "FROM ubuntu:25.04@sha256:",
            dockerfile,
        )
        self.assertIn("libcapstone5", dockerfile)

    def test_unicast_discovery_seed_is_reconciled(self) -> None:
        evidence = json.loads(
            (
                ROOT
                / "tests/network/worker_discovery_seed/"
                "evidence-2026-10-25-seed-nat-3x.json"
            ).read_text()
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(
            evidence["validation"],
            "virtual control-plane validation",
        )
        self.assertEqual(evidence["attempts_requested"], 3)
        self.assertEqual(evidence["attempts_completed"], 3)
        self.assertEqual(evidence["attempts_passed"], 3)
        self.assertEqual(len(evidence["checks_per_attempt"]), 23)
        self.assertTrue(
            all(
                status == "PASS"
                for status in evidence["checks_per_attempt"].values()
            )
        )
        self.assertTrue(evidence["input_assets_unchanged"])
        for name, relative in {
            "runner": (
                "tests/network/worker_discovery_seed/run_test.py"
            ),
            "worker_agent": "platform/tools/worker_agent.py",
            "worker_discovery": "platform/tools/worker_discovery.py",
            "worker_discovery_seed": (
                "platform/tools/worker_discovery_seed.py"
            ),
            "serve": "platform/tools/serve.py",
        }.items():
            self._assert_recorded_tool_hash(
                "worker-recorded-unicast-discovery", relative,
                evidence["tool_hashes"][name],
            )
        runs = evidence["runs"]
        self.assertEqual(len(runs), 3)
        self.assertEqual(
            {run["control_observed_sources"][0] for run in runs},
            {"10.213.1.1"},
        )
        self.assertEqual(
            len({run["control_url"] for run in runs}),
            3,
        )
        for run in runs:
            self.assertEqual(
                run["workers"]["seed_bootstrap"],
                {"returncode": 0, "state": "stopped"},
            )
            self.assertEqual(
                run["cleanup"]["namespaces"],
                [],
            )
            self.assertFalse(run["cleanup"]["nftables_contains_table"])

        worker_agent = (
            ROOT / "platform/tools/worker_agent.py"
        ).read_text()
        discovery = (
            ROOT / "platform/tools/worker_discovery.py"
        ).read_text()
        seed_server = (
            ROOT / "platform/tools/worker_discovery_seed.py"
        ).read_text()
        self.assertIn("--discover-control-seed-url", worker_agent)
        self.assertIn("fetch_discovery_beacon(", worker_agent)
        self.assertIn("_RejectDiscoveryRedirect", discovery)
        self.assertIn("unicast-seed", discovery)
        self.assertIn("Cache-Control", seed_server)
        self.assertIn("read_master_token_file", seed_server)

        status = (DOCS / "project-status.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        workstreams = (DOCS / "workstreams.md").read_text()
        handoff = (DOCS / "engineering-handoff.md").read_text()
        network_plan = (DOCS / "network-simulation-plan.md").read_text()
        architecture = (
            DOCS / "simulator-service-architecture.md"
        ).read_text()
        code_map = (DOCS / "code-map.md").read_text()
        ledger = (DOCS / "validation-ledger.md").read_text()
        tests_index = (ROOT / "tests/network/README.md").read_text()
        for text in (
            status,
            backlog,
            workstreams,
            handoff,
            network_plan,
            architecture,
            code_map,
            ledger,
            tests_index,
        ):
            self.assertIn("seed", text.lower())
        self.assertIn("3/3 PASS", ledger)
        self.assertIn("worker_discovery_seed", code_map)
        self.assertIn(
            "worker_discovery_seed/evidence-2026-10-25-seed-nat-3x.json",
            ledger,
        )
        self.assertIn(
            "--discover-control-seed-url",
            network_plan,
        )

    def test_worker_partition_side_effect_fencing_is_reconciled(self) -> None:
        evidence = json.loads(
            (
                ROOT
                / "tests/network/worker_partition_fencing/"
                "evidence-2026-10-25-partition-fencing-3x.json"
            ).read_text()
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(
            evidence["validation"],
            "virtual control-plane validation",
        )
        self.assertEqual(evidence["attempts_requested"], 3)
        self.assertEqual(evidence["attempts_completed"], 3)
        self.assertEqual(evidence["attempts_passed"], 3)
        self.assertEqual(len(evidence["checks_per_attempt"]), 18)
        self.assertTrue(
            all(
                value == "PASS"
                for value in evidence["checks_per_attempt"].values()
            )
        )
        self.assertTrue(evidence["input_assets_unchanged"])
        tool_paths = {
            "runner": (
                "tests/network/worker_partition_fencing/run_test.py"
            ),
            "runtime_fixture": (
                "tests/network/worker_partition_fencing/runtime_fixture.py"
            ),
            "worker_agent": "platform/tools/worker_agent.py",
            "device_service": "platform/tools/device_service.py",
            "serve": "platform/tools/serve.py",
        }
        for name in tool_paths:
            self.assertRegex(
                evidence["tool_hashes"][name],
                r"^[0-9a-f]{64}$",
            )
        self.assertEqual(len(evidence["runs"]), 3)
        for run in evidence["runs"]:
            self.assertEqual(run["attempts"], 2)
            self.assertEqual(run["result_state"], "PASS")
            self.assertNotEqual(run["first_worker_returncode"], 0)
            self.assertEqual(run["retry_worker_returncode"], 0)
            self.assertTrue(run["first_worker_lease_fenced"])
            self.assertTrue(run["first_side_effect_reaped"])
            self.assertTrue(run["retry_side_effect_reaped"])
            self.assertEqual(run["cleanup"]["namespaces"], [])

        qemu_evidence = json.loads(
            (
                ROOT
                / "tests/network/worker_partition_fencing/"
                "evidence-2026-10-25-partition-fencing-qemu-3x.json"
            ).read_text()
        )
        self.assertEqual(qemu_evidence["status"], "PASS")
        self.assertEqual(qemu_evidence["attempts_passed"], 3)
        self.assertEqual(len(qemu_evidence["checks_per_attempt"]), 18)
        self.assertEqual(
            qemu_evidence["checks_per_attempt"]["qemu_started"],
            "PASS",
        )
        self.assertEqual(
            qemu_evidence["tool_hashes"]["qemu"],
            "f024f034d20bd5b8e2c224ce69deed70984b0514f8a310d221b388b74c179ecb",
        )
        self.assertEqual(
            qemu_evidence["tool_hashes"]["firmware"],
            "c08196024019273ccadee9b4b3da303567f7ab206fa14edd1af283f04f6e98d8",
        )
        self.assertTrue(qemu_evidence["input_assets_unchanged"])
        self.assertEqual(len(qemu_evidence["runs"]), 3)
        for run in qemu_evidence["runs"]:
            self.assertEqual(run["runtime_kind"], "qemu")
            self.assertEqual(run["attempts"], 2)
            self.assertEqual(run["result_state"], "PASS")
            self.assertNotEqual(run["first_worker_returncode"], 0)
            self.assertEqual(run["retry_worker_returncode"], 0)
            self.assertTrue(run["first_side_effect_reaped"])
            self.assertTrue(run["retry_side_effect_reaped"])

        unified_evidence = json.loads(
            (
                ROOT
                / "tests/network/worker_partition_fencing/"
                "evidence-2026-10-25-partition-fencing-unified-3x.json"
            ).read_text()
        )
        self.assertEqual(unified_evidence["status"], "PASS")
        self.assertEqual(
            unified_evidence["validation"],
            "virtual control-plane + unified companion validation",
        )
        self.assertEqual(unified_evidence["attempts_passed"], 3)
        self.assertEqual(
            len(unified_evidence["checks_per_attempt"]),
            30,
        )
        self.assertTrue(
            all(
                status == "PASS"
                for status in unified_evidence[
                    "checks_per_attempt"
                ].values()
            )
        )
        self.assertTrue(unified_evidence["input_assets_unchanged"])
        self.assertTrue(unified_evidence["source_worktree_clean"])
        self.assertEqual(len(unified_evidence["runs"]), 3)
        for run in unified_evidence["runs"]:
            self.assertEqual(run["runtime_kind"], "qemu-unified")
            self.assertEqual(run["attempts"], 2)
            self.assertEqual(run["result_state"], "PASS")
            self.assertNotEqual(run["first_worker_returncode"], 0)
            self.assertEqual(run["retry_worker_returncode"], 0)
            self.assertTrue(run["first_worker_lease_fenced"])
            self.assertTrue(run["first_side_effect_reaped"])
            self.assertTrue(run["retry_side_effect_reaped"])
            self.assertEqual(
                run["companion_fencing"]["http_requests_before_fence"],
                1,
            )
            self.assertTrue(
                run["companion_fencing"]["ble_pass_before_fence"]
            )
            self.assertTrue(
                run["companion_fencing"]["ble_pid_reaped"]
            )
            self.assertGreater(
                run["companion_fencing"]["pcap_bytes_before_fence"],
                0,
            )
            self.assertEqual(
                run["companion_fencing"]["pcap_summary_after_fence"],
                "PASS",
            )
            self.assertEqual(
                run["companion_fencing"]["retry_pcap_summary"],
                "PASS",
            )

        worker_agent = (
            ROOT / "platform/tools/worker_agent.py"
        ).read_text()
        device_service = (
            ROOT / "platform/tools/device_service.py"
        ).read_text()
        unit_test = (
            ROOT / "platform/tests/test_worker_agent.py"
        ).read_text()
        partition_runner = (
            ROOT / "tests/network/worker_partition_fencing/run_test.py"
        ).read_text()
        self.assertIn(
            "operation: Callable[[float], Any]",
            worker_agent,
        )
        self.assertIn(
            "timeout=min(timeout, request_timeout)",
            worker_agent,
        )
        self.assertIn('M5_JOB_LEASE_SECONDS", "60"', device_service)
        self.assertIn(
            "test_transient_network_loss_is_time_bounded_and_fences_runtime",
            unit_test,
        )
        for fragment in (
            'qemu_mode.add_argument("--qemu"',
            '"--qemu-unified"',
            "upload_firmware(",
            "wait_qemu_started(",
            "wait_qemu_stopped(",
            "wait_unified_ready(",
            '"uiflow2-sticks3-unified"',
            '"capture_pcap": True',
            "unified_http_request_observed_before_partition",
            "unified_ble_pid_reaped",
            "retry_unified_pcap_finalized",
        ):
            self.assertIn(fragment, partition_runner)

        status = (DOCS / "project-status.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        workstreams = (DOCS / "workstreams.md").read_text()
        handoff = (DOCS / "engineering-handoff.md").read_text()
        network_plan = (DOCS / "network-simulation-plan.md").read_text()
        architecture = (
            DOCS / "simulator-service-architecture.md"
        ).read_text()
        code_map = (DOCS / "code-map.md").read_text()
        ledger = (DOCS / "validation-ledger.md").read_text()
        tests_index = (ROOT / "tests/network/README.md").read_text()
        for text in (
            status,
            backlog,
            workstreams,
            handoff,
            network_plan,
            architecture,
            code_map,
            ledger,
            tests_index,
        ):
            self.assertIn("partition", text.lower())
        self.assertIn("worker_partition_fencing", code_map)
        self.assertIn(
            "worker_partition_fencing/evidence-"
            "2026-10-25-partition-fencing-3x.json",
            ledger,
        )
        self.assertIn(
            "worker_partition_fencing/evidence-"
            "2026-10-25-partition-fencing-qemu-3x.json",
            ledger,
        )
        self.assertIn(
            "worker_partition_fencing/evidence-"
            "2026-10-25-partition-fencing-unified-3x.json",
            ledger,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
