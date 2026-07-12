#!/bin/bash
# Nuitka Package Compilation Script for TradeQuantX Backtest Engine
# Compiles the backtest_engine package to C extensions and builds a wheel
# Uses nuitka.distutils.Build backend via pyproject.toml configuration

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${PROJECT_DIR}/dist"

echo "=========================================="
echo "TradeQuantX Backtest Engine - Nuitka Build"
echo "=========================================="
echo "Project: ${PROJECT_DIR}"
echo "Build dir: ${BUILD_DIR}"
echo ""

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf "${BUILD_DIR}"
rm -rf "${PROJECT_DIR}/build"
rm -rf "${PROJECT_DIR}/*.egg-info"

# Build wheel using nuitka distutils backend (configured in pyproject.toml)
echo ""
echo "Building wheel with nuitka distutils backend..."
cd "${PROJECT_DIR}"
uv build --wheel --no-build-isolation --out-dir "${BUILD_DIR}"

echo ""
echo "=========================================="
echo "Build Complete!"
echo "=========================================="
echo "Wheel location:"
ls -la "${BUILD_DIR}"/*.whl

echo ""
echo "To test install:"
echo "  pip install ${BUILD_DIR}/backtest_engine-*.whl"
echo ""
echo "To test import:"
echo "  python -c \"from backtest_engine.data_provider import DataProviderClient; print('Import OK')\""
