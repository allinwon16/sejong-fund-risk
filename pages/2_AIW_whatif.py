# ==========================================
# 파일명: AIW_whatif.py
# 목적: 실시간 포트폴리오 시뮬레이터
# ==========================================
import streamlit as st
import pandas as pd
import numpy as np
import scipy.optimize as sco
import FinanceDataReader as fdr
import datetime
import plotly.express as px

from AIW_risk_engine import get_engine_data, calculate_portfolio_risks, COMPLIANCE_RULES

st.set_page_config(page_title="세투연펀드 What-If 시뮬레이터", layout="wide")

# 기준일 연동 및 엔진 가동
target_date_str = st.session_state.get('target_date', datetime.datetime.today().date()).strftime('%Y-%m-%d')
target_dt = pd.to_datetime(target_date_str)
df_portfolio, returns_df, benchmark_returns, rf_rate = get_engine_data(target_date_str)

# 세션 상태 초기화
if 'sim_df_portfolio' not in st.session_state: st.session_state.sim_df_portfolio = df_portfolio.copy()
if 'sim_returns_df' not in st.session_state: st.session_state.sim_returns_df = returns_df.copy()

# ==========================================
# 1. 신규 종목 동적 편입
# ==========================================
st.subheader("🔍 What-If 시뮬레이터")
with st.expander("편입을 고려 중인 새로운 종목을 검색하여 추가하세요", expanded=False):
    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
    new_ticker = c1.text_input("종목 코드 (티커)", placeholder="예: 035420")
    new_name = c2.text_input("종목명", placeholder="예: NAVER")
    new_sector = c3.selectbox("섹터 선택", ["IT/반도체", "IT/서비스", "IT/부품", "금융/지주", "바이오/제약", "원자재", "화장품/소비재", "기계/에너지", "전기/전자", "기타"])
    
    with c4:
        st.markdown("<div style='margin-top: 27px;'></div>", unsafe_allow_html=True)
        if st.button("➕ 추가", use_container_width=True):
            if new_ticker and new_name:
                if new_ticker in st.session_state.sim_df_portfolio['티커'].values:
                    st.warning("이미 유니버스에 존재하는 종목입니다.")
                else:
                    with st.spinner(f"{new_name} 데이터를 실시간으로 파싱 중입니다..."):
                        start_date = (target_dt - pd.Timedelta(days=365)).strftime('%Y-%m-%d')
                        try:
                            df_new = fdr.DataReader(new_ticker, start=start_date, end=target_date_str)
                            if not df_new.empty:
                                current_price = float(df_new['Close'].iloc[-1])
                                new_returns = df_new['Close'].pct_change().dropna()
                                new_returns.index = pd.to_datetime(new_returns.index).normalize()
                                
                                st.session_state.sim_returns_df[new_ticker] = new_returns
                                new_row = pd.DataFrame([{"티커": new_ticker, "종목명": new_name, "섹터": new_sector, "매수가": current_price, "현재가": current_price, "수량": 0, "평가금액": 0.0, "수익률": 0.0, "비중": 0.0}])
                                st.session_state.sim_df_portfolio = pd.concat([st.session_state.sim_df_portfolio, new_row], ignore_index=True)
                                
                                st.success(f"✅ {new_name} 편입 완료! (현재가: {int(current_price):,}원)")
                                st.rerun()
                            else: st.error("데이터를 불러올 수 없습니다. 티커를 확인해 주세요.")
                        except Exception as e: st.error(f"주가 연동 실패: {e}")
            else: st.warning("티커와 종목명을 모두 입력해 주세요.")
st.divider()

# 선행 리스크 계산
old_metrics = calculate_portfolio_risks(st.session_state.sim_df_portfolio, st.session_state.sim_returns_df, benchmark_returns, rf_rate)

# ==========================================
# 2. 컴플라이언스 연동형 AI 최적화 연산 함수
# ==========================================
def calculate_optimal_shares(df_sim, returns, bench_returns, rf, total_aum, min_shares_dict):
    valid_tickers = [t for t in df_sim[df_sim['티커'] != 'CASH']['티커'] if t in returns.columns]
    if not valid_tickers: return None

    mu, cov = returns[valid_tickers].mean() * 252, returns[valid_tickers].cov() * 252
    bm_std = bench_returns.std() * np.sqrt(252)

    k200_etfs = ['069500', '102110', '148020', '152100', '213610', '227830', '278530', '278540', '292750', '315930', '379660', '433330']
    etf_brands = ['KODEX', 'TIGER', 'KBSTAR', 'ACE', 'ARIRANG', 'KOSEF', 'HANARO']
    hedge_idx, other_idx = [], []
    
    for i, t in enumerate(valid_tickers):
        n = df_sim.loc[df_sim['티커'] == t, '종목명'].values[0].upper()
        if "레버리지" in n or "인버스" in n or "2X" in n: hedge_idx.append(i)
        elif t not in k200_etfs and (any(b in n for b in etf_brands) or "채권" in n): other_idx.append(i)

    def objective(w):
        port_std = np.sqrt(np.dot(w.T, np.dot(cov, w)))
        return 0 if port_std < 1e-4 else -((np.dot(w, mu) - rf) / port_std)

    c_rules = COMPLIANCE_RULES
    constraints = [
        {'type': 'ineq', 'fun': lambda w: bm_std - np.sqrt(np.dot(w.T, np.dot(cov, w)))},
        {'type': 'ineq', 'fun': lambda w: np.sum(w) - c_rules['MIN_STOCK_WEIGHT']},
        {'type': 'ineq', 'fun': lambda w: c_rules['MAX_STOCK_WEIGHT'] - np.sum(w)},
        {'type': 'ineq', 'fun': lambda w: c_rules['MAX_HEDGE_WEIGHT'] - (np.sum(w[hedge_idx]) if hedge_idx else 0)},
        {'type': 'ineq', 'fun': lambda w: c_rules['MAX_OTHER_WEIGHT'] - (np.sum(w[other_idx]) if other_idx else 0)}
    ]
    
    bounds = []
    for t in valid_tickers:
        price = df_sim.loc[df_sim['티커'] == t, '현재가'].values[0]
        min_w = (min_shares_dict.get(t, 0) * price) / total_aum if total_aum > 0 else 0
        max_w = 1.0 if t in k200_etfs else c_rules['MAX_INDIV_WEIGHT']
        bounds.append((min_w, max(min_w, max_w)))

    bounds = tuple(bounds)
    if sum([b[0] for b in bounds]) > c_rules['MAX_STOCK_WEIGHT']: return "EXCEED_AUM"

    init_weights = np.array([1.0 / len(valid_tickers)] * len(valid_tickers))
    init_std = np.sqrt(np.dot(init_weights.T, np.dot(cov, init_weights)))
    if init_std > bm_std: init_weights = init_weights * ((bm_std * 0.8) / init_std)
    
    init_guess = np.maximum(init_weights, [b[0] for b in bounds])
    init_guess = np.minimum(init_guess, [b[1] for b in bounds]) 
    if sum(init_guess) > c_rules['MAX_STOCK_WEIGHT']: init_guess = np.array([b[0] for b in bounds]) 

    res = sco.minimize(objective, init_guess, method='SLSQP', bounds=bounds, constraints=constraints)
    if res.success or "Positive directional derivative" in str(res.message):
        return {t: max(int((total_aum * res.x[i]) // df_sim.loc[df_sim['티커'] == t, '현재가'].values[0]), min_shares_dict.get(t, 0)) for i, t in enumerate(valid_tickers)}
    return None

# ==========================================
# 3. 주식 수 조절 패널 및 UI 렌더링
# ==========================================
df_sim = st.session_state.sim_df_portfolio.copy()
initial_aum = df_sim['평가금액'].sum() 

col_t, col_b = st.columns([4, 1])
col_t.subheader("1. 종목별 주식 수 및 현금 연동 조절")
col_t.caption("하한선 수량을 입력하고 AI 버튼을 누르면, 펀드 운용 규정(컴플라이언스)을 준수하는 Max Sharpe 비중을 산출합니다.")

if col_b.button("🤖 최적 조합 산출", use_container_width=True):
    with st.spinner("운용 규정 준수 및 최적 포트폴리오 연산 중..."):
        min_shares = {r['티커']: st.session_state.get(f"input_{r['티커']}", int(r['수량'])) for _, r in df_sim.iterrows() if r['티커'] != 'CASH'}
        opt_shares = calculate_optimal_shares(df_sim, st.session_state.sim_returns_df, benchmark_returns, rf_rate, initial_aum, min_shares)
        
        if opt_shares == "EXCEED_AUM": st.error("⚠️ 설정한 하한선 주식수가 너무 많아 펀드 규정(최대 주식비중)을 초과합니다.")
        elif opt_shares:
            for t, s in opt_shares.items(): st.session_state[f"input_{t}"] = s
            st.rerun() 
        else: st.error("운용 규정(한도 제한 등)을 모두 만족하면서 최적화할 수 있는 조합이 없습니다.")

# UI 렌더링 및 비중 계산
new_shares, stock_eval_sum, placeholders = [], 0, []
cols = st.columns(5)

for i, row in df_sim.iterrows():
    col = cols[i % 5]
    ph = col.empty()
    placeholders.append(ph)

    if row['티커'] == 'CASH':
        cash_ph = col.empty()
        cash_idx = i
        new_shares.append(0) 
    else:
        k = f"input_{row['티커']}"
        if k not in st.session_state: st.session_state[k] = int(row['수량'])
        val = col.number_input(f"{row['종목명']} 조절", min_value=0, step=1, key=k, label_visibility="collapsed")
        new_shares.append(val)
        stock_eval_sum += val * row['현재가']

sim_cash = initial_aum - stock_eval_sum
df_sim['평가금액'] = [sim_cash if r['티커'] == 'CASH' else new_shares[i] * r['현재가'] for i, r in df_sim.iterrows()]
df_sim['비중'] = df_sim['평가금액'] / initial_aum

for i, row in df_sim.iterrows():
    color = "#21c354" if row['비중'] > 0 else "gray"
    if row['티커'] == 'CASH' and row['비중'] < 0: color = "#ff4b4b" 
    placeholders[i].markdown(f"<div style='margin-bottom:5px;'><b>{row['종목명']}</b><br><span style='color:{color}; font-size:14px; font-weight:bold;'>비중: {row['비중']*100:.1f}%</span></div>", unsafe_allow_html=True)
    if i == cash_idx: cash_ph.text_input("현금액", value=f"{int(sim_cash):,} 원", disabled=True, label_visibility="collapsed")

if sim_cash < 0: st.warning("⚠️ **주의:** 자산 초과 매수로 현금이 마이너스(레버리지) 상태입니다.")

# ==========================================
# 4. 시뮬레이션 결과 연산 및 출력
# ==========================================
if initial_aum > 0:
    sim_metrics = calculate_portfolio_risks(df_sim, st.session_state.sim_returns_df, benchmark_returns, rf_rate)
    
    st.divider()
    st.subheader("2. 시뮬레이션 상세 분석")
    
    # 탭(Tabs) 생성
    tab1, tab2, tab3 = st.tabs(["🚀 성과 및 섹터 비중", "📉 VaR 리스크 분포", "🛡️ 컴플라이언스 점검"])
    
    # 탭 1: 핵심 성과 지표 및 섹터 쏠림
    with tab1:
        st.markdown("##### 🛡️ 핵심 위험 지표")
        risk_cols = st.columns(5)
        r_keys = [("포트폴리오_베타", "베타", "", 1.00), ("10일VaR", "10일 VaR (95%)", "%", sim_metrics.get("벤치마크_10일VaR",0)), ("10일ES", "10일 ES (95%)", "%", sim_metrics.get("벤치마크_10일ES",0)), ("MDD", "MDD", "%", sim_metrics.get("벤치마크_MDD",0)), ("주간MDD", "주간 MDD", "%", sim_metrics.get("벤치마크_주간MDD",0))]
        
        for col, (k, title, unit, bm) in zip(risk_cols, r_keys):
            o, n = old_metrics.get(k, 0), sim_metrics.get(k, 0)
            mult = 100 if unit == "%" else 1
            col.metric(title, f"{n*mult:.2f}{unit}", delta=f"{(n-o)*mult:.2f}{unit}", delta_color="normal" if "MDD" in k else "inverse")
            col.caption(f"벤치마크: {bm*mult:.2f}{unit}")

        st.markdown("<br>##### 🚀 핵심 성과 지표", unsafe_allow_html=True)
        perf_cols = st.columns(5)
        p_keys = [("샤프지수", "샤프 지수", sim_metrics.get("벤치마크_샤프", 0)), ("소티노지수", "소티노 지수", sim_metrics.get("벤치마크_소티노", 0))]
        
        for col, (k, title, bm) in zip(perf_cols[:2], p_keys):
            o, n = old_metrics.get(k, 0), sim_metrics.get(k, 0)
            col.metric(title, f"{n:.2f}", delta=f"{n-o:.2f}", delta_color="normal")
            col.caption(f"벤치마크: {bm:.2f}")

        st.divider()
        st.markdown("##### 🔍 시뮬레이션 적용 후 섹터 비중")
        sector_agg = df_sim.groupby('섹터', as_index=False)['비중'].sum().sort_values(by='비중', ascending=False)
        sector_agg['비중'] = sector_agg['비중'].apply(lambda x: f"{x*100:.2f}%")
        st.dataframe(sector_agg, hide_index=True, use_container_width=True)

    # 탭 2: VaR 쏠림 분포 파이차트 및 상세 표
    with tab2:
        st.markdown("##### 📉 종목별 VaR 기여도 분포")
        var_decomp = sim_metrics.get("VaR_기여도_DF")
        if var_decomp is not None and not var_decomp.empty:
            c1, c2 = st.columns([1.5, 1])
            with c1:
                ticker_to_name = {row['티커']: row['종목명'] for _, row in df_sim.iterrows()}
                display_var = var_decomp.rename(index=ticker_to_name).copy()
                display_var = display_var.rename(columns={"Weight": "비중", "Sector": "섹터", "VaR Contribution": "VaR 기여도", "Contribution %": "기여도 비율", "Marginal VaR": "1% 비중 증감시 VaR 증감"})
                display_var = display_var[["비중", "섹터", "VaR 기여도", "기여도 비율", "1% 비중 증감시 VaR 증감"]]
                
                def fmt_p(val): return f"{val*100:.2f}%" if pd.notna(val) else "N/A"
                for c in display_var.columns:
                    if c != "섹터": display_var[c] = display_var[c].apply(fmt_p)
                st.dataframe(display_var, use_container_width=True)
            
            with c2:
                pie_data = var_decomp.reset_index()
                pie_data["Abs_Contribution"] = pie_data["VaR Contribution"].abs()
                fig_pie = px.pie(pie_data, values="Abs_Contribution", names="index", title="종목별 VaR 기여도")
                fig_pie.update_layout(height=320, margin=dict(t=40, b=20, l=20, r=20), legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
                st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.warning("데이터가 부족하여 종목별 VaR 기여도를 계산할 수 없습니다.")

    # 탭 3: 컴플라이언스 룰 체크
    with tab3:
        st.markdown("##### 🛡️ 시뮬레이션 비중 컴플라이언스 점검")
        comp_data = sim_metrics.get("컴플라이언스_상세", [])
        if comp_data:
            comp_df = pd.DataFrame(comp_data)
            st.dataframe(comp_df, hide_index=True, use_container_width=True)
            
            violation_cnt = sim_metrics.get("컴플라이언스_위반건수", 0)
            if violation_cnt > 0:
                st.error(f"🚨 현재 설정된 비중은 펀드 운용 규정을 **{violation_cnt}건 위반**하고 있습니다. 비중을 다시 조절해주세요.")
            else:
                st.success("🟢 현재 설정된 비중은 모든 펀드 운용 규정을 완벽하게 준수하고 있습니다.")
        else:
            st.info("💡 컴플라이언스 점검 데이터가 없습니다.")

else:
    st.warning("⚠️ 포트폴리오 평가금액이 없습니다.")