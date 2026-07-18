<file_header
  author_agent="sub_agent_test_engineer"
  project_name="NetworkAgentDemo"
  file_type="TEST_PLAN"
  phase="SIMULATOR_TESTING"
  version="0.1.0"
  status="APPROVED"
  created_utc="2026-07-18T08:50:00Z"
/>

# Simulator Testing -- Test Plan

## Test Strategy

- **Test Target**: 7 source modules under `src/simulator/` and `src/tools/simulator_*.py`
- **Test Scope**: Unit tests for 4 core modules + 3 tool modules; E2E tests for full SSH + tool interaction
- **Out of Scope**: Abstract base class tests (covered by `test_tools.py`), performance benchmarks, security penetration tests, code coverage reporting
- **Test Environment**: Windows 11, Python 3.12, pytest 9.0.1, paramiko 3.4.0
- **Coverage Targets**: Unit >= 80%, Integration >= 90%, E2E critical path 100%

## Testing Levels

| Level | Files | Count | Description |
|-------|-------|-------|-------------|
| UNIT | test_simulator_state_manager.py | 45 | DeviceStateManager, PortState dataclass |
| UNIT | test_simulator_ssh_server.py | 47 | SimulatorCLI command parser (no paramiko) |
| UNIT | test_simulator_service.py | 36 | HTTP management API endpoints |
| UNIT | test_simulator_lifecycle_manager.py | 16 | Port allocation, heartbeat, instance management |
| E2E  | test_simulator_e2e.py | 8 | Full SSH session: show commands, configure |
| E2E  | test_simulator_tools_e2e.py | 12 | DiagTool, ConfigTool, BackupTool against real process |

## Test Case Inventory

### test_simulator_state_manager.py (45 tests)

| TC-ID | US | AC | Level | Description |
|-------|----|----|-------|-------------|
| TC-UNIT-001 | US-ST-001 | AC-001-01 | UNIT | Init creates 8 ports (Gi0/1-Gi0/8) with correct defaults |
| TC-UNIT-002 | US-ST-001 | AC-001-02 | UNIT | PortState.effective_status(): enabled=True returns status |
| TC-UNIT-003 | US-ST-001 | AC-001-02 | UNIT | PortState.effective_status(): enabled=False returns "administratively down" |
| TC-UNIT-004 | US-ST-001 | AC-001-03 | UNIT | configure_port() shutdown: enabled=False, success=True |
| TC-UNIT-005 | US-ST-001 | AC-001-03 | UNIT | configure_port() no-shutdown: enabled=True |
| TC-UNIT-006 | US-ST-001 | AC-001-04 | UNIT | configure_port() set-vlan valid (20) |
| TC-UNIT-007 | US-ST-001 | AC-001-04 | UNIT | configure_port() set-vlan invalid (0, 4095, non-numeric) |
| TC-UNIT-008 | US-ST-001 | AC-001-05 | UNIT | get_running_config() contains hostname, interfaces, shutdown/no shutdown |
| TC-UNIT-009 | US-ST-001 | -- | UNIT | get_all_ports() returns 8 PortState objects |
| TC-UNIT-010 | US-ST-001 | -- | UNIT | get_port(name) returns PortState or None |
| TC-UNIT-011 | US-ST-001 | -- | UNIT | get_up_ports() returns only effective_status=="up" |
| TC-UNIT-012 | US-ST-001 | -- | UNIT | get_cpu() returns dict with cpu_5s/1m/5m, processes |
| TC-UNIT-013 | US-ST-001 | -- | UNIT | get_memory_io() returns memory + IO dict |
| TC-UNIT-014 | US-ST-001 | -- | UNIT | PortState.to_summary() returns correct shape |
| TC-UNIT-015 | US-ST-001 | -- | UNIT | PortState.to_detail() returns correct shape |

### test_simulator_ssh_server.py (47 tests)

| TC-ID | US | AC | Level | Description |
|-------|----|----|-------|-------------|
| TC-UNIT-016 | US-ST-002 | AC-002-01 | UNIT | show interface status: header + 8 port rows |
| TC-UNIT-017 | US-ST-002 | AC-002-02 | UNIT | configure terminal enters config mode; exit/end exits |
| TC-UNIT-018 | US-ST-002 | AC-002-03 | UNIT | interface command with case-mismatch error (D-ST-001) |
| TC-UNIT-019 | US-ST-002 | AC-002-04 | UNIT | show version, show processes cpu, show memory, show io |
| TC-UNIT-020 | US-ST-002 | AC-002-05 | UNIT | Unknown command returns error; invalid interface returns error |
| TC-UNIT-021 | US-ST-002 | -- | UNIT | show mac address-table, show logging |
| TC-UNIT-022 | US-ST-002 | -- | UNIT | show running-config via CLI |
| TC-UNIT-023 | US-ST-002 | -- | UNIT | Prompt transitions: user, config, interface |
| TC-UNIT-024 | US-ST-002 | -- | UNIT | Empty command, enable, help (?) commands |

### test_simulator_service.py (36 tests)

| TC-ID | US | AC | Level | Description |
|-------|----|----|-------|-------------|
| TC-UNIT-025 | US-ST-003 | AC-003-01 | UNIT | GET /health: status="ok", device_name, ssh_port, ssh_running, uptime |
| TC-UNIT-026 | US-ST-003 | AC-003-02 | UNIT | GET /ports: 8 ports, up_ports_detail |
| TC-UNIT-027 | US-ST-003 | AC-003-03 | UNIT | POST /ports/Gi0/1/config: shutdown success |
| TC-UNIT-028 | US-ST-003 | AC-003-04 | UNIT | GET /nonexistent: 404 error |
| TC-UNIT-029 | US-ST-003 | AC-003-05 | UNIT | OPTIONS: CORS headers |
| TC-UNIT-030 | US-ST-003 | -- | UNIT | GET /status: cpu, memory, io |
| TC-UNIT-031 | US-ST-003 | -- | UNIT | POST /shutdown: returns 200 + message |
| TC-UNIT-032 | US-ST-003 | -- | UNIT | 500 when state_manager is None |

### test_simulator_lifecycle_manager.py (16 tests)

| TC-ID | US | AC | Level | Description |
|-------|----|----|-------|-------------|
| TC-UNIT-033 | US-ST-004 | AC-004-01 | UNIT | allocate_ports() returns (2222, 9222) when empty |
| TC-UNIT-034 | US-ST-004 | AC-004-02 | UNIT | check_port_used(): free port returns False, occupied returns True |
| TC-UNIT-035 | US-ST-004 | AC-004-05 | UNIT | heartbeat(): to listening port returns (True, ms); closed returns (False, None) |
| TC-UNIT-036 | US-ST-004 | -- | UNIT | list_instances() empty; shutdown_all() safe on empty |
| TC-UNIT-037 | US-ST-004 | -- | UNIT | get_status() returns STOPPED for unknown id |

### test_simulator_e2e.py (8 tests)

| TC-ID | US | AC | Level | Description |
|-------|----|----|-------|-------------|
| TC-E2E-001 | US-ST-005 | AC-005-01 | E2E | SSH connect succeeds; show version returns expected output |
| TC-E2E-002 | US-ST-005 | AC-005-02 | E2E | show interface status returns 8 ports |
| TC-E2E-003 | US-ST-005 | AC-005-03 | E2E | show running-config contains interfaces |
| TC-E2E-004 | US-ST-005 | AC-005-04 | E2E | Disconnect and reconnect; simulator stays running |
| TC-E2E-005 | US-ST-005 | -- | E2E | show processes cpu, show memory via SSH |

### test_simulator_tools_e2e.py (12 tests)

| TC-ID | US | AC | Level | Description |
|-------|----|----|-------|-------------|
| TC-E2E-006 | US-ST-006 | AC-006-01 | E2E | DiagTool show version returns DiagResult(success=True) |
| TC-E2E-007 | US-ST-006 | AC-006-02 | E2E | DiagTool show processes cpu returns process list |
| TC-E2E-008 | US-ST-006 | AC-006-03 | E2E | ConfigTool handles shell error gracefully |
| TC-E2E-009 | US-ST-006 | AC-006-04 | E2E | BackupTool backup returns BackupResult with config |
| TC-E2E-010 | US-ST-006 | AC-006-05 | E2E | Rollback with invalid backup_id returns error |

## Non-Testable Items

| AC-ID / REQ-ID | Reason |
|----------------|--------|
| REQ-FUNC-017 (SimulatorSSHServer public API with paramiko) | Deferred per NFUNC-006: test CLI parser directly without paramiko |
| REQ-FUNC-023 (start_simulator/stop_simulator full lifecycle) | @pytest.mark.slow; requires actual subprocess; tested in E2E scope |
| AC-005-03 (interface configure via shell) | D-ST-003: shell channel closes prematurely; interface case mismatch (D-ST-001) |

## Known Source Defects Discovered

| Defect ID | Module | Description | Severity |
|-----------|--------|-------------|----------|
| D-ST-001 | ssh_server.py | SimulatorCLI lowercases interface names before get_port() lookup, but port dictionary keys are title-case ("Gi0/1"). Prevents entering interface sub-mode and breaks 'show interface <name>' detail. | High |
| D-ST-002 | ssh_server.py | SSH server hardcodes hostname as "Sim-SW-01" in check_channel_exec_request and check_channel_shell_request instead of using self._state.device_name. | Medium |
| D-ST-003 | ssh_server.py | invoke_shell() channels close prematurely ("Socket is closed") after one command. Shell-based operations (ConfigTool, BackupTool rollback) are unreliable. | High |

## Test Execution Order

1. Phase 1: Unit tests (no e2e, no slow) -- must achieve >=80% pass rate
2. Phase 2: E2E tests -- run after unit tests pass
3. Test runner: `run_simulator_tests.sh`
