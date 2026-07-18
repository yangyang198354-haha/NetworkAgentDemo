#!/bin/bash
# Simulator Test Suite Runner
# @author sub_agent_test_engineer
# Executes unit tests first, then E2E tests, reports results.
set -e

cd "$(dirname "$0")" || exit 1

echo "=========================================="
echo "=== Simulator Test Suite                ==="
echo "=========================================="

# Phase 1: Unit Tests (no e2e, no slow)
echo ""
echo "=== Phase 1: Unit Tests ==="
python -m pytest tests/test_simulator_state_manager.py \
                tests/test_simulator_ssh_server.py \
                tests/test_simulator_service.py \
                tests/test_simulator_lifecycle_manager.py \
                -v --tb=short -k "not slow" 2>&1
UNIT_EXIT=$?

echo ""
if [ $UNIT_EXIT -eq 0 ]; then
    echo "=== Unit Tests: ALL PASSED ==="
else
    echo "=== Unit Tests: FAILURES DETECTED (exit code $UNIT_EXIT) ==="
fi

# Phase 2: E2E Tests
echo ""
echo "=== Phase 2: E2E Tests ==="
python -m pytest tests/test_simulator_e2e.py \
                tests/test_simulator_tools_e2e.py \
                -v --tb=short 2>&1
E2E_EXIT=$?

echo ""
if [ $E2E_EXIT -eq 0 ]; then
    echo "=== E2E Tests: ALL PASSED ==="
else
    echo "=== E2E Tests: FAILURES DETECTED (exit code $E2E_EXIT) ==="
fi

echo ""
echo "=========================================="
if [ $UNIT_EXIT -eq 0 ] && [ $E2E_EXIT -eq 0 ]; then
    echo "=== ALL TESTS PASSED ==="
    exit 0
else
    echo "=== SOME TESTS FAILED ==="
    exit 1
fi
