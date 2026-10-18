#!/usr/bin/env python3
"""Capture a bounded ESP32 serial boot/crash log."""

import argparse
import sys
import time


def make_parser():
    parser = argparse.ArgumentParser(description="Capture an ESP32 serial crash log")
    parser.add_argument("port", help="identified serial port, e.g. /dev/ttyUSB0, /dev/cu.usbserial, COM3")
    parser.add_argument("duration", nargs="?", type=float, default=20)
    parser.add_argument("--baud", type=int, default=115200)
    reset = parser.add_mutually_exclusive_group()
    reset.add_argument("--reset", action="store_true", help="explicitly toggle DTR/RTS to capture boot")
    reset.add_argument("--no-reset", action="store_true", help="compatibility option; no reset is now the default")
    return parser


def main(argv=None):
    args = make_parser().parse_args(argv)
    if args.duration <= 0 or args.duration > 3600:
        raise ValueError("duration must be in (0, 3600] seconds")
    if args.baud <= 0 or args.baud > 4_000_000:
        raise ValueError("baud must be in (0, 4000000]")
    try:
        import serial
    except ImportError as exc:
        raise RuntimeError("pyserial is required; install requirements-optional.txt") from exc

    # Configure line states before opening; Serial(port) would assert them first.
    connection = serial.Serial(port=None, baudrate=args.baud, timeout=0.3)
    connection.dtr = False
    connection.rts = False
    connection.port = args.port
    connection.open()
    try:
        if args.reset:
            connection.dtr = True
            connection.rts = True
            time.sleep(0.1)
            connection.dtr = False
            connection.rts = False
            time.sleep(0.05)

        print(f"=== Serial capture ({args.duration:g}s, reset={args.reset}) ===")
        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            data = connection.read(connection.in_waiting or 1)
            if data:
                sys.stdout.write(data.decode("utf-8", errors="replace"))
                sys.stdout.flush()
            time.sleep(0.02)
    finally:
        connection.close()
    print("\n=== done ===")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
