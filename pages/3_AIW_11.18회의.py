# ==========================================
# 파일명: 3_AIW_11_18_회의.py
# 목적: 11/18 회의용 실시간 비중 조절 및 시나리오 지표 비교
# ==========================================
import streamlit as st
import pandas as pd
import numpy as np
import datetime

from AIW_risk_engine import get_engine_data, calculate_portfolio_risks, generate_risk_report

st.set_page_config(page_title="AIW_11/18 회의", layout="wide")

# ==========================================
# 0. 기준일 연동 및 엔진 가동
# ==========================================
target_date_str = st.session_state.get('target_date', datetime.datetime.today().date()).strftime('%Y-%m-%d')
target_dt = pd.to_datetime(target_date_str)
df_portfolio, returns_df, benchmark_returns, rf_rate = get_engine_data(target_date_str)

st.title("🤝 AIW_11/18 회의 - 포트폴리오 전략 시뮬레이션")
st.markdown(f"**현재 설정된 기준일:** {target_date_str}")
st.divider()

# ==========================================
# 1. 종목별 위험지표
# ==========================================
st.subheader("1. 현재 편입 종목별 위험지표")

risk_df = generate_risk_report(df_portfolio, returns_df, benchmark_returns, rf_rate)

def fmt_p(val): return f"{val*100:.2f}%" if pd.notna(val) else "N/A"
def fmt_n(val): return f"{val:.2f}" if pd.notna(val) else "N/A"

if risk_df is not None and not risk_df.empty:
    formatted_risk_df = risk_df.copy()
    pct_cols = ['비중', '수익률', '표준편차(일간)', '표준편차(연환산)', '10일VaR(95%)', '10일ES(95%)', 'MDD', '주간 MDD']
    num_cols = ['베타', '샤프지수', '소티노지수']
    for c in pct_cols: formatted_risk_df[c] = formatted_risk_df[c].apply(fmt_p)
    for c in num_cols: formatted_risk_df[c] = formatted_risk_df[c].apply(fmt_n)
    st.dataframe(formatted_risk_df, hide_index=True, use_container_width=True)
else:
    st.warning("종목별 위험지표 데이터가 없습니다.")

st.divider()

# ==========================================
# 2. 실시간 비중 조절 포트폴리오 시뮬레이터 (슬라이더 + 직접 입력 동기화)
# ==========================================
st.subheader("2. 실시간 비중(%) 조절 시뮬레이터")
st.caption("숫자를 직접 입력하거나 슬라이더를 드래그하여 비중을 조절하세요. 남은 잔여 비중은 '현금'으로 자동 산정되어 표시됩니다.")

cols = st.columns(5)
new_weights = {}
total_stock_weight = 0.0

idx = 0
cash_container = None

# 전체 유니버스 반복 (현금 포함)
for i, row in df_portfolio.iterrows():
    col = cols[idx % 5]
    ticker = row['티커']
    
    if ticker == 'CASH':
        # 현금 UI가 들어갈 자리만 예약
        cash_container = col.container(border=True)
        idx += 1
        continue
        
    current_w = row['비중'] * 100
    sl_key = f"sl_{ticker}"
    num_key = f"num_{ticker}"
    
    if sl_key not in st.session_state: st.session_state[sl_key] = float(current_w)
    if num_key not in st.session_state: st.session_state[num_key] = float(current_w)
    
    def sync_sl_to_num(t=ticker): st.session_state[f"num_{t}"] = st.session_state[f"sl_{t}"]
    def sync_num_to_sl(t=ticker): st.session_state[f"sl_{t}"] = st.session_state[f"num_{t}"]
    
    with col.container(border=True):
        st.markdown(f"**{row['종목명']}**")
        w_val = st.number_input("비중 입력(%)", min_value=0.0, max_value=100.0, step=1.0, format="%.2f", key=num_key, on_change=sync_num_to_sl, label_visibility="collapsed")
        st.slider("비중 슬라이더(%)", min_value=0.0, max_value=100.0, step=0.1, key=sl_key, on_change=sync_sl_to_num, label_visibility="collapsed")
        
    new_weights[ticker] = w_val / 100.0
    total_stock_weight += (w_val / 100.0)
    idx += 1

cash_weight = 1.0 - total_stock_weight

# 연산이 끝난 최종 현금 비중 채워넣기 (읽기 전용)
if cash_container is not None:
    with cash_container:
        st.markdown("**현금 (자동 산정)**")
        st.number_input("현금 비중(%)", value=float(cash_weight * 100), disabled=True, format="%.2f", key="cash_num", label_visibility="collapsed")
        st.slider("현금 슬라이더(%)", min_value=0.0, max_value=100.0, value=float(max(0, cash_weight * 100)), disabled=True, key="cash_sl", label_visibility="collapsed")

if cash_weight < 0:
    st.error(f"🚨 총 편입 비중이 100%를 초과했습니다! (초과분: {abs(cash_weight)*100:.2f}%)")
else:
    st.success(f"🟢 포트폴리오 비중 설정 완료 (잔여 현금 버퍼: {cash_weight*100:.2f}%)")

# 시뮬레이션용 데이터프레임 재구성
sim_df_portfolio = df_portfolio.copy()
initial_aum = sim_df_portfolio['평가금액'].sum()

for i, row in sim_df_portfolio.iterrows():
    ticker = row['티커']
    if ticker == 'CASH':
        sim_df_portfolio.at[i, '비중'] = cash_weight
        sim_df_portfolio.at[i, '평가금액'] = initial_aum * cash_weight
    else:
        sim_df_portfolio.at[i, '비중'] = new_weights[ticker]
        sim_df_portfolio.at[i, '평가금액'] = initial_aum * new_weights[ticker]

# 현재(P0) 및 시뮬레이션 지표 연산
old_metrics = calculate_portfolio_risks(df_portfolio, returns_df, benchmark_returns, rf_rate)
sim_metrics = calculate_portfolio_risks(sim_df_portfolio, returns_df, benchmark_returns, rf_rate)

st.markdown("##### 🚀 조절 후 포트폴리오 핵심 지표 변화")
risk_cols = st.columns(6)
r_keys = [
    ("포트폴리오_베타", "베타", ""),
    ("10일VaR", "10일 VaR (95%)", "%"), ("10일ES", "10일 ES (95%)", "%"),
    ("MDD", "MDD", "%"), ("주간MDD", "주간 MDD", "%"),
    ("샤프지수", "샤프 지수", "")
]

for col, (k, title, unit) in zip(risk_cols, r_keys):
    o, n = old_metrics.get(k, 0), sim_metrics.get(k, 0)
    mult = 100 if unit == "%" else 1
    inv_color = "inverse" if k in ["10일VaR", "10일ES", "MDD", "주간MDD"] else "normal"
    col.metric(label=title, value=f"{n*mult:.2f}{unit}", delta=f"{(n-o)*mult:.2f}{unit}", delta_color=inv_color)

st.divider()

# ==========================================
# 3. 회의용 시나리오(P1~P5) 분배 및 지표 종합 비교 
# ==========================================
st.subheader("3. 시나리오별 포트폴리오 지표 종합 (P0 ~ P5)")

SCENARIOS = {
    "P1 회복": {"069500": 0.35, "005930": 0.20, "005935": 0.08, "000660": 0.20, "006400": 0.07, "032940": 0.10, "114800": 0.00},
    "P2 불확실": {"069500": 0.35, "005930": 0.15, "005935": 0.05, "000660": 0.10, "006400": 0.05, "032940": 0.10, "114800": 0.00},
    "P3 AI약화": {"069500": 0.20, "005930": 0.08, "005935": 0.04, "000660": 0.05, "006400": 0.05, "032940": 0.05, "114800": 0.25},
    "P4 매크로방어": {"069500": 0.10, "005930": 0.05, "005935": 0.03, "000660": 0.03, "006400": 0.03, "032940": 0.03, "114800": 0.25},
    "P5 확인된숏": {"069500": 0.00, "005930": 0.00, "005935": 0.00, "000660": 0.00, "006400": 0.00, "032940": 0.00, "114800": 0.40} 
}

# --- 3-1. 시나리오별 종목 분배 계획 ---
st.markdown("##### 📊 시나리오별 종목 배분 현황")
alloc_data = []

ticker_name_map = dict(zip(df_portfolio['티커'], df_portfolio['종목명']))
if "114800" not in ticker_name_map: ticker_name_map["114800"] = "KODEX 인버스"

for s_name, weights in SCENARIOS.items():
    row_data = {"시나리오": s_name}
    tot_weight = 0.0
    for t, w in weights.items():
        row_data[ticker_name_map.get(t, t)] = w
        tot_weight += w
    row_data["현금"] = 1.0 - tot_weight
    alloc_data.append(row_data)

df_alloc = pd.DataFrame(alloc_data).set_index("시나리오").fillna(0)
for c in df_alloc.columns: df_alloc[c] = df_alloc[c].apply(lambda x: f"{x*100:.1f}%")

st.dataframe(df_alloc, use_container_width=True)
st.markdown("<br>", unsafe_allow_html=True)

# --- 3-2. 시나리오별 위험 지표 비교 결과 ---
st.markdown("##### 📉 시나리오별 핵심 지표 변화 비교")

# 벤치마크 고정 지표 추출
bm_beta = 1.00
bm_var = old_metrics.get("벤치마크_10일VaR", 0)
bm_es = old_metrics.get("벤치마크_10일ES", 0)
bm_mdd = old_metrics.get("벤치마크_MDD", 0)
bm_wmdd = old_metrics.get("벤치마크_주간MDD", 0)
bm_sharpe = old_metrics.get("벤치마크_샤프", 0)
bm_sortino = old_metrics.get("벤치마크_소티노", 0)

bm_dict = {
    "베타": bm_beta, "10일VaR": bm_var, "10일ES": bm_es,
    "MDD": bm_mdd, "주간MDD": bm_wmdd, "샤프지수": bm_sharpe, "소티노지수": bm_sortino
}

scenario_results = []

# 1. 벤치마크 행 추가
scenario_results.append({
    "시나리오": "BM 벤치마크", 
    "베타": bm_beta, "10일VaR": bm_var, "10일ES": bm_es,
    "MDD": bm_mdd, "주간MDD": bm_wmdd,
    "샤프지수": bm_sharpe, "소티노지수": bm_sortino
})

# 2. P0 현재참조 행 추가
scenario_results.append({
    "시나리오": "P0 현재참조", 
    "베타": old_metrics.get("포트폴리오_베타", 0),
    "10일VaR": old_metrics.get("10일VaR", 0), "10일ES": old_metrics.get("10일ES", 0),
    "MDD": old_metrics.get("MDD", 0), "주간MDD": old_metrics.get("주간MDD", 0),
    "샤프지수": old_metrics.get("샤프지수", 0), "소티노지수": old_metrics.get("소티노지수", 0)
})

# 3. P1~P5 시나리오 행 추가
for s_name, weights in SCENARIOS.items():
    temp_df = df_portfolio.copy()
    tot_w = 0.0
    for i, row in temp_df.iterrows():
        t = row['티커']
        if t == 'CASH': continue
        w = weights.get(t, 0.0)
        temp_df.at[i, '비중'] = w
        tot_w += w
    temp_df.loc[temp_df['티커'] == 'CASH', '비중'] = 1.0 - tot_w
    
    s_metrics = calculate_portfolio_risks(temp_df, returns_df, benchmark_returns, rf_rate)
    scenario_results.append({
        "시나리오": s_name, 
        "베타": s_metrics.get("포트폴리오_베타", 0),
        "10일VaR": s_metrics.get("10일VaR", 0), "10일ES": s_metrics.get("10일ES", 0),
        "MDD": s_metrics.get("MDD", 0), "주간MDD": s_metrics.get("주간MDD", 0),
        "샤프지수": s_metrics.get("샤프지수", 0), "소티노지수": s_metrics.get("소티노지수", 0)
    })

# 4. 데이터프레임 변환 및 포맷팅 (본값 + 벤치마크 대비 Delta 텍스트)
df_scenarios = pd.DataFrame(scenario_results).set_index("시나리오")
pct_cols = ["10일VaR", "10일ES", "MDD", "주간MDD"]

for col in df_scenarios.columns:
    is_pct = col in pct_cols
    bm_val = bm_dict[col]
    new_col_data = []
    
    for idx, val in df_scenarios[col].items():
        if pd.isna(val):
            new_col_data.append("N/A")
            continue
        
        # [본값 포맷팅]
        main_val = val * 100 if is_pct else val
        if abs(main_val) < 0.005: main_str = f"0.00{'%' if is_pct else ''}"
        else: main_str = f"{'+' if main_val > 0 else ''}{main_val:.2f}{'%' if is_pct else ''}"
        
        if idx == "BM 벤치마크":
            new_col_data.append(main_str)
        else:
            # [벤치마크 대비 차이(Delta) 포맷팅]
            diff = val - bm_val
            diff_val = diff * 100 if is_pct else diff
            
            if abs(diff_val) < 0.005: # 차이가 거의 없을 때
                delta_str = f"(- 0.00{'%' if is_pct else ''})"
            else:
                arrow = "↑" if diff > 0 else "↓"
                delta_str = f"({arrow} {abs(diff_val):.2f}{'%' if is_pct else ''})"
                
            new_col_data.append(f"{main_str}  {delta_str}")
            
    df_scenarios[col] = new_col_data

st.dataframe(df_scenarios, use_container_width=True)
