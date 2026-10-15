#!/usr/bin/env python3

"""Check the Fetch through 'rosbridge' alone, as a teleoperation application reaches it, for 'ci/check-rosbridge.bash'.

The client connects to the WebSocket of 'rosbridge', subscribes to '/clock', '/joint_states', '/tf', and '/tf_static',
and waits for a message of each, with a clock that advances and the joints of the arm.
It then advertises 'fetch_ee_cmd_vel' and publishes a 'geometry_msgs/TwistStamped' at 20 Hz, whose angular speed
exceeds the limit of the relay, until the relay forwards it, clamped, to '/arm_controller/cartesian_twist/command'.
It then stops publishing and waits for the zero command that the relay sends once the input goes stale, so that the
simulated arm holds its pose.
It uses the standard library of Python only, and every request id starts with a random prefix of its own.
"""

import argparse
import base64
import hashlib
import json
import os
import socket
import struct
import sys
import time

WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

ARM_JOINT_NAMES = [
    "shoulder_pan_joint", "shoulder_lift_joint", "upperarm_roll_joint",
    "elbow_flex_joint", "forearm_roll_joint", "wrist_flex_joint", "wrist_roll_joint",
]

INPUT_TOPIC = "fetch_ee_cmd_vel"
OUTPUT_TOPIC = "/arm_controller/cartesian_twist/command"

# Command sent to the relay: a linear speed below its limit of 0.05 m/s, which it forwards as it is, and an angular
# speed above its limit of 0.10 rad/s, which it clamps, so that the output proves that the relay handled the command.
SENT_LINEAR_X = 0.02
SENT_ANGULAR_Z = 0.5
EXPECTED_ANGULAR_Z = 0.10


class WebSocketClient(object):
    """Minimal WebSocket client of RFC 6455 for text messages, enough for 'rosbridge'."""

    def __init__(self, host, port, timeout):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.buffer = b""
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            "GET / HTTP/1.1\r\n"
            "Host: {0}:{1}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: {2}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).format(host, port, key)
        self.sock.sendall(request.encode())
        while b"\r\n\r\n" not in self.buffer:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("rosbridge closed the connection during the handshake")
            self.buffer += chunk
        head, self.buffer = self.buffer.split(b"\r\n\r\n", 1)
        lines = head.decode("latin-1").split("\r\n")
        if " 101 " not in lines[0] + " ":
            raise ConnectionError("rosbridge refused the WebSocket upgrade: " + lines[0])
        accept = base64.b64encode(hashlib.sha1((key + WEBSOCKET_GUID).encode()).digest()).decode()
        headers = {line.split(":", 1)[0].strip().lower(): line.split(":", 1)[1].strip() for line in lines[1:] if ":" in line}
        if headers.get("sec-websocket-accept") != accept:
            raise ConnectionError("rosbridge answered the WebSocket upgrade with a wrong accept key")

    def _send_frame(self, opcode, payload):
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", length)
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def send(self, message):
        self._send_frame(0x1, json.dumps(message).encode())

    def _parse_frame(self):
        """Return '(fin, opcode, payload)' of the first whole frame of the buffer, or None."""
        if len(self.buffer) < 2:
            return None
        first, second = self.buffer[0], self.buffer[1]
        offset = 2
        length = second & 0x7F
        if length == 126:
            if len(self.buffer) < offset + 2:
                return None
            length = struct.unpack(">H", self.buffer[offset:offset + 2])[0]
            offset += 2
        elif length == 127:
            if len(self.buffer) < offset + 8:
                return None
            length = struct.unpack(">Q", self.buffer[offset:offset + 8])[0]
            offset += 8
        mask = None
        if second & 0x80:
            if len(self.buffer) < offset + 4:
                return None
            mask = self.buffer[offset:offset + 4]
            offset += 4
        if len(self.buffer) < offset + length:
            return None
        payload = self.buffer[offset:offset + length]
        self.buffer = self.buffer[offset + length:]
        if mask:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return bool(first & 0x80), first & 0x0F, payload

    def receive(self, timeout):
        """Return the next JSON message, or None when none arrives within the timeout."""
        deadline = time.monotonic() + timeout
        fragments = b""
        while True:
            frame = self._parse_frame()
            if frame is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self.sock.settimeout(remaining)
                try:
                    chunk = self.sock.recv(65536)
                except socket.timeout:
                    return None
                if not chunk:
                    raise ConnectionError("rosbridge closed the connection")
                self.buffer += chunk
                continue
            fin, opcode, payload = frame
            if opcode == 0x8:
                raise ConnectionError("rosbridge closed the connection")
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            fragments += payload
            if fin:
                return json.loads(fragments.decode())

    def close(self):
        try:
            self._send_frame(0x8, struct.pack(">H", 1000))
        except OSError:
            pass
        self.sock.close()


def connect(host, port, deadline):
    """Connect to 'rosbridge', retrying until it listens or the deadline passes."""
    last_error = None
    while time.monotonic() < deadline:
        try:
            return WebSocketClient(host, port, timeout=5.0)
        except (OSError, ConnectionError) as error:
            last_error = error
            time.sleep(1.0)
    raise SystemExit("FAIL: no 'rosbridge' answered on {0}:{1}: {2}".format(host, port, last_error))


def stamp_seconds(stamp):
    return stamp.get("secs", 0) + stamp.get("nsecs", 0) * 1e-9


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9090)
    parser.add_argument("--timeout", type=float, default=240.0, help="Seconds to wait for the simulation and every topic.")
    arguments = parser.parse_args()

    started = time.monotonic()
    deadline = started + arguments.timeout
    prefix = "ci-" + os.urandom(6).hex() + ":"
    client = connect(arguments.host, arguments.port, deadline)
    print("Connected to 'rosbridge' on {0}:{1} after {2:.0f} s.".format(arguments.host, arguments.port, time.monotonic() - started), flush=True)

    subscriptions = {
        "/clock": "rosgraph_msgs/Clock",
        "/joint_states": "sensor_msgs/JointState",
        "/tf": "tf2_msgs/TFMessage",
        "/tf_static": "tf2_msgs/TFMessage",
        OUTPUT_TOPIC: "geometry_msgs/TwistStamped",
    }
    for topic, message_type in subscriptions.items():
        client.send({"op": "subscribe", "id": prefix + "subscribe" + topic, "topic": topic, "type": message_type})

    # Wait for the clock to advance, the joints of the arm, a transform, and a static transform.
    clock_stamps = set()
    seen = {topic: 0 for topic in subscriptions}
    arm_positions = None
    while time.monotonic() < deadline:
        ready = len(clock_stamps) >= 2 and arm_positions is not None and seen["/tf"] > 0 and seen["/tf_static"] > 0
        if ready:
            break
        message = client.receive(timeout=1.0)
        if not message or message.get("op") != "publish":
            continue
        topic = message.get("topic")
        body = message.get("msg", {})
        if topic in seen:
            seen[topic] += 1
        if topic == "/clock":
            clock_stamps.add(stamp_seconds(body.get("clock", {})))
        elif topic == "/joint_states":
            names = body.get("name", [])
            if all(name in names for name in ARM_JOINT_NAMES):
                arm_positions = [body["position"][names.index(name)] for name in ARM_JOINT_NAMES]
        elif topic in ("/tf", "/tf_static") and not body.get("transforms"):
            seen[topic] -= 1
    else:
        missing = []
        if len(clock_stamps) < 2:
            missing.append("'/clock' advancing")
        if arm_positions is None:
            missing.append("'/joint_states' with the arm joints")
        for topic in ("/tf", "/tf_static"):
            if not seen[topic]:
                missing.append("'{0}' with a transform".format(topic))
        client.close()
        raise SystemExit("FAIL: after {0:.0f} s, 'rosbridge' never delivered {1}.".format(time.monotonic() - started, ", ".join(missing)))
    print("Received '/clock' advancing to {0:.2f} s, '/joint_states' with the 7 arm joints, '/tf', and '/tf_static' after {1:.0f} s.".format(max(clock_stamps), time.monotonic() - started), flush=True)

    # Publish the command at 20 Hz until the relay forwards it, clamped, to the Cartesian twist controller.
    client.send({"op": "advertise", "id": prefix + "advertise", "topic": INPUT_TOPIC, "type": "geometry_msgs/TwistStamped"})
    command = {
        "header": {"frame_id": "base_link"},
        "twist": {"linear": {"x": SENT_LINEAR_X, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": SENT_ANGULAR_Z}},
    }
    forwarded = None
    sent_count = 0
    relay_deadline = min(deadline, time.monotonic() + 60.0)
    next_send = time.monotonic()
    while forwarded is None and time.monotonic() < relay_deadline:
        if time.monotonic() >= next_send:
            client.send({"op": "publish", "id": prefix + "publish", "topic": INPUT_TOPIC, "msg": command})
            sent_count += 1
            next_send += 0.05
        message = client.receive(timeout=max(0.0, next_send - time.monotonic()))
        if message and message.get("op") == "publish" and message.get("topic") == OUTPUT_TOPIC:
            twist = message["msg"]["twist"]
            if abs(twist["linear"]["x"] - SENT_LINEAR_X) < 1e-6 and abs(twist["angular"]["z"] - EXPECTED_ANGULAR_Z) < 1e-6:
                forwarded = twist
    if forwarded is None:
        client.close()
        raise SystemExit("FAIL: the relay never forwarded the {0} commands of '{1}' to '{2}' with the angular speed clamped to {3}.".format(sent_count, INPUT_TOPIC, OUTPUT_TOPIC, EXPECTED_ANGULAR_Z))
    print("The relay forwarded the command of '{0}' to '{1}', with the linear speed {2} kept and the angular speed {3} clamped to {4}, after {5} commands.".format(INPUT_TOPIC, OUTPUT_TOPIC, SENT_LINEAR_X, SENT_ANGULAR_Z, EXPECTED_ANGULAR_Z, sent_count), flush=True)

    # Stop publishing, and wait for the zero command that the relay sends once the input goes stale.
    client.send({"op": "unadvertise", "id": prefix + "unadvertise", "topic": INPUT_TOPIC})
    stopped_deadline = time.monotonic() + 15.0
    stopped = False
    last_arm_positions = arm_positions
    while not stopped and time.monotonic() < stopped_deadline:
        message = client.receive(timeout=1.0)
        if not message or message.get("op") != "publish":
            continue
        if message.get("topic") == OUTPUT_TOPIC:
            twist = message["msg"]["twist"]
            values = [twist[part][axis] for part in ("linear", "angular") for axis in ("x", "y", "z")]
            stopped = all(value == 0.0 for value in values)
        elif message.get("topic") == "/joint_states":
            names = message["msg"].get("name", [])
            if all(name in names for name in ARM_JOINT_NAMES):
                last_arm_positions = [message["msg"]["position"][names.index(name)] for name in ARM_JOINT_NAMES]
    for topic in subscriptions:
        client.send({"op": "unsubscribe", "id": prefix + "subscribe" + topic, "topic": topic})
    client.close()
    if not stopped:
        raise SystemExit("FAIL: the relay never sent a zero command on '{0}' once the commands stopped.".format(OUTPUT_TOPIC))
    moved = max(abs(after - before) for before, after in zip(arm_positions, last_arm_positions))
    print("The relay sent a zero command once the commands stopped, and the simulated arm joints moved by up to {0:.4f} rad.".format(moved), flush=True)
    print("PASS: the Fetch answered over 'rosbridge' alone in {0:.0f} s.".format(time.monotonic() - started), flush=True)


if __name__ == "__main__":
    sys.exit(main())
