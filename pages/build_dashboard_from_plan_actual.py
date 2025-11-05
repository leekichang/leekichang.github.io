#!/usr/bin/env python3
"""
Build dashboard (EN default) with KO toggle.
Input schema (strict):
  date, type, distance_km, avg_pace, avg_hr_bpm, avg_cadence_spm, rpe, notes
"""
import argparse, re, json
from pathlib import Path
import pandas as pd
import numpy as np

def detect_and_read_csv(path: Path):
    for enc in ["utf-8-sig", "cp949", "euc-kr", "ISO-8859-1"]:
        try: return pd.read_csv(path, encoding=enc)
        except Exception: continue
    return pd.read_csv(path)

def parse_date(x):
    if pd.isna(x): return pd.NaT
    try: return pd.to_datetime(str(x).strip())
    except Exception: return pd.NaT

def parse_pace_mmss_to_minutes(x):
    if pd.isna(x): return np.nan
    s = str(x).strip()
    try: return float(s)
    except Exception: pass
    m = re.match(r'^\s*(\d{1,2})\s*:\s*(\d{1,2})\s*$', s)
    if m:
        mm, ss = int(m.group(1)), int(m.group(2))
        if 0 <= ss < 60: return mm + ss/60.0
    return np.nan

def monday_of_week(ts):
    if pd.isna(ts): return pd.NaT
    return (ts - pd.Timedelta(days=ts.weekday())).normalize()

def impute_with_medians(df, col, by="type"):
    s = df[col].copy()
    s = s.fillna(df.groupby(by)[col].transform('median'))
    if s.isna().any():
        gmed = float(np.nanmedian(s))
        if not np.isnan(gmed): s = s.fillna(gmed)
    return s

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Running Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;margin:24px}
  h1{margin-bottom:0}.sub{color:#555;margin-top:4px}
  .grid{display:grid;gap:20px}.two{grid-template-columns:1fr}.three{grid-template-columns:1fr}
  @media(min-width:1024px){.two{grid-template-columns:1fr 1fr}.three{grid-template-columns:1fr 1fr 1fr}}
  .card{border:1px solid #eee;border-radius:12px;padding:16px;box-shadow:0 2px 10px rgba(0,0,0,.05)}
  .controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:12px 0}
  .controls label{display:flex;gap:6px;align-items:center}
  input,select,button{padding:8px 10px;border-radius:8px;border:1px solid #ddd}
  #notes{white-space:pre-wrap;background:#fafafa;border-radius:8px;padding:12px;border:1px solid #eee}
  .muted{color:#666;font-size:12px}.spacer{flex:1 1 auto}
</style>
</head>
<body>
<h1 id="title">Running Dashboard</h1>
<div class="sub" id="subtitle">Daily/weekly trends, moving stats, pace↔speed, distributions, box plots, efficiency.</div>

<div class="card">
  <div class="controls">
    <label><span id="lblLang">Language</span>
      <select id="langSel">
        <option value="en">English</option>
        <option value="ko">한국어</option>
      </select>
    </label>
    <div class="spacer"></div>
    <label><span id="lblType">Type</span>
      <select id="typeFilter"><option value="__ALL__" id="optAll">All</option></select>
    </label>
    <label><span id="lblRange">Date</span>
      <input type="date" id="fromDate"> ~ <input type="date" id="toDate">
    </label>
    <label><span id="lblUnit">Unit</span>
      <select id="paceMode">
        <option value="pace" id="optPace">Pace (min/km)</option>
        <option value="speed" id="optSpeed">Speed (km/h)</option>
      </select>
    </label>
    <label><span id="lblRollStat">Rolling</span>
      <select id="rollStat">
        <option value="mean" id="optMean">Mean</option>
        <option value="median" id="optMedian">Median</option>
      </select>
    </label>
    <label><span id="lblWindow">Window</span>
      <select id="rollWin"><option value="7">7 days</option><option value="28">28 days</option></select>
    </label>
    <label><span id="lblGoal">Weekly goal (km)</span>
      <input type="number" id="weeklyGoal" value="30" min="0" step="1" style="width:110px;">
    </label>
    <button id="apply">Apply</button><button id="reset">Reset</button>
  </div>
  <div class="muted" id="hintClick">Tip: click a point to show notes below.</div>
</div>

<div class="grid two">
  <div class="card"><h3 id="hDailyDist">Daily distance (km) + rolling</h3><div id="distDaily" style="height:360px;"></div></div>
  <div class="card"><h3 id="hDailyPace">Daily pace (min/km) + rolling</h3><div id="paceDaily" style="height:360px;"></div></div>
</div>

<div class="grid two">
  <div class="card"><h3 id="hDailyRpe">Daily RPE</h3><div id="rpeDaily" style="height:300px;"></div></div>
  <div class="card"><h3 id="hWeeklyTotals">Weekly total vs goal</h3><div id="weeklyTotals" style="height:320px;"></div></div>
</div>

<div class="grid three">
  <div class="card"><h3 id="hHistPace">Distribution: pace/speed</h3><div id="histPace" style="height:280px;"></div></div>
  <div class="card"><h3 id="hHistDistRpe">Distribution: distance & RPE</h3><div id="histDistRpe" style="height:280px;"></div></div>
  <div class="card"><h3 id="hBoxByType">Box: by type</h3><div id="boxByType" style="height:280px;"></div></div>
</div>

<div class="card">
  <h3 id="hEfficiency">Efficiency (speed / HR)</h3>
  <div id="efficiency" style="height:320px;"></div>
  <div class="muted" id="hintHrMissing">* Days without HR are omitted.</div>
</div>

<div class="card">
  <h3 id="hNotes">Selected notes</h3>
  <div id="notes">(Click a point)</div>
</div>

<script>
const STR = {
  en:{title:"Running Dashboard",subtitle:"Daily/weekly trends, moving stats, pace↔speed, distributions, box plots, efficiency.",
      Language:"Language",Type:"Type",All:"All",Date:"Date",Unit:"Unit",Rolling:"Rolling",Mean:"Mean",Median:"Median",
      Window:"Window",WeeklyGoal:"Weekly goal (km)",Apply:"Apply",Reset:"Reset",
      HintClick:"Tip: click a point to show notes below.",
      DailyDist:"Daily distance (km) + rolling",DailyPace:"Daily pace (min/km) + rolling",DailySpeed:"Daily speed (km/h) + rolling",
      DailyRpe:"Daily RPE",WeeklyTotals:"Weekly total vs goal",HistPace:"Distribution: pace/speed",
      HistDistRpe:"Distribution: distance & RPE",BoxByType:"Box: by type",Efficiency:"Efficiency (speed / HR)",
      HrMissing:"* Days without HR are omitted.",Notes:"Selected notes",
      axisDate:"Date",axisKm:"km",axisMinPerKm:"min / km",axisKmH:"km/h",axisRpe:"RPE",axisCount:"Count",axisType:"Type",axisEff:"Efficiency (km/h per bpm)",
      traceDist:"Distance (km)",traceRollingMean:"Rolling mean",traceRollingMedian:"Rolling median",tracePace:"Pace",traceSpeed:"Speed",traceRpe:"RPE",traceGoal:"Goal",
      tooltipPace:"%{x}<br>%{y:.2f} min/km",tooltipSpeed:"%{x}<br>%{y:.2f} km/h",tooltipKm:"%{x}<br>%{y:.2f} km",tooltipWeekKm:"%{x}<br>%{y:.1f} km",
      tooltipEff:"%{x}<br>%{y:.4f} (km/h)/bpm",clickDate:"Date",clickType:"Type",clickDist:"Distance",clickPace:"Pace",clickSpeed:"Speed",clickHR:"Avg HR",clickRPE:"RPE",clickNoNotes:"(No notes)"},
  ko:{title:"러닝 대시보드",subtitle:"일일/주간 추이, 이동통계, 페이스↔스피드, 분포, 상자그림, 효율 지수.",
      Language:"언어",Type:"종류",All:"모두",Date:"기간",Unit:"값 단위",Rolling:"이동 통계",Mean:"평균",Median:"중앙값",
      Window:"윈도우",WeeklyGoal:"주간 목표(km)",Apply:"적용",Reset:"초기화",
      HintClick:"포인트를 클릭하면 아래 노트가 표시됩니다.",
      DailyDist:"일일 거리 (km) + 이동통계",DailyPace:"일일 페이스 (분/km) + 이동통계",DailySpeed:"일일 스피드 (km/h) + 이동통계",
      DailyRpe:"일일 RPE",WeeklyTotals:"주간 합계 vs 목표",HistPace:"분포: 페이스/스피드",
      HistDistRpe:"분포: 거리 & RPE",BoxByType:"상자그림: 타입별",Efficiency:"효율 지수 (speed / HR)",
      HrMissing:"* HR이 비어있는 날은 제외됩니다.",Notes:"선택한 러닝 노트",
      axisDate:"날짜",axisKm:"km",axisMinPerKm:"분 / km",axisKmH:"km/h",axisRpe:"RPE",axisCount:"카운트",axisType:"타입",axisEff:"효율 지수 (km/h per bpm)",
      traceDist:"거리(km)",traceRollingMean:"이동평균",traceRollingMedian:"이동중앙값",tracePace:"페이스",traceSpeed:"스피드",traceRpe:"RPE",traceGoal:"목표선",
      tooltipPace:"%{x}<br>%{y:.2f} 분/km",tooltipSpeed:"%{x}<br>%{y:.2f} km/h",tooltipKm:"%{x}<br>%{y:.2f} km",tooltipWeekKm:"%{x}<br>%{y:.1f} km",
      tooltipEff:"%{x}<br>%{y:.4f} (km/h)/bpm",clickDate:"날짜",clickType:"종류",clickDist:"거리",clickPace:"페이스",clickSpeed:"스피드",clickHR:"평균 심박",clickRPE:"RPE",clickNoNotes:"(노트 없음)"}
};

const DAILY = __DAILY__;
const WEEKLY = __WEEKLY__;

const el = id => document.getElementById(id);
const langSel = el('langSel');
let LANG = localStorage.getItem('runDashLang') || 'en';
langSel.value = LANG;

function applyLang(){
  const S = STR[LANG];
  el('title').textContent = S.title; el('subtitle').textContent = S.subtitle;
  el('lblLang').textContent = S.Language; el('lblType').textContent = S.Type; el('optAll').textContent = S.All;
  el('lblRange').textContent = S.Date; el('lblUnit').textContent = S.Unit;
  el('lblRollStat').textContent = S.Rolling; el('optMean').textContent = S.Mean; el('optMedian').textContent = S.Median;
  el('lblWindow').textContent = S.Window; el('lblGoal').textContent = S.WeeklyGoal;
  el('apply').textContent = S.Apply; el('reset').textContent = S.Reset;
  el('hintClick').textContent = S.HintClick; el('hDailyDist').textContent = S.DailyDist; el('hDailyRpe').textContent = S.DailyRpe;
  el('hWeeklyTotals').textContent = S.WeeklyTotals; el('hHistPace').textContent = S.HistPace; el('hHistDistRpe').textContent = S.HistDistRpe;
  el('hBoxByType').textContent = S.BoxByType; el('hEfficiency').textContent = S.Efficiency; el('hintHrMissing').textContent = S.HrMissing;
  const mode = el('paceMode').value;
  el('optPace').textContent = (LANG==='en'?'Pace (min/km)':'페이스(분/km)');
  el('optSpeed').textContent = (LANG==='en'?'Speed (km/h)':'스피드(km/h)');
  el('hDailyPace').textContent = (mode==='pace'? S.DailyPace : S.DailySpeed);
  render();
}
langSel.onchange = () => { LANG = langSel.value; localStorage.setItem('runDashLang', LANG); applyLang(); };

const typeSelect = el('typeFilter');
const types = Array.from(new Set(DAILY.map(d=>d.type))).filter(Boolean).sort();
types.forEach(t => { const o=document.createElement('option'); o.value=t; o.innerText=t; typeSelect.appendChild(o); });

const fromInput = el('fromDate'), toInput = el('toDate');
const dates = DAILY.map(d=>d.date).sort();
if (dates.length){ fromInput.value = dates[0]; toInput.value = dates[dates.length-1]; }

const paceModeSel = el('paceMode'), rollStatSel = el('rollStat'), rollWinSel = el('rollWin'), weeklyGoalInput = el('weeklyGoal');

function filteredDaily(){
  const t = typeSelect.value, from = fromInput.value || '0000-01-01', to = toInput.value || '9999-12-31';
  return DAILY.filter(d => (t==='__ALL__' || d.type===t) && d.date>=from && d.date<=to);
}

function rolling(values, window, stat){
  const out = new Array(values.length).fill(null);
  for (let i=0;i<values.length;i++){
    const start = Math.max(0,i-window+1);
    const seg = values.slice(start,i+1).filter(v=>v!=null && !Number.isNaN(v));
    if (!seg.length) continue;
    if (stat==='median'){
      const s = seg.slice().sort((a,b)=>a-b); const m = Math.floor(s.length/2);
      out[i] = s.length%2 ? s[m] : (s[m-1]+s[m])/2;
    } else {
      out[i] = seg.reduce((a,b)=>a+b,0)/seg.length;
    }
  }
  return out;
}

function render(){
  const S = STR[LANG], d = filteredDaily(), x = d.map(r=>r.date);
  const dist = d.map(r => (r.dist_km!=null? +r.dist_km : null));
  const rw = +rollWinSel.value, rs = rollStatSel.value, distRoll = rolling(dist, rw, rs);

  Plotly.newPlot('distDaily', [
    { x, y: dist, mode:'lines+markers', name:S.traceDist, hovertemplate:S.tooltipKm+'<extra></extra>' },
    { x, y: distRoll, mode:'lines', name:(rs==='median'?S.traceRollingMedian:S.traceRollingMean), hovertemplate:S.tooltipKm+'<extra></extra>' }
  ], { margin:{t:30,l:40,r:10,b:40}, xaxis:{title:S.axisDate}, yaxis:{title:S.axisKm} }, {displayModeBar:false});

  const mode = paceModeSel.value;
  let series=null, seriesRoll=null, yaxis={title:''}, hover='';
  if (mode==='pace'){ series = d.map(r=>r.pace_minpkm!=null? +r.pace_minpkm:null); seriesRoll = rolling(series,rw,rs);
    yaxis={title:S.axisMinPerKm,autorange:'reversed'}; hover=S.tooltipPace+'<extra></extra>'; el('hDailyPace').textContent=S.DailyPace;
  } else { series=d.map(r=>r.pace_minpkm!=null? (60.0/+r.pace_minpkm):null); seriesRoll=rolling(series,rw,rs);
    yaxis={title:S.axisKmH}; hover=S.tooltipSpeed+'<extra></extra>'; el('hDailyPace').textContent=S.DailySpeed; }

  Plotly.newPlot('paceDaily', [
    { x, y:series, mode:'lines+markers', name:(mode==='pace'?S.tracePace:S.traceSpeed), hovertemplate:hover },
    { x, y:seriesRoll, mode:'lines', name:(rs==='median'?S.traceRollingMedian:S.traceRollingMean), hovertemplate:hover }
  ], { margin:{t:30,l:50,r:10,b:40}, xaxis:{title:S.axisDate}, yaxis }, {displayModeBar:false});

  Plotly.newPlot('rpeDaily', [
    { x, y:d.map(r=>+r.rpe), mode:'lines+markers', name:S.traceRpe, hovertemplate:`%{x}<br>${S.traceRpe} %{y}<extra></extra>` }
  ], { margin:{t:30,l:40,r:10,b:40}, xaxis:{title:S.axisDate}, yaxis:{title:S.axisRpe, rangemode:'tozero'} }, {displayModeBar:false});

  const goal = Math.max(0, +weeklyGoalInput.value || 0);
  const weekX = WEEKLY.map(w=>w.week), weekDist = WEEKLY.map(w=>+w.dist_km);
  Plotly.newPlot('weeklyTotals', [
    { x:weekX, y:weekDist, type:'bar', name:S.WeeklyTotals, hovertemplate:S.tooltipWeekKm+'<extra></extra>' },
    { x:weekX, y:new Array(weekX.length).fill(goal), mode:'lines', name:S.traceGoal, hovertemplate:S.tooltipWeekKm+'<extra></extra>' }
  ], { margin:{t:30,l:40,r:40,b:40}, xaxis:{title:S.axisDate}, yaxis:{title:S.axisKm} }, {displayModeBar:false});

  const paceVals = d.map(r=>r.pace_minpkm!=null? +r.pace_minpkm:null).filter(v=>v!=null);
  const speedVals = paceVals.map(p=>60.0/p);
  Plotly.newPlot('histPace', [
    { x:(paceModeSel.value==='pace'? paceVals : speedVals), type:'histogram', name:(paceModeSel.value==='pace'? S.tracePace : S.traceSpeed) }
  ], { margin:{t:30,l:40,r:10,b:30}, xaxis:{title:(paceModeSel.value==='pace'? S.axisMinPerKm : S.axisKmH)}, yaxis:{title:S.axisCount} }, {displayModeBar:false});

  Plotly.newPlot('histDistRpe', [
    { x:dist.filter(v=>v!=null), type:'histogram', name:S.traceDist, opacity:0.75 },
    { x:d.map(r=>+r.rpe), type:'histogram', name:S.traceRpe, opacity:0.6 }
  ], { barmode:'overlay', margin:{t:30,l:40,r:10,b:30}, xaxis:{title:'Value'}, yaxis:{title:S.axisCount} }, {displayModeBar:false});

  const byType = {}; d.forEach(r=>{ const k=r.type||'unknown'; (byType[k]=byType[k]||[]).push(
    (paceModeSel.value==='pace'?(r.pace_minpkm!=null?+r.pace_minpkm:null):(r.pace_minpkm!=null?60.0/+r.pace_minpkm:null))
  );});
  const boxTraces = Object.keys(byType).sort().map(k=>({y:byType[k].filter(v=>v!=null), type:'box', name:k, boxpoints:false}));
  Plotly.newPlot('boxByType', boxTraces, { margin:{t:30,l:40,r:10,b:30}, yaxis:{title:(paceModeSel.value==='pace'? S.axisMinPerKm:S.axisKmH)}, xaxis:{title:S.axisType}}, {displayModeBar:false});

  const effX=[], effY=[]; d.forEach(r=>{ const p=r.pace_minpkm, hr=r.hr_avg; if(p!=null && hr!=null && hr>0){ effX.push(r.date); effY.push((60.0/p)/hr); }});
  Plotly.newPlot('efficiency', [{ x:effX, y:effY, mode:'lines+markers', name:S.Efficiency, hovertemplate:S.tooltipEff+'<extra></extra>' }],
    { margin:{t:30,l:40,r:10,b:40}, xaxis:{title:S.axisDate}, yaxis:{title:S.axisEff} }, {displayModeBar:false});

  const notes = document.getElementById('notes');
  const clickHandler = (data)=>{ if(!data.points||!data.points.length) return; const idx=data.points[0].pointIndex; const row=d[idx]; if(!row) return;
    const lines=[ `${STR[LANG].clickDate}: ${row.date}`, `${STR[LANG].clickType}: ${row.type}`, `${STR[LANG].clickDist}: ${row.dist_km} km`,
      `${STR[LANG].clickPace}: ${row.pace_minpkm?.toFixed(2)} ${STR[LANG].axisMinPerKm} (${STR[LANG].clickSpeed} ${(row.pace_minpkm?(60/row.pace_minpkm).toFixed(2):'N/A')} ${STR[LANG].axisKmH})`,
      `${STR[LANG].clickHR}: ${row.hr_avg ?? 'N/A'}`, `${STR[LANG].clickRPE}: ${row.rpe}`, '', (row.notes || STR[LANG].clickNoNotes) ];
    notes.textContent = lines.join('\n'); };
  ['distDaily','paceDaily','rpeDaily'].forEach(id=>{ document.getElementById(id).on('plotly_click', clickHandler); });
}

document.getElementById('apply').onclick = render;
document.getElementById('reset').onclick = ()=>{ typeSelect.value='__ALL__'; fromInput.value=dates[0]; toInput.value=dates[dates.length-1];
  paceModeSel.value='pace'; rollStatSel.value='mean'; rollWinSel.value='7'; weeklyGoalInput.value='30'; render(); };
applyLang();
</script>
</body>
</html>
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="run_log_plan_actual_summary.csv")
    ap.add_argument("--out", default="run_dashboard.html")
    args = ap.parse_args()

    df = detect_and_read_csv(Path(args.src))
    expected = ["date","type","distance_km","avg_pace","avg_hr_bpm","avg_cadence_spm","rpe","notes"]
    miss = [c for c in expected if c not in df.columns]
    if miss: raise ValueError(f"Missing columns: {miss}")

    df["date"] = df["date"].apply(parse_date)
    df = df.sort_values("date").reset_index(drop=True)
    df["type"] = df["type"].astype(str).str.strip().str.lower()
    df["dist_km"] = pd.to_numeric(df["distance_km"], errors="coerce")
    df["pace_minpkm"] = df["avg_pace"].apply(parse_pace_mmss_to_minutes)
    df["hr_avg"] = pd.to_numeric(df["avg_hr_bpm"], errors="coerce")
    df["cadence_spm"] = pd.to_numeric(df["avg_cadence_spm"], errors="coerce")
    df["rpe"] = pd.to_numeric(df["rpe"], errors="coerce")
    df["notes"] = df["notes"].astype(str).fillna("")
    df["week"] = df["date"].apply(monday_of_week)

    # Impute only missing values
    df["pace_minpkm"] = impute_with_medians(df, "pace_minpkm", by="type")
    df["hr_avg"] = impute_with_medians(df, "hr_avg", by="type")
    df["cadence_spm"] = impute_with_medians(df, "cadence_spm", by="type")
    type_rpe_default = {"easy":5,"long":6,"tempo":7,"interval":8,"race":9,"test":6,"rest":2}
    miss = df["rpe"].isna()
    df.loc[miss,"rpe"] = df.loc[miss,"type"].map(type_rpe_default)
    df["rpe"] = impute_with_medians(df, "rpe", by="type")

    daily = df[["date","type","dist_km","pace_minpkm","hr_avg","rpe","notes"]].copy()
    daily["date"] = pd.to_datetime(daily["date"]).dt.strftime("%Y-%m-%d")
    weekly = (df.groupby(pd.to_datetime(df["week"]).dt.strftime("%Y-%m-%d"), as_index=False)
                .agg(week=("week","first"), dist_km=("dist_km","sum"), runs=("date","count"),
                     pace_minpkm=("pace_minpkm","mean"), rpe=("rpe","mean"))
                .sort_values("week"))
    weekly["week"] = pd.to_datetime(weekly["week"]).dt.strftime("%Y-%m-%d")

    out = Path(args.out)
    out.write_text(HTML.replace("__DAILY__", json.dumps(json.loads(daily.to_json(orient="records")), ensure_ascii=False))
                        .replace("__WEEKLY__", json.dumps(json.loads(weekly.to_json(orient="records")), ensure_ascii=False)),
                   encoding="utf-8")
    print(f"Wrote {out}")

if __name__ == "__main__":
    main()



# #!/usr/bin/env python3
# """
# Build dashboard strictly from the fixed schema:
#   date, type, distance_km, avg_pace, avg_hr_bpm, avg_cadence_spm, rpe, notes

# - distance_km: decimal number (km)
# - avg_pace: "m:s" or "mm:ss" string (minutes:seconds per km). If a float is given, it's treated as minutes.
# - Missing values are imputed conservatively (per-type median -> global median), without changing existing filled values.
# - Outputs a standalone run_dashboard.html with interactive plots and filters.
# """
# import argparse, re, json
# from pathlib import Path
# import pandas as pd
# import numpy as np

# def detect_and_read_csv(path: Path) -> pd.DataFrame:
#     encodings = ["utf-8-sig", "cp949", "euc-kr", "ISO-8859-1"]
#     last_err = None
#     for enc in encodings:
#         try:
#             return pd.read_csv(path, encoding=enc)
#         except Exception as e:
#             last_err = e
#             continue
#     raise last_err or RuntimeError("Failed to read CSV")

# def parse_date(x):
#     if pd.isna(x): return pd.NaT
#     try:
#         return pd.to_datetime(str(x).strip())
#     except Exception:
#         return pd.NaT

# def parse_pace_mmss_to_minutes(x):
#     """Accept '6:30', '06:30', 6.5 -> minutes per km (float)."""
#     if pd.isna(x): return np.nan
#     s = str(x).strip()
#     # Allow raw float (already minutes)
#     try:
#         return float(s)
#     except Exception:
#         pass
#     m = re.match(r'^\s*(\d{1,2})\s*[:]\s*(\d{1,2})\s*$', s)
#     if m:
#         mm = int(m.group(1)); ss = int(m.group(2))
#         if 0 <= ss < 60:
#             return mm + ss/60.0
#     return np.nan

# def monday_of_week(ts: pd.Timestamp):
#     if pd.isna(ts): return pd.NaT
#     return (ts - pd.Timedelta(days=ts.weekday())).normalize()

# def impute_with_medians(df, col, by="type"):
#     s = df[col].copy()
#     # per-type median
#     med_by_type = df.groupby(by)[col].transform('median')
#     s = s.fillna(med_by_type)
#     # global median
#     if s.isna().any():
#         gmed = float(np.nanmedian(s))
#         if not np.isnan(gmed):
#             s = s.fillna(gmed)
#     return s

# DASHBOARD_HTML = r"""<!DOCTYPE html>
# <html lang="ko">
# <head>
#   <meta charset="utf-8">
#   <meta name="viewport" content="width=device-width, initial-scale=1">
#   <title>Running Dashboard (Fixed Schema)</title>
#   <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
#   <style>
#     body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 24px; }
#     h1 { margin-bottom: 0; }
#     .sub { color: #555; margin-top: 4px; }
#     .grid { display: grid; gap: 20px; }
#     .two { grid-template-columns: 1fr; }
#     .three { grid-template-columns: 1fr; }
#     @media (min-width: 1024px) {
#       .two { grid-template-columns: 1fr 1fr; }
#       .three { grid-template-columns: 1fr 1fr 1fr; }
#     }
#     .card { border: 1px solid #eee; border-radius: 12px; padding: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
#     .controls { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin: 12px 0; }
#     .controls label { display:flex; gap:6px; align-items:center; }
#     input, select, button { padding:8px 10px; border-radius:8px; border:1px solid #ddd; }
#     #notes { white-space: pre-wrap; background:#fafafa; border-radius:8px; padding:12px; border:1px solid #eee; }
#     .muted { color:#666; font-size: 12px; }
#   </style>
# </head>
# <body>
#   <h1>러닝 대시보드</h1>
#   <div class="sub">고정 스키마 CSV에서 직접 시각화. (일/주간 추이, 이동통계, Pace↔Speed, 분포, 상자그림, 효율지수)</div>

#   <div class="card">
#     <div class="controls">
#       <label>종류
#         <select id="typeFilter"><option value="__ALL__">모두</option></select>
#       </label>
#       <label>기간
#         <input type="date" id="fromDate"> ~ <input type="date" id="toDate">
#       </label>
#       <label>값 단위
#         <select id="paceMode">
#           <option value="pace">페이스(분/km)</option>
#           <option value="speed">스피드(km/h)</option>
#         </select>
#       </label>
#       <label>이동 통계
#         <select id="rollStat">
#           <option value="mean">평균</option>
#           <option value="median">중앙값</option>
#         </select>
#       </label>
#       <label>윈도우
#         <select id="rollWin">
#           <option value="7">7일</option>
#           <option value="28">28일</option>
#         </select>
#       </label>
#       <label>주간 목표(km)
#         <input type="number" id="weeklyGoal" value="30" min="0" step="1" style="width:90px;">
#       </label>
#       <button id="apply">적용</button>
#       <button id="reset">초기화</button>
#     </div>
#     <div class="muted">포인트를 클릭하면 아래 노트가 표시됩니다.</div>
#   </div>

#   <div class="grid two">
#     <div class="card">
#       <h3>일일 거리 (km) + 이동통계</h3>
#       <div id="distDaily" style="height:360px;"></div>
#     </div>
#     <div class="card">
#       <h3 id="paceTitle">일일 페이스 (분/km) + 이동통계</h3>
#       <div id="paceDaily" style="height:360px;"></div>
#     </div>
#   </div>

#   <div class="grid two">
#     <div class="card">
#       <h3>일일 RPE</h3>
#       <div id="rpeDaily" style="height:300px;"></div>
#     </div>
#     <div class="card">
#       <h3>주간 합계 vs 목표</h3>
#       <div id="weeklyTotals" style="height:320px;"></div>
#     </div>
#   </div>

#   <div class="grid three">
#     <div class="card">
#       <h3>분포: 페이스/스피드</h3>
#       <div id="histPace" style="height:280px;"></div>
#     </div>
#     <div class="card">
#       <h3>분포: 거리/ RPE</h3>
#       <div id="histDistRpe" style="height:280px;"></div>
#     </div>
#     <div class="card">
#       <h3>상자그림: 타입별 페이스/스피드</h3>
#       <div id="boxByType" style="height:280px;"></div>
#     </div>
#   </div>

#   <div class="card">
#     <h3>효율 지수 (speed / HR)</h3>
#     <div id="efficiency" style="height:320px;"></div>
#     <div class="muted">* HR이 비어있는 날은 제외됩니다.</div>
#   </div>

#   <div class="card">
#     <h3>선택한 러닝 노트</h3>
#     <div id="notes">(포인트를 클릭하세요)</div>
#   </div>

# <script>
# const DAILY = __DAILY__;
# const WEEKLY = __WEEKLY__;

# const typeSelect = document.getElementById('typeFilter');
# const types = Array.from(new Set(DAILY.map(d => d.type))).filter(Boolean);
# types.forEach(t => { const o=document.createElement('option'); o.value=t; o.innerText=t; typeSelect.appendChild(o); });

# const fromInput = document.getElementById('fromDate');
# const toInput = document.getElementById('toDate');
# const dates = DAILY.map(d => d.date).sort();
# if (dates.length) { fromInput.value = dates[0]; toInput.value = dates[dates.length-1]; }

# const paceModeSel = document.getElementById('paceMode');
# const rollStatSel = document.getElementById('rollStat');
# const rollWinSel = document.getElementById('rollWin');
# const weeklyGoalInput = document.getElementById('weeklyGoal');

# function filteredDaily() {
#   const t = typeSelect.value;
#   const from = fromInput.value || '0000-01-01';
#   const to = toInput.value || '9999-12-31';
#   return DAILY.filter(d => (t==='__ALL__' || d.type===t) && d.date>=from && d.date<=to);
# }

# function rolling(values, window, stat) {
#   const out = new Array(values.length).fill(null);
#   for (let i=0; i<values.length; i++) {
#     const start = Math.max(0, i-window+1);
#     const seg = values.slice(start, i+1).filter(v => v!=null && !Number.isNaN(v));
#     if (!seg.length) continue;
#     if (stat==='median') {
#       const s = seg.slice().sort((a,b)=>a-b);
#       const m = Math.floor(s.length/2);
#       out[i] = s.length%2 ? s[m] : (s[m-1]+s[m])/2;
#     } else {
#       out[i] = seg.reduce((a,b)=>a+b,0)/seg.length;
#     }
#   }
#   return out;
# }

# function render() {
#   const d = filteredDaily();
#   const x = d.map(r => r.date);

#   const dist = d.map(r => (r.dist_km!=null? +r.dist_km : null));
#   const rw = +rollWinSel.value;
#   const rs = rollStatSel.value;
#   const distRoll = rolling(dist, rw, rs);

#   Plotly.newPlot('distDaily', [
#     { x, y: dist, mode: 'lines+markers', name: '거리(km)', hovertemplate: '%{x}<br>%{y:.2f} km<extra></extra>' },
#     { x, y: distRoll, mode: 'lines', name: `이동${rs==='median'?'중앙값':'평균'}(${rw}일)`, hovertemplate: '%{x}<br>%{y:.2f} km (roll)<extra></extra>' }
#   ], { margin: {t:30,l:40,r:10,b:40}, xaxis: {title:'날짜'}, yaxis: {title:'km'} }, {displayModeBar:false});

#   const paceTitle = document.getElementById('paceTitle');
#   const mode = paceModeSel.value;
#   let series = null, seriesRoll = null, yaxis = {title:''}, hover = '';

#   if (mode==='pace') {
#     series = d.map(r => (r.pace_minpkm!=null? +r.pace_minpkm : null));
#     seriesRoll = rolling(series, rw, rs);
#     yaxis = {title:'분/ km', autorange:'reversed'};
#     hover = '%{x}<br>%{y:.2f} 분/km<extra></extra>';
#     paceTitle.textContent = '일일 페이스 (분/km) + 이동통계';
#   } else {
#     series = d.map(r => (r.pace_minpkm!=null? (60.0/ +r.pace_minpkm) : null));
#     seriesRoll = rolling(series, rw, rs);
#     yaxis = {title:'km/h'};
#     hover = '%{x}<br>%{y:.2f} km/h<extra></extra>';
#     paceTitle.textContent = '일일 스피드 (km/h) + 이동통계';
#   }

#   Plotly.newPlot('paceDaily', [
#     { x, y: series, mode: 'lines+markers', name: (mode==='pace'?'페이스':'스피드'), hovertemplate: hover },
#     { x, y: seriesRoll, mode: 'lines', name: `이동${rs==='median'?'중앙값':'평균'}(${rw}일)`, hovertemplate: hover }
#   ], { margin: {t:30,l:50,r:10,b:40}, xaxis: {title:'날짜'}, yaxis }, {displayModeBar:false});

#   Plotly.newPlot('rpeDaily', [
#     { x, y: d.map(r => +r.rpe), mode: 'lines+markers', name: 'RPE', hovertemplate: '%{x}<br>RPE %{y}<extra></extra>' }
#   ], { margin: {t:30,l:40,r:10,b:40}, xaxis: {title:'날짜'}, yaxis: {title:'RPE', rangemode:'tozero'} }, {displayModeBar:false});

#   const goal = Math.max(0, +weeklyGoalInput.value || 0);
#   const weekX = WEEKLY.map(w => w.week);
#   const weekDist = WEEKLY.map(w => +w.dist_km);
#   Plotly.newPlot('weeklyTotals', [
#     { x: weekX, y: weekDist, type: 'bar', name: '주간 거리(km)', hovertemplate: '%{x} 주<br>%{y:.1f} km<extra></extra>' },
#     { x: weekX, y: new Array(weekX.length).fill(goal), mode: 'lines', name: '목표선', hovertemplate: '%{x} 주<br>목표 %{y:.1f} km<extra></extra>' }
#   ], { margin: {t:30,l:40,r:40,b:40}, xaxis: {title:'주'}, yaxis: {title:'거리(km)'} }, {displayModeBar:false});

#   const paceVals = d.map(r => (r.pace_minpkm!=null? +r.pace_minpkm : null)).filter(v => v!=null);
#   const speedVals = paceVals.map(p => 60.0/p);
#   Plotly.newPlot('histPace', [
#     { x: (paceModeSel.value==='pace'? paceVals : speedVals), type:'histogram', name:(paceModeSel.value==='pace'?'페이스(분/km)':'스피드(km/h)') }
#   ], { margin: {t:30,l:40,r:10,b:30}, xaxis: {title:(paceModeSel.value==='pace'?'분/ km':'km/h')}, yaxis: {title:'카운트'} }, {displayModeBar:false});

#   Plotly.newPlot('histDistRpe', [
#     { x: dist.filter(v=>v!=null), type:'histogram', name:'거리(km)', opacity:0.75 },
#     { x: d.map(r=>+r.rpe), type:'histogram', name:'RPE', opacity:0.6 }
#   ], { barmode:'overlay', margin: {t:30,l:40,r:10,b:30}, xaxis: {title:'값'}, yaxis: {title:'카운트'} }, {displayModeBar:false});

#   const byType = {};
#   d.forEach(r => {
#     const key = r.type || 'unknown';
#     if (!byType[key]) byType[key] = [];
#     const v = (paceModeSel.value==='pace' ? (r.pace_minpkm!=null? +r.pace_minpkm : null) : (r.pace_minpkm!=null? 60.0/+r.pace_minpkm : null));
#     if (v!=null && !Number.isNaN(v)) byType[key].push(v);
#   });
#   const boxTraces = Object.keys(byType).sort().map(k => ({ y: byType[k], type:'box', name:k, boxpoints:false }));
#   Plotly.newPlot('boxByType', boxTraces, { margin: {t:30,l:40,r:10,b:30}, yaxis: {title:(paceModeSel.value==='pace'?'분/ km (낮을수록 좋음)':'km/h (높을수록 좋음)')}, xaxis: {title:'타입'} }, {displayModeBar:false});

#   const effX = [];
#   const effY = [];
#   d.forEach(r => {
#     const p = (r.pace_minpkm!=null? +r.pace_minpkm : null);
#     const hr = (r.hr_avg!=null? +r.hr_avg : null);
#     if (p!=null && hr!=null && !Number.isNaN(p) && !Number.isNaN(hr) && hr>0) {
#       const speed = 60.0/p;
#       effX.push(r.date);
#       effY.push(speed / hr);
#     }
#   });
#   Plotly.newPlot('efficiency', [
#     { x: effX, y: effY, mode:'lines+markers', name:'speed/HR', hovertemplate:'%{x}<br>%{y:.4f}} (km/h)/bpm<extra></extra>' }
#   ], { margin: {t:30,l:40,r:10,b:40}, xaxis: {title:'날짜'}, yaxis: {title:'효율 지수 (km/h per bpm)'} }, {displayModeBar:false});

#   const notes = document.getElementById('notes');
#   const clickHandler = (data) => {
#     if (!data.points || !data.points.length) return;
#     const idx = data.points[0].pointIndex;
#     const row = d[idx];
#     if (!row) return;
#     const text = [
#       `날짜: ${row.date}`,
#       `종류: ${row.type}`,
#       `거리: ${row.dist_km} km`,
#       `페이스: ${row.pace_minpkm.toFixed(2)} 분/km (스피드 ${(row.pace_minpkm? (60/row.pace_minpkm).toFixed(2):'N/A')} km/h)`,
#       `평균 심박: ${row.hr_avg ?? 'N/A'}`,
#       `RPE: ${row.rpe}`,
#       '',
#       (row.notes || '(노트 없음)')
#     ].join('\n');
#     notes.textContent = text;
#   };
#   ['distDaily','paceDaily','rpeDaily'].forEach(id => {
#     const gd = document.getElementById(id);
#     gd.on('plotly_click', clickHandler);
#   });
# }

# render();
# document.getElementById('apply').onclick = render;
# document.getElementById('reset').onclick = () => {
#   typeSelect.value='__ALL__';
#   fromInput.value = dates[0];
#   toInput.value = dates[dates.length-1];
#   paceModeSel.value='pace';
#   rollStatSel.value='mean';
#   rollWinSel.value='7';
#   weeklyGoalInput.value='30';
#   render();
# };
# </script>
# </body>
# </html>
# """

# def main():
#     ap = argparse.ArgumentParser()
#     ap.add_argument("--src", default="run_log_plan_actual_summary.csv")
#     ap.add_argument("--out", default="run_dashboard.html")
#     args = ap.parse_args()

#     df = detect_and_read_csv(Path(args.src))

#     expected = ["date","type","distance_km","avg_pace","avg_hr_bpm","avg_cadence_spm","rpe","notes"]
#     missing_cols = [c for c in expected if c not in df.columns]
#     if missing_cols:
#         raise ValueError(f"CSV missing required columns: {missing_cols}")

#     df["date"] = df["date"].apply(parse_date)
#     df = df.sort_values("date").reset_index(drop=True)

#     # Normalize fields
#     df["type"] = df["type"].astype(str).str.strip().str.lower()

#     # distance (km) - decimal
#     df["dist_km"] = pd.to_numeric(df["distance_km"], errors="coerce")

#     # pace (mm:ss -> minutes)
#     df["pace_minpkm"] = df["avg_pace"].apply(parse_pace_mmss_to_minutes)

#     # hr & cadence
#     df["hr_avg"] = pd.to_numeric(df["avg_hr_bpm"], errors="coerce")
#     df["cadence_spm"] = pd.to_numeric(df["avg_cadence_spm"], errors="coerce")

#     # rpe
#     df["rpe"] = pd.to_numeric(df["rpe"], errors="coerce")

#     # notes
#     df["notes"] = df["notes"].astype(str).fillna("")

#     # week (Monday)
#     df["week"] = df["date"].apply(monday_of_week)

#     # Impute only missing values (per-type median -> global median). Distances often 0 allowed; don't impute dist.
#     # pace
#     df["pace_minpkm"] = impute_with_medians(df, "pace_minpkm", by="type")
#     # hr
#     df["hr_avg"] = impute_with_medians(df, "hr_avg", by="type")
#     # cadence
#     df["cadence_spm"] = impute_with_medians(df, "cadence_spm", by="type")
#     # rpe: prefer type defaults if still missing
#     type_rpe_default = {"easy":5, "long":6, "tempo":7, "interval":8, "race":9, "test":6, "rest":2}
#     miss_rpe_mask = df["rpe"].isna()
#     df.loc[miss_rpe_mask, "rpe"] = df.loc[miss_rpe_mask, "type"].map(type_rpe_default)
#     df["rpe"] = impute_with_medians(df, "rpe", by="type")

#     # Prepare DAILY/WEEKLY JSON
#     daily = df[["date","type","dist_km","pace_minpkm","hr_avg","rpe","notes"]].copy()
#     daily["date"] = pd.to_datetime(daily["date"]).dt.strftime("%Y-%m-%d")

#     weekly = (
#         df.groupby(pd.to_datetime(df["week"]).dt.strftime("%Y-%m-%d"), as_index=False)
#           .agg(week=("week","first"),
#                dist_km=("dist_km","sum"),
#                runs=("date","count"),
#                pace_minpkm=("pace_minpkm","mean"),
#                rpe=("rpe","mean"))
#           .sort_values("week")
#     )
#     weekly["week"] = pd.to_datetime(weekly["week"]).dt.strftime("%Y-%m-%d")

#     html = (DASHBOARD_HTML
#             .replace("__DAILY__", json.dumps(json.loads(daily.to_json(orient="records")), ensure_ascii=False))
#             .replace("__WEEKLY__", json.dumps(json.loads(weekly.to_json(orient="records")), ensure_ascii=False)))

#     Path(args.out).write_text(html, encoding="utf-8")
#     print(f"Wrote {args.out}")

# if __name__ == "__main__":
#     main()
