import os
import sys
import time
import socket
import struct
import hashlib
import threading


host_name = socket.gethostname()
if host_name.count('-') >= 1:
    job_name = '-'.join(host_name.split('-')[:-1])
else:
    job_name = host_name
jash = int.from_bytes(hashlib.sha256(job_name.encode()).digest(), 'little')
MCAST_GRP = os.environ.get('DISCOVERY_GROUP', '224.1.%d.%d' % (1 + (jash % 254), 1 + ((jash // 254) % 254)))
MCAST_PORT = int(os.environ.get('DISCOVERY_PORT', 16307))
MULTICAST_TTL = int(os.environ.get('DISCOVERY_TTL', 8))
HEARTBEAT_INTERVAL = float(os.environ.get('DISCOVERY_INT', 1.0))
DISCOVERY_OUTPUT = os.environ.get('DISCOVERY_OUTPUT', 'bash')
DISCOVERY_DEBUG = int(os.environ.get('DISCOVERY_DEBUG', '0'))
if DISCOVERY_DEBUG:
    DISCOVERY_OUTPUT = 'all'
end = False
N_NODES = int(sys.argv[-1])


def whoami():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((MCAST_GRP, 80))
    addr = s.getsockname()[0]
    s.close()
    return addr


def sender():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, MULTICAST_TTL)
    try:
        while not end:
            time.sleep(HEARTBEAT_INTERVAL)
            sock.sendto(b'hb', (MCAST_GRP, MCAST_PORT))
    finally:
        sock.close()


def receiver():
    global end
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', MCAST_PORT))
    mreq = struct.pack("4sl", socket.inet_aton(MCAST_GRP), socket.INADDR_ANY)

    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.settimeout(HEARTBEAT_INTERVAL * 2 + 1)
    addrs = set()
    if DISCOVERY_DEBUG:
        print(MCAST_GRP, job_name, host_name, whoami())
    try:
        while not end:
            try:
                data, (ip, port) = (sock.recvfrom(10240))
            except socket.timeout:
                continue
            if DISCOVERY_DEBUG:
                print(data, (ip, port))
            if data != b'hb':
                print('Got Interference on Discovery Service!!!', data)
            else:
                addrs.add(ip)
                if len(addrs) == N_NODES:
                    end = True
                    break
    finally:
        sock.close()
    rank = sorted(addrs).index(whoami())
    master = sorted(addrs)[0]
    if DISCOVERY_OUTPUT == 'bash':
        print("export NODE_RANK=%d" % rank)
        print("export MASTER_ADDR=%s" % master)
    if DISCOVERY_OUTPUT == 'cmd':
        print("set NODE_RANK=%d" % rank)
        print("set MASTER_ADDR=%s" % master)
    if DISCOVERY_OUTPUT == 'ini':
        print("NODE_RANK=%d" % rank)
        print("MASTER_ADDR=%s" % master)
    if DISCOVERY_OUTPUT == 'all':
        for addr in sorted(addrs):
            print(addr)
        print("whoami:", rank, sorted(addrs)[rank])


def main():
    t1 = threading.Thread(target=receiver)
    t1.start()
    t2 = threading.Thread(target=sender)
    t2.start()
    t1.join()
    t2.join()


if __name__ == '__main__':
    main()
