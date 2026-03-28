import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from backtest import fetch_ohlcv, fetch_funding_rates, run_backtest, run_ensemble_backtest, optimize_strategy, optimize_ensemble, walk_forward_backtest
from exchange import get_exchange, fetch_account_status, fetch_pnl_snapshot
from performance import read_events, summarize, strategy_breakdown
from profiles import RISK_PROFILES
from risk_guard import can_trade, GuardConfig
from wallet_history import append_wallet_snapshot, read_wallet_history
from strategy_store import (
    save_strategy_params,
    get_strategy_params,
    list_strategy_versions,
    save_portfolio_weights,
    get_portfolio_weights,
    set_latest_from_version,
    save_named_preset,
    list_named_presets,
    get_named_preset,
)
from market_symbols import fetch_symbols
from news_panel import get_macro_crypto_news
from paper_live import load_state as load_paper_state, start_session as start_paper_session, pause_session as pause_paper_session, resume_session as resume_paper_session, reset_session as reset_paper_session, update_session as update_paper_session
from market_intel import get_market_brief
from predict_model import predict_event

load_dotenv()


def format_kst(iso_text: str) -> str:
    if not iso_text:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_text)
        return dt.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")
    except Exception:
        return str(iso_text)

st.set_page_config(page_title="Hoya Trading SW v2", page_icon="📈", layout="wide")
st.markdown(
    """
    <style>
    .stApp { background: linear-gradient(180deg, #F8FAFF 0%, #F4F7FF 100%); }
    .hp-card { background:white; border-radius:20px; padding:16px 18px; box-shadow:0 6px 20px rgba(47,123,255,.08); border:1px solid #E8EEFF; }
    .hp-pill { display:inline-block; padding:6px 10px; border-radius:999px; font-size:12px; font-weight:700; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("📈 Hoya Trading SW v2")
st.caption("기존 기능 유지 + 시장 인텔리전스 기반 투자 의사결정")


@st.cache_data(ttl=60 * 30)
def get_symbol_options(market_type: str, min_quote_volume_usdt: float = 0.0):
    last_err = None
    for _ in range(2):
        try:
            ex = get_exchange(read_only=True, market_type=("swap" if market_type == "futures" else "spot"))
            return fetch_symbols(ex, market_type, min_quote_volume_usdt=min_quote_volume_usdt)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"failed to load symbol list: {last_err}")


@st.cache_data(ttl=60 * 10)
def get_cached_ohlcv(market_type: str, symbol: str, timeframe: str, start_iso: str, end_iso: str):
    ex = get_exchange(read_only=True, market_type=("swap" if market_type == "futures" else "spot"))
    return fetch_ohlcv(ex, symbol, timeframe, start_iso, end_iso)


@st.cache_data(ttl=60 * 10)
def get_cached_funding(symbol: str, start_iso: str, end_iso: str):
    ex = get_exchange(read_only=True, market_type="swap")
    return fetch_funding_rates(ex, symbol, start_iso, end_iso)


@st.cache_data(ttl=60 * 5)
def get_cached_news(limit: int = 12):
    return get_macro_crypto_news(limit=limit)

guard_cfg_spot = GuardConfig(
    daily_loss_limit_usdt=float(os.getenv("DAILY_LOSS_LIMIT_USDT_SPOT", os.getenv("DAILY_LOSS_LIMIT_USDT", "30"))),
    max_consecutive_losses=int(os.getenv("MAX_CONSECUTIVE_LOSSES_SPOT", os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))),
)

guard_cfg_futures = GuardConfig(
    daily_loss_limit_usdt=float(os.getenv("DAILY_LOSS_LIMIT_USDT_FUTURES", os.getenv("DAILY_LOSS_LIMIT_USDT", "30"))),
    max_consecutive_losses=int(os.getenv("MAX_CONSECUTIVE_LOSSES_FUTURES", os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))),
)

events = read_events()
summary = summarize(events)

live_realized = summary["realized_pnl"]
live_unrealized = summary["unrealized_pnl"]
try:
    ex_live = get_exchange(read_only=False)
    pnl_live = fetch_pnl_snapshot(ex_live)
    live_realized = pnl_live.get("realized_pnl", live_realized)
    live_unrealized = pnl_live.get("unrealized_pnl", live_unrealized)
except Exception:
    pass

market_brief = get_market_brief(force_refresh=False)
latest_event = (market_brief.get("top") or [{}])[0] if market_brief.get("top") else {}
ml_pred = predict_event(latest_event) if latest_event else {}
if ml_pred:
    p1_ = ml_pred.get("label_up_1h", {})
    p4_ = ml_pred.get("label_up_4h", {})
    p24_ = ml_pred.get("label_up_24h", {})
    up1_ = (p1_.get("proba", [0, 0])[1] if p1_.get("ok") and len(p1_.get("proba", [])) > 1 else 0)
    up4_ = (p4_.get("proba", [0, 0])[1] if p4_.get("ok") and len(p4_.get("proba", [])) > 1 else 0)
    up24_ = (p24_.get("proba", [0, 0])[1] if p24_.get("ok") and len(p24_.get("proba", [])) > 1 else 0)
    ml_composite_dashboard = (up1_ * 0.2) + (up4_ * 0.5) + (up24_ * 0.3)
else:
    ml_composite_dashboard = 0.0

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("🔥 누적 수익률(시작~현재)", f"{summary['return_pct']:.2f}%")
k2.metric("실현손익 합계(USDT)", f"{live_realized:.2f}")
k3.metric("미실현손익 합계(USDT)", f"{live_unrealized:.2f}")
k4.metric("총 체결 건수", summary["total_trades"])
k5.metric("시장 바이어스", market_brief.get("bias", "neutral"))

st.markdown("---")

tab_overview, tab_backtest, tab_strategy, tab_live, tab_paper, tab_market, tab_risk = st.tabs([
    "개요",
    "(숨김예정) 백테스트",
    "(숨김예정) 전략 성과",
    "실시간 계정",
    "모의투자",
    "시장 인텔리전스",
    "리스크 가드",
])

with tab_overview:
    # 메인 페이지는 실제 지갑 연동 잔고 기준으로 표시
    overview_market_type = st.selectbox("메인 잔고 기준 마켓", ["spot", "futures"], index=0, key="overview_market")

    latest_wallet_status = None
    wallet_error = None
    try:
        ex_overview = get_exchange(read_only=False, market_type=("swap" if overview_market_type == "futures" else "spot"))
        latest_wallet_status = fetch_account_status(ex_overview)
        bal = (latest_wallet_status or {}).get("balance") or {}
        usdt_total = bal.get("usdt_total")
        if isinstance(usdt_total, (int, float)):
            append_wallet_snapshot(
                market_type=overview_market_type,
                usdt_total=float(usdt_total),
                usdt_free=bal.get("usdt_free"),
                usdt_used=bal.get("usdt_used"),
            )
    except Exception as e:
        wallet_error = str(e)

    # 그래프 영역을 페이지 가로의 약 1/3로 유지 + 운용상태를 그래프 아래로 배치
    c1, c2 = st.columns([1, 2])

    with c1:
        st.subheader("잔고 변화 (실지갑)")
        range_label = st.radio(
            "조회 구간",
            ["1시간", "1일", "1주", "1달"],
            horizontal=True,
            key="balance_range",
        )

        history = read_wallet_history()
        wallet_df = pd.DataFrame(history)

        if wallet_df.empty:
            st.info("실지갑 스냅샷 데이터가 아직 없습니다. API 연동 후 새로고침하면 기록됩니다.")
        else:
            if "market_type" in wallet_df.columns:
                wallet_df = wallet_df[wallet_df["market_type"] == overview_market_type].copy()
            else:
                wallet_df = pd.DataFrame()

            if wallet_df.empty:
                st.info(f"{overview_market_type} 지갑 스냅샷이 없습니다.")
            else:
                wallet_df["ts"] = pd.to_datetime(wallet_df["ts"], utc=True)
                now_ts = pd.Timestamp.now(tz="UTC")

                if range_label == "1시간":
                    cutoff = now_ts - pd.Timedelta(hours=1)
                elif range_label == "1일":
                    cutoff = now_ts - pd.Timedelta(days=1)
                elif range_label == "1주":
                    cutoff = now_ts - pd.Timedelta(days=7)
                else:
                    cutoff = now_ts - pd.Timedelta(days=30)

                filtered = wallet_df[wallet_df["ts"] >= cutoff].copy()
                if filtered.empty:
                    st.info(f"선택한 구간({range_label})에 데이터가 없습니다.")
                else:
                    fig = px.line(filtered, x="ts", y="usdt_total", title=f"Wallet Balance ({overview_market_type}, {range_label})")
                    fig.update_layout(height=280, margin=dict(l=10, r=10, t=40, b=10))
                    st.plotly_chart(fig, use_container_width=True)

        st.subheader("운용 상태")
        api_key = os.getenv("API_KEY", "")
        st.write("API Key 설정:", "✅" if api_key and "YOUR_" not in api_key else "❌")
        st.write("거래소:", os.getenv("EXCHANGE", "binance"))
        st.write("테스트넷:", os.getenv("BINANCE_TESTNET", "false"))
        st.write("DRY_RUN:", os.getenv("DRY_RUN", "true"))

        if latest_wallet_status and latest_wallet_status.get("balance"):
            b = latest_wallet_status.get("balance") or {}
            st.write("USDT Total:", b.get("usdt_total"))
            st.write("USDT Free:", b.get("usdt_free"))
            st.write("USDT Used:", b.get("usdt_used"))

        if wallet_error:
            st.warning(f"지갑 조회 오류: {wallet_error}")
        elif latest_wallet_status:
            for k in ["balance_error", "positions_error", "open_orders_error"]:
                if latest_wallet_status.get(k):
                    st.warning(f"{k}: {latest_wallet_status[k]}")

        st.code("python main.py\nstreamlit run dashboard.py")

    with c2:
        st.subheader("📰 매크로/정책 뉴스 요약")
        st.caption("트럼프/연준/금리 관련 이슈를 카드형으로 표시")

        if "expanded_news_idx" not in st.session_state:
            st.session_state.expanded_news_idx = None
        if "news_page" not in st.session_state:
            st.session_state.news_page = 0
        if "news_nonce" not in st.session_state:
            st.session_state.news_nonce = 0

        top_ctrl1, top_ctrl2, top_ctrl3 = st.columns([1, 1, 2])
        with top_ctrl1:
            if st.button("↻ 새로고침", key="refresh_news"):
                st.session_state.news_nonce += 1
                st.session_state.news_page = 0
                st.session_state.expanded_news_idx = None
                get_cached_news.clear()
                st.rerun()
        with top_ctrl2:
            st.caption("수동 새로고침 권장")

        news_items = get_cached_news(limit=12)

        if not news_items:
            st.info("뉴스를 불러오지 못했습니다. 잠시 후 다시 시도해줘.")
        else:
            page_size = 4
            total_pages = max(1, (len(news_items) + page_size - 1) // page_size)
            st.session_state.news_page = max(0, min(st.session_state.news_page, total_pages - 1))

            nav1, nav2, nav3 = st.columns([1, 1, 2])
            with nav1:
                if st.button("< 이전", key="news_prev"):
                    st.session_state.news_page = (st.session_state.news_page - 1) % total_pages
                    st.session_state.expanded_news_idx = None
                    st.rerun()
            with nav2:
                if st.button("다음 >", key="news_next"):
                    st.session_state.news_page = (st.session_state.news_page + 1) % total_pages
                    st.session_state.expanded_news_idx = None
                    st.rerun()
            with nav3:
                st.caption(f"페이지 {st.session_state.news_page + 1}/{total_pages}")

            start = st.session_state.news_page * page_size
            end = start + page_size
            page_items = news_items[start:end]

            expanded = st.session_state.expanded_news_idx
            if expanded is not None and 0 <= expanded < len(page_items):
                n = page_items[expanded]
                with st.container(border=True):
                    st.markdown(f"### {n.get('title_ko') or n['title']}")
                    st.markdown(f"**영향도:** {n.get('impact', '🟡 Neutral')}  |  **중요도:** {n.get('priority', 0)}")
                    st.write(n.get("summary_ko") or n.get("summary") or "요약 없음")
                    st.caption(n.get("published") or "")
                    st.link_button("원문 보기", n["link"])
                    if st.button("접기", key=f"collapse_news_{expanded}"):
                        st.session_state.expanded_news_idx = None
                        st.rerun()

            row1 = st.columns(2)
            row2 = st.columns(2)
            cells = [row1[0], row1[1], row2[0], row2[1]]

            for i, n in enumerate(page_items):
                with cells[i]:
                    with st.container(border=True):
                        st.markdown(f"**{n['title'][:88]}{'...' if len(n['title']) > 88 else ''}**")
                        st.caption(f"{n.get('impact', '🟡 Neutral')} · 중요도 {n.get('priority', 0)}")
                        short = (n.get("summary_ko") or n.get("summary") or "요약 없음")
                        st.caption(short[:120] + ("..." if len(short) > 120 else ""))

                        is_open = st.session_state.expanded_news_idx == i
                        btn_text = "자세히 보기" if not is_open else "닫기"
                        if st.button(btn_text, key=f"open_news_{st.session_state.news_page}_{i}"):
                            st.session_state.expanded_news_idx = None if is_open else i
                            st.rerun()

with tab_backtest:
    st.subheader("백테스트 기능 축소")
    st.info("v2 방향에 맞춰 백테스트/전략 검증 UI는 단계적으로 제거 중입니다. 현재는 모의투자와 시장 인텔리전스 중심으로 사용해주세요.")
    st.caption("내부 엔진은 모의투자 계산용으로만 유지됩니다.")
    st.subheader("기간형 백테스트")
    left, right = st.columns([1, 2])

    with left:
        market_type = st.selectbox("마켓", ["spot", "futures"], index=0)

        min_quote_volume_m = st.slider("최소 24h 거래대금(백만 USDT)", 0, 200, 0)

        # Binance 전체 상장 심볼 연동 + 드롭다운 검색(Selectbox 기본 검색 지원)
        try:
            symbol_options = get_symbol_options(market_type, min_quote_volume_usdt=float(min_quote_volume_m) * 1_000_000.0)
        except Exception:
            symbol_options = ["BTC/USDT", "ETH/USDT", "SOL/USDT"] if market_type == "spot" else ["BTC/USDT:USDT", "ETH/USDT:USDT"]

        if not symbol_options:
            st.warning("조건에 맞는 심볼이 없습니다. 최소 거래대금 조건을 낮춰보세요.")
            symbol_options = ["BTC/USDT"] if market_type == "spot" else ["BTC/USDT:USDT"]

        symbol = st.selectbox(
            "심볼 (검색 가능)",
            symbol_options,
            index=0,
            help="드롭다운 클릭 후 코인 티커를 입력하면 연관 심볼이 필터링됩니다. (USDT 마켓만)",
        )

        timeframe = st.selectbox("타임프레임", ["5m", "15m", "1h"], index=0)
        side_mode = st.selectbox("포지션 방향", ["long", "short", "both"], index=(2 if market_type == "futures" else 0), help="요청사항 반영: futures는 long/short/both 지원")
        if market_type == "spot" and side_mode != "long":
            st.info("Spot 백테스트는 long-only로 동작합니다.")
            side_mode = "long"
        strategy_options = {
            "trend_continuation_system": "[NEW] Trend Continuation System (추세 눌림목, 추세장)",
            "liquidation_reversal_setup": "[NEW] Liquidation Reversal Setup (과열 반전, 급등락 직후)",
            "ensemble_regime": "[PRO] Ensemble Regime Blend (시장상태 자동전환)",
            "dual_momentum_trend": "[ADD] Dual Momentum + Trend Filter (강한 모멘텀 추세)",
            "volatility_breakout_atr": "[ADD] Volatility Breakout (변동성 확장 구간)",
            "donchian_vol_filter": "[ADD] Donchian + Vol Filter (돌파장)",
            "mean_reversion_zscore": "[ADD] Mean Reversion Z-score (횡보 과매수/과매도)",
            "rsi_failure_structure": "[ADD] RSI Failure + Structure (약한 반전 확인)",
            "vwap_anchored_intraday": "[ADD] Anchored VWAP Intraday (단기 추세 확인)",
            "funding_oi_reversal_pro": "[ADD] Funding+OI Reversal Pro (펀딩 과열 역추세)",
            "adaptive_vol_target": "[ADD] Adaptive Vol-Target (변동성 적응형)",
            "tlab_strategy_ever_need": "[TOP] The Only Trading Strategy You'll Ever Need (범용 추세)",
            "tlab_fvg_secret": "[TOP] I Found A Secret To Fair Value Gaps (불균형 메움)",
            "tlab_candlestick_filter": "[TOP] Candlestick Patterns... (캔들 필터)",
            "tlab_daytrading_beginner": "[TOP] How To Day Trade... (입문형 추세)",
            "ema_cross": "EMA Cross (기본 추세추종)",
            "rsi_reversion": "RSI Reversion (기본 역추세)",
            "breakout_20": "Breakout 20 (기본 돌파)",
        }

        bull_keys = [
            "trend_continuation_system", "dual_momentum_trend", "volatility_breakout_atr",
            "donchian_vol_filter", "vwap_anchored_intraday", "ema_cross",
            "tlab_strategy_ever_need", "tlab_daytrading_beginner"
        ]
        sideway_keys = [
            "mean_reversion_zscore", "rsi_reversion", "rsi_failure_structure",
            "tlab_fvg_secret", "tlab_candlestick_filter", "adaptive_vol_target"
        ]
        bear_keys = [
            "liquidation_reversal_setup", "funding_oi_reversal_pro", "breakout_20",
            "ensemble_regime"
        ]

        st.markdown("#### 시장 국면별 전략 선택")
        c_bull, c_side, c_bear = st.columns(3)
        with c_bull:
            bull_strategy = st.selectbox(
                "상승장 전략",
                bull_keys,
                index=0,
                format_func=lambda k: strategy_options.get(k, k),
                key="bull_strategy_select",
            )
        with c_side:
            side_strategy = st.selectbox(
                "횡보장 전략",
                sideway_keys,
                index=0,
                format_func=lambda k: strategy_options.get(k, k),
                key="side_strategy_select",
            )
        with c_bear:
            bear_strategy = st.selectbox(
                "하락장 전략",
                bear_keys,
                index=0,
                format_func=lambda k: strategy_options.get(k, k),
                key="bear_strategy_select",
            )

        regime = st.selectbox("현재 적용할 시장 국면", ["상승장", "횡보장", "하락장"], index=0)
        strategy = bull_strategy if regime == "상승장" else (side_strategy if regime == "횡보장" else bear_strategy)
        st.caption(f"현재 적용 전략: {strategy_options.get(strategy, strategy)}")

        strategy_usage = {
            "trend_continuation_system": "추세장(상승/하락)에서 눌림 진입에 유리",
            "liquidation_reversal_setup": "급등/급락 과열 구간의 되돌림 공략",
            "ensemble_regime": "시장상태(추세/과열/중립) 자동 분기",
            "dual_momentum_trend": "강한 모멘텀 코인 추세 추종",
            "volatility_breakout_atr": "변동성 확장 초입 추종",
            "donchian_vol_filter": "박스권 돌파 후 추세 연장",
            "mean_reversion_zscore": "횡보장에서 평균회귀 공략",
            "rsi_failure_structure": "반전 신호 + 구조 전환 확인",
            "vwap_anchored_intraday": "단기 체결강도/VWAP 기준 추세",
            "funding_oi_reversal_pro": "펀딩 과열 시 역추세 단타",
            "adaptive_vol_target": "변동성에 따라 포지션 크기 자동 조절",
            "tlab_strategy_ever_need": "범용 추세형, 중기 구간",
            "tlab_fvg_secret": "FVG 불균형 구간 메움/반등",
            "tlab_candlestick_filter": "캔들 패턴 필터 기반 진입",
            "tlab_daytrading_beginner": "입문용 단순 추세/반전",
            "ema_cross": "기본 추세 추종",
            "rsi_reversion": "기본 과매수/과매도 반전",
            "breakout_20": "N봉 돌파 추세 추종",
        }
        strategy_tags = {
            "trend_continuation_system": ["📈 추세", "🎯 눌림"],
            "liquidation_reversal_setup": ["🔁 반전", "⚡ 고변동"],
            "ensemble_regime": ["🧠 자동분기", "🛡️ 분산"],
            "dual_momentum_trend": ["📈 추세", "🚀 모멘텀"],
            "volatility_breakout_atr": ["⚡ 고변동", "📈 돌파"],
            "donchian_vol_filter": ["📈 돌파", "🧱 박스권이탈"],
            "mean_reversion_zscore": ["↔️ 횡보", "🔁 평균회귀"],
            "rsi_failure_structure": ["🔁 반전", "🧩 구조확인"],
            "vwap_anchored_intraday": ["⏱️ 단기", "📈 추세"],
            "funding_oi_reversal_pro": ["💸 펀딩", "🔁 반전"],
            "adaptive_vol_target": ["🛡️ 리스크", "⚖️ 변동성적응"],
            "tlab_strategy_ever_need": ["📈 추세"],
            "tlab_fvg_secret": ["🕳️ FVG", "🔁 반전"],
            "tlab_candlestick_filter": ["🕯️ 캔들", "🔍 필터"],
            "tlab_daytrading_beginner": ["⏱️ 단기", "📈 추세"],
            "ema_cross": ["📈 추세"],
            "rsi_reversion": ["↔️ 횡보", "🔁 반전"],
            "breakout_20": ["📈 돌파"],
        }
        tags = " · ".join(strategy_tags.get(strategy, []))
        st.caption(f"전략 사용 상황: {strategy_usage.get(strategy, '-')}  |  {tags}")
        risk_profile = st.radio(
            "투자 성향",
            ["safe", "aggressive"],
            format_func=lambda k: f"{RISK_PROFILES[k]['label']} ({k})",
        )

        latest_saved = get_strategy_params(symbol, timeframe, strategy)
        versions = list_strategy_versions(symbol, timeframe, strategy)
        presets = list_named_presets(symbol, timeframe, strategy)

        preset_names = ["(latest)"] + sorted(list(presets.keys()))
        selected_preset_name = st.selectbox("저장된 파라미터 프리셋", preset_names, index=0)
        saved = latest_saved if selected_preset_name == "(latest)" else get_named_preset(symbol, timeframe, strategy, selected_preset_name)

        # ensemble_top_* 빠른 비교용 목록
        ensemble_top_presets = [n for n in presets.keys() if str(n).startswith("ensemble_top_")]

        st.markdown("#### 전략 파라미터")
        ema_fast_period = st.slider("EMA Fast (↑ 빠를수록 신호 많아짐 / ↓ 느릴수록 신호 적어짐)", 5, 50, int(saved.get("ema_fast_period", 20)))
        ema_slow_period = st.slider("EMA Slow (↑ 장기추세 위주 / ↓ 단기변화 민감)", 20, 200, int(saved.get("ema_slow_period", 50)))
        rsi_period = st.slider("RSI Period (↑ 완만하고 늦음 / ↓ 민감하고 빠름)", 7, 30, int(saved.get("rsi_period", 14)))
        rsi_lower = st.slider("RSI Lower (↑ 진입 쉬움 / ↓ 더 과매도에서만 진입)", 10, 40, int(saved.get("rsi_lower", 30)))
        rsi_upper = st.slider("RSI Upper (↑ 청산 늦게 / ↓ 청산 빠르게)", 55, 90, int(saved.get("rsi_upper", 65)))
        breakout_lookback = st.slider("Breakout Lookback (↑ 큰 돌파만 / ↓ 잦은 돌파)", 10, 60, int(saved.get("breakout_lookback", 20)))
        sl_pct = st.slider("Stop Loss % (↑ 손절 넓어짐 / ↓ 손절 타이트)", 0.2, 5.0, float(saved.get("sl_pct", 1.0)), 0.1)
        tp_rr = st.slider("Take Profit RR (↑ 목표수익 큼 / ↓ 목표수익 빠름)", 0.5, 5.0, float(saved.get("tp_rr", 1.5)), 0.1)
        funding_rate_per_8h = st.slider("Funding Rate %/8h (↑ 롱 비용 증가 / ↓ 비용 감소)", -0.20, 0.20, float(saved.get("funding_rate_per_8h", 0.0)), 0.01)
        leverage = st.slider("Leverage (선물 전용, 백테스트)", 1, 20, int(saved.get("leverage", 1)))
        use_binance_funding = st.checkbox("Binance 실제 펀딩비 이력 사용", value=True)
        if market_type == "spot":
            leverage = 1

        if strategy == "ensemble_regime":
            st.markdown("#### Ensemble 가중치/레짐 설정")
            ens_trend_w = st.slider("Trend 비중", 0.0, 1.0, float(saved.get("ens_trend_w", 0.4)), 0.05)
            ens_rev_w = st.slider("Reversal 비중", 0.0, 1.0, float(saved.get("ens_rev_w", 0.3)), 0.05)
            ens_base_w = st.slider("Base(EMA) 비중", 0.0, 1.0, float(saved.get("ens_base_w", 0.3)), 0.05)
            ens_spread_th = st.slider("Trend Spread 임계값", 0.002, 0.05, float(saved.get("ens_spread_th", 0.01)), 0.001)
            ens_rsi_low = st.slider("Reversal RSI Low", 10, 45, int(saved.get("ens_rsi_low", 30)))
            ens_rsi_high = st.slider("Reversal RSI High", 55, 90, int(saved.get("ens_rsi_high", 70)))
        else:
            ens_trend_w, ens_rev_w, ens_base_w = 0.4, 0.3, 0.3
            ens_spread_th, ens_rsi_low, ens_rsi_high = 0.01, 30, 70

        default_start = datetime.utcnow() - timedelta(days=90)
        start_date = st.date_input("백테스트 시작일", value=default_start.date(), key="bt_start")
        end_date = st.date_input("백테스트 종료일", value=datetime.utcnow().date(), key="bt_end")
        initial_usdt = st.number_input("백테스트 시작 자본 (USDT)", min_value=10.0, value=float(saved.get("initial_usdt", 1000.0)), step=10.0)

        auto_backtest = st.checkbox("파라미터 변경 시 자동 백테스트", value=False)
        run_bt = st.button("백테스트 실행", type="primary")
        run_compare = st.button("전략 3종 비교", type="secondary")
        run_portfolio = st.button("전략 포트폴리오 비교", type="secondary")
        objective_options = {
            "return": "return (수익률 최우선)",
            "balanced": "balanced (수익/리스크 균형)",
            "safe": "safe (낙폭 억제, 안정형)",
            "aggressive": "aggressive (고수익 지향, 변동성 큼)",
        }
        optimize_objective = st.selectbox("최적화 성향", list(objective_options.keys()), index=1, format_func=lambda k: objective_options[k])
        run_optimize = st.button("파라미터 최적화", type="secondary")
        run_ensemble_optimize = st.button("Ensemble 최적화", type="secondary")
        ens_max_mdd = st.slider("Ensemble 최대 허용 MDD(%)", 5, 80, 40)
        ens_max_liq = st.slider("Ensemble 최대 강제청산 허용 횟수", 0, 20, 3)
        ens_min_trades = st.slider("Ensemble 최소 거래 수", 1, 50, 5)
        run_walkforward = st.button("워크포워드 테스트", type="secondary")
        run_compare_ensemble_presets = st.button("저장된 ensemble_top 프리셋 비교", type="secondary")

        save_params_btn = st.button("현재 파라미터 저장", type="secondary")
        preset_name = st.text_input("프리셋 이름", value="")
        save_preset_btn = st.button("현재 파라미터를 프리셋으로 저장", type="secondary")

        if versions:
            st.caption(f"저장 버전 수: {len(versions)} (최근 저장: {versions[-1].get('saved_at', '-')})")
            version_options = list(range(len(versions)))
            selected_version = st.selectbox("활성화할 버전 인덱스", version_options, index=len(version_options)-1)
            if st.button("선택 버전 활성화", key="activate_version"):
                ok = set_latest_from_version(symbol, timeframe, strategy, int(selected_version))
                if ok:
                    st.success(f"버전 {selected_version} 활성화 완료")
                else:
                    st.warning("버전 활성화 실패")

        current_params = {
            "ema_fast_period": ema_fast_period,
            "ema_slow_period": ema_slow_period,
            "rsi_period": rsi_period,
            "rsi_lower": rsi_lower,
            "rsi_upper": rsi_upper,
            "breakout_lookback": breakout_lookback,
            "sl_pct": sl_pct,
            "tp_rr": tp_rr,
            "funding_rate_per_8h": funding_rate_per_8h,
            "leverage": leverage,
            "initial_usdt": initial_usdt,
            "ens_trend_w": ens_trend_w,
            "ens_rev_w": ens_rev_w,
            "ens_base_w": ens_base_w,
            "ens_spread_th": ens_spread_th,
            "ens_rsi_low": ens_rsi_low,
            "ens_rsi_high": ens_rsi_high,
        }

        if save_params_btn:
            save_strategy_params(symbol, timeframe, strategy, current_params)
            st.success("파라미터 저장 완료")

        if save_preset_btn:
            if not preset_name.strip():
                st.warning("프리셋 이름을 입력해줘")
            else:
                save_named_preset(symbol, timeframe, strategy, preset_name.strip(), current_params)
                st.success(f"프리셋 저장 완료: {preset_name.strip()}")

    with right:
        should_run_main_backtest = auto_backtest or run_bt
        if should_run_main_backtest or run_compare or run_portfolio or run_optimize or run_ensemble_optimize or run_walkforward or run_compare_ensemble_presets:
            with st.spinner("백테스트 실행 중..."):
                try:
                    start_iso = f"{start_date.isoformat()}T00:00:00+00:00"
                    end_iso = f"{end_date.isoformat()}T23:59:59+00:00"
                    candles = get_cached_ohlcv(market_type, symbol, timeframe, start_iso, end_iso)
                    if not candles:
                        st.error("해당 심볼/기간에서 캔들 데이터를 가져오지 못했습니다. 다른 심볼을 선택해보세요.")
                        st.stop()

                    funding_events = None
                    if market_type == "futures" and use_binance_funding:
                        funding_events = get_cached_funding(symbol, start_iso, end_iso)

                    if run_compare or run_portfolio:
                        rows = []
                        for sname in ["ensemble_regime", "trend_continuation_system", "liquidation_reversal_setup", "dual_momentum_trend", "volatility_breakout_atr", "donchian_vol_filter", "mean_reversion_zscore", "rsi_failure_structure", "vwap_anchored_intraday", "funding_oi_reversal_pro", "adaptive_vol_target", "tlab_strategy_ever_need", "tlab_fvg_secret", "tlab_candlestick_filter", "tlab_daytrading_beginner", "ema_cross", "rsi_reversion", "breakout_20"]:
                            r = run_backtest(
                                candles,
                                strategy=sname,
                                initial_usdt=initial_usdt,
                                ema_fast_period=ema_fast_period,
                                ema_slow_period=ema_slow_period,
                                rsi_period=rsi_period,
                                rsi_lower=rsi_lower,
                                rsi_upper=rsi_upper,
                                breakout_lookback=breakout_lookback,
                                sl_pct=sl_pct/100.0,
                                tp_rr=tp_rr,
                                funding_rate_per_8h=(funding_rate_per_8h/100.0 if market_type == "futures" else 0.0),
                                funding_events=funding_events,
                                position_mode=side_mode,
                                leverage=leverage,
                            )
                            rows.append({
                                "strategy": sname,
                                "return_pct": r.get("return_pct", 0.0),
                                "total_trades": r.get("total_trades", 0),
                                "win_rate": r.get("win_rate", 0.0),
                                "profit_factor": r.get("profit_factor", 0.0),
                                "max_drawdown_pct": r.get("max_drawdown_pct", 0.0),
                            })

                        cmp_df = pd.DataFrame(rows).sort_values("return_pct", ascending=False)

                        if run_compare:
                            st.subheader("전략 비교 결과")
                            st.dataframe(cmp_df, use_container_width=True)
                            st.plotly_chart(px.bar(cmp_df, x="strategy", y="return_pct", title="전략별 수익률(%)"), use_container_width=True)

                        if run_portfolio:
                            st.subheader("전략 포트폴리오(가중치) 결과")
                            pw = get_portfolio_weights(symbol, timeframe)
                            d_ema = int(pw.get("ema", 40))
                            d_rsi = int(pw.get("rsi", 30))
                            d_bo = int(pw.get("breakout", 30))

                            w_ema = st.slider("가중치 EMA", 0, 100, d_ema, key="w_ema")
                            w_rsi = st.slider("가중치 RSI", 0, 100, d_rsi, key="w_rsi")
                            w_bo = st.slider("가중치 Breakout", 0, 100, d_bo, key="w_bo")
                            total_w = w_ema + w_rsi + w_bo

                            if st.button("가중치 저장", key="save_portfolio_weights"):
                                save_portfolio_weights(symbol, timeframe, {"ema": w_ema, "rsi": w_rsi, "breakout": w_bo})
                                st.success("포트폴리오 가중치 저장 완료")

                            if total_w == 0:
                                st.warning("가중치 합이 0이면 계산할 수 없습니다.")
                            else:
                                weights = {
                                    "ema_cross": w_ema / total_w,
                                    "rsi_reversion": w_rsi / total_w,
                                    "breakout_20": w_bo / total_w,
                                }
                                cmp_df["weight"] = cmp_df["strategy"].map(weights).fillna(0.0)
                                portfolio_return = float((cmp_df["return_pct"] * cmp_df["weight"]).sum())
                                portfolio_pf = float((cmp_df["profit_factor"] * cmp_df["weight"]).sum())
                                portfolio_mdd = float((cmp_df["max_drawdown_pct"] * cmp_df["weight"]).sum())

                                p1, p2, p3 = st.columns(3)
                                p1.metric("포트폴리오 가중 수익률", f"{portfolio_return:.2f}%")
                                p2.metric("포트폴리오 가중 PF", f"{portfolio_pf:.2f}")
                                p3.metric("포트폴리오 가중 MDD", f"{portfolio_mdd:.2f}%")
                                st.dataframe(cmp_df, use_container_width=True)

                    if run_optimize:
                        if strategy == "ensemble_regime":
                            st.info("Ensemble 전략은 아래 'Ensemble 최적화'를 사용해줘.")
                            opt = {"best": None, "rows": []}
                        else:
                            opt = optimize_strategy(candles, strategy=strategy, objective=optimize_objective)
                        best = opt.get("best")
                        rows = opt.get("rows", [])
                        st.subheader(f"파라미터 최적화 ({strategy})")
                        if best:
                            st.json(best)
                            if st.button("최적 파라미터 저장", key=f"save_best_{strategy}"):
                                save_strategy_params(symbol, timeframe, strategy, best)
                                st.success("최적 파라미터 저장 완료")
                        if rows:
                            opt_df = pd.DataFrame(rows).sort_values("return_pct", ascending=False)
                            st.dataframe(opt_df.head(20), use_container_width=True)

                    if run_ensemble_optimize:
                        eopt = optimize_ensemble(
                            candles,
                            objective=optimize_objective,
                            initial_usdt=initial_usdt,
                            position_mode=side_mode,
                            leverage=leverage,
                            funding_rate_per_8h=(funding_rate_per_8h/100.0 if market_type == "futures" else 0.0),
                            funding_events=funding_events,
                            max_mdd_pct=float(ens_max_mdd),
                            max_liquidations=int(ens_max_liq),
                            min_trades=int(ens_min_trades),
                        )
                        st.subheader("Ensemble 최적화 결과")
                        ebest = eopt.get("best")
                        erows = eopt.get("rows", [])
                        if ebest:
                            st.json(ebest)

                            # 자동 적용: 현재 턴에서 바로 best 파라미터로 백테스트 재실행
                            if st.button("Ensemble 최적 조합 자동 적용 + 재백테스트", key="apply_best_ensemble"):
                                applied = run_ensemble_backtest(
                                    candles,
                                    initial_usdt=initial_usdt,
                                    position_mode=side_mode,
                                    leverage=leverage,
                                    funding_rate_per_8h=(funding_rate_per_8h/100.0 if market_type == "futures" else 0.0),
                                    funding_events=funding_events,
                                    trend_weight=float(ebest.get("trend_weight", ens_trend_w)),
                                    reversal_weight=float(ebest.get("reversal_weight", ens_rev_w)),
                                    base_weight=float(ebest.get("base_weight", ens_base_w)),
                                    trend_spread_threshold=float(ebest.get("trend_spread_threshold", ens_spread_th)),
                                    reversal_rsi_low=float(ebest.get("reversal_rsi_low", ens_rsi_low)),
                                    reversal_rsi_high=float(ebest.get("reversal_rsi_high", ens_rsi_high)),
                                )
                                st.success("최적 조합 자동 적용 결과")
                                st.json(applied)

                            # Top N 원클릭 프리셋 저장
                            top_n = st.slider("Top N 프리셋 저장", 1, 10, 3, key="ens_topn_save")
                            if st.button("상위 N개를 프리셋으로 저장", key="save_topn_ensemble"):
                                saved_count = 0
                                for idx, row in enumerate(erows[:top_n]):
                                    pname = f"ensemble_top_{idx+1}_{optimize_objective}"
                                    save_named_preset(
                                        symbol,
                                        timeframe,
                                        "ensemble_regime",
                                        pname,
                                        {
                                            "ens_trend_w": row.get("trend_weight", ens_trend_w),
                                            "ens_rev_w": row.get("reversal_weight", ens_rev_w),
                                            "ens_base_w": row.get("base_weight", ens_base_w),
                                            "ens_spread_th": row.get("trend_spread_threshold", ens_spread_th),
                                            "ens_rsi_low": row.get("reversal_rsi_low", ens_rsi_low),
                                            "ens_rsi_high": row.get("reversal_rsi_high", ens_rsi_high),
                                            "initial_usdt": initial_usdt,
                                            "leverage": leverage,
                                            "sl_pct": sl_pct,
                                            "tp_rr": tp_rr,
                                            "funding_rate_per_8h": funding_rate_per_8h,
                                            "return_pct": row.get("return_pct", 0.0),
                                            "profit_factor": row.get("profit_factor", 0.0),
                                            "max_drawdown_pct": row.get("max_drawdown_pct", 0.0),
                                            "liquidation_count": row.get("liquidation_count", 0),
                                            "opt_objective": optimize_objective,
                                        },
                                    )
                                    saved_count += 1
                                st.success(f"Ensemble 프리셋 저장 완료: {saved_count}개")

                        if erows:
                            edf = pd.DataFrame(erows)
                            st.dataframe(edf.head(30), use_container_width=True)

                    if run_walkforward:
                        wf = walk_forward_backtest(candles, strategy=strategy)
                        st.subheader(f"워크포워드 테스트 ({strategy})")
                        st.json(wf)

                    if run_compare_ensemble_presets:
                        st.subheader("저장된 ensemble_top 프리셋 비교")
                        if not ensemble_top_presets:
                            st.info("ensemble_top_* 프리셋이 아직 없습니다. 먼저 Ensemble 최적화를 실행해 저장해줘.")
                        else:
                            rows = []
                            for pname in sorted(ensemble_top_presets):
                                p = get_named_preset(symbol, timeframe, "ensemble_regime", pname)
                                if not p:
                                    continue
                                r = run_ensemble_backtest(
                                    candles,
                                    initial_usdt=float(p.get("initial_usdt", initial_usdt)),
                                    position_mode=side_mode,
                                    leverage=float(p.get("leverage", leverage)),
                                    funding_rate_per_8h=(float(p.get("funding_rate_per_8h", funding_rate_per_8h))/100.0 if market_type == "futures" else 0.0),
                                    funding_events=funding_events,
                                    trend_weight=float(p.get("ens_trend_w", ens_trend_w)),
                                    reversal_weight=float(p.get("ens_rev_w", ens_rev_w)),
                                    base_weight=float(p.get("ens_base_w", ens_base_w)),
                                    trend_spread_threshold=float(p.get("ens_spread_th", ens_spread_th)),
                                    reversal_rsi_low=float(p.get("ens_rsi_low", ens_rsi_low)),
                                    reversal_rsi_high=float(p.get("ens_rsi_high", ens_rsi_high)),
                                )
                                rows.append({
                                    "preset": pname,
                                    "return_pct": r.get("return_pct", 0.0),
                                    "final_usdt": r.get("final_usdt", 0.0),
                                    "trades": r.get("total_trades", 0),
                                    "liquidations": r.get("liquidation_count", 0),
                                })

                            if rows:
                                rdf = pd.DataFrame(rows).sort_values("return_pct", ascending=False)
                                st.dataframe(rdf, use_container_width=True)
                                st.plotly_chart(px.bar(rdf, x="preset", y="return_pct", title="ensemble_top 프리셋 수익률 비교"), use_container_width=True)
                            else:
                                st.info("비교 가능한 프리셋이 없습니다.")

                    if strategy == "ensemble_regime":
                        result = run_ensemble_backtest(
                            candles,
                            initial_usdt=initial_usdt,
                            position_mode=side_mode,
                            leverage=leverage,
                            funding_rate_per_8h=(funding_rate_per_8h/100.0 if market_type == "futures" else 0.0),
                            funding_events=funding_events,
                            trend_weight=ens_trend_w,
                            reversal_weight=ens_rev_w,
                            base_weight=ens_base_w,
                            trend_spread_threshold=ens_spread_th,
                            reversal_rsi_low=float(ens_rsi_low),
                            reversal_rsi_high=float(ens_rsi_high),
                        )
                    else:
                        result = run_backtest(
                            candles,
                            strategy=strategy,
                            initial_usdt=initial_usdt,
                            ema_fast_period=ema_fast_period,
                            ema_slow_period=ema_slow_period,
                            rsi_period=rsi_period,
                            rsi_lower=rsi_lower,
                            rsi_upper=rsi_upper,
                            breakout_lookback=breakout_lookback,
                            sl_pct=sl_pct/100.0,
                            tp_rr=tp_rr,
                            funding_rate_per_8h=(funding_rate_per_8h/100.0 if market_type == "futures" else 0.0),
                            funding_events=funding_events,
                            position_mode=side_mode,
                            leverage=leverage,
                        )

                    if result.get("error"):
                        st.error(result["error"])
                    else:
                        st.success(f"백테스트 완료 ({risk_profile} / {strategy})")
                        b1, b2, b3, b4, b5, b6, b7, b8 = st.columns(8)
                        b1.metric("수익률(총)", f"{result['return_pct']:.2f}%")
                        b2.metric("종료 자본(USDT)", f"{result.get('final_usdt', 0.0):.2f}")
                        b3.metric("총 트레이드", result["total_trades"])
                        b4.metric("승률", f"{result['win_rate']:.2f}%")
                        b5.metric("Profit Factor", f"{result.get('profit_factor', 0.0):.2f}")
                        b6.metric("Max DD", f"{result.get('max_drawdown_pct', 0.0):.2f}%")
                        total_funding = sum(t.get("funding_fee", 0.0) for t in result.get("trades", []))
                        b7.metric("Funding Fee", f"{total_funding:.4f}")
                        b8.metric("강제청산 횟수", int(result.get("liquidation_count", 0)))

                        candle_df = pd.DataFrame(candles, columns=["ts", "open", "high", "low", "close", "volume"])
                        candle_df["ts"] = pd.to_datetime(candle_df["ts"], unit="ms")
                        fig_price = go.Figure(
                            data=[
                                go.Candlestick(
                                    x=candle_df["ts"],
                                    open=candle_df["open"],
                                    high=candle_df["high"],
                                    low=candle_df["low"],
                                    close=candle_df["close"],
                                    name="Price",
                                )
                            ]
                        )

                        trades = pd.DataFrame(result["trades"])
                        if not trades.empty:
                            trades["entry_dt"] = pd.to_datetime(trades["entry_ts"], unit="ms")
                            trades["exit_dt"] = pd.to_datetime(trades["exit_ts"], unit="ms")

                            fig_price.add_trace(
                                go.Scatter(x=trades["entry_dt"], y=trades["entry"], mode="markers", marker=dict(symbol="triangle-up", size=10), name="Buy")
                            )
                            fig_price.add_trace(
                                go.Scatter(x=trades["exit_dt"], y=trades["exit"], mode="markers", marker=dict(symbol="triangle-down", size=10), name="Sell")
                            )

                        fig_price.update_layout(title="백테스트 차트 (매수/매도 시점)", xaxis_rangeslider_visible=False, height=520)
                        st.plotly_chart(fig_price, use_container_width=True)

                        eq = pd.DataFrame(result["equity_curve"])
                        if not eq.empty:
                            eq["ts"] = pd.to_datetime(eq["ts"], unit="ms")
                            fig = px.line(eq, x="ts", y="equity", title="Backtest Equity Curve")
                            st.plotly_chart(fig, use_container_width=True)

                        if not trades.empty:
                            st.dataframe(trades.tail(30), use_container_width=True)

                            monthly = trades.copy()
                            monthly["month"] = monthly["exit_dt"].dt.to_period("M").astype(str)
                            monthly_report = monthly.groupby("month", as_index=False).agg(
                                pnl=("pnl", "sum"),
                                trades=("pnl", "count"),
                                wins=("pnl", lambda s: int((s > 0).sum())),
                                gross_profit=("pnl", lambda s: float(s[s > 0].sum())),
                                gross_loss=("pnl", lambda s: float(abs(s[s < 0].sum()))),
                            )
                            monthly_report["win_rate"] = (monthly_report["wins"] / monthly_report["trades"] * 100.0).round(2)
                            monthly_report["profit_factor"] = monthly_report.apply(
                                lambda r: (r["gross_profit"] / r["gross_loss"]) if r["gross_loss"] > 0 else 0.0,
                                axis=1,
                            )

                            mdd_rows = []
                            for m in monthly["month"].unique():
                                md = monthly[monthly["month"] == m].copy().sort_values("exit_dt")
                                curve = md["pnl"].cumsum()
                                peak = curve.cummax()
                                dd = ((peak - curve) / peak.replace(0, pd.NA)).fillna(0) * 100.0
                                mdd_rows.append({"month": m, "max_drawdown_pct": float(dd.max() if not dd.empty else 0.0)})

                            mdd_df = pd.DataFrame(mdd_rows)
                            monthly_report = monthly_report.merge(mdd_df, on="month", how="left")

                            st.subheader("월별 백테스트 리포트")
                            st.dataframe(monthly_report, use_container_width=True)
                            csv_bytes = monthly_report.to_csv(index=False).encode("utf-8")
                            st.download_button(
                                "월별 리포트 CSV 다운로드",
                                data=csv_bytes,
                                file_name=f"monthly_report_{symbol.replace('/', '_').replace(':', '_')}_{timeframe}.csv",
                                mime="text/csv",
                            )
                            st.plotly_chart(px.bar(monthly_report, x="month", y="pnl", title="월별 PnL"), use_container_width=True)
                except Exception as e:
                    st.exception(e)
        else:
            st.info("좌측에서 기간/심볼을 선택하세요. 자동 백테스트가 켜져 있으면 바로 갱신됩니다.")

with tab_strategy:
    st.subheader("전략 검증 기능 축소")
    st.info("전략 선택/검증 기능은 단계적으로 제거 중입니다. v2는 인텔리전스 기반 모의투자/실투자 흐름에 집중합니다.")
    st.caption("이 영역은 향후 모의투자 성과/운용 이력 중심으로 대체될 예정입니다.")
    st.subheader("전략별 성과 비교")
    rows = strategy_breakdown(events)
    if not rows:
        st.info("전략별 분석을 위한 주문 데이터가 아직 없습니다.")
    else:
        sdf = pd.DataFrame(rows)
        st.dataframe(sdf, use_container_width=True)
        st.plotly_chart(px.bar(sdf, x="strategy", y="orders", title="전략별 주문 수"), use_container_width=True)
        st.plotly_chart(px.bar(sdf, x="strategy", y=["realized_pnl", "unrealized_pnl"], barmode="group", title="전략별 PnL"), use_container_width=True)

with tab_live:
    st.subheader("Binance 실시간 계정 상태")
    live_market_type = st.selectbox("조회 마켓", ["spot", "futures"], index=0)
    if st.button("실시간 상태 새로고침", type="primary"):
        try:
            ex = get_exchange(read_only=False, market_type=("swap" if live_market_type == "futures" else "spot"))
            status = fetch_account_status(ex)
            pnl = fetch_pnl_snapshot(ex)

            bal = status.get("balance") or {}
            l1, l2, l3 = st.columns(3)
            l1.metric("USDT Total", f"{(bal.get('usdt_total') or 0):.4f}")
            l2.metric("USDT Free", f"{(bal.get('usdt_free') or 0):.4f}")
            l3.metric("USDT Used", f"{(bal.get('usdt_used') or 0):.4f}")

            p1, p2 = st.columns(2)
            p1.metric("실현손익(거래소 조회)", f"{pnl.get('realized_pnl', 0.0):.4f}")
            p2.metric("미실현손익(포지션 합)", f"{pnl.get('unrealized_pnl', 0.0):.4f}")

            positions = status.get("positions") or []
            st.write("활성 포지션")
            st.dataframe(pd.DataFrame(positions) if positions else pd.DataFrame(columns=["symbol", "side", "contracts"]), use_container_width=True)

            opens = status.get("open_orders") or []
            st.write("오픈 주문")
            st.dataframe(pd.DataFrame(opens) if opens else pd.DataFrame(columns=["symbol", "side", "type", "amount", "price", "status"]), use_container_width=True)

            for k in ["balance_error", "positions_error", "open_orders_error"]:
                if status.get(k):
                    st.warning(f"{k}: {status[k]}")
        except Exception as e:
            st.exception(e)

with tab_paper:
    st.subheader("🧪 실시간 모의투자")
    st.caption("전략+파라미터를 설정해 시작 시점부터 현재 시세로 가상자금 시뮬레이션")

    p_left, p_right = st.columns([1, 2])

    with p_left:
        pm_market = st.selectbox("마켓", ["spot", "futures"], index=1, key="paper_market")
        pm_symbol_options = get_symbol_options(pm_market, min_quote_volume_usdt=0.0)
        if not pm_symbol_options:
            pm_symbol_options = ["BTC/USDT:USDT"] if pm_market == "futures" else ["BTC/USDT"]
        pm_symbol = st.selectbox("심볼", pm_symbol_options, key="paper_symbol")
        pm_timeframe = st.selectbox("타임프레임", ["5m", "15m", "1h", "4h"], index=1, key="paper_tf")
        pm_side = st.selectbox("포지션 방향", ["long", "short", "both"], index=(2 if pm_market == "futures" else 0), key="paper_side")
        if pm_market == "spot" and pm_side != "long":
            pm_side = "long"

        pm_strategy_options = {
            "ensemble_regime": "[PRO] Ensemble Regime Blend",
            "trend_continuation_system": "[NEW] Trend Continuation",
            "liquidation_reversal_setup": "[NEW] Liquidation Reversal",
            "dual_momentum_trend": "[ADD] Dual Momentum",
            "volatility_breakout_atr": "[ADD] Volatility Breakout",
            "donchian_vol_filter": "[ADD] Donchian Vol Filter",
            "mean_reversion_zscore": "[ADD] Mean Reversion Z-score",
            "rsi_failure_structure": "[ADD] RSI Failure Structure",
            "vwap_anchored_intraday": "[ADD] Anchored VWAP",
            "funding_oi_reversal_pro": "[ADD] Funding OI Reversal",
            "adaptive_vol_target": "[ADD] Adaptive Vol Target",
            "tlab_strategy_ever_need": "[TOP] Strategy Ever Need",
            "tlab_fvg_secret": "[TOP] FVG Secret",
            "tlab_candlestick_filter": "[TOP] Candlestick Filter",
            "tlab_daytrading_beginner": "[TOP] Daytrading Beginner",
            "ema_cross": "EMA Cross",
            "rsi_reversion": "RSI Reversion",
            "breakout_20": "Breakout 20",
        }
        pm_strategy = st.selectbox("전략", list(pm_strategy_options.keys()), format_func=lambda k: pm_strategy_options[k], key="paper_strategy")

        pm_presets = list_named_presets(pm_symbol, pm_timeframe, pm_strategy)
        pm_preset_names = ["(latest)"] + sorted(list(pm_presets.keys()))
        pm_preset_sel = st.selectbox("프리셋", pm_preset_names, key="paper_preset")
        pm_saved = get_strategy_params(pm_symbol, pm_timeframe, pm_strategy) if pm_preset_sel == "(latest)" else get_named_preset(pm_symbol, pm_timeframe, pm_strategy, pm_preset_sel)

        pm_initial = st.number_input("가상 시작자금 (USDT)", min_value=10.0, value=float(pm_saved.get("initial_usdt", 1000.0)), step=10.0, key="paper_initial")
        pm_lev = st.slider("레버리지", 1, 20, int(pm_saved.get("leverage", 1)), key="paper_lev")
        if pm_market == "spot":
            pm_lev = 1
        pm_sl = st.slider("SL %", 0.2, 5.0, float(pm_saved.get("sl_pct", 1.0)), 0.1, key="paper_sl")
        pm_tp = st.slider("TP RR", 0.5, 5.0, float(pm_saved.get("tp_rr", 1.5)), 0.1, key="paper_tp")
        pm_funding = st.slider("Funding %/8h", -0.20, 0.20, float(pm_saved.get("funding_rate_per_8h", 0.0)), 0.01, key="paper_funding")

        pm_refresh = st.slider("자동 갱신 주기(초)", 10, 120, 30, key="paper_refresh")
        pm_auto = st.checkbox("자동 새로고침", value=False, key="paper_auto")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            pm_start = st.button("시작", key="paper_start")
        with c2:
            pm_now = st.button("지금 갱신", key="paper_update")
        with c3:
            pm_pause = st.button("일시정지", key="paper_pause")
        with c4:
            pm_resume = st.button("재개", key="paper_resume")

        pm_reset = st.button("초기화(기록 삭제)", key="paper_reset")

        if pm_start:
            start_paper_session({
                "market_type": pm_market,
                "symbol": pm_symbol,
                "timeframe": pm_timeframe,
                "strategy": pm_strategy,
                "position_mode": pm_side,
                "initial_usdt": pm_initial,
                "leverage": pm_lev,
                "sl_pct": pm_sl,
                "tp_rr": pm_tp,
                "funding_rate_per_8h": pm_funding,
                "use_binance_funding": True,
                "ema_fast_period": int(pm_saved.get("ema_fast_period", 20)),
                "ema_slow_period": int(pm_saved.get("ema_slow_period", 50)),
                "rsi_period": int(pm_saved.get("rsi_period", 14)),
                "rsi_lower": float(pm_saved.get("rsi_lower", 30)),
                "rsi_upper": float(pm_saved.get("rsi_upper", 65)),
                "breakout_lookback": int(pm_saved.get("breakout_lookback", 20)),
                "ens_trend_w": float(pm_saved.get("ens_trend_w", 0.4)),
                "ens_rev_w": float(pm_saved.get("ens_rev_w", 0.3)),
                "ens_base_w": float(pm_saved.get("ens_base_w", 0.3)),
                "ens_spread_th": float(pm_saved.get("ens_spread_th", 0.01)),
                "ens_rsi_low": float(pm_saved.get("ens_rsi_low", 30)),
                "ens_rsi_high": float(pm_saved.get("ens_rsi_high", 70)),
            })
            st.success("모의투자 시작")

        live_cfg = {
            "market_type": pm_market,
            "symbol": pm_symbol,
            "timeframe": pm_timeframe,
            "strategy": pm_strategy,
            "position_mode": pm_side,
            "initial_usdt": pm_initial,
            "leverage": pm_lev,
            "sl_pct": pm_sl,
            "tp_rr": pm_tp,
            "funding_rate_per_8h": pm_funding,
            "use_binance_funding": True,
            "ema_fast_period": int(pm_saved.get("ema_fast_period", 20)),
            "ema_slow_period": int(pm_saved.get("ema_slow_period", 50)),
            "rsi_period": int(pm_saved.get("rsi_period", 14)),
            "rsi_lower": float(pm_saved.get("rsi_lower", 30)),
            "rsi_upper": float(pm_saved.get("rsi_upper", 65)),
            "breakout_lookback": int(pm_saved.get("breakout_lookback", 20)),
            "ens_trend_w": float(pm_saved.get("ens_trend_w", 0.4)),
            "ens_rev_w": float(pm_saved.get("ens_rev_w", 0.3)),
            "ens_base_w": float(pm_saved.get("ens_base_w", 0.3)),
            "ens_spread_th": float(pm_saved.get("ens_spread_th", 0.01)),
            "ens_rsi_low": float(pm_saved.get("ens_rsi_low", 30)),
            "ens_rsi_high": float(pm_saved.get("ens_rsi_high", 70)),
        }

        if pm_now:
            update_paper_session()
        if pm_pause:
            pause_paper_session()
            st.info("모의투자 일시정지")
        if pm_resume:
            resume_paper_session(config_updates=live_cfg)
            st.success("모의투자 재개 (현재 설정 반영)")
        if pm_reset:
            reset_paper_session()
            st.warning("모의투자 초기화 완료")

    with p_right:
        pstate = load_paper_state()
        if pstate.get("running"):
            pstate = update_paper_session()

        running = bool(pstate.get("running"))
        paused = bool(pstate.get("paused"))
        started_at = pstate.get("started_at")
        last_update = pstate.get("last_update")

        status_box = st.container(border=True)
        with status_box:
            if running:
                st.markdown("### 🟢 모의투자 진행중")
                components.html("""
                <div style='display:flex;align-items:center;gap:8px;font-size:14px;'>
                  <span style='display:inline-block;width:10px;height:10px;background:#22c55e;border-radius:50%;animation:pulse 1.2s infinite;'></span>
                  <span style='color:#9CA3AF;'>실시간 시뮬레이션이 동작 중입니다</span>
                </div>
                <style>
                @keyframes pulse {0%{opacity:1;transform:scale(1);}50%{opacity:.25;transform:scale(1.25);}100%{opacity:1;transform:scale(1);}}
                </style>
                """, height=36)
            elif paused:
                st.markdown("### 🟡 모의투자 일시정지")
            else:
                st.markdown("### ⚪ 모의투자 대기중")
            st.caption(f"시작 시각: {format_kst(started_at)}")
            st.caption(f"최근 갱신: {format_kst(last_update)}")

            cfg = pstate.get("config") or {}
            st.markdown(
                "**현재 적용 설정**\n"
                f"- 전략: `{cfg.get('strategy', '-')}`\n"
                f"- 심볼/TF: `{cfg.get('symbol', '-')}` / `{cfg.get('timeframe', '-')}`\n"
                f"- 방향/레버리지: `{cfg.get('position_mode', '-')}` / `{cfg.get('leverage', '-')}`x\n"
                f"- SL/TP: `{cfg.get('sl_pct', '-')}`% / RR `{cfg.get('tp_rr', '-')}`\n"
                f"- 자본: `{cfg.get('initial_usdt', '-')}` USDT"
            )

        metrics = pstate.get("metrics", {})
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("가상자금", f"{metrics.get('virtual_balance', 0):.2f} USDT")
        m2.metric("수익률", f"{metrics.get('return_pct', 0):.2f}%")
        m3.metric("거래수", int(metrics.get('trades', 0)))
        m4.metric("청산", int(metrics.get('liquidations', 0)))

        pres = pstate.get("result") or {}
        ptrades = pd.DataFrame(pres.get("trades", []))
        if not ptrades.empty:
            ptrades["entry_dt"] = pd.to_datetime(ptrades["entry_ts"], unit="ms")
            ptrades["exit_dt"] = pd.to_datetime(ptrades["exit_ts"], unit="ms")

            st.subheader("실시간 모의투자 거래내역")
            st.dataframe(ptrades.tail(30), use_container_width=True)

            cfg = pstate.get("config") or {}
            symbol = cfg.get("symbol", "BTC/USDT:USDT")
            tf = cfg.get("timeframe", "15m")
            start_iso = pstate.get("started_at")
            end_iso = datetime.now(timezone.utc).isoformat()
            if start_iso:
                cands = get_cached_ohlcv(cfg.get("market_type", "futures"), symbol, tf, start_iso, end_iso)
                if cands:
                    cdf = pd.DataFrame(cands, columns=["ts", "open", "high", "low", "close", "volume"])
                    cdf["ts"] = pd.to_datetime(cdf["ts"], unit="ms")
                    fig = go.Figure(data=[go.Candlestick(x=cdf["ts"], open=cdf["open"], high=cdf["high"], low=cdf["low"], close=cdf["close"], name="Price")])
                    fig.add_trace(go.Scatter(
                        x=ptrades["entry_dt"],
                        y=ptrades["entry"],
                        mode="markers",
                        marker=dict(symbol="triangle-up", size=14, color="#2F7BFF", line=dict(color="#0A2A66", width=2)),
                        name="진입",
                    ))
                    fig.add_trace(go.Scatter(
                        x=ptrades["exit_dt"],
                        y=ptrades["exit"],
                        mode="markers",
                        marker=dict(symbol="triangle-down", size=14, color="#FF3B30", line=dict(color="#3A0000", width=2)),
                        name="청산",
                    ))
                    fig.update_layout(title="모의투자 실시간 차트(진입/청산 시점)", xaxis_rangeslider_visible=False, height=520)
                    st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("모의투자 거래내역이 아직 없습니다.")

        if pm_auto and pstate.get("running"):
            components.html(f"<script>setTimeout(()=>window.location.reload(), {int(pm_refresh)*1000});</script>", height=0)

with tab_market:
    st.subheader("🧠 시장 인텔리전스 (뉴스/공식발표/공식계정 기반)")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("종합 점수", f"{market_brief.get('score', 0.0):.2f}")
    m2.metric("최종 시그널", market_brief.get("signal", "중립"))
    m3.metric("바이어스", market_brief.get("bias", "neutral"))
    m4.metric("신뢰도", f"{market_brief.get('confidence', 0.0) * 100:.1f}%")
    m5.metric("트럼프 이슈", int(market_brief.get("count_trump", 0)))
    m6.metric("예정 발표", int(market_brief.get("count_scheduled", 0)))

    st.markdown("#### ML 예측 확률 (최신 이벤트 기준)")
    p1, p2, p3, p4 = st.columns(4)
    pred_1h = ml_pred.get("label_up_1h", {})
    pred_4h = ml_pred.get("label_up_4h", {})
    pred_24h = ml_pred.get("label_up_24h", {})
    p1.metric("1h 상승확률", f"{((pred_1h.get('proba', [0, 0])[1] if pred_1h.get('ok') and len(pred_1h.get('proba', [])) > 1 else 0) * 100):.1f}%")
    p2.metric("4h 상승확률", f"{((pred_4h.get('proba', [0, 0])[1] if pred_4h.get('ok') and len(pred_4h.get('proba', [])) > 1 else 0) * 100):.1f}%")
    p3.metric("24h 상승확률", f"{((pred_24h.get('proba', [0, 0])[1] if pred_24h.get('ok') and len(pred_24h.get('proba', [])) > 1 else 0) * 100):.1f}%")
    p4.metric("혼합 ML 점수", f"{ml_composite_dashboard * 100:.1f}%")
    model_family = pred_4h.get('model_family') or pred_1h.get('model_family') or 'none'
    st.caption(f"현재 예측 엔진: {model_family}")

    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("크립토 직접이슈", f"{market_brief.get('crypto_score', 0.0):.2f}")
    s2.metric("거시 점수", f"{market_brief.get('macro_score', 0.0):.2f}")
    s3.metric("국제정세 점수", f"{market_brief.get('geo_score', 0.0):.2f}")
    s4.metric("공식발표 건수", int(market_brief.get("count_official", 0)))
    s5.metric("공식계정 건수", int(market_brief.get("count_tweet", 0)))

    if st.button("시장 인텔리전스 새로고침", key="refresh_market_intel"):
        market_brief = get_market_brief(force_refresh=True)
        st.rerun()

    bias = market_brief.get("bias", "neutral")
    final_signal = market_brief.get("signal", "중립")
    if final_signal == "공격":
        st.success("최종 시그널: 공격 — 거시/정세 포함 종합 흐름이 우호적입니다.")
    elif final_signal == "방어":
        st.error("최종 시그널: 방어 — 국제정세/거시 리스크를 우선 고려해야 합니다.")
    elif bias == "bullish":
        st.success("현재 흐름은 BTC 우호(Bullish): 롱 시그널 가중치 확대 가능")
    elif bias == "bearish":
        st.error("현재 흐름은 BTC 비우호(Bearish): 롱 보수/포지션 축소 권장")
    else:
        st.info("현재 흐름은 중립(Neutral): 기존 리스크 규칙 유지")

    top = pd.DataFrame(market_brief.get("top", []))
    if top.empty:
        st.info("현재 분석 가능한 신뢰 소스 데이터가 없습니다.")
    else:
        show_cols = [c for c in ["published", "source", "kind", "topic", "score", "title", "link"] if c in top.columns]
        st.dataframe(top[show_cols], use_container_width=True)

with tab_risk:
    st.subheader("리스크 가드레일")

    spot_state_path = os.getenv("RISK_STATE_PATH_SPOT", "data/risk_state_spot.json")
    futures_state_path = os.getenv("RISK_STATE_PATH_FUTURES", "data/risk_state_futures.json")

    guard_spot = can_trade(guard_cfg_spot, path=spot_state_path)
    guard_futures = can_trade(guard_cfg_futures, path=futures_state_path)

    st.markdown("### Spot")
    s1, s2, s3 = st.columns(3)
    s1.metric("오늘 실현손익(Spot)", f"{guard_spot['state'].get('daily_realized_pnl', 0.0):.2f} USDT")
    s2.metric("연속 손실(Spot)", int(guard_spot["state"].get("consecutive_losses", 0)))
    s3.metric("신규 진입 가능(Spot)", "YES" if guard_spot["allowed"] else "NO")
    st.write("Spot 중지 사유:", guard_spot["state"].get("reason") or "-없음-")

    st.markdown("### Futures")
    f1, f2, f3 = st.columns(3)
    f1.metric("오늘 실현손익(Futures)", f"{guard_futures['state'].get('daily_realized_pnl', 0.0):.2f} USDT")
    f2.metric("연속 손실(Futures)", int(guard_futures["state"].get("consecutive_losses", 0)))
    f3.metric("신규 진입 가능(Futures)", "YES" if guard_futures["allowed"] else "NO")
    st.write("Futures 중지 사유:", guard_futures["state"].get("reason") or "-없음-")

    st.write("한도 설정:")
    st.write(f"- Spot: 일일 손실 {guard_cfg_spot.daily_loss_limit_usdt} USDT / 연속 손실 {guard_cfg_spot.max_consecutive_losses}회")
    st.write(f"- Futures: 일일 손실 {guard_cfg_futures.daily_loss_limit_usdt} USDT / 연속 손실 {guard_cfg_futures.max_consecutive_losses}회")

    st.caption("`/trade/result`로 손익 이벤트를 입력하면 마켓별 가드 상태가 업데이트됩니다.")
