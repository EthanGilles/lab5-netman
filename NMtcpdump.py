from scapy.all import rdpcap, IPv6
from netaddr import EUI, IPAddress


def eui64_to_mac(ipv6_addr):
    iid = int(IPAddress(ipv6_addr)) & 0xFFFFFFFFFFFFFFFF
    # Build EUI-64, flip bit 7, then remove the FF:FE to get the 48-bit MAC
    eui64 = EUI(iid, version=64)
    eui64[0] = eui64[0] ^ 0x02
    # Remove middle FF:FE bytes (bytes 3-4) to form EUI-48
    mac = EUI(str(eui64).replace("FF-FE-", ""))
    return str(mac)


def extract_mac_addresses():
    """Extract MAC addresses and IPv6 addresses of R2-F0/0 and R3-F0/0 from pcap file."""
    src_addrs = set()
    for pkt in rdpcap("lab5.pcap"):
        if pkt.haslayer(IPv6):
            src_addrs.add(pkt[IPv6].src)

    eui64_addrs = sorted(addr for addr in src_addrs if "2001:db8:1:" in addr)

    mac_addresses = {}
    ipv6_addresses = {}
    names = ["R2-F0/0", "R3-F0/0"]
    for name, addr in zip(names, eui64_addrs):
        mac_addresses[name] = eui64_to_mac(addr)
        ipv6_addresses[name] = addr
    
    return mac_addresses, ipv6_addresses


if __name__ == "__main__":
    mac_addresses, ipv6_addresses = extract_mac_addresses()
    for name in ["R2-F0/0", "R3-F0/0"]:
        if name in mac_addresses:
            print(f"{name} IPv6: {ipv6_addresses[name]}")
            print(f"{name} MAC:  {mac_addresses[name]}")

