# StickS3 weather dashboard

A normal UIFlow2 weather application for StickS3. It reuses the configured
Wi-Fi connection, fetches live weather from Open-Meteo and renders a focused
135 x 240 dashboard with a small amount of meaningful motion.

- The hero weather icon animates sun rays, cloud drift and rain.
- City changes use a short slide transition; loading uses a compact spinner.
- Button A cycles through Shenzhen, Shanghai and Beijing.
- Button B toggles Celsius and Fahrenheit.
- Weather refreshes every 15 minutes.

The page is composed once on a reusable M5GFX Canvas. Idle animation only
redraws a 56 x 56 weather-icon canvas and an 18 x 18 status-dot canvas at
8 FPS, avoiding continuous full-screen redraws.

For the QEMU development network, the app falls back to the open development
SSID only when no saved network is already connected. QEMU results are
simulation-only; real Wi-Fi, display, buttons and animation should still be
confirmed on hardware.
