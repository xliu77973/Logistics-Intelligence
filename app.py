import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import requests
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET
import re

st.set_page_config(page_title="Logistics Intelligence | DFW Lane", page_icon="🌐", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
.block-container{padding-top:1rem;padding-bottom:2rem}[data-testid="stSidebar"]{background:#0b1220}
.hero{padding:1rem 1.3rem;border-radius:14px;background:linear-gradient(115deg,#081321,#123650,#155567);color:#fff}
.hero h1{font-size:1.8rem;margin:0}.hero p{color:#c9e7f5;margin:.35rem 0 0}
div[data-testid="stMetric"]{background:#111e30;border:1px solid #22344a;padding:12px;border-radius:10px}
.small-muted{font-size:12px;color:#9aabba}
</style>""", unsafe_allow_html=True)

LOCATIONS=[
 {"name":"Shenzhen","lat":22.5431,"lon":114.0579,"role":"Factory / export origin"},
 {"name":"Taiwan / Taoyuan","lat":25.0797,"lon":121.2342,"role":"Factory region / export airport"},
 {"name":"Port of Los Angeles","lat":33.7405,"lon":-118.2775,"role":"Ocean port / rail transfer"},
 {"name":"Port of Long Beach","lat":33.7542,"lon":-118.2165,"role":"Ocean port / rail transfer"},
 {"name":"DFW Airport","lat":32.8998,"lon":-97.0403,"role":"Destination / air cargo"},
]
TIMEOUT=12
HEADERS={"User-Agent":"LogisticsIntelligenceMVP/0.3 (public-data dashboard)"}

def get_json(url,params=None,headers=None):
 r=requests.get(url,params=params,headers=headers or HEADERS,timeout=TIMEOUT)
 r.raise_for_status()
 return r.json()

def weather_label(code):
 return {0:"Clear",1:"Mostly clear",2:"Partly cloudy",3:"Overcast",45:"Fog",48:"Freezing fog",51:"Light drizzle",53:"Drizzle",55:"Heavy drizzle",61:"Light rain",63:"Rain",65:"Heavy rain",71:"Light snow",73:"Snow",75:"Heavy snow",80:"Showers",81:"Heavy showers",82:"Violent showers",95:"Thunderstorm",96:"Thunderstorm / hail",99:"Severe thunderstorm / hail"}.get(code,"Unknown")

def fetch_weather(loc):
 try:
  j=get_json("https://api.open-meteo.com/v1/forecast",{"latitude":loc["lat"],"longitude":loc["lon"],"current":"temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,wind_gusts_10m","daily":"weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max","forecast_days":3,"timezone":"auto"})
  c=j.get("current",{});d=j.get("daily",{})
  return {**loc,"temp":c.get("temperature_2m"),"humidity":c.get("relative_humidity_2m"),"precip":c.get("precipitation"),"wind":c.get("wind_speed_10m"),"gust":c.get("wind_gusts_10m"),"code":c.get("weather_code"),"forecast_wind":(d.get("wind_speed_10m_max") or [None])[0],"precip_prob":(d.get("precipitation_probability_max") or [None])[0],"condition":weather_label(c.get("weather_code")),"observed":c.get("time","—"),"status":"REAL · Open-Meteo"}
 except Exception as e:
  return {**loc,"temp":None,"humidity":None,"precip":None,"wind":None,"gust":None,"code":None,"forecast_wind":None,"precip_prob":None,"condition":"Unavailable","observed":"—","status":"UNAVAILABLE","error":str(e)}

def risk(w):
 if w["status"]=="UNAVAILABLE": return "UNKNOWN"
 wind=w.get("forecast_wind");prob=w.get("precip_prob");code=w.get("code")
 if (wind is not None and wind>=55) or code in (95,96,99): return "ELEVATED"
 if (wind is not None and wind>=35) or (prob is not None and prob>=70) or code in (65,82): return "WATCH"
 return "ROUTINE"

def fetch_nws():
 url="https://api.weather.gov/alerts/active"
 try:
  data=get_json(url,{"point":f'{LOCATIONS[-1]["lat"]},{LOCATIONS[-1]["lon"]}'},{"User-Agent":"LogisticsIntelligenceMVP/0.3 contact dashboard"})
  rows=[]
  for f in data.get("features",[]):
   p=f.get("properties",{})
   rows.append({"Severity":p.get("severity") or "Unknown","Event":p.get("event") or "Weather alert","Area":p.get("areaDesc") or "DFW area","Headline":p.get("headline") or p.get("description") or "","Effective":p.get("effective"),"Expires":p.get("expires"),"Source":"US National Weather Service","URL":p.get("web") or ""})
  return rows,None
 except Exception as e:return [],str(e)

def fetch_cwa_warnings():
 # CWA public open data requires an API authorization key; never pretend a missing key means no warnings.
 key=st.secrets.get("CWA_API_KEY","") if hasattr(st,"secrets") else ""
 if not key: return [],"需要中央氣象署 Open Data API 授權碼；未配置 CWA_API_KEY，故未判定台湾是否有警报。"
 urls=[
  "https://opendata.cwa.gov.tw/api/v1/rest/datastore/W-C0033-001",
  "https://opendata.cwa.gov.tw/api/v1/rest/datastore/W-C0034-001",
 ]
 for url in urls:
  try:
   data=get_json(url,{"Authorization":key,"format":"JSON","limit":100})
   records=data.get("records",{})
   # Keep raw record text robustly; schema can vary by warning product.
   rows=[]
   def walk(obj):
    if isinstance(obj,dict):
     textval=" ".join(str(v) for k,v in obj.items() if isinstance(v,(str,int,float)) and k.lower() not in ("lat","lon","latitude","longitude"))
     if any(x in textval.lower() for x in ["typhoon","颱風","豪雨","大雨","強風","陸上強風"]):
      rows.append({"Severity":"Official CWA bulletin","Event":textval[:240],"Area":"Taiwan / CWA bulletin","Headline":textval[:500],"Effective":"","Expires":"","Source":"Taiwan Central Weather Administration","URL":"https://www.cwa.gov.tw/"})
     for v in obj.values(): walk(v)
    elif isinstance(obj,list):
     for v in obj: walk(v)
   walk(records)
   if rows:return rows[:30],None
  except Exception:
   continue
 return [],"CWA endpoint did not return a usable response. Check API key, product schema, or service availability; this is not proof of no warning."

@st.cache_data(ttl=900,show_spinner=False)
def load_weather():return [fetch_weather(loc) for loc in LOCATIONS]
@st.cache_data(ttl=300,show_spinner=False)
def load_nws():return fetch_nws()
@st.cache_data(ttl=300,show_spinner=False)
def load_cwa():return fetch_cwa_warnings()
@st.cache_data(ttl=1800,show_spinner=False)
def fetch_port_news():
 # Official Port of Los Angeles RSS feed; news is a signal, not an operational status API.
 feeds=[
  ("Port of Los Angeles","https://www.portoflosangeles.org/rss.xml"),
  ("Port of Long Beach","https://polb.com/rss/news.xml"),
 ]
 rows=[];errors=[]
 for name,url in feeds:
  try:
   resp=requests.get(url,headers=HEADERS,timeout=TIMEOUT);resp.raise_for_status()
   root=ET.fromstring(resp.content)
   items=root.findall(".//item")
   for it in items[:15]:
    title=(it.findtext("title") or "").strip()
    link=(it.findtext("link") or "").strip()
    pub=(it.findtext("pubDate") or "").strip()
    desc=re.sub("<[^>]+>"," ",it.findtext("description") or "").strip()
    if title:
     # Only keyword-flag items; general port news stays available but isn't falsely called a disruption.
     text=(title+" "+desc).lower()
     terms=["closure","closed","suspend","suspended","disruption","delay","delayed","strike","fire","earthquake","storm","flood","terminal","congestion","labor","outage","emergency","incident","shutdown","停","关闭","延误","中断"]
     match=any(t in text for t in terms)
     rows.append({"Location":name,"Headline":title,"Published":pub,"Potential signal":"REVIEW · keyword match" if match else "General port news","Summary":desc[:320],"Source URL":link or url,"Data status":"REAL · OFFICIAL PORT NEWS"})
  except Exception as e:errors.append(f"{name}: {e}")
 rows.sort(key=lambda x:x["Published"],reverse=True)
 return rows,errors

with st.sidebar:
 st.markdown("## CONTROL PANEL");st.caption("SHENZHEN / TAIWAN → DFW")
 mode=st.multiselect("Transport mode",["Ocean","Air","Rail","Truck"],default=["Ocean","Air","Rail","Truck"])
 show_demo=st.toggle("Show simulated incidents",True)
 if st.button("↻ Refresh live data",use_container_width=True):st.cache_data.clear();st.rerun()
 st.divider();st.markdown("**LIVE SOURCES**");st.write("• Open-Meteo weather API");st.write("• US NWS alerts near DFW");st.write("• Official LA/LB port news RSS (if reachable)")
 st.markdown("**LIMITED / NOT CONNECTED**");st.write("• Taiwan CWA alerts require API key");st.write("• Shenzhen official warning feed not connected");st.write("• Vessel / airline / rail shipment tracking")

now=datetime.now(timezone.utc).astimezone()
st.markdown(f"""<div class="hero"><h1>🌐 LOGISTICS INTELLIGENCE CENTER</h1><p>GLOBAL SITUATIONAL AWARENESS · EXTREME WEATHER · TRANSPORT DISRUPTION</p><p>SHENZHEN / TAIWAN → US WEST COAST → DALLAS–FORT WORTH</p></div>""",unsafe_allow_html=True)
st.caption(f"Updated {now.strftime('%Y-%m-%d %H:%M:%S %Z')} · Weather cache 15 min · Alerts 5 min · Port news 30 min")

# Interactive Three.js globe
globe_html=r"""
<div id="globe-shell" style="position:relative;width:100%;height:520px;background:radial-gradient(ellipse at 50% 48%,#102844 0%,#050b16 68%);border:1px solid #203a55;border-radius:14px;overflow:hidden;">
<div style="position:absolute;z-index:2;left:16px;top:14px;color:#a9dfff;font:700 12px Arial;letter-spacing:2px;">GLOBAL ROUTE INTELLIGENCE</div>
<div style="position:absolute;z-index:2;right:14px;top:14px;color:#a9c0d7;font:11px Arial;text-align:right;">INTERACTIVE 3D GLOBE<br>DRAG TO ROTATE · SCROLL TO ZOOM</div>
<div id="globe-fallback" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#8eb8d9;font:14px Arial;text-align:center;padding:30px;">Loading 3D globe…</div>
<div style="position:absolute;z-index:2;bottom:12px;left:14px;color:#c5d9ea;font:11px Arial;line-height:1.7;">● ORIGIN: SHENZHEN / TAIWAN<br>● OCEAN: WEST COAST PORTS<br>● DESTINATION: DFW</div></div>
<script src="https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js"></script>
<script>
(()=>{const root=document.getElementById('globe-shell'),fb=document.getElementById('globe-fallback');if(!window.THREE){fb.innerHTML='3D library blocked; the rest of the dashboard remains available.';return;}fb.style.display='none';
const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(40,root.clientWidth/root.clientHeight,.1,100);camera.position.z=3.25;const renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});renderer.setPixelRatio(Math.min(devicePixelRatio||1,2));renderer.setSize(root.clientWidth,root.clientHeight);renderer.domElement.style.cssText='position:absolute;inset:0;touch-action:none';root.appendChild(renderer.domElement);const g=new THREE.Group();scene.add(g);
g.add(new THREE.Mesh(new THREE.SphereGeometry(1,64,64),new THREE.MeshPhongMaterial({color:0x16466b,emissive:0x061525,shininess:20})));g.add(new THREE.Mesh(new THREE.SphereGeometry(1.004,36,24),new THREE.MeshBasicMaterial({color:0x3d91bd,wireframe:true,transparent:true,opacity:.16})));g.add(new THREE.Mesh(new THREE.SphereGeometry(1.035,48,48),new THREE.MeshBasicMaterial({color:0x168bd0,transparent:true,opacity:.1,side:THREE.BackSide})));scene.add(new THREE.AmbientLight(0x9dbedc,1.35));const l=new THREE.DirectionalLight(0xffffff,2);l.position.set(3,2,4);scene.add(l);
function xyz(lat,lon,r=1.014){let a=(90-lat)*Math.PI/180,b=(lon+180)*Math.PI/180;return new THREE.Vector3(-r*Math.sin(a)*Math.cos(b),r*Math.cos(a),r*Math.sin(a)*Math.sin(b));}
function route(a,b,color,h=.25){let p=xyz(...a),q=xyz(...b),m=p.clone().add(q).multiplyScalar(.5).normalize().multiplyScalar(1+h),c=new THREE.QuadraticBezierCurve3(p,m,q);g.add(new THREE.Mesh(new THREE.TubeGeometry(c,70,.003,5,false),new THREE.MeshBasicMaterial({color,transparent:true,opacity:.95})));}
function mark(a,color){let p=xyz(...a,1.02),m=new THREE.Mesh(new THREE.SphereGeometry(.02,12,12),new THREE.MeshBasicMaterial({color}));m.position.copy(p);g.add(m);}
let sz=[22.5431,114.0579],tw=[25.0797,121.2342],la=[33.7405,-118.2775],lb=[33.7542,-118.2165],dfw=[32.8998,-97.0403];route(sz,la,0x25d9ff,.35);route(tw,lb,0x47b7ff,.32);route(la,dfw,0xffbd59,.16);route(lb,dfw,0xffbd59,.15);route(sz,dfw,0x9677ff,.45);route(tw,dfw,0x9677ff,.4);[[sz,0x28e5ff],[tw,0x28e5ff],[la,0xffbf5f],[lb,0xffbf5f],[dfw,0xff5b6e]].forEach(v=>mark(v[0],v[1]));
let drag=false,x=0,y=0,ry=0,rx=.15;renderer.domElement.onpointerdown=e=>{drag=true;x=e.clientX;y=e.clientY;renderer.domElement.setPointerCapture(e.pointerId)};renderer.domElement.onpointermove=e=>{if(!drag)return;ry+=(e.clientX-x)*.006;rx=Math.max(-1.1,Math.min(1.1,rx+(e.clientY-y)*.004));x=e.clientX;y=e.clientY};renderer.domElement.onpointerup=renderer.domElement.onpointercancel=()=>drag=false;renderer.domElement.addEventListener('wheel',e=>{camera.position.z=Math.max(2.1,Math.min(5,camera.position.z+e.deltaY*.002));e.preventDefault()},{passive:false});
function anim(){requestAnimationFrame(anim);if(!drag)ry+=.0018;g.rotation.y=ry;g.rotation.x=rx;renderer.render(scene,camera)}anim();new ResizeObserver(()=>{camera.aspect=root.clientWidth/root.clientHeight;camera.updateProjectionMatrix();renderer.setSize(root.clientWidth,root.clientHeight)}).observe(root);})();
</script>"""
st.subheader("GLOBAL SITUATIONAL AWARENESS")
st.caption("Interactive globe; route arcs are schematic, not live vessel or flight tracks.")
components.html(globe_html,height=535,scrolling=False)

with st.spinner("Fetching public weather, alerts, and port news…"):
 weather=load_weather();nws_rows,nws_error=load_nws();cwa_rows,cwa_error=load_cwa();port_rows,port_errors=fetch_port_news()
watch=sum(risk(w) in ("WATCH","ELEVATED") for w in weather)
m1,m2,m3,m4=st.columns(4);m1.metric("Monitoring points",len(LOCATIONS));m2.metric("NWS alerts near DFW",len(nws_rows));m3.metric("Weather watch / elevated",watch);m4.metric("Port news items",len(port_rows),help="Official port news feed; keyword matches require human verification.")
st.divider();st.subheader("WEATHER & ROUTE EXPOSURE")
st.caption("Risk screening is preliminary and does not predict shipment delay.")
cols=st.columns(3)
for i,w in enumerate(weather):
 with cols[i%3]:
  lvl=risk(w)
  if lvl=="ELEVATED":st.error(f"{w['name']} · {lvl}")
  elif lvl=="WATCH":st.warning(f"{w['name']} · {lvl}")
  elif lvl=="UNKNOWN":st.info(f"{w['name']} · {lvl}")
  else:st.success(f"{w['name']} · {lvl}")
  if w["temp"] is not None:
   st.metric("Temperature",f"{w['temp']} °C",w["condition"]);x,y=st.columns(2);x.metric("Wind",f"{w['wind']} km/h" if w['wind'] is not None else "—");y.metric("Gusts",f"{w['gust']} km/h" if w['gust'] is not None else "—")
   st.caption(f"Humidity {w['humidity']}% · Rain {w['precip']} mm · Forecast max wind {w['forecast_wind']} km/h · Rain probability {w['precip_prob']}%")
   st.caption(f"{w['role']} · {w['status']} · {w['observed']}")
  else:st.warning("Live weather unavailable.")

st.divider();st.subheader("OFFICIAL WEATHER WARNINGS")
st.markdown("**United States · NWS near DFW**")
if nws_error:st.warning("NWS API unavailable; no-alert status cannot be confirmed.")
elif nws_rows:st.dataframe(pd.DataFrame(nws_rows),use_container_width=True,hide_index=True)
else:st.success("NWS reports no active alerts for the DFW Airport point.")
st.markdown("**Taiwan · Central Weather Administration (CWA)**")
if cwa_rows:st.dataframe(pd.DataFrame(cwa_rows),use_container_width=True,hide_index=True)
else:st.info(cwa_error)
st.markdown("**Shenzhen · official warning integration**")
st.info("Not connected yet. Shenzhen Meteorological Bureau directs the public to Shenzhen Open Data Platform for official weather warnings and observations. This version does not scrape the site or fabricate warning status.")
st.markdown("[Shenzhen official open-data portal](https://opendata.sz.gov.cn/data/catalog/toDataCatalog) · [Taiwan CWA Open Data](https://opendata.cwa.gov.tw/user/apply/2)")

st.divider();st.subheader("LOS ANGELES / LONG BEACH · OFFICIAL PORT NEWS")
st.caption("News can signal a possible issue but is not a live terminal status feed. Keyword matches need human review.")
if port_rows:
 df=pd.DataFrame(port_rows)
 filt=st.selectbox("Filter port-news items",["All items","Potential signal only","Port of Los Angeles","Port of Long Beach"])
 if filt=="Potential signal only":df=df[df["Potential signal"].str.startswith("REVIEW")]
 elif filt!="All items":df=df[df["Location"]==filt]
 st.dataframe(df[["Location","Headline","Published","Potential signal","Source URL","Data status"]],use_container_width=True,hide_index=True,column_config={"Source URL":st.column_config.LinkColumn("Official source")})
else:st.warning("Port RSS feeds did not return items. Use official port pages below.")
if port_errors:st.caption("Feed retrieval notes: "+" · ".join(port_errors))
st.markdown("[Port of Los Angeles official news](https://www.portoflosangeles.org/news/latest-news) · [Port of Long Beach official website](https://polb.com/)")

st.divider();st.subheader("LOGISTICS INCIDENT FEED")
st.caption("No live carrier / vessel / airline / rail status feed is connected yet.")
demo=[{"Severity":"Medium","Location":"Pacific route","Mode":"Ocean","Event":"Sample: vessel schedule slippage","Action":"Verify with carrier and booking ETA.","Data status":"SIMULATED — NOT REAL"},{"Severity":"High","Location":"DFW destination","Mode":"Air","Event":"Sample: destination handling disruption","Action":"Verify with airline / cargo terminal.","Data status":"SIMULATED — NOT REAL"}]
filtered=[x for x in demo if x["Mode"] in mode] if show_demo else []
if filtered:st.dataframe(pd.DataFrame(filtered),use_container_width=True,hide_index=True)
else:st.info("No simulated incidents selected. No live shipment event feed is connected.")

with st.expander("Sources, setup, and limitations"):
 st.markdown("- Weather: Open-Meteo public API.\n- US alerts: official NWS API.\n- Taiwan alerts: CWA Open Data requires an API authorization key. Add `CWA_API_KEY` to `.streamlit/secrets.toml`; no key means unknown status, not no warnings.\n- Shenzhen: official Shenzhen Open Data portal is identified, but not yet integrated.\n- Port information: official port RSS/news where reachable; news is not a terminal operations status API.\n- Globe routes are illustrative; no vessel/flight tracking or rail ETA feed is connected.\n- Preliminary weather thresholds are not validated against historical shipment delays.")
st.caption("LOGISTICS INTELLIGENCE MVP · V0.3 · Real public sources prioritized; unavailable integrations are explicitly labeled.")
