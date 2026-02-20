#!/usr/bin/env python3
import re
import time
from netmiko import ConnectHandler
from sshInfo import load_ssh_info
from NMtcpdump import extract_mac_addresses


def get_r5_ipv6_from_r4(routers_info):
    r4_info = next((r for r in routers_info if r.get("name") == "R4"), None)
    if not r4_info:
        raise ValueError("R4 not found in SSH info")
    
    device_config = {
        'device_type': 'cisco_ios',
        'host': r4_info["host"],
        'port': r4_info.get("port", 22),
        'username': r4_info["username"],
        'password': r4_info["password"]
    }
    
    device = ConnectHandler(**device_config)
    output = device.send_command("show ipv6 neighbors F0/0")
    print(f"R4 F0/0 Neighbors:\n{output}")
    device.disconnect()
    
    # Looking for addresses starting with 2001:db8:1: that appear on F0/0
    for line in output.split('\n'):
        line = line.lower()
        # Skip link-local addresses (FE80) and focus on global addresses (2001:db8:1:)
        if '2001:db8:1:' in line:
            match = re.search(r'(2001:db8:1:[0-9a-f:]+)', line)
            if match:
                return match.group(1)
    
    raise ValueError("Could not extract R5-F0/0 IPv6 address from R4")


def configure_dhcp_on_r5(r5_ipv6, mac_addresses, routers_info):
    """SSH to R5 and configure DHCP pools."""
    r5_info = next((r for r in routers_info if r.get("name") == "R5"), None)
    if not r5_info:
        raise ValueError("R5 not found in SSH info")
    device_config = {
        'device_type': 'cisco_ios',
        'host': r5_ipv6,
        'port': r5_info.get("port", 22),
        'username': r5_info["username"],
        'password': r5_info["password"]
    }
    
    device = ConnectHandler(**device_config)
    
    # Configure DHCP on R5
    commands = [
        "service dhcp",
        "ip dhcp excluded-address 198.51.101.5",
        "ip dhcp excluded-address 198.51.101.254",
        # Host pool for R2-F0/0
        "ip dhcp pool R2_POOL",
        "host 198.51.101.2 255.255.255.0",
        f"hardware-address {mac_addresses['R2-F0/0']} ieee802",
        "default-router 198.51.101.5",
        "exit",
        # Host pool for R3-F0/0
        "ip dhcp pool R3_POOL",
        "host 198.51.101.4 255.255.255.0",
        f"hardware-address {mac_addresses['R3-F0/0']} ieee802",
        "default-router 198.51.101.5",
        "exit",
        # Dynamic pool for R4-F0/0
        "ip dhcp pool R4_POOL",
        "network 198.51.101.0 255.255.255.0",
        "default-router 198.51.101.5",
        "excluded-address 198.51.101.1 198.51.101.5",
        "lease 1",
    ]
    output = device.send_config_set(commands)
    device.disconnect()
    
    return output


def get_dhcp_bindings(r5_ipv6, routers_info):
    r5_info = next((r for r in routers_info if r.get("name") == "R5"), None)
    if not r5_info:
        raise ValueError("R5 not found in SSH info")
    
    device_config = {
        'device_type': 'cisco_ios',
        'host': r5_ipv6,
        'port': r5_info.get("port", 22),
        'username': r5_info["username"],
        'password': r5_info["password"]
    }
    
    device = ConnectHandler(**device_config)
    output = device.send_command("show ip dhcp binding")
    print(f"R5 DHCP Bindings:\n{output}")
    device.disconnect()
    
    client_ips = []
    for line in output.split('\n'):
        # Parse lines with format: IP MAC Type Lease Time
        parts = line.split()
        if len(parts) >= 2 and re.match(r'\d+\.\d+\.\d+\.\d+', parts[0]):
            client_ips.append(parts[0])
    
    return client_ips


def main():
    """Main function to configure DHCP on R5."""
    print("Extracting MAC addresses from pcap file...")
    mac_addresses, ipv6_addresses = extract_mac_addresses()
    print(f"R2-F0/0 IPv6: {ipv6_addresses['R2-F0/0']}")
    print(f"R2-F0/0 MAC: {mac_addresses['R2-F0/0']}")
    print(f"R3-F0/0 IPv6: {ipv6_addresses['R3-F0/0']}")
    print(f"R3-F0/0 MAC: {mac_addresses['R3-F0/0']}")
    
    print("\nLoading SSH information...")
    routers_info = load_ssh_info()
    
    print("Getting R5-F0/0 IPv6 address from R4...")
    r5_ipv6 = get_r5_ipv6_from_r4(routers_info)
    print(f"R5-F0/0 IPv6: {r5_ipv6}")
    
    print("Configuring DHCP on R5...")
    configure_dhcp_on_r5(r5_ipv6, mac_addresses, routers_info)
    print("DHCP configuration complete!")
    
    print("Waiting 30 seconds for DHCP clients to obtain IP addresses...")
    time.sleep(30)
    
    print("Retrieving DHCP client bindings...")
    client_ips = get_dhcp_bindings(r5_ipv6, routers_info)
    
    print("\nDHCPv4 Client IP Addresses:")
    for ip in sorted(client_ips):
        print(f"  - {ip}")


if __name__ == "__main__":
    main()
