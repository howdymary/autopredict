#!/bin/bash

echo "======================================================================"
echo "AutoPredict Testing Infrastructure Verification"
echo "======================================================================"
echo ""

echo "1. Dataset Generation"
echo "----------------------------------------------------------------------"
echo "Checking generated datasets..."
if [ -f "datasets/sample_markets_100.json" ]; then
    echo "  ✓ 100-market dataset exists ($(wc -c < datasets/sample_markets_100.json) bytes)"
else
    echo "  ✗ 100-market dataset missing"
fi

if [ -f "datasets/sample_markets_500.json" ]; then
    echo "  ✓ 500-market dataset exists ($(wc -c < datasets/sample_markets_500.json) bytes)"
else
    echo "  ✗ 500-market dataset missing"
fi

if [ -f "datasets/test_markets_minimal.json" ]; then
    echo "  ✓ Minimal test dataset exists ($(wc -c < datasets/test_markets_minimal.json) bytes)"
else
    echo "  ✗ Minimal test dataset missing"
fi
echo ""

echo "2. Dataset Validation"
echo "----------------------------------------------------------------------"
echo "Validating 100-market dataset..."
python3 validation/validator.py datasets/sample_markets_100.json 2>&1 | grep -E "Status|Total|Valid|Errors|Warnings" | head -6
echo ""

echo "3. Test Suite"
echo "----------------------------------------------------------------------"
echo "Running test suite..."
python3 -m pytest tests/ -v --tb=no 2>&1 | tail -1
echo ""

echo "4. Code Coverage"
echo "----------------------------------------------------------------------"
echo "Checking core module coverage..."
python3 -m pytest tests/ --cov=agent --cov=market_env --cov=validation.validator --cov-report=term 2>&1 | grep -E "agent.py|market_env.py|validator.py|TOTAL"
echo ""

echo "======================================================================"
echo "Verification Complete"
echo "======================================================================"
