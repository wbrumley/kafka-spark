#!/bin/bash
# Security Events System Launcher
# This script provides a simple interface to start the security monitoring system

# Set colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Print banner
echo -e "${BLUE}"
echo "======================================================================================="
echo "  _____                      _ _          _____                 _       "
echo " / ____|                    (_) |        |  ___| __ __   __ _ _| |_ ___ "
echo " | (___   ___  ___ _   _ _ __| | |_ _   _| |_ | '__/  \ /  (_| | __/ __)"
echo " \___ \ / _ \/ __| | | | '__| | __| | | |  _|| | / /\ \ | | | | |_\__ \\"
echo " ____) |  __/ (__| |_| | |  | | |_| |_| | |  | |/ ____ \| |_| | |_|__) |"
echo " |_____/ \___|\___|\__,_|_|  |_|\__|\__, |_|  |_/_/    \_\__,_|\__|___/ "
echo "                                      __/ |                              "
echo "                                     |___/   Security Monitoring System  "
echo "======================================================================================="
echo -e "${NC}"

# Display menu
echo -e "${GREEN}Select a mode to run the security monitoring system:${NC}"
echo -e "1) ${YELLOW}Kafka + Spark Integration${NC} (distributed system with streaming analytics)"
echo -e "2) ${YELLOW}Unified Processor${NC} (simplified all-in-one solution)"
echo -e "3) ${YELLOW}Dashboard Only${NC} (requires Kafka + Spark to be running)"
echo -e "q) ${RED}Quit${NC}"

# Get user input
read -p "Enter your choice [1-3 or q]: " choice

# Process user input
case $choice in
    1)
        echo -e "${GREEN}Starting Kafka + Spark Integration...${NC}"
        echo -e "${BLUE}(Press Ctrl+C to stop)${NC}"
        ./run_combined.sh
        ;;
    2)
        echo -e "${GREEN}Starting Unified Processor...${NC}"
        echo -e "${BLUE}(Press Ctrl+C to stop)${NC}"
        ./run_combined.sh --unified
        ;;
    3)
        echo -e "${GREEN}Starting Dashboard...${NC}"
        echo -e "${BLUE}(Press Ctrl+C to stop)${NC}"
        ./run_dashboard.sh
        ;;
    q|Q)
        echo -e "${RED}Exiting...${NC}"
        exit 0
        ;;
    *)
        echo -e "${RED}Invalid choice. Exiting...${NC}"
        exit 1
        ;;
esac 