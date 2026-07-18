<file_header
  author_agent="sub_agent_requirement_analyst"
  project_name="NetworkAgentDemo"
  file_type="STORIES"
  phase="SIMULATOR_TESTING"
  version="0.1.0"
  status="APPROVED"
  created_utc="2026-07-18T00:00:00Z"
/>

# Simulator Testing User Stories

## 用户角色地图（Actor x Feature Matrix）

| Actor | Port & State | CLI Commands | HTTP Mgmt API | Lifecycle | SSH E2E | Tools E2E | Test Script |
|-------|-------------|-------------|---------------|-----------|---------|-----------|-------------|
| QA Engineer | US-ST-001 | US-ST-002 | US-ST-003 | US-ST-004 | US-ST-005 | US-ST-006 | US-ST-007 |
| CI Pipeline | US-ST-001 | US-ST-002 | -- | -- | -- | -- | US-ST-007 |

---

## 用户故事详情

---

### US-ST-001: Port State Management Unit Testing

- **用户故事**：As a QA Engineer, I want to run comprehensive unit tests against the `DeviceStateManager` and `PortState` classes, so that I can verify port initialization, state queries, port configuration, system resource simulation, and running-config generation all work correctly in isolation.
- **关联需求**：REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-003, REQ-FUNC-004, REQ-FUNC-005, REQ-FUNC-006, REQ-FUNC-007, REQ-FUNC-008, REQ-FUNC-009, REQ-FUNC-010
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-001-01**
  - **Given** a fresh `DeviceStateManager` instance with device_name="Sim-SW-01"
  - **When** `get_all_ports()` is called
  - **Then** it returns exactly 8 `PortState` objects with names Gi0/1 through Gi0/8, and port Gi0/1 has status="up", vlan=1, description="Uplink to Core", while port Gi0/2 has status="down"

- **AC-001-02**
  - **Given** a `PortState` with enabled=True and status="up"
  - **When** `effective_status()` is called
  - **Then** it returns "up"
  - **When** `enabled` is changed to `False` and `effective_status()` is called again
  - **Then** it returns "administratively down"

- **AC-001-03**
  - **Given** a `DeviceStateManager` instance with all default ports
  - **When** `configure_port("Gi0/1", "shutdown")` is called
  - **Then** it returns `(True, "[OK] Gi0/1 disabled")` and port Gi0/1 has `enabled=False`
  - **When** `configure_port("Gi0/1", "no-shutdown")` is called
  - **Then** it returns `(True, "[OK] Gi0/1 enabled")` and port Gi0/1 has `enabled=True`

- **AC-001-04**
  - **Given** a `DeviceStateManager` instance
  - **When** `configure_port("Gi0/3", "set-vlan", "20")` is called
  - **Then** it returns `(True, "[OK] Gi0/3 switchport access vlan 20")` and `get_port("Gi0/3").vlan == 20`
  - **When** `configure_port("Gi0/3", "set-vlan", "5000")` is called
  - **Then** it returns `(False, message containing "超出范围 (1-4094)")`

- **AC-001-05**
  - **Given** a `DeviceStateManager` instance
  - **When** `get_running_config()` is called
  - **Then** the returned string contains "hostname Sim-SW-01", "interface Gi0/1" through "interface Gi0/8", and correctly shows "shutdown" for administratively down ports and "no shutdown" for enabled ports

---

### US-ST-002: CLI Command Parser Unit Testing

- **用户故事**：As a QA Engineer, I want to directly test the `SimulatorCLI` class without paramiko dependencies, so that I can verify all 27 CLI commands, mode transitions, and error handling logic are correct in pure unit test isolation.
- **关联需求**：REQ-FUNC-011, REQ-FUNC-012, REQ-FUNC-013, REQ-FUNC-014, REQ-FUNC-015, REQ-FUNC-016
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-002-01**
  - **Given** a `SimulatorCLI` instance backed by a fresh `DeviceStateManager`
  - **When** `execute("show interface status")` is called
  - **Then** the output contains a header row with "Port", "Name", "Status", "Vlan", "Duplex", "Speed", "Type" and exactly 8 port rows including Gi0/1 (up), Gi0/2 (down), Gi0/7 (notconnect), Gi0/8 (notconnect)

- **AC-002-02**
  - **Given** a `SimulatorCLI` instance in user EXEC mode
  - **When** `execute("configure terminal")` is called
  - **Then** the output is "Enter configuration commands, one per line. End with CNTL/Z." and `in_config_mode` is `True`
  - **When** `execute("exit")` is then called
  - **Then** `in_config_mode` is `False` and the prompt returns to `"Sim-SW-01> "`

- **AC-002-03**
  - **Given** a `SimulatorCLI` in config mode
  - **When** `execute("interface Gi0/1")` is called
  - **Then** `current_interface` is `"Gi0/1"` and the prompt is `"Sim-SW-01(config-if)# "`
  - **When** `execute("shutdown")` is called in this interface sub-mode
  - **Then** it returns `"[OK] Gi0/1 disabled"` and the state_manager's port Gi0/1 has `enabled=False`

- **AC-002-04**
  - **Given** a `SimulatorCLI` in user EXEC mode
  - **When** `execute("show version")` is called
  - **Then** the output contains "Cisco IOS Software, Simulator Version 17.9.0" and the hostname
  - **When** `execute("show processes cpu")` is called
  - **Then** the output contains "CPU utilization for five seconds:" with numerical percentages and a process table with columns PID, Runtime, Invoked, 5Sec, 1Min, 5Min, Process

- **AC-002-05**
  - **Given** a `SimulatorCLI` in user EXEC mode
  - **When** `execute("invalid command")` is called
  - **Then** it returns `"% Unknown command: invalid command"`
  - **When** `execute("interface Gi0/99")` is called in config mode
  - **Then** it returns `"% Invalid interface: Gi0/99"`

---

### US-ST-003: Simulator Service HTTP Management API Testing

- **用户故事**：As a QA Engineer, I want to run unit tests against the `SimulatorService` HTTP management API endpoints, so that I can verify health checks, status queries, port listing, port configuration, and graceful shutdown all return correct JSON responses.
- **关联需求**：REQ-FUNC-018, REQ-FUNC-019, REQ-FUNC-020
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-003-01**
  - **Given** a configured `SimulatorService` with a running SSH server on port 2222 and management API on port 9222
  - **When** an HTTP GET request is sent to `/health`
  - **Then** the response has HTTP status 200, Content-Type is `application/json`, and the body contains `"status": "ok"`, `"device_name": "Sim-SW-01"`, `"ssh_port": 2222`, `"ssh_running": true`, and a numeric `uptime_seconds`

- **AC-003-02**
  - **Given** a configured `SimulatorService`
  - **When** an HTTP GET request is sent to `/ports`
  - **Then** the response body contains a `ports` array with 8 entries (each with name, status, vlan, duplex, speed, type, description) and an `up_ports_detail` array containing only the up ports with detailed statistics (mac_address, mtu, bandwidth_kbps, input_packets, output_packets, etc.)

- **AC-003-03**
  - **Given** a configured `SimulatorService`
  - **When** an HTTP POST request is sent to `/ports/Gi0/1/config` with body `{"action": "shutdown"}`
  - **Then** the response has HTTP status 200 and body contains `"success": true`, `"port_name": "Gi0/1"`, `"action": "shutdown"`

- **AC-003-04**
  - **Given** a configured `SimulatorService`
  - **When** an HTTP GET request is sent to `/nonexistent`
  - **Then** the response has HTTP status 404 and body contains `"error": "not found"`

- **AC-003-05**
  - **Given** a configured `SimulatorService`
  - **When** an HTTP OPTIONS request is sent to any endpoint
  - **Then** the response has HTTP status 200, `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods` containing GET, POST, OPTIONS, and `Access-Control-Allow-Headers` containing Content-Type

---

### US-ST-004: Simulator Lifecycle Manager Unit Testing

- **用户故事**：As a QA Engineer, I want to run unit tests against `SimulatorLifecycleManager` for port allocation, process start/stop, heartbeat checks, and instance listing, so that I can verify the lifecycle management logic is correct before using it in E2E tests.
- **关联需求**：REQ-FUNC-021, REQ-FUNC-022, REQ-FUNC-023, REQ-FUNC-024
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-004-01**
  - **Given** a fresh `SimulatorLifecycleManager` with no running instances
  - **When** `allocate_ports()` is called
  - **Then** it returns `(2222, 9222)` — the default starting port pair

- **AC-004-02**
  - **Given** a port 2222 that is already bound by another process
  - **When** `check_port_used(2222)` is called
  - **Then** it returns `True`
  - **Given** a port 54321 that is unused
  - **When** `check_port_used(54321)` is called
  - **Then** it returns `False`

- **AC-004-03**
  - **Given** a fresh `SimulatorLifecycleManager`
  - **When** `start_simulator(device_id=1, device_name="Test-SW")` is called
  - **Then** it returns `(True, message, ssh_port, mgmt_port)` with ssh_port and mgmt_port being valid non-None integers, and `list_instances()` returns a list containing an entry with `device_id=1` and `running=True`

- **AC-004-04**
  - **Given** a running simulator with device_id=1
  - **When** `stop_simulator(device_id=1)` is called
  - **Then** it returns `(True, message)` and `list_instances()` returns an empty list, and the SSH/mgmt ports are released (verified by `check_port_used` returning False)

- **AC-004-05**
  - **Given** a running simulator SSH server on localhost:2222
  - **When** `heartbeat("127.0.0.1", 2222, timeout=3.0)` is called
  - **Then** it returns `(True, response_time_ms)` where response_time_ms is a positive float
  - **Given** no server on port 19999
  - **When** `heartbeat("127.0.0.1", 19999, timeout=1.0)` is called
  - **Then** it returns `(False, None)`

---

### US-ST-005: End-to-End SSH Session Testing

- **用户故事**：As a QA Engineer, I want to run an E2E test that starts a real simulator process, connects via SSH, executes diagnostic and configuration commands, and verifies the running-config reflects changes, so that I can confirm the full SSH interaction pipeline works end-to-end.
- **关联需求**：REQ-FUNC-025
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-005-01**
  - **Given** a simulator process started via `SimulatorLifecycleManager.start_simulator()` with device_id=100 and device_name="E2E-Test-SW"
  - **When** a paramiko SSHClient connects to `127.0.0.1:<ssh_port>` with valid credentials
  - **Then** the SSH connection succeeds and `exec_command("show version")` returns output containing "Simulator Version 17.9.0" and "E2E-Test-SW"

- **AC-005-02**
  - **Given** an active SSH connection to the simulator
  - **When** `exec_command("show interface status")` is executed
  - **Then** the output contains 8 port lines with correct status values for each port

- **AC-005-03**
  - **Given** an active SSH connection to the simulator
  - **When** configuration commands are sent via shell channel: "configure terminal", "hostname E2E-Changed", "interface Gi0/3", "shutdown", "end"
  - **Then** `exec_command("show running-config")` returns a config containing "hostname E2E-Changed" and "interface Gi0/3" followed by "shutdown"

- **AC-005-04**
  - **Given** an active SSH connection
  - **When** the SSH client disconnects cleanly
  - **Then** no exception is raised and the connection is closed
  - **And** the simulator process is still running (verified via heartbeat)

- **AC-005-05**
  - **Given** a running E2E test
  - **When** the test completes (pass or fail)
  - **Then** `stop_simulator(device_id=100)` is called in a teardown/finally block, and the process is fully terminated, and ports are released

---

### US-ST-006: End-to-End Simulator Tools Testing

- **用户故事**：As a QA Engineer, I want to run E2E tests that exercise `SimulatorDiagTool`, `SimulatorConfigTool`, and `SimulatorBackupTool` against a real running simulator process, so that I can verify the tool layer correctly integrates with the SSH server.
- **关联需求**：REQ-FUNC-026
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-006-01**
  - **Given** a running simulator process on port `<ssh_port>` with credentials admin/switch123
  - **When** `SimulatorDiagTool._run(device_ip="127.0.0.1", command="show version", auth=auth)` is called
  - **Then** it returns a `DiagResult` with `success=True`, `output` containing "Simulator Version 17.9.0", and `execution_time_ms` > 0

- **AC-006-02**
  - **Given** a running simulator process
  - **When** `SimulatorDiagTool._run(device_ip="127.0.0.1", command="show processes cpu", auth=auth)` is called
  - **Then** it returns `DiagResult(success=True)` with output containing "CPU utilization for five seconds:" and a process list

- **AC-006-03**
  - **Given** a running simulator process and a valid `DeviceAuth` with SSH port and credentials
  - **When** `SimulatorConfigTool._run(device_ip="127.0.0.1", commands=["hostname ConfigTest", "interface Gi0/5", "description E2E Test Port"], auth=auth)` is called
  - **Then** it returns a `ConfigResult` with `success=True`, `commands_executed=3`, `commands_failed=0`

- **AC-006-04**
  - **Given** a running simulator process
  - **When** `SimulatorBackupTool._do_backup(device_ip="127.0.0.1", auth=auth)` is called
  - **Then** it returns `BackupResult(success=True)` with a non-empty `backup_id` (UUID string) and `config` containing "hostname" and interface definitions

- **AC-006-05**
  - **Given** a successful backup with `backup_id=B1` from the simulator
  - **When** `SimulatorBackupTool._do_rollback(device_ip="127.0.0.1", backup_id=B1, auth=auth)` is called
  - **Then** it returns `RollbackResult(success=True)` with output confirming rollback
  - **When** rollback is attempted with an invalid `backup_id`
  - **Then** it returns `RollbackResult(success=False)` with an error about backup not found

---

### US-ST-007: Test Execution Script

- **用户故事**：As a CI Pipeline operator, I want a single shell script that orchestrates the full simulator test suite, so that I can run unit tests first, then E2E tests, and get a unified pass/fail result without manual intervention.
- **关联需求**：REQ-NFUNC-005
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-007-01**
  - **Given** the project workspace with all 6 test files present
  - **When** `run_simulator_tests.sh` is executed
  - **Then** it first runs `python -m pytest tests/test_simulator*.py -v --tb=short -k "not e2e and not slow"` and reports the unit test results

- **AC-007-02**
  - **Given** unit tests pass (exit code 0)
  - **When** the script proceeds to E2E test execution
  - **Then** it runs `python -m pytest tests/test_simulator*e2e*.py -v --tb=short` and reports the E2E test results

- **AC-007-03**
  - **Given** all tests pass
  - **When** the script completes
  - **Then** the exit code is 0 and the final output line summarizes "All X tests passed" or similar success message

- **AC-007-04**
  - **Given** any test step fails
  - **When** the script detects non-zero exit code
  - **Then** it prints the failing test details and exits with a non-zero status code, without proceeding (for unit test failures) or after reporting (for E2E failures) [INFERRED — requires PM confirmation on whether to stop on first failure or continue]

- **AC-007-05**
  - **Given** the script is run from the `project_workspace/` directory
  - **When** all test steps complete
  - **Then** no orphan simulator processes remain on the system (verified by checking that no processes listening on the test ports remain)
