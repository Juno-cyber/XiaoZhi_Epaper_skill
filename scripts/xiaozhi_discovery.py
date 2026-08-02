#!/usr/bin/env python3
"""
xiaozhi Discovery — 局域网自动发现小智设备

发现策略（按优先级）：
  1. mDNS 查询 xiaozhi.local（最快，<100ms）
  2. 读取已知 IP 缓存 ~/.hermes/xiaozhi_ip.txt（上次发现的结果）
  3. HTTP 探测缓存 IP 是否还在线
  4. UDP 广播扫描局域网（最慢但最可靠）

用法：
  python3 xiaozhi_discovery.py           # 发现并打印 IP
  python3 xiaozhi_discovery.py --health   # 发现并做健康检查
  python3 xiaozhi_discovery.py --save     # 发现并保存到缓存文件

输出：
  发现成功打印 IP 地址到 stdout，退出码 0
  发现失败打印错误到 stderr，退出码 1
"""

import socket
import json
import time
import sys
import os
import subprocess
import argparse
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

PORT = 8080
MDNS_HOSTNAME = "xiaozhi.local"
DISCOVERY_PORT = 50001  # 用于 UDP 广播探测的端口
DISCOVERY_MAGIC = b"XIAOZHI_DISCOVER"
DISCOVERY_RESPONSE = b"XIAOZHI_HERE"
DISCOVERY_TIMEOUT = 3.0
CACHE_FILE = os.path.expanduser("~/.hermes/xiaozhi_ip.txt")
SCAN_PORTS = [8080]

def try_mdns():
    """策略1：通过 mDNS 解析 xiaozhi.local"""
    try:
        result = socket.getaddrinfo(MDNS_HOSTNAME, PORT, socket.AF_INET, socket.SOCK_STREAM)
        if result:
            ip = result[0][4][0]
            return ip
    except Exception:
        pass
    
    # 尝试用 avahi-resolve（Linux）
    try:
        r = subprocess.run(["avahi-resolve-host-name", MDNS_HOSTNAME],
                          capture_output=True, text=True, timeout=2)
        if r.returncode == 0 and r.stdout.strip():
            parts = r.stdout.strip().split("\t")
            if len(parts) >= 2:
                return parts[1]
    except Exception:
        pass
    
    return None


def try_cache():
    """策略2：读取缓存的 IP"""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE) as f:
                ip = f.read().strip()
                if ip:
                    return ip
    except Exception:
        pass
    return None


def try_health(ip, timeout=2.0):
    """HTTP 健康检查：GET http://ip:8080/"""
    url = f"http://{ip}:{PORT}/"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                if data.get("status") == "ok" and "board" in data:
                    return data
    except Exception:
        pass
    return None


def try_udp_broadcast():
    """策略3：UDP 广播扫描局域网"""
    # 获取本机 IP 和子网
    local_ip = get_local_ip()
    if not local_ip:
        return None
    
    # 构造广播地址
    parts = local_ip.split(".")
    broadcast_addr = f"{parts[0]}.{parts[1]}.{parts[2]}.255"
    
    # 发送广播
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(DISCOVERY_TIMEOUT)
    
    try:
        sock.bind(("0.0.0.0", DISCOVERY_PORT))
    except OSError:
        # 端口被占，只用发送
        pass
    
    try:
        sock.sendto(DISCOVERY_MAGIC, (broadcast_addr, DISCOVERY_PORT))
    except Exception:
        pass
    
    # 等待响应
    start = time.time()
    while time.time() - start < DISCOVERY_TIMEOUT:
        try:
            data, addr = sock.recvfrom(1024)
            if data == DISCOVERY_RESPONSE:
                return addr[0]
        except socket.timeout:
            break
        except Exception:
            break
    
    sock.close()
    return None


def try_port_scan():
    """策略4：扫描局域网所有 IP 的 8080 端口"""
    local_ip = get_local_ip()
    if not local_ip:
        return None
    
    parts = local_ip.split(".")
    base = f"{parts[0]}.{parts[1]}.{parts[2]}"
    
    def check(ip):
        h = try_health(ip, timeout=0.5)
        if h:
            return ip
        return None
    
    ips = [f"{base}.{i}" for i in range(1, 255)]
    
    with ThreadPoolExecutor(max_workers=50) as pool:
        futures = {pool.submit(check, ip): ip for ip in ips}
        for f in as_completed(futures):
            result = f.result()
            if result:
                # 取消剩余任务
                for ff in futures:
                    ff.cancel()
                return result
    
    return None


def get_local_ip():
    """获取本机局域网 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 不真正发送，只是让 OS 选路由
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def discover():
    """按优先级依次尝试发现策略"""
    # 策略1：mDNS
    ip = try_mdns()
    if ip:
        h = try_health(ip)
        if h:
            return ip, h
    
    # 策略2：缓存
    cached = try_cache()
    if cached:
        h = try_health(cached)
        if h:
            return cached, h
    
    # 策略3：UDP 广播
    ip = try_udp_broadcast()
    if ip:
        h = try_health(ip)
        if h:
            return ip, h
    
    # 策略4：端口扫描
    ip = try_port_scan()
    if ip:
        h = try_health(ip)
        if h:
            return ip, h
    
    return None, None


def save_cache(ip):
    """保存 IP 到缓存文件"""
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            f.write(ip)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="发现局域网内的小智设备")
    parser.add_argument("--health", action="store_true", help="发现后做健康检查")
    parser.add_argument("--save", action="store_true", help="保存 IP 到缓存")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示详细过程")
    args = parser.parse_args()
    
    if args.verbose:
        print(f"[*] 本机 IP: {get_local_ip()}", file=sys.stderr)
        print(f"[*] 开始发现小智设备...", file=sys.stderr)
    
    ip, health = discover()
    
    if ip:
        if args.save:
            save_cache(ip)
            if args.verbose:
                print(f"[*] IP 已保存到 {CACHE_FILE}", file=sys.stderr)
        
        print(ip)
        if args.health and health:
            print(json.dumps(health, indent=2, ensure_ascii=False), file=sys.stderr)
        sys.exit(0)
    else:
        print("未找到小智设备", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
