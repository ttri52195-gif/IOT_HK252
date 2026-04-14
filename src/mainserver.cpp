#include "mainserver.h"
#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <Preferences.h>

bool isAPMode = true;

WebServer server(80);
DNSServer dnsServer;
Preferences wifiPrefs;

unsigned long connect_start_ms = 0;
bool connecting = false;
String connect_state = "idle"; // idle | connecting | success | failed
String last_sta_ip = "";

static const byte DNS_PORT = 53;

void saveWifiCredentials(const String &savedSsid, const String &savedPass)
{
  wifiPrefs.begin("wifi_cfg", false);
  wifiPrefs.putString("ssid", savedSsid);
  wifiPrefs.putString("pass", savedPass);
  wifiPrefs.end();
}

bool loadWifiCredentials(String &savedSsid, String &savedPass)
{
  wifiPrefs.begin("wifi_cfg", true);
  savedSsid = wifiPrefs.getString("ssid", "");
  savedPass = wifiPrefs.getString("pass", "");
  wifiPrefs.end();
  return savedSsid.length() > 0;
}

String escapeJsonString(const String &in)
{
  String out;
  out.reserve(in.length() + 8);
  for (size_t i = 0; i < in.length(); i++)
  {
    char c = in[i];
    if (c == '\\' || c == '"')
    {
      out += '\\';
      out += c;
    }
    else if (c == '\n')
    {
      out += "\\n";
    }
    else if (c == '\r')
    {
      out += "\\r";
    }
    else if (c == '\t')
    {
      out += "\\t";
    }
    else
    {
      out += c;
    }
  }
  return out;
}

bool isApModeRequest()
{
  return isAPMode;
}

String getApRootUrl()
{
  return "http://" + WiFi.softAPIP().toString() + "/";
}

void redirectToApRoot()
{
  server.sendHeader("Location", getApRootUrl(), true);
  server.send(302, "text/plain", "");
}

void handleCaptivePortal()
{
  if (isApModeRequest())
  {
    redirectToApRoot();
  }
  else
  {
    server.sendHeader("Location", "/", true);
    server.send(302, "text/plain", "");
  }
}

void handleGenerate204()
{
  server.send(204, "text/plain", "");
}

void handleHotspotDetect()
{
  server.send(200, "text/html", "<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>");
}

void handleConnectTestTxt()
{
  server.send(200, "text/plain", "Microsoft Connect Test");
}

void handleNcsiTxt()
{
  server.send(200, "text/plain", "Microsoft NCSI");
}

String mainPage()
{
  // String led1 = led1_state ? "ON" : "OFF";
  // String led2 = led2_state ? "ON" : "OFF";

  return R"rawliteral(
  <!DOCTYPE html>
  <html lang="vi">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ESP32 Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
      body {
        font-family: "Segoe UI", Arial, sans-serif;
        background: #f2f3f5;
        color: #333;
        text-align: center;
        margin: 0;
        min-height: 100vh;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 12px;
        box-sizing: border-box;
      }
      .container {
        background: linear-gradient(135deg, #1e90ff, #00bfff);
        padding: 20px 24px;
        border-radius: 20px;
        box-shadow: 0 4px 25px rgba(0,0,0,0.15);
        width: 100%;
        max-width: none;
        min-height: calc(100vh - 24px);
        box-sizing: border-box;
        color: #fff;
        display: flex;
        flex-direction: column;
      }
      h1 { font-size: 1.8em; margin-bottom: 15px; margin-top: 0; }
      .sensor-box {
        display: flex; justify-content: space-around;
        background: rgba(255, 255, 255, 0.2);
        border-radius: 15px; padding: 18px; margin-bottom: 16px;
      }
      .sensor { font-size: 1.2em; }
      .sensor span { font-weight: bold; font-size: 1.8em; }
      .charts-grid {
        display: grid;
        grid-template-columns: 1fr;
        gap: 16px;
        margin-bottom: 20px;
        flex: 1;
      }
      .chart-card {
        background: #fff;
        border-radius: 15px;
        padding: 12px;
        display: flex;
        flex-direction: column;
      }
      .chart-title {
        color: #333;
        font-weight: 700;
        margin: 0 0 8px 0;
        font-size: 1em;
      }
      .chart-card canvas {
        width: 100% !important;
        height: 240px !important;
      }
      @media (min-width: 740px) {
        .charts-grid {
          grid-template-columns: 1fr 1fr;
        }
        .chart-card canvas {
          height: 320px !important;
        }
      }
      button {
        margin: 5px; background: #00ffcc; color: #000;
        font-weight: bold; border: none; border-radius: 20px;
        padding: 10px 20px; cursor: pointer; transition: all 0.3s;
      }
      button:hover { background: #00e0b0; transform: scale(1.05); }
      #settings { background: #f2f3f5; color: #007bff; margin-top: 15px; }
      .led-mode-card {
        margin-top: 10px;
        background: rgba(255, 255, 255, 0.2);
        border-radius: 15px;
        padding: 12px;
      }
      .led-mode-title {
        font-weight: 700;
        margin: 0 0 8px 0;
      }
      .led-mode-row {
        display: flex;
        gap: 8px;
        align-items: center;
        justify-content: center;
        flex-wrap: wrap;
      }
      #manualColor {
        width: 54px;
        height: 36px;
        border: none;
        border-radius: 10px;
        padding: 0;
        background: #fff;
        cursor: pointer;
      }
      #manualLabel {
        font-weight: 600;
      }
    </style>
  </head>
  <body>
    <div class="container">
      <h1>📊 Thông số Môi trường</h1>
      
      <div class="sensor-box">
        <div class="sensor">🌡️ Nhiệt độ:<br><span id="temp">--</span> &deg;C</div>
        <div class="sensor">💧 Độ ẩm:<br><span id="hum">--</span> %</div>
      </div>

      <div class="charts-grid">
        <div class="chart-card">
          <p class="chart-title">Nhiệt độ (°C)</p>
          <canvas id="tempChart"></canvas>
        </div>
        <div class="chart-card">
          <p class="chart-title">Độ ẩm (%)</p>
          <canvas id="humChart"></canvas>
        </div>
      </div>
      <p id="chartStatus" style="margin:0 0 12px 0;font-weight:600;"></p>

      <div>
        <button id="btnLed1" onclick='toggleLED(1)' style="display:none;">💡 LED1: <span id="l1">OFF</span></button>
      </div>

      <div class="led-mode-card">
        <p class="led-mode-title">LED mode (Task 1/2/3)</p>
        <div class="led-mode-row">
          <button id="btnAuto" onclick="setLedMode('auto')">AUTO</button>
          <button id="btnManual" onclick="setLedMode('manual')">MANUAL</button>
        </div>
        <div class="led-mode-row" style="margin-top:8px;">
          <span id="manualLabel">Màu LED RGB:</span>
          <input id="manualColor" type="color" value="#0000ff" onchange="setManualColor(this.value)">
        </div>
        <div class="led-mode-row" style="margin-top:8px;">
          <span id="brightnessLabel">Độ sáng:</span>
          <input id="brightnessSlider" type="range" min="0" max="100" value="100" onchange="setLedBrightness(this.value)" style="width: 100px;">
          <span id="brightnessValue">100%</span>
        </div>
      </div>

      <button id="settings" onclick="window.location='/settings'">⚙️ Cài đặt Wi-Fi</button>
    </div>

    <script>
      const samplePeriodSec = 5; // temp_humi_monitor updates every 5 seconds

      function buildTimeLabels(n) {
        const labels = [];
        const start = -(n - 1) * samplePeriodSec;
        for (let i = 0; i < n; i++) {
          const sec = start + i * samplePeriodSec;
          labels.push(sec + 's');
        }
        return labels;
      }

      let tempChart = null;
      let humChart = null;
      let useFallbackCanvas = false;
      let fallbackAnimFrameId = null;

      if (window.Chart) {
        document.getElementById('chartStatus').innerText = '';
        const tempCtx = document.getElementById('tempChart').getContext('2d');
        tempChart = new Chart(tempCtx, {
          type: 'line',
          data: {
            labels: buildTimeLabels(10),
            datasets: [
              {
                label: 'Nhiệt độ (°C)',
                borderColor: '#ff4757',
                backgroundColor: 'rgba(255, 71, 87, 0.18)',
                data: [],
                tension: 0.35,
                fill: true
              }
            ]
          },
          options: {
            plugins: { legend: { display: false } },
            responsive: true,
            maintainAspectRatio: false,
            scales: {
              x: { title: { display: true, text: 'Thời gian (10 mẫu gần nhất)' } },
              y: { title: { display: true, text: 'Nhiệt độ (°C)' }, min: 0, max: 40 }
            }
          }
        });

        const humCtx = document.getElementById('humChart').getContext('2d');
        humChart = new Chart(humCtx, {
          type: 'line',
          data: {
            labels: buildTimeLabels(10),
            datasets: [
              {
                label: 'Độ ẩm (%)',
                borderColor: '#1e90ff',
                backgroundColor: 'rgba(30, 144, 255, 0.18)',
                data: [],
                tension: 0.35,
                fill: true
              }
            ]
          },
          options: {
            plugins: { legend: { display: false } },
            responsive: true,
            maintainAspectRatio: false,
            scales: {
              x: { title: { display: true, text: 'Thời gian (10 mẫu gần nhất)' } },
              y: { title: { display: true, text: 'Độ ẩm (%)' }, beginAtZero: true, suggestedMax: 100, min: 0 }
            }
          }
        });
      } else {
        useFallbackCanvas = true;
        document.getElementById('chartStatus').innerText = '';
        console.warn('Chart.js not loaded. Using fallback canvas charts.');
      }

      function drawFallbackChart(canvasId, values, lineColor, yMin, yMax, yAxisTitle, xAxisTitle, yStep, xOffsetPx = 0) {
        const canvas = document.getElementById(canvasId);
        if (!canvas || !values || values.length === 0) return;

        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        const cssWidth = canvas.clientWidth || 320;
        const cssHeight = canvas.clientHeight || 240;

        if (canvas.width !== Math.floor(cssWidth * dpr) || canvas.height !== Math.floor(cssHeight * dpr)) {
          canvas.width = Math.floor(cssWidth * dpr);
          canvas.height = Math.floor(cssHeight * dpr);
        }

        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.scale(dpr, dpr);
        ctx.clearRect(0, 0, cssWidth, cssHeight);

        const left = 46;
        const right = 8;
        const top = 8;
        const bottom = 34;
        const w = cssWidth - left - right;
        const h = cssHeight - top - bottom;
        if (w <= 0 || h <= 0) return;
        const stepX = values.length > 1 ? w / (values.length - 1) : 0;

        // Panel background for AP fallback (closer look to Chart.js card style)
        const panelGradient = ctx.createLinearGradient(0, top, 0, top + h);
        panelGradient.addColorStop(0, 'rgba(255,255,255,0.95)');
        panelGradient.addColorStop(1, 'rgba(248,250,255,0.98)');
        ctx.fillStyle = panelGradient;
        ctx.fillRect(left, top, w, h);

        // Axes
        ctx.strokeStyle = '#aab2c2';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(left, top);
        ctx.lineTo(left, top + h);
        ctx.lineTo(left + w, top + h);
        ctx.stroke();

        const step = Math.max(1, yStep || 10);
        const firstTick = Math.ceil(yMin / step) * step;

        ctx.strokeStyle = 'rgba(170, 178, 194, 0.35)';
        ctx.fillStyle = '#555555';
        ctx.font = '11px Segoe UI';
        ctx.textAlign = 'right';

        for (let tick = firstTick; tick <= yMax; tick += step) {
          const y = top + h - ((tick - yMin) / (yMax - yMin || 1)) * h;
          ctx.beginPath();
          ctx.moveTo(left, y);
          ctx.lineTo(left + w, y);
          ctx.stroke();
          ctx.fillText(String(tick), left - 6, y + 4);
        }

        // X grid lines and labels
        const timeLabels = buildTimeLabels(values.length);
        ctx.textAlign = 'center';
        ctx.fillStyle = '#666666';
        ctx.save();
        ctx.beginPath();
        ctx.rect(left, top, w, h + 16);
        ctx.clip();
        for (let i = 0; i < values.length; i++) {
          const x = left + (values.length === 1 ? 0 : (i * w) / (values.length - 1)) + xOffsetPx;
          ctx.beginPath();
          ctx.moveTo(x, top);
          ctx.lineTo(x, top + h);
          ctx.stroke();
          if (i % 2 === 0 || i === values.length - 1) {
            ctx.fillText(timeLabels[i], x, top + h + 14);
          }
        }
        ctx.restore();

        ctx.fillText(String(yMax), left - 6, top + 4);
        ctx.fillText(String(yMin), left - 6, top + h);

        // Axis titles (Vietnamese with full diacritics)
        ctx.textAlign = 'center';
        ctx.fillText(xAxisTitle, left + w / 2, cssHeight - 6);

        ctx.save();
        ctx.translate(12, top + h / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText(yAxisTitle, 0, 0);
        ctx.restore();

        // Build points first
        const points = [];
        for (let i = 0; i < values.length; i++) {
          const x = left + (values.length === 1 ? 0 : (i * w) / (values.length - 1)) + xOffsetPx;
          let v = Number(values[i]);
          if (Number.isNaN(v)) v = yMin;
          if (v < yMin) v = yMin;
          if (v > yMax) v = yMax;
          const y = top + h - ((v - yMin) / (yMax - yMin || 1)) * h;
          points.push({ x, y });
        }

        ctx.save();
        ctx.beginPath();
        ctx.rect(left, top, w, h);
        ctx.clip();

        // Filled area under line
        const areaGradient = ctx.createLinearGradient(0, top, 0, top + h);
        areaGradient.addColorStop(0, lineColor === '#ff4757' ? 'rgba(255, 71, 87, 0.25)' : 'rgba(30, 144, 255, 0.25)');
        areaGradient.addColorStop(1, lineColor === '#ff4757' ? 'rgba(255, 71, 87, 0.02)' : 'rgba(30, 144, 255, 0.02)');
        ctx.fillStyle = areaGradient;
        ctx.beginPath();
        ctx.moveTo(points[0].x, top + h);
        for (let i = 0; i < points.length; i++) {
          ctx.lineTo(points[i].x, points[i].y);
        }
        ctx.lineTo(points[points.length - 1].x, top + h);
        ctx.closePath();
        ctx.fill();

        // Data line
        ctx.strokeStyle = lineColor;
        ctx.lineWidth = 2.4;
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        ctx.beginPath();
        for (let i = 0; i < points.length; i++) {
          if (i === 0) {
            ctx.moveTo(points[i].x, points[i].y);
          } else {
            const prev = points[i - 1];
            const curr = points[i];
            const xc = (prev.x + curr.x) / 2;
            ctx.quadraticCurveTo(prev.x, prev.y, xc, (prev.y + curr.y) / 2);
            if (i === points.length - 1) {
              ctx.quadraticCurveTo(curr.x, curr.y, curr.x, curr.y);
            }
          }
        }
        ctx.stroke();

        // Point markers
        for (let i = 0; i < points.length; i++) {
          ctx.beginPath();
          ctx.fillStyle = '#ffffff';
          ctx.arc(points[i].x, points[i].y, 3.5, 0, 2 * Math.PI);
          ctx.fill();
          ctx.beginPath();
          ctx.fillStyle = lineColor;
          ctx.arc(points[i].x, points[i].y, 2.2, 0, 2 * Math.PI);
          ctx.fill();
        }
        ctx.restore();
      }

      function drawFallbackCharts(data, xOffsetPx = 0) {
        const tempData = (data.temp || []).map(Number);
        const humData = (data.hum || []).map(Number);

        drawFallbackChart('tempChart', tempData, '#ff4757', 0, 40, 'Nhiệt độ (°C)', 'Thời gian (10 mẫu gần nhất)', 5, xOffsetPx);
        drawFallbackChart('humChart', humData, '#1e90ff', 0, 100, 'Độ ẩm (%)', 'Thời gian (10 mẫu gần nhất)', 20, xOffsetPx);
      }

      function animateFallbackChartsLeft(data) {
        if (fallbackAnimFrameId) {
          cancelAnimationFrame(fallbackAnimFrameId);
          fallbackAnimFrameId = null;
        }

        const tempCanvas = document.getElementById('tempChart');
        const humCanvas = document.getElementById('humChart');
        const tempW = tempCanvas ? (tempCanvas.clientWidth || 320) : 320;
        const humW = humCanvas ? (humCanvas.clientWidth || 320) : 320;
        const count = Math.max((data.temp || []).length, (data.hum || []).length, 1);
        const tempStep = count > 1 ? (tempW - 46 - 8) / (count - 1) : 0;
        const humStep = count > 1 ? (humW - 46 - 8) / (count - 1) : 0;
        const startOffset = Math.max(0, Math.min(tempStep, humStep));

        const durationMs = 450;
        const startTs = performance.now();

        function frame(ts) {
          const progress = Math.min(1, (ts - startTs) / durationMs);
          const easeOut = 1 - Math.pow(1 - progress, 3);
          const offset = (1 - easeOut) * startOffset;

          drawFallbackCharts(data, offset);

          if (progress < 1) {
            fallbackAnimFrameId = requestAnimationFrame(frame);
          } else {
            fallbackAnimFrameId = null;
            drawFallbackCharts(data, 0);
          }
        }

        fallbackAnimFrameId = requestAnimationFrame(frame);
      }

      function refreshFromHistory() {
        fetch('/history').then(res=>res.json()).then(data => {
          const labels = buildTimeLabels(data.temp.length);

          if (tempChart && humChart) {
            tempChart.data.labels = labels;
            tempChart.data.datasets[0].data = data.temp;
            humChart.data.labels = labels;
            humChart.data.datasets[0].data = data.hum;
            tempChart.update();
            humChart.update();
          } else if (useFallbackCanvas) {
            animateFallbackChartsLeft(data);
          }
          
          // Cập nhật số liệu hiển thị bằng mẫu mới nhất trong mảng lịch sử
          if (data.temp.length > 0 && data.hum.length > 0) {
            document.getElementById('temp').innerText = Number(data.temp[data.temp.length - 1]).toFixed(1);
            document.getElementById('hum').innerText = Number(data.hum[data.hum.length - 1]).toFixed(1);
          }
        });
      }

      function toHex(v) {
        const h = Number(v || 0).toString(16).padStart(2, '0');
        return h.length > 2 ? h.slice(-2) : h;
      }

      function applyLedStatus(status) {
        const isAuto = status.mode === 'auto';
        const btnAuto = document.getElementById('btnAuto');
        const btnManual = document.getElementById('btnManual');
        const btnLed1 = document.getElementById('btnLed1');
        const colorInput = document.getElementById('manualColor');
        const manualLabel = document.getElementById('manualLabel');
        const brightnessSlider = document.getElementById('brightnessSlider');
        const brightnessValue = document.getElementById('brightnessValue');
        const brightnessLabel = document.getElementById('brightnessLabel');

        btnAuto.style.opacity = isAuto ? '1' : '0.65';
        btnManual.style.opacity = isAuto ? '0.65' : '1';
        btnLed1.style.display = !isAuto ? 'inline-block' : 'none';
        btnLed1.disabled = isAuto;
        btnLed1.style.opacity = isAuto ? '0.65' : '1';
        colorInput.disabled = isAuto;
        manualLabel.style.opacity = isAuto ? '0.65' : '1';
        brightnessSlider.disabled = isAuto;
        brightnessLabel.style.opacity = isAuto ? '0.65' : '1';

        if (typeof status.led1 === 'string') {
          document.getElementById('l1').innerText = status.led1;
        }

        const hex = '#' + toHex(status.r) + toHex(status.g) + toHex(status.b);
        colorInput.value = hex;

        if (typeof status.brightness !== 'undefined') {
          brightnessSlider.value = status.brightness;
          brightnessValue.innerText = status.brightness + '%';
        }
      }

      function fetchLedStatus() {
        fetch('/led-status')
          .then(r => r.json())
          .then(applyLedStatus)
          .catch(() => {});
      }

      function setLedMode(mode) {
        fetch('/led-mode?mode=' + encodeURIComponent(mode))
          .then(r => r.json())
          .then(applyLedStatus)
          .catch(() => {});
      }

      function setManualColor(hex) {
        const value = (hex || '#000000').replace('#', '');
        if (value.length !== 6) return;

        const r = parseInt(value.slice(0, 2), 16);
        const g = parseInt(value.slice(2, 4), 16);
        const b = parseInt(value.slice(4, 6), 16);
        fetch('/led-rgb?r=' + r + '&g=' + g + '&b=' + b)
          .then(r => r.json())
          .then(applyLedStatus)
          .catch(() => {});
      }

      function setLedBrightness(value) {
        const brightness = parseInt(value) || 100;
        fetch('/led-brightness?brightness=' + brightness)
          .then(r => r.json())
          .then(applyLedStatus)
          .catch(() => {});
      }

      function toggleLED(id) {
        fetch('/toggle?led=' + id).then(r => r.json()).then(json => {
          if (typeof json.led1 !== 'undefined') {
            document.getElementById('l1').innerText = json.led1;
          }
        });
      }

      // Lấy dữ liệu khi vừa mở trang
      // Luôn refresh từ mảng lịch sử trên server
      setInterval(refreshFromHistory, 3000);
      setInterval(fetchLedStatus, 5000);
    </script>
  </body>
  </html>
  )rawliteral";
}

String settingsPage()
{
  return R"rawliteral(
  <!DOCTYPE html>
  <html lang="vi">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wi-Fi Settings</title>
    <style>
      body {
        font-family: "Segoe UI", Arial, sans-serif;
        background: #f2f3f5;
        color: #333;
        text-align: center;
        margin: 0;
        height: 100vh;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
      }

      .logo {
        width: 220px;
        height: 90px;
        border-radius: 20px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.2);
        margin-bottom: 25px;
        background: #f2f3f5;
        object-fit: contain;
        padding: 10px 15px;
      }

      .container {
        background: linear-gradient(135deg, #1e90ff, #00bfff);
        padding: 35px 45px;
        border-radius: 20px;
        box-shadow: 0 4px 25px rgba(0,0,0,0.15);
        width: 90%;
        max-width: 400px;
        color: #f2f3f5;
        backdrop-filter: blur(6px);
      }

      h1 {
        font-size: 1.8em;
        margin-bottom: 20px;
      }

      input[type=text], input[type=password], select {
        width: 100%;
        padding: 10px;
        border: none;
        border-radius: 10px;
        font-size: 1em;
        box-sizing: border-box;
        margin-bottom: 15px;
        outline: none;
      }

      button {
        margin-top: 10px;
        background: #00ffcc;
        color: #000;
        font-weight: bold;
        border: none;
        border-radius: 25px;
        padding: 10px 20px;
        cursor: pointer;
        transition: all 0.3s;
        font-size: 1em;
      }

      button:hover {
        background: #00e0b0;
        transform: scale(1.05);
      }

      #back {
        background: #f2f3f5;
        color: #007bff;
        margin-left: 5px;
      }

      #back:hover {
        background: #e6f3ff;
      }

      #gotoSta {
        display: none;
        background: #ffe082;
        color: #5d3b00;
      }

      #gotoSta:hover {
        background: #ffd54f;
      }

      .ssid-row {
        display: flex;
        gap: 8px;
        align-items: center;
        margin-bottom: 15px;
      }

      .ssid-row select {
        margin-bottom: 0;
        flex: 1;
      }

      #scanBtn {
        margin-top: 0;
        padding: 10px 12px;
        border-radius: 10px;
        background: #d1f8ff;
        color: #003f5c;
        font-size: 0.9em;
        white-space: nowrap;
      }

      #connectStatus {
        margin: 14px 0 0;
        font-weight: 700;
        min-height: 1.4em;
      }

      #connectStatus.connecting {
        color: #fff3cd;
      }

      #connectStatus.success {
        color: #d4edda;
      }

      #connectStatus.failed {
        color: #ffd1d1;
      }
    </style>
  </head>

  <body>
    <img src="data:image/png;base64,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" alt="Project Icon" class="logo">
    <div class="container">
      <h1>⚙️ Cấu hình Wi-Fi</h1>
      <form id="wifiForm">
        <div class="ssid-row">
          <select name="ssid" id="ssid" required>
            <option value="">Đang quét Wi-Fi...</option>
          </select>
          <button type="button" id="scanBtn">Quét lại</button>
        </div>
        <input name="password" id="pass" type="password" placeholder="Mật khẩu (bỏ trống nếu không có)"><br><br>
        <button type="submit" id="btnConnect">Kết nối</button>
        <button type="button" id="back" onclick="window.location='/dashboard'">Quay lại</button>
        <button type="button" id="gotoSta">Mở trang STA</button>
        <p id="connectStatus"></p>
      </form>
    </div>

    <script>
      const gotoStaBtn = document.getElementById('gotoSta');
      const connectBtn = document.getElementById('btnConnect');
      const ssidSelect = document.getElementById('ssid');
      const scanBtn = document.getElementById('scanBtn');
      const connectStatus = document.getElementById('connectStatus');
      let statusTimer = null;
      let redirectTimer = null;

      function setConnectStatus(text, state) {
        connectStatus.textContent = text || '';
        connectStatus.className = state || '';
      }

      function clearRedirectTimer() {
        if (redirectTimer) {
          clearTimeout(redirectTimer);
          redirectTimer = null;
        }
      }

      function scheduleAutoRedirect(ip) {
        clearRedirectTimer();
        setConnectStatus('Kết nối thành công. AP vẫn đang mở. STA IP: ' + ip, 'success');
      }

      function setSsidOptions(networks) {
        ssidSelect.innerHTML = '';

        if (!Array.isArray(networks) || networks.length === 0) {
          const opt = document.createElement('option');
          opt.value = '';
          opt.textContent = 'Không tìm thấy mạng Wi-Fi';
          ssidSelect.appendChild(opt);
          return;
        }

        const first = document.createElement('option');
        first.value = '';
        first.textContent = 'Chọn mạng Wi-Fi';
        ssidSelect.appendChild(first);

        networks.forEach((n) => {
          const opt = document.createElement('option');
          opt.value = n.ssid || '';
          const lock = n.open ? '' : ' 🔒';
          const rssi = typeof n.rssi === 'number' ? ' (' + n.rssi + ' dBm)' : '';
          opt.textContent = (n.ssid || 'Hidden') + lock + rssi;
          ssidSelect.appendChild(opt);
        });
      }

      function scanNetworks() {
        scanBtn.disabled = true;
        scanBtn.textContent = 'Đang quét...';
        fetch('/scan-networks')
          .then(r => r.json())
          .then(data => {
            setSsidOptions(data.networks || []);
          })
          .catch(() => {
            setSsidOptions([]);
          })
          .finally(() => {
            scanBtn.disabled = false;
            scanBtn.textContent = 'Quét lại';
          });
      }

      function stopStatusPolling() {
        if (statusTimer) {
          clearInterval(statusTimer);
          statusTimer = null;
        }
      }

      function startStatusPolling() {
        stopStatusPolling();
        setConnectStatus('Đang kết nối Wi-Fi đã chọn...', 'connecting');
        statusTimer = setInterval(() => {
          fetch('/connect-status')
            .then(r => r.json())
            .then(s => {
              if (s.state === 'success' && s.ip) {
                gotoStaBtn.style.display = 'inline-block';
                gotoStaBtn.onclick = function() {
                  clearRedirectTimer();
                  window.location = 'http://' + s.ip;
                };
                connectBtn.disabled = false;
                scheduleAutoRedirect(s.ip);
                stopStatusPolling();
              } else if (s.state === 'failed') {
                clearRedirectTimer();
                gotoStaBtn.style.display = 'none';
                connectBtn.disabled = false;
                setConnectStatus('Kết nối thất bại. AP vẫn được giữ để bạn chọn lại Wi-Fi.', 'failed');
                stopStatusPolling();
              }
            })
            .catch(() => {
              connectBtn.disabled = false;
              setConnectStatus('Không đọc được trạng thái kết nối. Vui lòng thử lại.', 'failed');
              stopStatusPolling();
            });
        }, 1000);
      }

      document.getElementById('wifiForm').onsubmit = function(e){
        e.preventDefault();
        let ssid = ssidSelect.value;
        let pass = document.getElementById('pass').value;

        if (!ssid) {
          return;
        }

        connectBtn.disabled = true;
        gotoStaBtn.style.display = 'none';
        clearRedirectTimer();
        setConnectStatus('Đã gửi yêu cầu kết nối...', 'connecting');

        fetch('/connect?ssid='+encodeURIComponent(ssid)+'&pass='+encodeURIComponent(pass))
          .then(r=>r.text())
          .then(() => {
            startStatusPolling();
          })
          .catch(() => {
            connectBtn.disabled = false;
            setConnectStatus('Không gửi được yêu cầu kết nối.', 'failed');
          });
      };

      scanBtn.onclick = scanNetworks;
      scanNetworks();
    </script>
  </body>
  </html>
  )rawliteral";
}

// ========== Handlers ==========
void handleRoot()
{
  server.send(200, "text/html", mainPage());
}

void handleDashboard() { server.send(200, "text/html", mainPage()); }

void handleToggle()
{
  int led = server.arg("led").toInt();

  // Single LED is user-controlled only in manual mode.
  led_auto_mode = false;

  if (led == 1)
  {
    led_manual_1 = !led_manual_1;
    digitalWrite(LED1_PIN, led_manual_1 ? HIGH : LOW);
  }

  server.send(200, "application/json",
              "{\"led1\":\"" + String(led_manual_1 ? "ON" : "OFF") + "\"}");
}

void handleSensors()
{
  float t = glob_temperature;
  float h = glob_humidity;
  String json = "{\"temp\":" + String(t) + ",\"hum\":" + String(h) + "}";
  server.send(200, "application/json", json);
}

void handleSettings() { server.send(200, "text/html", settingsPage()); }

void handleConnect()
{
  wifi_ssid = server.arg("ssid");
  wifi_password = server.arg("pass");
  saveWifiCredentials(wifi_ssid, wifi_password);
  server.send(200, "text/plain", "Connecting....");
  isAPMode = true;
  connecting = true;
  connect_state = "connecting";
  last_sta_ip = "";
  Serial.println("Received Wi-Fi credentials:");
  connect_start_ms = millis();
  connectToWiFi();
}

void handleConnectStatus()
{
  String json = "{\"state\":\"" + connect_state + "\",\"ip\":\"" + last_sta_ip + "\"}";
  server.send(200, "application/json", json);
}

void handleHistory() {
  String json = "{\"temp\":[";
  for (int i = 0; i < 10; i++) {
    json += String(temp_history[i]);
    if (i < 9) json += ",";
  }
  json += "],\"hum\":[";
  for (int i = 0; i < 10; i++) {
    json += String(humi_history[i]);
    if (i < 9) json += ",";
  }
  json += "]}";
  
  server.send(200, "application/json", json);
}

void handleLedStatus()
{
  String mode = led_auto_mode ? "auto" : "manual";
  String json = "{\"mode\":\"" + mode + "\",\"r\":" + String((int)led_manual_r) + ",\"g\":" + String((int)led_manual_g) + ",\"b\":" + String((int)led_manual_b) + ",\"brightness\":" + String((int)led_brightness) + ",\"led1\":\"" + String(led_manual_1 ? "ON" : "OFF") + "\"}";
  server.send(200, "application/json", json);
}

void handleLedBrightness()
{
  int brightness = server.arg("brightness").toInt();
  brightness = constrain(brightness, 0, 100);
  led_brightness = (uint8_t)brightness;
  handleLedStatus();
}

void handleLedMode()
{
  String mode = server.arg("mode");
  mode.toLowerCase();
  if (mode == "auto")
  {
    led_auto_mode = true;
  }
  else if (mode == "manual")
  {
    led_auto_mode = false;
  }

  handleLedStatus();
}

void handleLedRgb()
{
  int r = server.arg("r").toInt();
  int g = server.arg("g").toInt();
  int b = server.arg("b").toInt();

  r = constrain(r, 0, 255);
  g = constrain(g, 0, 255);
  b = constrain(b, 0, 255);

  led_manual_r = (uint8_t)r;
  led_manual_g = (uint8_t)g;
  led_manual_b = (uint8_t)b;
  led_auto_mode = false;
  handleLedStatus();
}

void handleScanNetworks()
{
  int networkCount = WiFi.scanNetworks(false, true);
  String json = "{\"networks\":[";

  for (int i = 0; i < networkCount; i++)
  {
    String foundSsid = WiFi.SSID(i);
    if (foundSsid.length() == 0)
    {
      continue;
    }

    if (json.charAt(json.length() - 1) != '[')
    {
      json += ",";
    }

    json += "{\"ssid\":\"" + escapeJsonString(foundSsid) + "\",\"rssi\":" + String(WiFi.RSSI(i)) + ",\"open\":" + String(WiFi.encryptionType(i) == WIFI_AUTH_OPEN ? "true" : "false") + "}";
  }

  json += "]}";
  WiFi.scanDelete();
  server.send(200, "application/json", json);
}

// ========== WiFi ==========
void setupServer()
{
  Serial.println("Setting up web server...");
  server.on("/", HTTP_GET, handleRoot);
  server.on("/dashboard", HTTP_GET, handleDashboard);
  server.on("/index.html", HTTP_GET, handleRoot);
  server.on("/toggle", HTTP_GET, handleToggle);
  server.on("/sensors", HTTP_GET, handleSensors);
  server.on("/settings", HTTP_GET, handleSettings); 
  server.on("/history", HTTP_GET, handleHistory);
  server.on("/led-status", HTTP_GET, handleLedStatus);
  server.on("/led-mode", HTTP_GET, handleLedMode);
  server.on("/led-rgb", HTTP_GET, handleLedRgb);
  server.on("/led-brightness", HTTP_GET, handleLedBrightness);
  server.on("/scan-networks", HTTP_GET, handleScanNetworks);
  server.on("/connect-status", HTTP_GET, handleConnectStatus);
  Serial.println("Web server handlers set up.");
  server.on("/connect", HTTP_GET, handleConnect);
  Serial.println("Web server handlers set up.");
  server.on("/generate_204", HTTP_GET, handleGenerate204);
  server.on("/success.txt", HTTP_GET, handleGenerate204);
  server.on("/hotspot-detect.html", HTTP_GET, handleHotspotDetect);
  server.on("/connecttest.txt", HTTP_GET, handleConnectTestTxt);
  server.on("/ncsi.txt", HTTP_GET, handleNcsiTxt);
  server.on("/fwlink", HTTP_GET, redirectToApRoot);
  server.on("/redirect", HTTP_GET, redirectToApRoot);
  server.onNotFound(handleCaptivePortal);
  server.begin();
}

void startAP()
{
  dnsServer.stop();
  WiFi.mode(WIFI_AP);
  WiFi.softAP(ssid.c_str(), password.c_str());
  Serial.print("AP IP address: ");
  Serial.println(WiFi.softAPIP());
  dnsServer.start(DNS_PORT, "*", WiFi.softAPIP());
  isAPMode = true;
  connecting = false;
}

void connectToWiFi()
{ 
  Serial.println("Connecting to Wi-Fi while keeping AP active...");
  WiFi.mode(WIFI_AP_STA);
  if (wifi_password.isEmpty())
  {
    WiFi.begin(wifi_ssid.c_str());
  }
  else
  {
    WiFi.begin(wifi_ssid.c_str(), wifi_password.c_str());
  }
  Serial.print("Connecting to: ");
  Serial.print(wifi_ssid.c_str());

  Serial.print(" Password: ");
  Serial.print(wifi_password.c_str());
}

// ========== Main task ==========
void main_server_task(void *pvParameters)
{
  pinMode(BOOT_PIN, INPUT_PULLUP);
  pinMode(LED1_PIN, OUTPUT);
  digitalWrite(LED1_PIN, LOW);
  Serial.println("Starting main server task...");
  startAP();
  setupServer();

  String savedSsid;
  String savedPass;
  if (loadWifiCredentials(savedSsid, savedPass))
  {
    wifi_ssid = savedSsid;
    wifi_password = savedPass;
    connect_state = "connecting";
    connecting = true;
    connect_start_ms = millis();
    Serial.print("Found saved Wi-Fi, auto connecting to: ");
    Serial.println(wifi_ssid);
    connectToWiFi();
  }

  delay(1000); // wait for AP to start
  Serial.println("Main server task started!");
  while (1)
  {
    if (isAPMode)
    {
      dnsServer.processNextRequest();
    }
    server.handleClient();
    //Serial.println("Main server task running...");
    // BOOT Button to switch to AP Mode

    if (digitalRead(BOOT_PIN) == LOW)
    {
      Serial.println("BOOT button pressed! Switching to AP mode...");
      vTaskDelay(100);
      if (digitalRead(BOOT_PIN) == LOW)
      {
        if (!isAPMode)
        {
          startAP();
          setupServer();
        }
      }
    }

    // STA Mode
    if (connecting)
    {
      if (WiFi.status() == WL_CONNECTED)
      {
        Serial.print("STA IP address: ");
        Serial.println(WiFi.localIP());
        isWifiConnected = true; // Internet access
        connect_state = "success";
        last_sta_ip = WiFi.localIP().toString();

        xSemaphoreGive(xBinarySemaphoreInternet);

        // Keep AP active so the user can stay on the setup page.
        WiFi.mode(WIFI_AP_STA);
        isAPMode = true;
        connecting = false;
      }
      else if (millis() - connect_start_ms > 10000)
      { // timeout 10s
        Serial.println("WiFi connect failed! Keep AP mode active.");
        WiFi.disconnect();
        connect_state = "failed";
        last_sta_ip = "";
        isAPMode = true;
        connecting = false;
        isWifiConnected = false;
      }
    }

    vTaskDelay(20); // avoid watchdog reset
  }
}