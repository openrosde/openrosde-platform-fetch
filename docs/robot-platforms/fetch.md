# Fetch

Platform-specific documentation for the [Fetch Robotics Fetch](https://fetchrobotics.github.io/docs/) within OpenRoSDE.

## 🔗 External Resources

- Official documentation: [https://fetchrobotics.github.io/docs/](https://fetchrobotics.github.io/docs/)
- ROS wiki: [http://wiki.ros.org/Robots/Fetch](http://wiki.ros.org/Robots/Fetch)
- GitHub repository (fetch_ros): [https://github.com/fetchrobotics/fetch_ros](https://github.com/fetchrobotics/fetch_ros)
- GitHub repository (fetch_gazebo): [https://github.com/fetchrobotics/fetch_gazebo](https://github.com/fetchrobotics/fetch_gazebo)

## 🔩 Hardware Overview

The Fetch Robotics Fetch platform consists of the following components:

- **Robot:** [Fetch Robotics Fetch](https://fetchrobotics.github.io/docs/) mobile manipulator.
- **On-board computer:** Intel-based computer running Ubuntu with ROS.
- **Arm:** 7-DOF manipulator with parallel-jaw gripper.
- **LiDAR:** SICK TiM571 laser scanner.
- **Camera:** Primesense Carmine 1.09 short-range depth sensor (head-mounted).

## ⚙️ Platform Configuration

Clone this platform into `extensions/` of the core of OpenRoSDE, then switch to the Fetch Robotics Fetch platform:

```shell
git clone https://gitlab.com/coarobo/openrosde/openrosde-platform-fetch.git extensions/openrosde-platform-fetch
bash ./SWITCH-ROBOT-PLATFORM.bash fetch
```

> [!NOTE]
> The switch creates the `.env.custom` file of the core with the Fetch Robotics Fetch configuration of `env/fetch.env`, then clones the Git submodules of every extension and applies their patches.

## 🌐 Network Configuration

The Fetch Robotics Fetch robot uses mDNS host names for network discovery.

| Device | Host Name | Notes |
| --- | --- | --- |
| Fetch Robotics Fetch | `fetch.local` | Default mDNS hostname |

To connect to the real robot, update the ROS master hostname in `.env.custom`:

```shell
OPENROSDE_ROS_MASTER_HOSTNAME=fetch.local
```

## 🚀 Gazebo Simulation

Start the Fetch Robotics Fetch Gazebo simulation using the `tmux` session of the platform:

```shell
bash ./RUN-TMUX-SESSION.bash #[docker-project] default-gazebo
```

The Terminator layout of earlier releases still opens with `bash ./RUN-TERMINATOR-TERMINAL.bash #[docker-project] default-gazebo`.

Or start the launch files manually in the Docker container:

```shell
roslaunch openrosde_fetch_launch fetch_bringup_default_gazebo.launch
roslaunch openrosde_fetch_launch fetch_navigation_default_gazebo.launch
roslaunch openrosde_fetch_launch fetch_moveit_default.launch
roslaunch openrosde_fetch_launch fetch_rviz_default.launch
```

## 🕐 Clock Synchronization

The Fetch Robotics Fetch robot requires clock synchronization between the host machine and the robot via Chrony.
Run the following script to restart the Chrony service on both the host and the robot:

```shell
bash ./RESTART-CHRONY-SERVICE.bash
```

> [!NOTE]
> The script connects to the robot via SSH using the default credentials (`fetch` / `robotics`).
> The robot hostname is resolved from `OPENROSDE_ROBOT_HOSTNAME` in `env/fetch.env` (default: `fetch.local`).

## 🤖 Real Robot Operation

Start the Fetch Robotics Fetch real robot stack using the `tmux` session of the platform:

```shell
bash ./RUN-TMUX-SESSION.bash #[docker-project] default-realworld
```

The Terminator layout of earlier releases still opens with `bash ./RUN-TERMINATOR-TERMINAL.bash #[docker-project] default-realworld`.

Or start the launch files manually in the Docker container:

```shell
roslaunch openrosde_fetch_launch fetch_bringup_default_realworld.launch
roslaunch openrosde_fetch_launch fetch_mapping_default.launch
roslaunch openrosde_fetch_launch fetch_moveit_default.launch
roslaunch openrosde_fetch_launch fetch_rviz_default.launch
```

## 📋 Launch Files Reference

The following launch files are available for the Fetch Robotics Fetch platform (package: `openrosde_fetch_launch`):

| Launch File | Description |
| --- | --- |
| `fetch_bringup_default_gazebo.launch` | Fetch Robotics Fetch Gazebo simulation |
| `fetch_bringup_default_realworld.launch` | Fetch Robotics Fetch real robot bringup |
| `fetch_navigation_default_gazebo.launch` | Navigation stack (Gazebo) |
| `fetch_mapping_default.launch` | SLAM mapping (build_map) |
| `fetch_moveit_default.launch` | MoveIt motion planning |
| `fetch_rviz_default.launch` | RViz visualization |
| `fetch_teleop_default.launch` | End effector teleoperation from `geometry_msgs/TwistStamped` commands on `fetch_ee_cmd_vel` (relay of the package `openrosde_fetch_teleop`) |

## 🥽 End Effector Teleoperation

`fetch_teleop_default.launch` starts the relay of `openrosde_fetch_teleop`, which moves the end effector of the Fetch Robotics Fetch from `geometry_msgs/TwistStamped` velocity commands, such as those of a teleoperation application on a mixed reality headset.

- A client publishes the commands on `fetch_ee_cmd_vel`, for example through `rosbridge` on port `9090` (`openrosde_launch:rosbridge_server_default.launch`), which the `tmux` sessions of the core start.
- The relay clamps each command to small velocity limits, streams it at 20 Hz to `/arm_controller/cartesian_twist/command`, the Cartesian twist controller that the real Fetch loads, and sends zeros once the commands stop, so that the arm holds its pose.
- In Gazebo, the patch `patches/ros/fetch_catkin_ws/src/fetch_gazebo/0001-add-cartesian-twist-controller.patch` adds that controller to the simulated Fetch.
- The `tmux` panes and the Terminator layouts of the platform start it in both environments.

The CI of OpenRoSDE checks this path in Gazebo with `ci/check-rosbridge.bash`, as the README describes.

## 🧪 FlexBE Behavior

The `openrosde_fetch_flexbe_behaviors` package provides an example behavior that loops navigation between two waypoints using `MoveBaseState` and `WaitState`.

To start the FlexBE behavior engine and app:

```shell
roslaunch openrosde_launch flexbe_app_default.launch
```

Load the `Fetch Example Behavior` behavior in the FlexBE App and press **Start**.

## 📜 Third-Party Software and Licensing

This platform is distributed under the [Apache License 2.0](../../LICENSE).
Its Catkin workspace builds a Git submodule of Fetch Robotics, and its image installs the packages of Fetch Robotics, each under its own license:

| Component | Source | License |
| --- | --- | --- |
| `fetch_gazebo`, `fetch_gazebo_demo` | Git submodule from [https://github.com/fetchrobotics/fetch_gazebo](https://github.com/fetchrobotics/fetch_gazebo), branch `gazebo11`, patched by `patches/` | [BSD-3-Clause](https://spdx.org/licenses/BSD-3-Clause.html) (Fetch Robotics, Inc.) |
| `fetch_description` | `ros-noetic-fetch-ros` in the image `fetch-devel`, from [https://github.com/fetchrobotics/fetch_ros](https://github.com/fetchrobotics/fetch_ros) | [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) (Fetch Robotics, Inc.) |
| `openrosde_fetch_launch`, `openrosde_fetch_teleop`, `openrosde_fetch_behaviors` (this repository) | [https://gitlab.com/coarobo/openrosde/openrosde-platform-fetch](https://gitlab.com/coarobo/openrosde/openrosde-platform-fetch) | [Apache-2.0](../../LICENSE) (Coarobo GK) |

The relay `fetch_cartesian_twist_control.py` was ported into the SDE from the `fetch_servoing` package written by Gustavo Garcia.

> [!WARNING]
> `fetch_description` holds the description and the meshes of the Fetch under CC BY-NC-SA 4.0, which allows no commercial use.
> The image `fetch-devel` redistributes it, so a commercial use of the image needs the agreement of the rights holder.
