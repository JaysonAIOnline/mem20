#!/bin/bash
# Dual-platform build script for The Unreliable Prophecy
# Usage: ./build_both.sh [windows|linux|both]

set -e

PROJECT_PATH="/home/jayson/Desktop/jayson-openwebui/projects/unreliable_prophecy/engine_project"
UNITY_PATH="/home/jayson/Unity/Hub/Editor/6000.5.9f1/Editor/Unity"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== The Unreliable Prophecy - Dual Platform Build ===${NC}"

# Check Unity exists
if [ ! -f "$UNITY_PATH" ]; then
    echo -e "${RED}Error: Unity not found at $UNITY_PATH${NC}"
    exit 1
fi

echo -e "Using Unity: ${YELLOW}$UNITY_PATH${NC}"
echo -e "Project: ${YELLOW}$PROJECT_PATH${NC}"

# Use xvfb-run for headless Unity on Linux
XVFB_RUN="xvfb-run -a -s '-screen 0 1920x1080x24'"

echo -e "Using Unity: ${YELLOW}$UNITY_PATH${NC}"
echo -e "Project: ${YELLOW}$PROJECT_PATH${NC}"

# Parse argument
BUILD_TARGET="${1:-both}"

run_unity() {
    local method="$1"
    local target_name="$2"
    echo -e "${GREEN}Building $target_name...${NC}"
    $XVFB_RUN "$UNITY_PATH" -batchmode -projectPath "$PROJECT_PATH" -executeMethod "$method" -quit
}

case "$BUILD_TARGET" in
    windows)
        run_unity "BuildProject.BuildWindows" "Windows x64"
        ;;
    linux)
        run_unity "BuildProject.BuildLinux" "Linux x64"
        ;;
    both)
        run_unity "BuildProject.BuildWindows" "Windows x64"
        run_unity "BuildProject.BuildLinux" "Linux x64"
        ;;
    *)
        echo -e "${RED}Usage: $0 [windows|linux|both]${NC}"
        exit 1
        ;;
esac

# Check results
if [ "$BUILD_TARGET" = "windows" ] || [ "$BUILD_TARGET" = "both" ]; then
    if [ -f "$PROJECT_PATH/Builds/Windows/v0.5.0_VerticalSlice/TheUnreliableProphecy.exe" ]; then
        SIZE=$(du -h "$PROJECT_PATH/Builds/Windows/v0.5.0_VerticalSlice/TheUnreliableProphecy.exe" | cut -f1)
        echo -e "${GREEN}✓ Windows build successful: $SIZE${NC}"
    else
        echo -e "${RED}✗ Windows build failed${NC}"
    fi
fi

if [ "$BUILD_TARGET" = "linux" ] || [ "$BUILD_TARGET" = "both" ]; then
    if [ -f "$PROJECT_PATH/Builds/Linux/v0.5.0_VerticalSlice/TheUnreliableProphecy" ]; then
        SIZE=$(du -h "$PROJECT_PATH/Builds/Linux/v0.5.0_VerticalSlice/TheUnreliableProphecy" | cut -f1)
        echo -e "${GREEN}✓ Linux build successful: $SIZE${NC}"
    else
        echo -e "${RED}✗ Linux build failed${NC}"
    fi
fi

echo -e "${GREEN}=== Build Complete ===${NC}"