# Logistics Intelligence MVP v0.3

Run in the same PyCharm project environment:
```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Features:
- Interactive 3D globe and schematic Shenzhen/Taiwan → US West Coast → DFW routes.
- Open-Meteo public weather observations and forecast at five route points.
- Official US NWS alerts near DFW.
- Taiwan CWA warning integration scaffold; requires CWA Open Data API key.
- Official Port of Los Angeles / Port of Long Beach news RSS attempts, clearly described as news signals rather than operational status.
- Shenzhen official open-data portal linked; warning feed not falsely represented as integrated.
- Demo incidents clearly marked SIMULATED — NOT REAL.

Optional Taiwan API key:
Create `.streamlit/secrets.toml` in the project folder:
```toml
CWA_API_KEY = "YOUR_CWA_OPEN_DATA_API_KEY"
```
Do not commit or share the key.

Important: The globe uses Three.js from a CDN. Route lines are illustrative. No live vessel, airline, terminal, or BNSF rail tracking is connected.
