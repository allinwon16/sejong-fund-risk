# ==========================================
# 파일명: AIW_risk_report.py
# 목적: 리스크 보고서 생성 및 핵심 지표 관리
# ==========================================
import streamlit as st
import pandas as pd
import numpy as np
import datetime
import plotly.express as px

from AIW_risk_engine import get_engine_data, calculate_portfolio_risks, generate_risk_report, fallback_rf_rate

# 페이지 설정
st.set_page_config(page_title="세투연펀드 리스크 보고서", layout="wide")

# ==========================================
# 1. 데이터 로드 및 사이드바
# ==========================================
# 날짜 연동
target_date_str = st.session_state.get('target_date', datetime.datetime.today().date()).strftime('%Y-%m-%d')
target_dt = pd.to_datetime(target_date_str)

# 엔진에서 기본 데이터 로드
df_portfolio, returns_df, benchmark_returns, engine_rf_rate = get_engine_data(target_date_str)

# 무위험수익률(Rf) 수동 입력 및 상태 표시
with st.sidebar:
    st.header("⚙️ 시스템 로드 상태")
    manual_rf = st.number_input(
        "무위험수익률 (Rf) 설정",
        min_value=0.0, max_value=10.0, 
        value=float(engine_rf_rate * 100), 
        step=0.1, format="%.2f"
    )
    rf_rate = manual_rf / 100.0

    if rf_rate == fallback_rf_rate:
        st.warning(f"⚠️ 외부 금리 연동 실패\n수동/기본값({rf_rate*100:.2f}%) 적용 중")
    else:
        st.success(f"✅ 적용 금리: {rf_rate*100:.2f}%")

risk_df = generate_risk_report(df_portfolio, returns_df, benchmark_returns, rf_rate)
metrics = calculate_portfolio_risks(df_portfolio, returns_df, benchmark_returns, rf_rate)

# ==========================================
# 2. 유틸리티 및 상태 판별
# ==========================================
def fmt_p(val): return f"{val*100:.2f}%" if pd.notna(val) else "N/A"
def fmt_n(val): return f"{val:.2f}" if pd.notna(val) else "N/A"

stat_beta = metrics.get("베타_상태", "⚪️ N/A")
stat_var = metrics.get("10일VaR_상태", "⚪️ N/A")
stat_es = metrics.get("10일ES_상태", "⚪️ N/A")
stat_mdd = metrics.get("MDD_상태", "⚪️ N/A")
stat_wmdd = metrics.get("주간MDD_상태", "⚪️ N/A")
stat_concentration = metrics.get("쏠림_상태", "⚪️ N/A") 
stat_sector_concentration = metrics.get("섹터_쏠림_상태", "⚪️ N/A")
violation_cnt = metrics.get("컴플라이언스_위반건수", 0)

all_stats = [stat_beta, stat_var, stat_es, stat_mdd, stat_wmdd, stat_concentration, stat_sector_concentration]
if violation_cnt > 0: all_stats.append("🔴 위험")

if any("⚪" in s or "N/A" in s for s in all_stats): overall_status = "⚪️ 연산 오류 (N/A)"
elif any("🔴" in s for s in all_stats): overall_status = "🔴 위험"
elif any("🟡" in s for s in all_stats): overall_status = "🟡 경계"
else: overall_status = "🟢 정상"

# PDF 인쇄용 최적화 CSS
st.markdown("""
    <style>
    @media print {
        header, .stDeployButton, footer {display: none !important;}
        .appview-container .main .block-container { max-width: 100% !important; width: 100% !important; padding: 0 !important; }
        table th, table td { padding: 4px 6px !important; white-space: nowrap !important; }
        canvas, img, svg, div { max-width: 100% !important; page-break-inside: avoid !important; }
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 보고서 UI 렌더링
# ==========================================
st.markdown(f"<h1 style='text-align: center; font-size: 45px;'>세투연펀드 7기 리스크 보고서 ({target_dt.strftime('%Y-%m-%d')})</h1>", unsafe_allow_html=True)
st.divider()

# Section 1. 종합현황
st.subheader("1. 종합현황 및 요약")

col1, col2, col3, col4 = st.columns(4) 
col1.metric("현재 리스크 수준", overall_status)
col2.metric("컴플라이언스 위반", "🟢 0 건" if pd.isna(violation_cnt) or violation_cnt == 0 else f"🚨 {violation_cnt} 건")
port_w_ret = metrics.get("포트폴리오_주간수익률", np.nan)
bm_w_ret = metrics.get("벤치마크_주간수익률", np.nan)
alpha_w_ret = port_w_ret - bm_w_ret if pd.notna(port_w_ret) and pd.notna(bm_w_ret) else np.nan

col3.metric("포트폴리오 주간 수익률", fmt_p(port_w_ret), delta=f"BM 대비 {fmt_p(alpha_w_ret)}", help="최근 5영업일 기준 누적 수익률입니다.")
col4.metric("벤치마크 주간 수익률", fmt_p(bm_w_ret), help="KODEX 200의 최근 5영업일 누적 수익률입니다.")

st.text_area("💬 주간 요약 코멘트", value="여기에 이번 주 시장 상황, 주요 지표 변화 원인, 그리고 향후 펀드 운용 계획 등을 자유롭게 작성하세요.", height=100)
st.divider()

# Section 2. 포트폴리오 위험 지표
st.subheader("2. 포트폴리오 위험 지표")

# 지표명, 값, 툴팁 설명 형태로 리스트 구성
display_items = [
    ("포트폴리오 베타", fmt_n(metrics.get("포트폴리오_베타")), "시장(벤치마크)이 1% 움직일 때 우리 펀드가 반응하는 민감도입니다."), 
    ("10일 VaR (95%)", fmt_p(metrics.get("10일VaR")), "확률적으로 향후 10일간 발생할 수 있는 '최대 예상 손실률'의 마지노선입니다."),
    ("10일 ES (95%)", fmt_p(metrics.get("10일ES")), "VaR 마지노선이 뚫리는 최악의 5% 상황이 터졌을 때의 '평균 손실률'입니다."), 
    ("트래킹 에러", fmt_p(metrics.get("트래킹에러")), "우리 펀드가 벤치마크(시장)의 궤적을 얼마나 벗어나 독자적으로 움직이는지 보여주는 수치입니다."),
    ("표준편차(일간)", fmt_p(metrics.get("표준편차(일간)")), "하루 동안 펀드 수익률이 평균에서 위아래로 출렁이는 정도(변동성)입니다."), 
    ("표준편차(연환산)", fmt_p(metrics.get("표준편차(연환산)")), "1년 동안 펀드 수익률이 위아래로 출렁일 것으로 예상되는 변동성입니다."),
    ("MDD", fmt_p(metrics.get("MDD")), "과거 최고점 대비 최저점까지의 '최대 낙폭'으로 투자자가 겪을 수 있는 최악의 손실률입니다."), 
    ("주간 MDD", fmt_p(metrics.get("주간MDD")), "주간 단위로 측정한 포트폴리오의 최대 낙폭입니다."),
    ("샤프 지수", fmt_n(metrics.get("샤프지수")), "위험(변동성) 1단위를 감수할 때 얻는 '초과 수익률'로, 펀드의 가성비 지표입니다."), 
    ("소티노 지수", fmt_n(metrics.get("소티노지수")), "투자자가 싫어하는 '하락' 변동성만 떼어내서 계산한 더 엄격한 가성비 지표입니다."),
    ("주식 비중", fmt_p(metrics.get("주식비중")), "포트폴리오 내 주식 등 위험 자산이 차지하는 비중입니다."), 
    ("현금 비중", fmt_p(metrics.get("현금비중")), "위기 대응을 위해 포트폴리오 내에 확보해둔 현금의 비중입니다."),
    ("무위험수익률", fmt_p(rf_rate), "은행 예금이나 국채처럼 리스크 없이 얻을 수 있는 기본 수익률(Rf)입니다.")
]

for i in range(0, len(display_items), 4):
    cols = st.columns(4)
    for col, (k, v, help_text) in zip(cols, display_items[i:i+4]):
        col.metric(k, v, help=help_text)
st.divider()

# Section 3. 종목별 위험지표
st.subheader("3. 종목별 위험지표")
if risk_df is not None and not risk_df.empty:
    formatted_risk_df = risk_df.copy()
    pct_cols = ['비중', '수익률', '표준편차(일간)', '표준편차(연환산)', '10일VaR(95%)', '10일ES(95%)', 'MDD', '주간 MDD']
    num_cols = ['베타', '샤프지수', '소티노지수']
    for c in pct_cols: formatted_risk_df[c] = formatted_risk_df[c].apply(fmt_p)
    for c in num_cols: formatted_risk_df[c] = formatted_risk_df[c].apply(fmt_n)
    st.dataframe(formatted_risk_df, hide_index=True)
else:
    st.warning("종목별 위험지표 데이터가 없습니다.")
st.divider()

# Section 4. 핵심 위험/성과 지표 관리
st.subheader("4. 핵심 위험 지표 및 성과 지표 관리")
col1, col2 = st.columns(2)

with col1:
    st.markdown("##### 🛡️ 핵심 위험 지표")
    bm_var, bm_es, bm_mdd, bm_wmdd = metrics.get("벤치마크_10일VaR", 0), metrics.get("벤치마크_10일ES", 0), metrics.get("벤치마크_MDD", 0), metrics.get("벤치마크_주간MDD", 0)
    
    st.dataframe(pd.DataFrame({
        "지표": ["베타", "10일 VaR (95%)", "10일 ES (95%)", "MDD", "주간 MDD"],
        "우리 펀드": [fmt_n(metrics.get("포트폴리오_베타")), fmt_p(metrics.get("10일VaR")), fmt_p(metrics.get("10일ES")), fmt_p(metrics.get("MDD")), fmt_p(metrics.get("주간MDD"))],
        "벤치마크": ["1.00", fmt_p(bm_var), fmt_p(bm_es), fmt_p(bm_mdd), fmt_p(bm_wmdd)],
        "관리 기준(경/위)": ["0.6 ~ 1.2", f"BM*1.1 / 1.2", f"BM*1.1 / 1.2", f"BM*1.1 / 1.2", f"BM*1.15 / 1.3"],
        "상태": [stat_beta, stat_var, stat_es, stat_mdd, stat_wmdd]
    }), hide_index=True)

with col2:
    st.markdown("##### 🚀 핵심 성과 지표")
    is_sharpe_good = metrics.get("샤프지수", 0) > metrics.get("벤치마크_샤프", 0)
    is_sortino_good = metrics.get("소티노지수", 0) > metrics.get("벤치마크_소티노", 0)
    
    st.dataframe(pd.DataFrame({
        "지표": ["샤프 지수", "소티노 지수"],
        "우리 펀드": [fmt_n(metrics.get("샤프지수")), fmt_n(metrics.get("소티노지수"))],
        "벤치마크": [fmt_n(metrics.get("벤치마크_샤프")), fmt_n(metrics.get("벤치마크_소티노"))],
        "목표": ["> 벤치마크", "> 벤치마크"],
        "상태": ["✅ 충족" if is_sharpe_good else "❌ 미충족", "✅ 충족" if is_sortino_good else "❌ 미충족"]
    }), hide_index=True)
st.divider()

# PDF 페이지 넘김
st.markdown('<div style="page-break-before: always;"></div>', unsafe_allow_html=True)

# Section 5. 섹터별 포트폴리오 비중
st.subheader("5. 섹터별 포트폴리오 비중")
col1, col2 = st.columns([1, 2.0]) 
with col1:
    sector_display_df = df_portfolio[['섹터', '종목명', '비중']].sort_values(by=['섹터', '비중'], ascending=[True, False]).copy()
    sector_display_df['비중'] = sector_display_df['비중'].apply(fmt_p)
    st.dataframe(sector_display_df, hide_index=True, use_container_width=True)

with col2:
    tree_df = df_portfolio[df_portfolio['평가금액'] > 0].copy()
    tree_df['비중_텍스트'] = tree_df['비중'].apply(lambda x: f"{x*100:.1f}%")
    fig_tree = px.treemap(tree_df, path=['섹터', '종목명'], values='평가금액', color='섹터', custom_data=['비중_텍스트'])
    fig_tree.update_traces(texttemplate="<b>%{label}</b><br>%{customdata[0]}", textinfo="label+text", hovertemplate="<b>%{label}</b><br>평가금액: %{value:,.0f}원<br>비중: %{customdata[0]}", textfont=dict(color='white'), marker=dict(line=dict(color='#0E1117', width=3)))
    fig_tree.update_layout(margin=dict(t=20, l=20, r=20, b=20), height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_tree, use_container_width=True)

# Section 6. 종목별 VaR 분포
st.subheader("6. 종목별 VaR 분포")
port_var = metrics.get("10일VaR", 0)
limit_var = bm_var * 1.1

if port_var > limit_var and limit_var > 0:
    st.error(f"🚨 **위험!** 현재 포트폴리오 VaR가 위험 기준을 **{fmt_p(port_var - limit_var)}** 초과했습니다.")
else:
    st.success(f"🟢 **안정권:** 현재 포트폴리오 VaR가 위험 기준보다 **{fmt_p(limit_var - port_var if limit_var > 0 else 0)}** 낮습니다.")
st.markdown("<br>", unsafe_allow_html=True)

# 섹터별/개별종목 VaR 기여도 UI 및 경고
sector_var_df = metrics.get("섹터_VaR_기여도_DF")
if sector_var_df is not None and not sector_var_df.empty:
    sector_warnings = [
        f"{'🔴 **[위험]**' if abs(row['Contribution %']) > 0.60 else '🟡 **[경계]**'} {sec} 섹터 ({abs(row['Contribution %'])*100:.1f}%)" 
        for sec, row in sector_var_df.iterrows() if sec != '벤치마크' and abs(row["Contribution %"]) > 0.50
    ]
    if sector_warnings: st.warning("⚠️ **섹터 리스크 쏠림 감지 (한도 60%):** " + ", ".join(sector_warnings))

var_decomp = metrics.get("VaR_기여도_DF")
if var_decomp is not None and not var_decomp.empty:
    concentration_warnings = []
    for ticker, row in var_decomp.iterrows():
        if ticker == '069500': continue 
        cont_pct = abs(row["Contribution %"])
        if cont_pct > 0.40:
            stock_name = df_portfolio.loc[df_portfolio['티커'] == ticker, '종목명'].values
            stock_name = stock_name[0] if len(stock_name) > 0 else ticker
            concentration_warnings.append(f"{'🔴 **[위험]**' if cont_pct > 0.50 else '🟡 **[경계]**'} {stock_name} ({cont_pct*100:.1f}%)")
            
    if concentration_warnings: st.warning("⚠️ **개별종목 리스크 쏠림 감지 (한도 50%):** " + ", ".join(concentration_warnings))

    col1, col2 = st.columns([1.5, 1])
    with col1:
        display_var = var_decomp.rename(index={row['티커']: row['종목명'] for _, row in df_portfolio.iterrows()}).copy()
        display_var = display_var.rename(columns={"Weight": "비중", "Sector": "섹터", "VaR Contribution": "VaR 기여도", "Contribution %": "기여도 비율", "Marginal VaR": "1% 비중 변동시 VaR 증감"})[["비중", "섹터", "VaR 기여도", "기여도 비율", "1% 비중 변동시 VaR 증감"]]        
        for c in display_var.columns: 
            if c != "섹터": display_var[c] = display_var[c].apply(fmt_p)
        st.dataframe(display_var)

    with col2:
        pie_data = var_decomp.reset_index()
        pie_data["Abs_Contribution"] = pie_data["VaR Contribution"].abs()
        fig_pie = px.pie(pie_data, values="Abs_Contribution", names="index", title="종목별 VaR 기여도 비중")
        fig_pie.update_layout(height=320, margin=dict(t=40, b=20, l=20, r=20), legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
        st.plotly_chart(fig_pie, use_container_width=True)
else:
    st.warning("데이터가 부족하여 종목별 VaR 기여도를 계산할 수 없습니다.")
st.divider()

# Section 7. 종목 간 상관관계
st.subheader("7. 종목 간 상관관계 히트맵")
valid_tickers = [t for t in returns_df.columns if t != 'CASH']
if len(valid_tickers) > 1:
    corr_matrix = returns_df[valid_tickers].corr().rename(index={row['티커']: row['종목명'] for _, row in df_portfolio.iterrows()}, columns={row['티커']: row['종목명'] for _, row in df_portfolio.iterrows()})
    fig_corr = px.imshow(corr_matrix, text_auto=".2f", aspect="auto", color_continuous_scale="RdBu_r", zmin=-1, zmax=1, title="포트폴리오 구성 종목 일간 수익률 상관계수")
    st.plotly_chart(fig_corr)
else:
    st.info("💡 종목이 2개 이상이어야 상관관계를 분석할 수 있습니다.")
st.divider()

# PDF 페이지 넘김
st.markdown('<div style="page-break-before: always;"></div>', unsafe_allow_html=True)

# Section 8. 컴플라이언스 점검
st.subheader("8. 컴플라이언스 점검")
comp_data = metrics.get("컴플라이언스_상세", [])
if comp_data:
    st.dataframe(pd.DataFrame(comp_data), hide_index=True, use_container_width=True)
else:
    st.info("💡 컴플라이언스 점검 데이터가 없습니다.")
