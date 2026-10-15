#!/bin/bash

# This script runs the checks of the Fetch platform inside the container of a setup, as part of the CI of OpenRoSDE.
# 'gitlab-ci/run-extension-checks.bash' of the core runs it once the Catkin workspaces of the setup are built and sourced, in the container that 'gitlab-ci/test-catkin-workspaces.bash' disconnected from every network.
#
# Usage: bash ./ci/check-in-container.bash <robot-setup>
#
# <robot-setup>: The setup that the CI tests, which activates this platform, such as 'fetch'.

################################################################################

# Resolve the folder of the checks.
OPENROSDE_FETCH_CI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check the Fetch over 'rosbridge' in a setup of the Fetch only, since a setup of another platform may still activate this repository.
if [ "${OPENROSDE_ROBOT_PLATFORM}" != "fetch" ]; then
  echo "Skipping the check of the Fetch over 'rosbridge', since the setup '$1' runs the platform '${OPENROSDE_ROBOT_PLATFORM}'."
  exit 0
fi
bash "${OPENROSDE_FETCH_CI_DIR}/check-rosbridge.bash"
