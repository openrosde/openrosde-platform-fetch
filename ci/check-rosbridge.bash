#!/bin/bash

# This script checks that a client reaches the Fetch through 'rosbridge' alone, with every interface that a teleoperation application uses, as part of the CI of OpenRoSDE.
# It starts 'ci/fetch_rosbridge_check.launch': the Fetch in Gazebo without a GUI ('gzserver' alone), 'rosbridge' on port 9090 as 'openrosde_launch:rosbridge_server_default.launch' starts it, and the relay of 'fetch_teleop_default.launch'.
# The WebSocket client 'ci/check-rosbridge.py' then connects to port 9090 and checks '/clock', '/joint_states', '/tf', and '/tf_static', and that a 'geometry_msgs/TwistStamped' published on 'fetch_ee_cmd_vel' reaches '/arm_controller/cartesian_twist/command' through the relay.
# It starts nothing in a container with a network interface other than the loopback that is up, so that only the simulated arm can move, as in the container of the CI, which is disconnected from every network before any check runs.
# 'gitlab-ci/check-no-motion.bash' of the core allows its launch file, since 'ci/allowed-simulation-launches.txt' names it.
#
# Usage: bash ./ci/check-rosbridge.bash [timeout]
#
# [timeout]: Seconds that the simulation and the topics may take to come up.
#            Default value is '240'.

################################################################################

# Resolve the folder of the checks, and name the log of the launch file and the timeout.
OPENROSDE_FETCH_CI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENROSDE_FETCH_LAUNCH_LOG_FILE="$(mktemp /tmp/openrosde-fetch-rosbridge-XXXXXX.log)"
OPENROSDE_FETCH_CHECK_TIMEOUT="$1"
if [ -z "${OPENROSDE_FETCH_CHECK_TIMEOUT}" ]; then
  OPENROSDE_FETCH_CHECK_TIMEOUT=240
fi

# Refuse to start any node while a network interface other than the loopback is up, whose flags carry 'IFF_UP' (0x1).
# An entry of '/sys/class/net/' without flags, such as 'bonding_masters', is no interface.
for OPENROSDE_FETCH_NETWORK_INTERFACE_DIR in /sys/class/net/*; do
  OPENROSDE_FETCH_NETWORK_INTERFACE="$(basename "${OPENROSDE_FETCH_NETWORK_INTERFACE_DIR}")"
  if [ "${OPENROSDE_FETCH_NETWORK_INTERFACE}" = "lo" ] || [ ! -f "${OPENROSDE_FETCH_NETWORK_INTERFACE_DIR}/flags" ]; then
    continue
  fi
  if (( $(cat "${OPENROSDE_FETCH_NETWORK_INTERFACE_DIR}/flags") & 0x1 )); then
    echo "Error: The network interface '${OPENROSDE_FETCH_NETWORK_INTERFACE}' is up, so this check starts no node: run it in a container without network, as the CI does."
    exit 1
  fi
done

################################################################################

# Run the ROS master on the loopback, and keep Gazebo from looking for models online, which the container cannot reach.
export ROS_MASTER_URI=http://localhost:11311
export ROS_HOSTNAME=localhost
unset ROS_IP
export GAZEBO_MODEL_DATABASE_URI=

# Stop every node of the launch file, Gazebo included, by stopping its process group, then print the end of its log when the check failed.
function openrosde-fetch-stop-launch () {
  local OPENROSDE_FETCH_CHECK_EXIT_CODE=$?
  local OPENROSDE_FETCH_WAITED_SECONDS
  if [ -n "${OPENROSDE_FETCH_LAUNCH_PID}" ]; then
    kill -INT -- "-${OPENROSDE_FETCH_LAUNCH_PID}" > /dev/null 2>&1
    for OPENROSDE_FETCH_WAITED_SECONDS in $(seq 1 30); do
      kill -0 -- "-${OPENROSDE_FETCH_LAUNCH_PID}" > /dev/null 2>&1 || break
      sleep 1
    done
    kill -KILL -- "-${OPENROSDE_FETCH_LAUNCH_PID}" > /dev/null 2>&1
  fi
  if [ "${OPENROSDE_FETCH_CHECK_EXIT_CODE}" -ne 0 ]; then
    echo "End of the log of 'ci/fetch_rosbridge_check.launch':"
    tail -n 80 "${OPENROSDE_FETCH_LAUNCH_LOG_FILE}"
  fi
  rm -f "${OPENROSDE_FETCH_LAUNCH_LOG_FILE}"
  exit "${OPENROSDE_FETCH_CHECK_EXIT_CODE}"
}
trap openrosde-fetch-stop-launch EXIT

################################################################################

# Start the simulation, 'rosbridge', and the relay in a process group of their own, then run the client against 'rosbridge'.
echo "Starting the Fetch in Gazebo, 'rosbridge', and the relay, with no network..."
setsid roslaunch "${OPENROSDE_FETCH_CI_DIR}/fetch_rosbridge_check.launch" < /dev/null > "${OPENROSDE_FETCH_LAUNCH_LOG_FILE}" 2>&1 &
OPENROSDE_FETCH_LAUNCH_PID=$!
timeout "$((OPENROSDE_FETCH_CHECK_TIMEOUT + 120))" python3 "${OPENROSDE_FETCH_CI_DIR}/check-rosbridge.py" --timeout "${OPENROSDE_FETCH_CHECK_TIMEOUT}"
