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
def default_cache_file():
    override = os.environ.get("XIAOZHI_CACHE_FILE")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA", os.path.expanduser("~/AppData/Local"))
    else:
        root = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    return os.path.join(root, "xiaozhi", "devices.txt")


DEFAULT_CACHE_FILE = default_cache_file()
LEGACY_CACHE_FILES = [os.path.expanduser("~/.hermes/xiaozhi_ip.txt"), os.path.expanduser("~/.cache/xiaozhi_ip.txt")]
DEFAULT_TIMEOUT = 3.0
DEFAULT_SCAN_TIMEOUT = 2.0
DEFAULT_WORKERS = 16
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
    return (isinstance(data, dict) and data.get("status") == "ok"
            and isinstance(data.get("board"), str) and bool(data["board"]))


def try_health(host, port=DEFAULT_PORT, timeout=DEFAULT_TIMEOUT):
    try:
        request = urllib.request.Request(f"http://{host}:{port}/", method="GET")
        with HEALTH_OPENER.open(request, timeout=timeout) as response:
            if response.status != 200:
                return None
            data = json.loads(response.read(65537).decode("utf-8"))
            return data if valid_health(data) else None
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def resolve_ipv4(host, port=DEFAULT_PORT):
    """Bound DNS/mDNS lookup too: socket timeouts do not bound getaddrinfo()."""
    if unique_private_ipv4([host]):
        return [host]
    code = "import json,socket,sys; print(json.dumps([r[4][0] for r in socket.getaddrinfo(sys.argv[1],int(sys.argv[2]),socket.AF_INET,socket.SOCK_STREAM)]))"
    try:
        result = subprocess.run([sys.executable, "-c", code, host, str(port)],
                                capture_output=True, text=True, timeout=3, check=False)
        addresses = json.loads(result.stdout)
        return unique_private_ipv4(addresses) if isinstance(addresses, list) else []
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return []


def resolve_mdns_candidates(port=DEFAULT_PORT):
    """Resolve the compatibility hostname and optionally browse HTTP mDNS services."""
    candidates = resolve_ipv4(MDNS_FALLBACK, port)

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
        candidates.extend(resolve_ipv4(match.group(1).rstrip("."), port))
    return unique_private_ipv4(candidates)


def read_cache(path=DEFAULT_CACHE_FILE):
    try:
        with open(path, encoding="utf-8") as handle:
            return unique_private_ipv4(line.strip() for line in handle)
    except OSError:
        return []


def cached_addresses(path=DEFAULT_CACHE_FILE):
    paths = [path] + (LEGACY_CACHE_FILES if path == DEFAULT_CACHE_FILE else [])
    return unique_private_ipv4(address for source in paths for address in read_cache(source))


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


def networks_from_windows(text):
    """PowerShell JSON avoids parsing translated ipconfig field names."""
    try:
        records = json.loads(text.lstrip("\ufeff"))
    except ValueError:
        return []
    if isinstance(records, dict):
        records = [records]
    networks = []
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        try:
            address = record["IPAddress"]
            network = ipaddress.ip_network(f"{address}/{int(record['PrefixLength'])}", strict=False)
            if is_trusted_network(network) and not network.is_loopback:
                networks.append(bounded_local_network(address, network))
        except (KeyError, ValueError, TypeError):
            continue
    return list(dict.fromkeys(networks))


def local_networks():
    """Read real interface prefixes on Linux, with a conservative /24 fallback."""
    networks = []
    if sys.platform == "win32":
        command = "Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.AddressState -eq 'Preferred'} | Select-Object IPAddress,PrefixLength | ConvertTo-Json -Compress"
        networks.extend(networks_from_windows(_bounded_command_output(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command], 5)))
        if networks:
            return networks
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
            if interface.get("ifname") == "lo" or interface.get("operstate") == "DOWN":
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


def scan_networks(networks, port=DEFAULT_PORT, timeout=DEFAULT_SCAN_TIMEOUT, workers=DEFAULT_WORKERS, all_devices=True, exclude=()):
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
        # Finish the small in-flight batch before callers start device control.
        pool.shutdown(wait=True, cancel_futures=True)
    return dict(sorted(found.items(), key=lambda item: ipaddress.ip_address(item[0])))


def discover(networks, port=DEFAULT_PORT, all_devices=False, verbose=False,
             cache_file=DEFAULT_CACHE_FILE, workers=DEFAULT_WORKERS,
             timeout=DEFAULT_TIMEOUT, scan_timeout=DEFAULT_SCAN_TIMEOUT, hosts=(),
             restrict_networks=False):
    found = {}

    def probe(stage, candidates):
        for address in candidates:
            if restrict_networks and not any(ipaddress.ip_address(address) in network for network in networks):
                continue
            if address in found:
                continue
            health = try_health(address, port, timeout)
            if health is None:
                # Only read-only identity checks are retried, once and serially.
                health = try_health(address, port, timeout)
            if health is not None:
                found[address] = health
                if verbose:
                    print(f"[*] {stage}: {address}", file=sys.stderr)
                if not all_devices:
                    return True
        return False

    if hosts:
        probe("explicit", unique_private_ipv4(address for host in hosts for address in resolve_ipv4(host, port)))
        return found
    if probe("cache", cached_addresses(cache_file)):
        return found
    if probe("mDNS", resolve_mdns_candidates(port)):
        return found
    if probe("UDP", udp_discover(networks)):
        return found
    if verbose:
        print(f"[*] subnet scan: {workers} workers, {scan_timeout:g}s per host", file=sys.stderr)
    scanned = scan_networks(networks, port=port, workers=workers, timeout=scan_timeout,
                            all_devices=all_devices, exclude=found)
    found.update(scanned)
    if verbose:
        for address in scanned:
            print(f"[*] scan: {address}", file=sys.stderr)
    return found


def make_parser():
    parser = argparse.ArgumentParser(description="Discover xiaozhi devices on local IPv4 networks")
    parser.add_argument("--health", action="store_true", help="print health JSON to stderr")
    parser.add_argument("--json", action="store_true", help="print a JSON array with IP, identity and firmware")
    parser.add_argument("--host", action="append", default=[], help="probe only this LAN IP/hostname; repeatable")
    parser.add_argument("--save", action="store_true", help="save discovered address(es)")
    parser.add_argument("--cache-file", default=DEFAULT_CACHE_FILE)
    parser.add_argument("--subnet", action="append", default=[], metavar="CIDR", help="scan this subnet; repeatable")
    parser.add_argument("--all", action="store_true", help="return every detected device")
    parser.add_argument("--allow-large-scan", action="store_true")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="known-host health timeout (seconds)")
    parser.add_argument("--scan-timeout", type=float, default=DEFAULT_SCAN_TIMEOUT, help="subnet health timeout (seconds)")
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def main(argv=None):
    args = make_parser().parse_args(argv)
    if not 1 <= args.port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    if not 1 <= args.workers <= 128:
        raise ValueError("workers must be between 1 and 128")
    if not 0 < args.timeout <= 30 or not 0 < args.scan_timeout <= 30:
        raise ValueError("timeouts must be in (0, 30] seconds")
    if args.host:
        networks = []
    elif args.subnet:
        networks = parse_networks(args.subnet, args.allow_large_scan)
    else:
        networks = parse_networks([str(network) for network in local_networks()], args.allow_large_scan)
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
        timeout=args.timeout,
        scan_timeout=args.scan_timeout,
        hosts=args.host,
        restrict_networks=bool(args.subnet) and not args.host,
    )
    if not devices:
        if args.json:
            print("[]")
        print("No XiaoZhi found. Check same LAN/Wi-Fi and power; try --host IP or --subnet CIDR --scan-timeout 4. VPN/guest isolation may block discovery.", file=sys.stderr)
        return 1
    addresses = list(devices)
    if args.save:
        save_cache(addresses, cache_file)
    if args.json:
        print(json.dumps([dict(devices[address], ip=address) for address in addresses], ensure_ascii=False, indent=2))
    for address in addresses:
        if not args.json:
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
