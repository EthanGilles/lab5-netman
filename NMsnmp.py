#!/usr/bin/env python3
import json
import time
from datetime import datetime
from collections import defaultdict
import matplotlib.pyplot as plt
from easysnmp import Session, exceptions

# Router configurations
ROUTERS = {
    'R1': {'host': '198.51.1.1', 'community': 'public'},
    'R2': {'host': '198.51.1.3', 'community': 'public'},
    'R3': {'host': '198.51.1.2', 'community': 'public'},
    'R4': {'host': '198.51.100.1', 'community': 'public'},
    'R5': {'host': '198.51.101.5', 'community': 'public'},
}

# SNMP OIDs
OID_IPV4_ADDRESS = '1.3.6.1.2.1.4.20.1.1'
OID_IPV4_IFINDEX = '1.3.6.1.2.1.4.20.1.2'
OID_IPV4_NETMASK = '1.3.6.1.2.1.4.20.1.4'
OID_IPV6_ADDRESS = '1.3.6.1.2.1.4.34.1.3'
OID_INTERFACE_STATUS = '1.3.6.1.2.1.2.2.1.8'
OID_INTERFACE_NAME = '1.3.6.1.2.1.2.2.1.2'
OID_CPU_USAGE = '1.3.6.1.4.1.9.9.109.1.1.1.1.5.1'

# Interface status mapping
INTERFACE_STATUS = {
    '1': 'up',
    '2': 'down',
    '3': 'testing',
    '4': 'unknown',
    '5': 'dormant',
    '6': 'notPresent',
    '7': 'lowerLayerDown'
}


def snmp_get(host, community, oid):
    try:
        session = Session(hostname=host, community=community, version=2, timeout=2, retries=2)
        result = session.get(oid)
        return result
    except exceptions.EasySNMPError as e:
        print(f"Error getting {oid} from {host}: {e}")
        return None
    except Exception as e:
        print(f"Exception getting {oid} from {host}: {e}")
        return None


def snmp_walk(host, community, oid):
    try:
        session = Session(hostname=host, community=community, version=2, timeout=2, retries=2)
        result = session.walk(oid)
        return result
    except exceptions.EasySNMPError as e:
        print(f"Error walking {oid} from {host}: {e}")
        return None
    except Exception as e:
        print(f"Exception walking {oid} from {host}: {e}")
        return None


def fetch_ipv4_addresses(host, community):
    """Fetch all IPv4 addresses"""
    ipv4_addresses = []
    try:
        # Get IPv4 addresses
        results = snmp_walk(host, community, OID_IPV4_ADDRESS)
        if results:
            for var in results:
                oid_parts = str(var.oid).split('.')
                if len(oid_parts) >= 4:
                    ip_addr = '.'.join(oid_parts[-4:])
                    ipv4_addresses.append(f"{ip_addr}/24")
    except Exception as e:
        print(f"Error fetching IPv4 from {host}: {e}")
    
    return ipv4_addresses
        
def fetch_ipv6_addresses(host, community):
    """Fetch all IPv6 addresses"""
    ipv6_addresses = []
    try:
        results = snmp_walk(host, community, OID_IPV6_ADDRESS)
        
        if results:
            for i, var in enumerate(results):
                try:
                    oid_str = str(var.oid)
                    # Remove 'iso' prefix if present
                    if oid_str.startswith('iso.'):
                        oid_str = oid_str[4:]
                    
                    parts = oid_str.split('.')
                    base_parts = 9
                    
                    if len(parts) >= base_parts + 18:  # ifIndex(1) + addressType(1) + address(16)
                        addr_indices = parts[base_parts + 2:base_parts + 18]
                        if len(addr_indices) == 16:
                            addr_bytes = [format(int(idx), '02x') for idx in addr_indices]
                            ipv6_addr = ':'.join([''.join(addr_bytes[i:i+2]) for i in range(0, 16, 2)])
                            ipv6_addresses.append(f"{ipv6_addr}/64")
                except Exception as e:
                    continue
    except Exception as e:
        print(f"Error fetching IPv6 from {host}: {e}")
    
    return ipv6_addresses


def fetch_interface_status(host, community):
    interface_data = {}
    interface_names = {}
    
    try:
        # Get interface names
        results = snmp_walk(host, community, OID_INTERFACE_NAME)
        if results:
            for var in results:
                oid_parts = var.oid.split('.')
                if_index = oid_parts[-1]
                interface_names[if_index] = var.value
        
        # Get interface status
        results = snmp_walk(host, community, OID_INTERFACE_STATUS)
        if results:
            for var in results:
                oid_parts = var.oid.split('.')
                if_index = oid_parts[-1]
                status_code = var.value
                status = INTERFACE_STATUS.get(status_code, 'unknown')
                
                if_name = interface_names.get(if_index, f'if{if_index}')
                # Skip Null0 interface
                if if_name.lower() != 'null0':
                    interface_data[if_name] = status
    except Exception as e:
        print(f"Error fetching interfaces from {host}: {e}")
    
    return interface_data


def fetch_cpu_utilization(host, community):
    try:
        result = snmp_get(host, community, OID_CPU_USAGE)
        if result:
            return int(result.value)
    except Exception as e:
        print(f"Error fetching CPU from {host}: {e}")
    return None


def collect_network_data():
    addresses_data = {}
    interface_data = {}
    
    for router_name, router_info in ROUTERS.items():
        host = router_info['host']
        community = router_info['community']
        
        print(f"\nFetching data from {router_name} ({host})...")
        ipv4_addresses = fetch_ipv4_addresses(host, community)
        ipv6_addresses = fetch_ipv6_addresses(host, community)
        router_addresses = {
            'v4': ipv4_addresses,
            'v6': ipv6_addresses
        }
        
        addresses_data[router_name] = router_addresses
        interfaces = fetch_interface_status(host, community)
        interface_data[router_name] = interfaces
    
    return addresses_data, interface_data


def save_network_data(addresses_data, interface_data, filename='snmp_data.txt'):
    output_data = {
        "addresses": addresses_data,
        "interface_status": interface_data
    }
    try:
        with open(filename, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"\nNetwork data saved to {filename}")
        return True
    except Exception as e:
        print(f"Error saving data to {filename}: {e}")
        return False


def monitor_cpu_utilization(router_name, duration_seconds=120, interval_seconds=5):
    router_info = ROUTERS.get(router_name)
    if not router_info:
        print(f"Router {router_name} not found in configuration")
        return None
    
    host = router_info['host']
    community = router_info['community']
    
    cpu_data = {
        'timestamps': [],
        'cpu_values': []
    }
    
    start_time = time.time()
    sample_count = 0
    
    print(f"\nMonitoring CPU utilization of {router_name} for {duration_seconds} seconds...")
    print("(Collecting CPU data at 5-second intervals)")
    
    while (time.time() - start_time) < duration_seconds:
        try:
            cpu_value = fetch_cpu_utilization(host, community)
            if cpu_value is not None:
                timestamp = time.time() - start_time
                cpu_data['timestamps'].append(round(timestamp, 1))
                cpu_data['cpu_values'].append(cpu_value)
                sample_count += 1
                print(f"  Sample {sample_count}: {cpu_value}% at {round(timestamp, 1)}s")
            
            # Wait for next interval
            time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\nMonitoring interrupted by user")
            break
        except Exception as e:
            print(f"Error during monitoring: {e}")
            time.sleep(interval_seconds)
    
    return cpu_data


def plot_cpu_utilization(cpu_data, router_name='R1', filename='cpu_utilization.jpg'): 
    try:
        plt.figure(figsize=(12, 6))
        plt.plot(cpu_data['timestamps'], cpu_data['cpu_values'], linewidth=2, marker='o', markersize=4, color='#2E86AB')
        
        plt.title(f'{router_name} CPU Utilization Over 2 Minutes', fontsize=14, fontweight='bold')
        plt.xlabel('Time (seconds)', fontsize=12)
        plt.ylabel('CPU Utilization (%)', fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.ylim(0, 100)
        
        # Add stats annotation
        avg_cpu = sum(cpu_data['cpu_values']) / len(cpu_data['cpu_values'])
        max_cpu = max(cpu_data['cpu_values'])
        min_cpu = min(cpu_data['cpu_values'])
        
        stats_text = f'Avg: {avg_cpu:.1f}% | Max: {max_cpu}% | Min: {min_cpu}%'
        # Place the stats text in the upper left corner of the plot
        plt.text(0.02, 0.95, stats_text, transform=plt.gca().transAxes,
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5),
                verticalalignment='top', fontsize=10)
        
        plt.tight_layout()
        plt.savefig(filename, format='jpg')
        print(f"\nCPU utilization graph saved to {filename}")
        plt.close()
        return True
    except Exception as e:
        print(f"Error plotting CPU data: {e}")
        return False


def main():
    print("SNMP Network Monitoring Script")
    
    print("\nStep 1: Collecting Network Data from all routers")
    addresses_data, interface_data = collect_network_data()
    
    print("\nStep 2: Saving Network Data")
    save_network_data(addresses_data, interface_data, 'snmp_data.txt')
    
    print("\nStep 3: Monitoring R1 CPU Utilization")
    cpu_data = monitor_cpu_utilization('R1', duration_seconds=120, interval_seconds=5)
    
    if cpu_data:
        print("\nStep 4: Generating CPU Utilization Graph...")
        plot_cpu_utilization(cpu_data, 'R1', 'cpu_utilization.jpg')

if __name__ == '__main__':
    main()
