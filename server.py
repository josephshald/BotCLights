from flask import Flask, request, render_template_string
from rpi_ws281x import PixelStrip, Color
import threading, json, os, tempfile, time, random

# -----------------------------
# Config
# -----------------------------
NUM_LEDS = 20
STATE_PATH = "/home/pi/led_state.json"

LED_PIN = 18
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 255
LED_INVERT = False
LED_CHANNEL = 0

# -----------------------------
# State
# -----------------------------
labels = [f"LED {i}" for i in range(NUM_LEDS)]
modes  = ["off"] * NUM_LEDS
state_version = 0

state_lock = threading.Lock()
led_hw_lock = threading.Lock()
show_lock = threading.Lock()

# -----------------------------
# Flask
# -----------------------------
app = Flask(__name__)

# -----------------------------
# LED setup
# -----------------------------
strip = PixelStrip(
    NUM_LEDS,
    LED_PIN,
    LED_FREQ_HZ,
    LED_DMA,
    LED_INVERT,
    LED_BRIGHTNESS,
    LED_CHANNEL
)
strip.begin()

# -----------------------------
# Helpers
# -----------------------------
def bump_version():
    global state_version
    state_version += 1

def color_for_mode(mode):
    # GRB order
    if mode == "off":    return Color(0, 0, 0)
    if mode == "white":  return Color(255, 255, 255)
    if mode == "purple": return Color(0, 128, 128)
    if mode == "yellow": return Color(255, 255, 0)
    if mode == "red":    return Color(0, 255, 0)
    return Color(0, 0, 0)

def render_leds():
    with state_lock:
        current_modes = list(modes)
    with led_hw_lock:
        for i in range(NUM_LEDS):
            strip.setPixelColor(i, color_for_mode(current_modes[i]))
        strip.show()

def load_state():
    global labels, modes
    if not os.path.exists(STATE_PATH):
        return
    with open(STATE_PATH, "r") as f:
        data = json.load(f)
    labels = data.get("labels", labels)
    modes  = data.get("modes", modes)

def save_state():
    data = {"labels": labels, "modes": modes}
    d = os.path.dirname(STATE_PATH)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".led_state_", text=True)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.replace(tmp, STATE_PATH)

# -----------------------------
# Colors (GRB)
# -----------------------------
OFF    = Color(0, 0, 0)
WHITE  = Color(255, 255, 255)
BLUE   = Color(0, 0, 255)
RED    = Color(0, 255, 0)
ORANGE = Color(80, 255, 0)

# -----------------------------
# Animations
# -----------------------------
def chase_fill(color, delay_s):
    for i in range(NUM_LEDS):
        strip.setPixelColor(i, color)
        strip.show()
        time.sleep(delay_s)

def light_display_2s():
    total = 2.0
    delay = (total / 3) / max(NUM_LEDS, 1)
    chase_fill(BLUE, delay)
    chase_fill(WHITE, delay)
    chase_fill(OFF, delay)

def show_good_team_wins_10s():
    """
    Blue-heavy fireworks with white highlights
    """
    duration = 10.0
    start = time.time()

    levels = [0] * NUM_LEDS
    colors = [BLUE] * NUM_LEDS

    with led_hw_lock:
        while time.time() - start < duration:
            for _ in range(random.randint(3, 7)):
                idx = random.randrange(NUM_LEDS)
                levels[idx] = random.randint(170, 255)
                colors[idx] = BLUE if random.random() < 0.8 else WHITE

            if random.random() < 0.22:
                center = random.randrange(NUM_LEDS)
                burst_color = BLUE if random.random() < 0.85 else WHITE
                for d in (-2, -1, 0, 1, 2):
                    j = center + d
                    if 0 <= j < NUM_LEDS:
                        levels[j] = max(levels[j], random.randint(190, 255))
                        colors[j] = burst_color

            for i in range(NUM_LEDS):
                levels[i] = max(0, levels[i] - random.randint(30, 60))
                lvl = levels[i]
                c = colors[i]
                g = (c >> 16) & 0xFF
                r = (c >> 8) & 0xFF
                b = c & 0xFF
                strip.setPixelColor(i, Color((g * lvl)//255, (r * lvl)//255, (b * lvl)//255))

            strip.show()
            time.sleep(0.045)

def show_bad_team_wins_10s():
    """
    Darker, slower, heavier hellfire (red + orange only).
    With cooling so it never gets stuck orange.
    """
    duration = 10.0
    start = time.time()

    heat = [random.randint(5, 70) for _ in range(NUM_LEDS)]

    with led_hw_lock:
        while time.time() - start < duration:
            for i in range(NUM_LEDS):
                heat[i] += random.randint(-35, 25)
                heat[i] -= random.randint(8, 18)
                heat[i] = max(0, min(255, heat[i]))

            if random.random() < 0.25:
                p = random.randrange(NUM_LEDS)
                heat[p] = min(255, heat[p] + random.randint(170, 230))
                if p > 0:
                    heat[p-1] = min(255, heat[p-1] + random.randint(70, 140))
                if p < NUM_LEDS - 1:
                    heat[p+1] = min(255, heat[p+1] + random.randint(70, 140))

            for i in range(NUM_LEDS):
                h = heat[i]
                if h < 210:
                    c = RED
                    scale = int(h * 1.5)
                else:
                    c = ORANGE
                    scale = h

                g = (c >> 16) & 0xFF
                r = (c >> 8) & 0xFF
                b = c & 0xFF
                strip.setPixelColor(i, Color((g * scale)//255, (r * scale)//255, (b * scale)//255))

            strip.show()
            time.sleep(0.09)

def run_show_and_restore(fn):
    if not show_lock.acquire(blocking=False):
        return
    try:
        fn()
    finally:
        render_leds()
        show_lock.release()

# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def index():
    with state_lock:
        return render_template_string(
            HTML,
            labels=list(labels),
            modes=list(modes),
            num_leds=NUM_LEDS
        )

@app.route("/set_mode", methods=["POST"])
def set_mode():
    d = request.json
    with state_lock:
        modes[int(d["index"])] = d["mode"]
    render_leds()
    save_state()
    bump_version()
    return "ok"

@app.route("/set_label", methods=["POST"])
def set_label():
    d = request.json
    with state_lock:
        labels[int(d["index"])] = d["label"][:60]
    save_state()
    bump_version()
    return "ok"

@app.route("/clear_all", methods=["POST"])
def clear_all():
    with state_lock:
        for i in range(NUM_LEDS):
            modes[i] = "off"
    render_leds()
    save_state()
    bump_version()
    return "ok"

@app.route("/reset_labels", methods=["POST"])
def reset_labels():
    with state_lock:
        for i in range(NUM_LEDS):
            labels[i] = f"LED {i}"
    save_state()
    bump_version()
    return "ok"

@app.route("/light_display", methods=["POST"])
def light_display():
    threading.Thread(target=lambda: run_show_and_restore(light_display_2s), daemon=True).start()
    return "ok"

@app.route("/good_team_wins", methods=["POST"])
def good_team_wins():
    threading.Thread(target=lambda: run_show_and_restore(show_good_team_wins_10s), daemon=True).start()
    return "ok"

@app.route("/bad_team_wins", methods=["POST"])
def bad_team_wins():
    threading.Thread(target=lambda: run_show_and_restore(show_bad_team_wins_10s), daemon=True).start()
    return "ok"

@app.route("/state_version")
def version():
    return str(state_version)

# -----------------------------
# HTML
# -----------------------------
HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>BOTC Lights - One</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body{
      background:#111;
      color:#fff;
      font-family:sans-serif;
      padding:10px;
      margin:0;
    }
    h2{
      margin:0 0 8px 0;
      font-size:1.1em;
    }
    .row{
      display:flex;
      align-items:center;
      gap:8px;
      margin:2px 0;
      flex-wrap:nowrap;
    }
    .row span{
      width:1.3em;
      text-align:center;
    }
    input, select, button{
      font-size:0.95em;
    }
    input{
      width:150px;
      padding:2px 6px;
      box-sizing:border-box;
    }
    select{
      width:120px;
      padding:2px 6px;
    }
    hr{ margin:12px 0; }
    .controls{
      display:flex;
      gap:10px;
      align-items:center;
      flex-wrap:wrap;
    }
    button{
      padding:6px 14px;
      cursor:pointer;
    }
    .hidden-row{ display:none; }
  </style>
</head>
<body>

<h2>BOTC Lights - One</h2>

<div id="rows">
{% for i in range(num_leds) %}
  <div class="row" data-index="{{i}}">
    <span>
      {% if modes[i]=="off" %}⚫
      {% elif modes[i]=="white" %}⚪
      {% elif modes[i]=="purple" %}🟣
      {% elif modes[i]=="yellow" %}🟡
      {% elif modes[i]=="red" %}🔴
      {% endif %}
    </span>

    <input value="{{labels[i]}}" oninput="setLabel({{i}}, this.value); applyHideFilter();">
    <select onchange="setMode({{i}}, this.value)">
      {% for m in ["off","white","purple","yellow","red"] %}
        <option value="{{m}}" {% if modes[i]==m %}selected{% endif %}>{{m}}</option>
      {% endfor %}
    </select>
  </div>
{% endfor %}
</div>

<hr>

<div class="controls">
  <button onclick="toggleHideDefaults()" id="hideBtn">🙈 Hide default/blank labels</button>
  <button onclick="testLights()">✨ Test lights</button>
  <button onclick="goodTeamWins()">🎆 Good team wins</button>
  <button onclick="badTeamWins()">🔥 Bad team wins</button>
  <button onclick="resetLabels()">📝 Reset labels</button>
  <button onclick="clearAll()">🧹 Clear all</button>
</div>

<script>
let lastVersion = null;
let hideDefaults = (localStorage.getItem("hideDefaults") === "1");

function isDefaultOrBlank(label, index){
  const t = (label || "").trim();
  if (t.length === 0) return true;
  return t === ("LED " + index);
}

function applyHideFilter(){
  if (!hideDefaults){
    document.querySelectorAll(".row").forEach(r => r.classList.remove("hidden-row"));
    return;
  }
  document.querySelectorAll(".row").forEach(r => {
    const idx = parseInt(r.getAttribute("data-index"), 10);
    const input = r.querySelector("input");
    const label = input ? input.value : "";
    if (isDefaultOrBlank(label, idx)) r.classList.add("hidden-row");
    else r.classList.remove("hidden-row");
  });
}

function updateHideButton(){
  const btn = document.getElementById("hideBtn");
  btn.textContent = hideDefaults ? "👁️ Show all rows" : "🙈 Hide default/blank labels";
}

function toggleHideDefaults(){
  hideDefaults = !hideDefaults;
  localStorage.setItem("hideDefaults", hideDefaults ? "1" : "0");
  updateHideButton();
  applyHideFilter();
}

// restore state on load + preserve scroll
window.addEventListener("load", ()=>{
  updateHideButton();
  applyHideFilter();

  const y = sessionStorage.getItem("scrollY");
  if(y !== null){
    window.scrollTo(0, parseInt(y,10) || 0);
    sessionStorage.removeItem("scrollY");
  }
});

function setMode(i, m){
  fetch("/set_mode",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({index:i,mode:m})});
}

function setLabel(i, l){
  fetch("/set_label",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({index:i,label:l})});
}

function clearAll(){
  if(!confirm("Clear ALL LEDs (set them all to off)?")) return;
  fetch("/clear_all",{method:"POST"}).then(()=>location.reload());
}

function resetLabels(){
  if(!confirm("Reset ALL label names?")) return;
  fetch("/reset_labels",{method:"POST"}).then(()=>{
    // NEW: after resetting labels, force all rows visible
    localStorage.setItem("hideDefaults", "0");
    location.reload();
  });
}

function testLights(){
  fetch("/light_display",{method:"POST"});
}

function goodTeamWins(){
  fetch("/good_team_wins",{method:"POST"});
}

function badTeamWins(){
  fetch("/bad_team_wins",{method:"POST"});
}

async function poll(){
  try{
    const v = await fetch("/state_version",{cache:"no-store"}).then(r=>r.text());
    if(lastVersion === null){ lastVersion = v; return; }
    if(v !== lastVersion){
      const active = document.activeElement;
      if(active && active.tagName === "INPUT"){
        lastVersion = v;
        return;
      }
      sessionStorage.setItem("scrollY", String(window.scrollY));
      location.reload();
    }
  }catch(e){}
}

setInterval(poll,1000);
</script>

</body>
</html>
"""

# -----------------------------
# Startup
# -----------------------------
if __name__ == "__main__":
    load_state()
    # startup plug-check (2s), then restore
    run_show_and_restore(light_display_2s)
    app.run(host="0.0.0.0", port=5000)


