#!/usr/bin/env python3
"""Discover one or more xiaozhi devices on local IPv4 networks."""

import argparse
import http.client
import ipaddress
import itertools
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT_PORT = 8080
MDNS_FALLBACK = "xiaozhi.local"
DISCOVERY_PORT = 50001
DISCOVERY_MAGIC = b"XIAOZHI_DISCOVER"
DISCOVERY_RESPONSE = b"XIAOZHI_HERE"
DEFAULT_CACHE_FILE = os.path.expanduser("~/.hermes/xiaozhi_ip.txt")
MAX_SCAN_HOSTS = 4096
HARD_MAX_SCAN_HOSTS = 65536
RFC1918_NETWORKS = tuple(ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


HEALTH_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def is_trusted_ipv4(value):
    address = value if isinstance(value, ipaddress.IPv4Address) else ipaddress.ip_address(value)
    return address.version == 4 and (
        address.is_loopback or address.is_link_local or any(address in network for network in RFC1918_NETWORKS)
    )


def is_trusted_network(network):
    return network.version == 4 and (
        network.subnet_of(ipaddress.ip_network("127.0.0.0/8"))
        or network.subnet_of(ipaddress.ip_network("169.254.0.0/16"))
        or any(network.subnet_of(candidate) for candidate in RFC1918_NETWORKS)
    )


def scan_host_count(network):
    return network.num_addresses if network.prefixlen >= 31 else network.num_addresses - 2


def bounded_local_network(address, network):
    """Keep automatic scans finite on broad local interfaces."""
    return network if scan_host_count(network) <= MAX_SCAN_HOSTS else ipaddress.ip_network(f"{address}/24", strict=False)


def valid_health(data):
    return isinstance(data, dict) and data.get("status") == "ok" and isinstance(data.get("board"), str)


def try_health(host, port=DEFAULT_PORT, timeout=1.0):
    try:
        request = urllib.request.Request(f"http://{host}:{port}/", method="GET")
        with HEALTH_OPENER.open(request, timeout=timeout) as response:
            if response.status != 200:
                return None
            data = json.loads(response.read(65537).decode("utf-8"))
            return data if valid_health(data) else None
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def resolve_mdns_candidates(port=DEFAULT_PORT):
    """Resolve the compatibility hostname and optionally browse HTTP mDNS services."""
    candidates = []
    try:
        for result in socket.getaddrinfo(MDNS_FALLBACK, port, socket.AF_INET, socket.SOCK_STREAM):
            candidates.append(result[4][0])
    except socket.gaierror:
        pass

    try:
        result = subprocess.run(
            ["avahi-browse", "-rtp", "_http._tcp"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        for line in result.stdout.splitlines():
            fields = line.split(";")
            if len(fields) >= 9 and fields[0] == "=":
                service_name, hostname, address, service_port = fields[3], fields[6], fields[7], fields[8]
                if "xiaozhi" in (service_name + hostname).lower() and service_port == str(port):
                    candidates.append(address)
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    candidates.extend(resolve_dnssd_candidates(port))
    return unique_private_ipv4(candidates)


def _bounded_command_output(command, timeout):
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False).stdout
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        return output.decode(errors="replace") if isinstance(output, bytes) else output
    except (OSError, subprocess.SubprocessError):
        return ""


def resolve_dnssd_candidates(port=DEFAULT_PORT):
    """Browse xiaozhi HTTP services with the macOS dns-sd utility."""
    browse = _bounded_command_output(["dns-sd", "-B", "_http._tcp", "local."], 2)
    services = []
    for line in browse.splitlines():
        match = re.search(r"\s_http\._tcp\.\s+(.+)$", line)
        if match and "xiaozhi" in match.group(1).lower():
            name = match.group(1).strip()
            if 0 < len(name) <= 128 and name not in services:
                services.append(name)
    candidates = []
    for name in services[:8]:
        lookup = _bounded_command_output(["dns-sd", "-L", name, "_http._tcp", "local."], 2)
        match = re.search(r"can be reached at\s+([^\s:]+)\.?:(\d+)", lookup, re.IGNORECASE)
        if not match or match.group(2) != str(port):
            continue
        try:
            for result in socket.getaddrinfo(match.group(1).rstrip("."), port, socket.AF_INET, socket.SOCK_STREAM):
                candidates.append(result[4][0])
        except socket.gaierror:
            continue
    return unique_private_ipv4(candidates)


def read_cache(path=DEFAULT_CACHE_FILE):
    try:
        with open(path, encoding="utf-8") as handle:
            return unique_private_ipv4(line.strip() for line in handle)
    except OSError:
        return []


def save_cache(addresses, path=DEFAULT_CACHE_FILE):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write("\n".join(addresses) + "\n")
    os.replace(temporary, path)


def unique_private_ipv4(values):
    output = []
    seen = set()
    for value in values:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            continue
        if not is_trusted_ipv4(address):
            continue
        canonical = str(address)
        if canonical not in seen:
            seen.add(canonical)
            output.append(canonical)
    return output


def networks_from_ifconfig(text):
    """Parse macOS/BSD ifconfig IPv4 addresses and hexadecimal netmasks."""
    networks = []
    for match in re.finditer(r"^\s*inet\s+(\d+(?:\.\d+){3})\s+netmask\s+(0x[0-9a-fA-F]+|\d+(?:\.\d+){3})", text, re.MULTILINE):
        address, mask = match.groups()
        try:
            if mask.lower().startswith("0x"):
                mask = str(ipaddress.IPv4Address(int(mask, 16)))
            network = ipaddress.ip_network(f"{address}/{mask}", strict=False)
            if is_trusted_network(network) and not network.subnet_of(ipaddress.ip_network("127.0.0.0/8")):
                networks.append(bounded_local_network(address, network))
        except ValueError:
            continue
    return list(dict.fromkeys(networks))


def local_networks():
    """Read real interface prefixes on Linux, with a conservative /24 fallback."""
    networks = []
    try:
        result = subprocess.run(
            ["ip", "-json", "-4", "address", "show", "up"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        interfaces = json.loads(result.stdout or "[]")
        if not isinstance(interfaces, list):
            raise ValueError("ip output is not an array")
        for interface in interfaces:
            if not isinstance(interface, dict):
                continue
            if interface.get("ifname") == "lo":
                continue
            address_info = interface.get("addr_info", [])
            if not isinstance(address_info, list):
                continue
            for info in address_info:
                if not isinstance(info, dict):
                    continue
                if info.get("family") != "inet" or info.get("scope") != "global":
                    continue
                network = ipaddress.ip_network(f"{info['local']}/{info['prefixlen']}", strict=False)
                if is_trusted_network(network):
                    networks.append(bounded_local_network(info['local'], network))
    except (FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError, KeyError, ValueError):
        pass

    if not networks:
        try:
            result = subprocess.run(
                ["ifconfig"], capture_output=True, text=True, timeout=2, check=False
            )
            networks.extend(networks_from_ifconfig(result.stdout))
        except (FileNotFoundError, subprocess.SubprocessError):
            pass

    if not networks:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("192.0.2.1", 9))
            address = sock.getsockname()[0]
            sock.close()
            if is_trusted_ipv4(address):
                networks.append(ipaddress.ip_network(f"{address}/24", strict=False))
        except OSError:
            pass
    return list(dict.fromkeys(networks))


def parse_networks(values, allow_large_scan=False):
    networks = []
    for value in values:
        try:
            network = ipaddress.ip_network(value, strict=False)
        except ValueError as exc:
            raise ValueError(f"invalid subnet {value!r}: {exc}") from exc
        if not is_trusted_network(network):
            raise ValueError(f"subnet {network} is not a private/local IPv4 network")
        host_count = scan_host_count(network)
        if host_count > HARD_MAX_SCAN_HOSTS:
            raise ValueError(f"subnet {network} exceeds the hard safety limit of {HARD_MAX_SCAN_HOSTS} hosts")
        if host_count > MAX_SCAN_HOSTS and not allow_large_scan:
            raise ValueError(
                f"subnet {network} has {host_count} hosts; use --allow-large-scan to exceed {MAX_SCAN_HOSTS}"
            )
        networks.append(network)
    networks = list(dict.fromkeys(networks))
    total_hosts = sum(scan_host_count(network) for network in networks)
    if total_hosts > HARD_MAX_SCAN_HOSTS:
        raise ValueError(f"combined subnets exceed the hard safety limit of {HARD_MAX_SCAN_HOSTS} hosts")
    if total_hosts > MAX_SCAN_HOSTS and not allow_large_scan:
        raise ValueError(f"combined subnets have {total_hosts} hosts; use --allow-large-scan to exceed {MAX_SCAN_HOSTS}")
    return networks


def udp_discover(networks, timeout=2.0):
    found = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.2)
    try:
        sock.bind(("0.0.0.0", 0))
        for network in networks:
            sock.sendto(DISCOVERY_MAGIC, (str(network.broadcast_address), DISCOVERY_PORT))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, address = sock.recvfrom(1024)
                if data == DISCOVERY_RESPONSE:
                    found.append(address[0])
            except socket.timeout:
                continue
    except OSError:
        pass
    finally:
        sock.close()
    return unique_private_ipv4(found)


def scan_networks(networks, port=DEFAULT_PORT, timeout=0.5, workers=48, all_devices=True, exclude=()):
    def unique_addresses():
        seen = set(exclude)
        for network in networks:
            for host in network.hosts():
                address = str(host)
                if address not in seen:
                    seen.add(address)
                    yield address

    found = {}
    worker_count = min(max(1, workers), 128)
    pool = ThreadPoolExecutor(max_workers=worker_count)
    try:
        iterator = unique_addresses()
        while True:
            batch = list(itertools.islice(iterator, 1024))
            if not batch:
                break
            futures = {pool.submit(try_health, address, port, timeout): address for address in batch}
            for future in as_completed(futures):
                try:
                    health = future.result()
                except Exception:
                    health = None
                if health is not None:
                    found[futures[future]] = health
                    if not all_devices:
                        return dict(sorted(found.items(), key=lambda item: ipaddress.ip_address(item[0])))
    finally:
        pool.shutdown(wait=all_devices, cancel_futures=not all_devices)
    return dict(sorted(found.items(), key=lambda item: ipaddress.ip_address(item[0])))


def discover(networks, port=DEFAULT_PORT, all_devices=False, verbose=False, cache_file=DEFAULT_CACHE_FILE, workers=48):
    found = {}

    def probe(stage, candidates, timeout=1.0):
        for address in candidates:
            if address in found:
                continue
            health = try_health(address, port, timeout)
            if health is not None:
                found[address] = health
                if verbose:
                    print(f"[*] {stage}: {address}", file=sys.stderr)
                if not all_devices:
                    return True
        return False

    if probe("mDNS", resolve_mdns_candidates(port)):
        return found
    if probe("cache", read_cache(cache_file)):
        return found
    if probe("UDP", udp_discover(networks)):
        return found
    scanned = scan_networks(networks, port=port, workers=workers, all_devices=all_devices, exclude=found)
    found.update(scanned)
    if verbose:
        for address in scanned:
            print(f"[*] scan: {address}", file=sys.stderr)
    return found


def make_parser():
    parser = argparse.ArgumentParser(description="Discover xiaozhi devices on local IPv4 networks")
    parser.add_argument("--health", action="store_true", help="print health JSON to stderr")
    parser.add_argument("--save", action="store_true", help="save discovered address(es)")
    parser.add_argument("--cache-file", default=DEFAULT_CACHE_FILE)
    parser.add_argument("--subnet", action="append", default=[], metavar="CIDR", help="scan this subnet; repeatable")
    parser.add_argument("--all", action="store_true", help="return every detected device")
    parser.add_argument("--allow-large-scan", action="store_true")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--workers", type=int, default=48)
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def main(argv=None):
    args = make_parser().parse_args(argv)
    if not 1 <= args.port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    if not 1 <= args.workers <= 128:
        raise ValueError("workers must be between 1 and 128")
    if args.subnet:
        networks = parse_networks(args.subnet, args.allow_large_scan)
    else:
        networks = parse_networks([str(network) for network in local_networks()], args.allow_large_scan)
    if not networks:
        raise RuntimeError("no local IPv4 network detected; pass --subnet CIDR")
    if args.verbose:
        print("[*] scan networks: " + ", ".join(map(str, networks)), file=sys.stderr)

    cache_file = os.path.abspath(os.path.expanduser(args.cache_file))
    devices = discover(
        networks,
        port=args.port,
        all_devices=args.all,
        verbose=args.verbose,
        cache_file=cache_file,
        workers=args.workers,
    )
    if not devices:
        print("未找到小智设备", file=sys.stderr)
        return 1
    addresses = list(devices)
    if args.save:
        save_cache(addresses, cache_file)
    for address in addresses:
        print(address)
        if args.health:
            print(json.dumps(devices[address], indent=2, ensure_ascii=False), file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
