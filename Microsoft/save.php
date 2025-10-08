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

error_log("captive-portal: $line");

header('Location: password.php?user=' . urlencode($user), true, 303);
exit;


