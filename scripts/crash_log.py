#!/usr/bin/env python3
"""快速抓取 ESP32 崩溃日志

用法：
  python3 crash_log.py              # 抓取 20 秒启动日志
  python3 crash_log.py /dev/ttyUSB0 # 指定串口
  python3 crash_log.py /dev/ttyUSB0 30  # 指定串口和时长（秒）

前提：pyserial 已安装 (pip install pyserial)，串口权限已设置 (chmod 666 /dev/ttyUSB0)
"""
import serial
import time
import sys

PORT = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyUSB0'
DURATION = int(sys.argv[2]) if len(sys.argv) > 2 else 20
BAUD = 115200

ser = serial.Serial(PORT, BAUD, timeout=0.3)

# 硬复位
ser.dtr = True; ser.rts = True; time.sleep(0.1)
ser.dtr = False; ser.rts = False; time.sleep(0.05)

print(f"=== 抓取启动日志 ({DURATION}秒) ===")
start = time.time()
while time.time() - start < DURATION:
    data = ser.read(ser.in_waiting or 1)
    if data:
        sys.stdout.write(data.decode('utf-8', errors='replace'))
        sys.stdout.flush()
    time.sleep(0.02)
ser.close()
print("\n=== done ===")
