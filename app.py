import os
import zipfile
import tempfile

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# Try to import geopandas for shapefile support
try:
    import geopandas as gpd
    GEOPANDAS_AVAILABLE = True
except ImportError:
    GEOPANDAS_AVAILABLE = False

# ---------------------------------
# Page setup
# ---------------------------------
st.set_page_config(
    page_title="Nitrogen Management Decision Support Tool",
    layout="wide",
    page_icon="🚜"
)

# ---------------------------------
# Custom styling
# ---------------------------------
st.markdown(
    """
    <style>
    .main { padding-top: 1.2rem; }
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    .hero-box {
        background: linear-gradient(135deg, #10233d 0%, #16385c 100%);
        padding: 1.4rem 1.6rem;
        border-radius: 18px;
        border: 1px solid rgba(255,255,255,0.08);
        margin-bottom: 1rem;
    }
    .hero-title { font-size: 2rem; font-weight: 700; color: white; margin-bottom: 0.4rem; }
    .hero-subtitle { font-size: 1rem; color: #d7e7f7; margin-bottom: 0.2rem; }
    .crop-tag {
        display: inline-block;
        background: rgba(255,255,255,0.12);
        color: #ffffff;
        padding: 0.45rem 0.75rem;
        border-radius: 999px;
        font-size: 0.9rem;
        font-weight: 600;
        margin-top: 0.5rem;
    }
    .kpi-card {
        background: #111827;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 16px;
        padding: 1rem 1rem 0.85rem 1rem;
        margin-bottom: 0.75rem;
    }
    .kpi-label { font-size: 0.9rem; color: #9ca3af; margin-bottom: 0.35rem; }
    .kpi-value { font-size: 1.65rem; font-weight: 700; color: #f9fafb; }
    .summary-box {
        background: linear-gradient(135deg, #13304d 0%, #1d4c73 100%);
        padding: 1.15rem 1.2rem;
        border-radius: 18px;
        border: 1px solid rgba(255,255,255,0.08);
        color: white;
        margin-bottom: 1rem;
    }
    .summary-title { font-size: 1.25rem; font-weight: 700; margin-bottom: 0.6rem; }
    .small-note { color: #9ca3af; font-size: 0.88rem; margin-top: 0.2rem; }
    .logic-box {
        background: #1e293b;
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 14px;
        padding: 0.9rem 1.1rem;
        color: #e2e8f0;
        font-size: 0.93rem;
        margin-bottom: 0.75rem;
    }
    div[data-baseweb="select"] > div { border-radius: 12px !important; }
    </style>
    """,
    unsafe_allow_html=True
)

# ---------------------------------
# Header
# ---------------------------------
st.markdown(
    """
    <div class="hero-box">
        <div class="hero-title">AI Nitrogen Management Decision Support Tool — Mason Shenner, Capstone 2026</div>
        <div class="hero-subtitle">
            Upload nitrogen prescription and yield data to compare original agronomist decisions
            with AI-assisted nitrogen recommendations.
        </div>
        <div class="crop-tag">Crop Type: CWRS &nbsp;|&nbsp; Variety: AAC Wheatland VB</div>
    </div>
    """,
    unsafe_allow_html=True
)

# ---------------------------------
# Helpers
# ---------------------------------
def clean_columns(df):
    df.columns = [str(col).strip() for col in df.columns]
    return df


def read_uploaded_file(uploaded_file):
    if uploaded_file is None:
        return None, "No file uploaded."
    file_name = uploaded_file.name.lower()
    if file_name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
        return clean_columns(df), "CSV file loaded successfully."
    if file_name.endswith(".xlsx") or file_name.endswith(".xls"):
        df = pd.read_excel(uploaded_file)
        return clean_columns(df), "Excel file loaded successfully."
    if file_name.endswith(".zip"):
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, uploaded_file.name)
            with open(zip_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(tmpdir)
                extracted_files = zip_ref.namelist()
            for inner_file in extracted_files:
                if inner_file.lower().endswith(".csv"):
                    df = pd.read_csv(os.path.join(tmpdir, inner_file))
                    return clean_columns(df), f"ZIP → CSV: {inner_file}"
            for inner_file in extracted_files:
                if inner_file.lower().endswith((".xlsx", ".xls")):
                    df = pd.read_excel(os.path.join(tmpdir, inner_file))
                    return clean_columns(df), f"ZIP → Excel: {inner_file}"
            shp_files = [f for f in extracted_files if f.lower().endswith(".shp")]
            if shp_files:
                if not GEOPANDAS_AVAILABLE:
                    return None, "ZIP contains a shapefile but geopandas is not installed."
                shp_path = os.path.join(tmpdir, shp_files[0])
                try:
                    try:
                        gdf = gpd.read_file(shp_path, engine="pyogrio")
                    except Exception:
                        gdf = gpd.read_file(shp_path)
                    return clean_columns(gdf), f"ZIP → Shapefile: {shp_files[0]}"
                except Exception as e:
                    return None, f"Shapefile found but could not be read: {e}"
            return None, "ZIP was read but no CSV, Excel, or shapefile was found inside."
    return None, "Unsupported file type."


def add_kpi(label, value, color="#f9fafb"):
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value" style="color:{color};">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def safe_qcut(series, q, labels):
    try:
        return pd.qcut(series, q=q, labels=labels, duplicates="drop")
    except ValueError:
        ranked = series.rank(method="first")
        return pd.qcut(ranked, q=q, labels=labels, duplicates="drop")


def make_rate_range_labels(series, bins=6, decimals=1):
    s = pd.to_numeric(series, errors="coerce")
    valid = s.dropna()
    if valid.empty:
        return pd.Series(["Unknown"] * len(series), index=series.index), ["Unknown"]
    min_val, max_val = float(valid.min()), float(valid.max())
    if min_val == max_val:
        label = f"{round(min_val, decimals)} lb/ac"
        return pd.Series([label] * len(series), index=series.index), [label]
    edges = [round(min_val + (max_val - min_val) / bins * i, decimals) for i in range(bins + 1)]
    for i in range(1, len(edges)):
        if edges[i] <= edges[i - 1]:
            edges[i] = round(edges[i - 1] + 10 ** -decimals, decimals)
    labels = [f"{edges[i]:.{decimals}f}–{edges[i+1]:.{decimals}f} lb/ac" for i in range(len(edges) - 1)]
    categorized = pd.cut(s, bins=edges, labels=labels, include_lowest=True, duplicates="drop")
    return categorized.astype(str), labels


# ---------------------------------
# Required column check
# ---------------------------------
REQUIRED_N_COLS  = ["AppliedRate", "DISTANCE", "SWATHWIDTH"]
REQUIRED_Y_COLS  = ["VRYIELDVOL", "DISTANCE", "SWATHWIDTH"]

def check_columns(df, required, label):
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error(
            f"**{label}** is missing required columns: `{'`, `'.join(missing)}`\n\n"
            f"This tool expects **John Deere Operations Center** exports. "
            f"Available columns in your file: `{'`, `'.join(df.columns.tolist())}`"
        )
        return False
    return True


# ---------------------------------
# Upload section
# ---------------------------------
st.divider()
st.subheader("Upload Field Data")

upload_col1, upload_col2 = st.columns(2)
with upload_col1:
    n_file = st.file_uploader("Upload Nitrogen Prescription File", type=["csv", "xlsx", "xls", "zip"])
with upload_col2:
    y_file = st.file_uploader("Upload Yield Data File", type=["csv", "xlsx", "xls", "zip"])

st.markdown(
    '<div class="small-note">Accepted formats: CSV, Excel, and ZIP exports (including shapefiles) '
    'from John Deere Operations Center. Required columns: '
    '<code>AppliedRate</code>, <code>VRYIELDVOL</code>, <code>DISTANCE</code>, <code>SWATHWIDTH</code>.</div>',
    unsafe_allow_html=True,
)

# ---------------------------------
# Main processing
# ---------------------------------
if n_file is not None and y_file is not None:
    n_df, n_message = read_uploaded_file(n_file)
    y_df, y_message = read_uploaded_file(y_file)

    st.divider()
    st.subheader("File Processing Status")
    status_col1, status_col2 = st.columns(2)
    with status_col1:
        st.write(f"**Nitrogen file:** {n_message}")
    with status_col2:
        st.write(f"**Yield file:** {y_message}")

    if n_df is None or y_df is None:
        st.error("One or both files could not be read. See messages above.")
        st.stop()
    else:
        st.success("Both files loaded successfully.")

    # Column validation
    n_ok = check_columns(n_df, REQUIRED_N_COLS, "Nitrogen Prescription File")
    y_ok = check_columns(y_df, REQUIRED_Y_COLS, "Yield Data File")
    if not n_ok or not y_ok:
        st.stop()

    # ---------------------------------
    # Preview data
    # ---------------------------------
    preview_col1, preview_col2 = st.columns(2)
    with preview_col1:
        st.subheader("Nitrogen Prescription Preview")
        st.dataframe(
            pd.DataFrame(n_df).drop(columns=["geometry"], errors="ignore").head(),
            use_container_width=True,
        )
    with preview_col2:
        st.subheader("Yield Data Preview")
        st.dataframe(
            pd.DataFrame(y_df).drop(columns=["geometry"], errors="ignore").head(),
            use_container_width=True,
        )

    # ---------------------------------
    # Fertilizer cost input
    # ---------------------------------
    st.divider()
    st.subheader("Fertilizer Cost Settings")
    n_cost_per_lb = st.number_input(
        "Nitrogen Fertilizer Cost ($/lb)",
        min_value=0.01,
        max_value=5.00,
        value=0.50,
        step=0.01,
        help="Enter the cost per pound of nitrogen fertilizer. Default $0.50/lb is a typical urea equivalent.",
    )
    st.markdown(
        '<div class="small-note">Used to calculate estimated fertilizer cost savings between '
        'agronomist and AI-recommended nitrogen rates.</div>',
        unsafe_allow_html=True,
    )

    # ---------------------------------
    # Agronomy calculations
    # ---------------------------------
    n = n_df.copy()
    y = y_df.copy()
    sqft_to_acres = 1 / 43560

    n["Area_ac"] = n["DISTANCE"] * n["SWATHWIDTH"] * sqft_to_acres
    y["Area_ac"] = y["DISTANCE"] * y["SWATHWIDTH"] * sqft_to_acres
    y["Yield"]   = y["VRYIELDVOL"]

    min_len = min(len(n), len(y))
    merged = pd.DataFrame()
    merged["Area_ac"]      = y["Area_ac"].iloc[:min_len].values
    merged["Yield"]        = y["Yield"].iloc[:min_len].values
    merged["NitrogenRate"] = n["AppliedRate"].iloc[:min_len].values

    merged["N_Efficiency"] = merged["Yield"] / merged["NitrogenRate"]

    if "geometry" in y.columns:
        merged["geometry"] = y["geometry"].iloc[:min_len].values
    elif "geometry" in n.columns:
        merged["geometry"] = n["geometry"].iloc[:min_len].values

    merged = merged.replace([float("inf"), -float("inf")], pd.NA)
    merged = merged.dropna(subset=["Area_ac", "Yield", "NitrogenRate", "N_Efficiency"])

    if merged.empty:
        st.error(
            "The data processed to an empty dataset after cleaning. "
            "Check that your nitrogen and yield files are from the same growing season."
        )
        st.stop()

    merged["YieldClass"] = safe_qcut(
        merged["Yield"], 5,
        ["Very Low", "Low", "Medium", "High", "Very High"],
    )

    summary = merged.groupby("YieldClass", observed=False).agg(
        Area_ac=("Area_ac", "sum"),
        Yield=("Yield", "mean"),
        NitrogenRate=("NitrogenRate", "mean"),
        N_Efficiency=("N_Efficiency", "mean"),
    ).reset_index()

    summary = summary.rename(columns={
        "YieldClass":    "Yield Class",
        "Area_ac":       "Area (ac)",
        "Yield":         "Yield (bu/ac)",
        "NitrogenRate":  "N Rate (lb/ac)",
        "N_Efficiency":  "N Efficiency (NUE)",
    })

    # ---------------------------------
    # AI recommendation model
    # ---------------------------------
    ai_table = summary.copy()

    def adjust_n_rate(row):
        """
        Rule-based NUE decision model:
          NUE < 0.40  →  reduce N by 10%  (poor response, likely over-applied)
          NUE < 0.60  →  reduce N by  5%  (below-average response)
          NUE < 0.75  →  keep N the same  (adequate response)
          NUE ≥ 0.75  →  increase N by 5% (strong response, crop can use more)
        """
        nue = row["N Efficiency (NUE)"]
        n   = row["N Rate (lb/ac)"]
        if nue < 0.40:
            return n * 0.90
        elif nue < 0.60:
            return n * 0.95
        elif nue < 0.75:
            return n
        else:
            return n * 1.05

    ai_table["AI N Rate (lb/ac)"] = ai_table.apply(adjust_n_rate, axis=1)
    ai_table["N Change (lb/ac)"]  = ai_table["AI N Rate (lb/ac)"] - ai_table["N Rate (lb/ac)"]

    # Cost calculations
    ai_table["Original Cost ($)"] = (
        ai_table["N Rate (lb/ac)"] * ai_table["Area (ac)"] * n_cost_per_lb
    )
    ai_table["AI Cost ($)"] = (
        ai_table["AI N Rate (lb/ac)"] * ai_table["Area (ac)"] * n_cost_per_lb
    )
    ai_table["Cost Savings ($)"] = ai_table["Original Cost ($)"] - ai_table["AI Cost ($)"]

    # ---------------------------------
    # Rounded display tables
    # ---------------------------------
    summary_display = summary.copy()
    ai_display = ai_table.copy()

    for col in ["Area (ac)", "Yield (bu/ac)", "N Rate (lb/ac)", "N Efficiency (NUE)"]:
        summary_display[col] = summary_display[col].round(2)

    for col in [
        "Area (ac)", "Yield (bu/ac)", "N Rate (lb/ac)", "N Efficiency (NUE)",
        "AI N Rate (lb/ac)", "N Change (lb/ac)",
        "Original Cost ($)", "AI Cost ($)", "Cost Savings ($)",
    ]:
        if col in ai_display.columns:
            ai_display[col] = ai_display[col].round(2)

    # ---------------------------------
    # KPI values
    # ---------------------------------
    total_area       = summary["Area (ac)"].sum()
    avg_original_n   = ai_table["N Rate (lb/ac)"].mean()
    avg_ai_n         = ai_table["AI N Rate (lb/ac)"].mean()
    avg_n_change     = ai_table["N Change (lb/ac)"].mean()
    avg_nue          = ai_table["N Efficiency (NUE)"].mean()
    total_savings    = ai_table["Cost Savings ($)"].sum()
    total_orig_cost  = ai_table["Original Cost ($)"].sum()
    total_ai_cost    = ai_table["AI Cost ($)"].sum()

    # ---------------------------------
    # KPI cards — 3 rows of 3
    # ---------------------------------
    kpi1, kpi2, kpi3 = st.columns(3)
    with kpi1:
        add_kpi("Estimated Field Area", f"{total_area:.1f} ac")
    with kpi2:
        add_kpi("Average Original N Rate", f"{avg_original_n:.1f} lb/ac")
    with kpi3:
        add_kpi("Average AI N Rate", f"{avg_ai_n:.1f} lb/ac")

    kpi4, kpi5, kpi6 = st.columns(3)
    with kpi4:
        change_color = "#22c55e" if avg_n_change >= 0 else "#f97316"
        add_kpi("Average N Rate Change", f"{avg_n_change:+.1f} lb/ac", color=change_color)
    with kpi5:
        add_kpi("Average NUE (Field)", f"{avg_nue:.2f} bu/lb N")
    with kpi6:
        savings_color = "#22c55e" if total_savings >= 0 else "#f97316"
        add_kpi("Estimated Cost Savings", f"${total_savings:,.0f}", color=savings_color)

    # ---------------------------------
    # AI logic explainer
    # ---------------------------------
    with st.expander("How does the AI recommendation work?", expanded=False):
        st.markdown(
            """
            <div class="logic-box">
            <b>Decision Model — Nitrogen Use Efficiency (NUE) Thresholds</b><br><br>
            The tool calculates NUE for each yield class using:<br>
            <code>NUE = Yield (bu/ac) ÷ Nitrogen Rate (lb/ac)</code><br><br>
            It then adjusts the nitrogen rate for each zone based on how efficiently nitrogen was used:
            <br><br>
            <table style="width:100%; border-collapse:collapse; font-size:0.92rem;">
              <tr style="border-bottom:1px solid rgba(255,255,255,0.1);">
                <th style="text-align:left; padding:4px 8px;">NUE Range</th>
                <th style="text-align:left; padding:4px 8px;">Interpretation</th>
                <th style="text-align:left; padding:4px 8px;">Adjustment</th>
              </tr>
              <tr><td style="padding:4px 8px;">NUE &lt; 0.40</td><td style="padding:4px 8px;">Poor response — likely over-applied</td><td style="padding:4px 8px; color:#f97316;">−10%</td></tr>
              <tr><td style="padding:4px 8px;">0.40 – 0.60</td><td style="padding:4px 8px;">Below average response</td><td style="padding:4px 8px; color:#fbbf24;">−5%</td></tr>
              <tr><td style="padding:4px 8px;">0.60 – 0.75</td><td style="padding:4px 8px;">Adequate response</td><td style="padding:4px 8px; color:#9ca3af;">No change</td></tr>
              <tr><td style="padding:4px 8px;">NUE ≥ 0.75</td><td style="padding:4px 8px;">Strong response — crop can use more</td><td style="padding:4px 8px; color:#22c55e;">+5%</td></tr>
            </table>
            <br>
            This is a rule-based decision model derived from agronomic NUE research.
            It uses the same data inputs an agronomist has access to, and is intended as a
            comparison tool — not a replacement for professional judgment.
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ---------------------------------
    # Summary box
    # ---------------------------------
    lowest_eff_class  = ai_table.loc[ai_table["N Efficiency (NUE)"].idxmin(), "Yield Class"]
    highest_eff_class = ai_table.loc[ai_table["N Efficiency (NUE)"].idxmax(), "Yield Class"]

    st.markdown(
        f"""
        <div class="summary-box">
            <div class="summary-title">AI Recommendation Summary</div>
            <div>
                The field was divided into yield zones to compare how nitrogen performed across different areas.
                Lower-yield areas showed weaker nitrogen use efficiency, while higher-yield areas showed a
                stronger response to the nitrogen applied.
                <br><br>
                Based on these patterns, the model recommends reducing nitrogen in lower-performing zones
                and maintaining or slightly increasing rates in stronger-performing zones.
                <br><br>
                The weakest nitrogen performance was in the <b>{lowest_eff_class}</b> zone (NUE: {ai_table["N Efficiency (NUE)"].min():.2f} bu/lb N),
                and the strongest was in the <b>{highest_eff_class}</b> zone (NUE: {ai_table["N Efficiency (NUE)"].max():.2f} bu/lb N).
                <br><br>
                Original average nitrogen rate: <b>{avg_original_n:.1f} lb/ac</b> →
                AI-recommended rate: <b>{avg_ai_n:.1f} lb/ac</b>
                (average change: <b>{avg_n_change:+.1f} lb/ac</b>).
                <br><br>
                Estimated total fertilizer cost at ${n_cost_per_lb:.2f}/lb:
                Original <b>${total_orig_cost:,.0f}</b> → AI <b>${total_ai_cost:,.0f}</b>
                — a potential saving of <b>${total_savings:,.0f}</b>.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---------------------------------
    # Nitrogen rate chart
    # ---------------------------------
    with st.expander("View Nitrogen Rate by Yield Class", expanded=False):
        st.markdown("Compare the original nitrogen rate with the AI-recommended rate for each yield class.")
        fig_n = go.Figure()
        fig_n.add_trace(go.Bar(
            x=summary_display["Yield Class"],
            y=summary_display["N Rate (lb/ac)"],
            name="Original N Rate",
            text=summary_display["N Rate (lb/ac)"],
            textposition="outside",
        ))
        fig_n.add_trace(go.Bar(
            x=ai_display["Yield Class"],
            y=ai_display["AI N Rate (lb/ac)"],
            name="AI N Rate",
            text=ai_display["AI N Rate (lb/ac)"],
            textposition="outside",
        ))
        fig_n.update_layout(
            barmode="group",
            height=430,
            xaxis_title="Yield Class",
            yaxis_title="Nitrogen Rate (lb/ac)",
            margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig_n, use_container_width=True, config={"displayModeBar": False})

    # NUE chart
    with st.expander("View Nitrogen Use Efficiency (NUE) by Yield Class", expanded=False):
        st.markdown(
            "NUE = Yield (bu/ac) ÷ N Rate (lb/ac). "
            "Higher values mean nitrogen was used more efficiently by the crop."
        )
        nue_colors = ["#dc2626", "#f97316", "#eab308", "#84cc16", "#16a34a"]
        fig_nue = go.Figure()
        fig_nue.add_trace(go.Bar(
            x=summary_display["Yield Class"],
            y=summary_display["N Efficiency (NUE)"].round(2),
            name="NUE",
            marker_color=nue_colors[:len(summary_display)],
            text=summary_display["N Efficiency (NUE)"].round(2),
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>NUE: %{y:.2f} bu/lb N<extra></extra>",
        ))
        fig_nue.update_layout(
            height=400,
            xaxis_title="Yield Class",
            yaxis_title="NUE (bu/lb N)",
            margin=dict(l=20, r=20, t=20, b=20),
            showlegend=False,
        )
        st.plotly_chart(fig_nue, use_container_width=True, config={"displayModeBar": False})

    # Cost chart
    with st.expander("View Estimated Fertilizer Cost by Yield Class", expanded=False):
        st.markdown(
            f"Estimated fertilizer cost at **${n_cost_per_lb:.2f}/lb** for each yield zone, "
            "comparing original and AI-recommended rates."
        )
        fig_cost = go.Figure()
        fig_cost.add_trace(go.Bar(
            x=ai_display["Yield Class"],
            y=ai_display["Original Cost ($)"],
            name="Original Cost ($)",
            text=ai_display["Original Cost ($)"].apply(lambda v: f"${v:,.0f}"),
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>Original Cost: $%{y:,.0f}<extra></extra>",
        ))
        fig_cost.add_trace(go.Bar(
            x=ai_display["Yield Class"],
            y=ai_display["AI Cost ($)"],
            name="AI Cost ($)",
            text=ai_display["AI Cost ($)"].apply(lambda v: f"${v:,.0f}"),
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>AI Cost: $%{y:,.0f}<extra></extra>",
        ))
        fig_cost.update_layout(
            barmode="group",
            height=430,
            xaxis_title="Yield Class",
            yaxis_title="Estimated Cost ($)",
            margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig_cost, use_container_width=True, config={"displayModeBar": False})

    # ---------------------------------
    # Side-by-side comparison tables
    # ---------------------------------
    st.subheader("Comparison: Agronomist vs AI Recommendation")
    table_col1, table_col2 = st.columns(2)
    with table_col1:
        st.markdown("#### Original Agronomist")
        st.dataframe(summary_display, use_container_width=True, hide_index=True)
    with table_col2:
        st.markdown("#### AI Recommendation")
        cols_to_show = [
            "Yield Class", "Area (ac)", "Yield (bu/ac)", "N Rate (lb/ac)",
            "N Efficiency (NUE)", "AI N Rate (lb/ac)", "N Change (lb/ac)",
            "Original Cost ($)", "AI Cost ($)", "Cost Savings ($)",
        ]
        st.dataframe(
            ai_display[[c for c in cols_to_show if c in ai_display.columns]],
            use_container_width=True,
            hide_index=True,
        )

    # ---------------------------------
    # Download button
    # ---------------------------------
    st.divider()
    st.subheader("Export AI Recommendations")
    export_cols = [
        "Yield Class", "Area (ac)", "Yield (bu/ac)", "N Rate (lb/ac)",
        "N Efficiency (NUE)", "AI N Rate (lb/ac)", "N Change (lb/ac)",
        "Original Cost ($)", "AI Cost ($)", "Cost Savings ($)",
    ]
    export_df = ai_display[[c for c in export_cols if c in ai_display.columns]]
    csv_bytes = export_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️  Download AI Recommendations as CSV",
        data=csv_bytes,
        file_name="ai_nitrogen_recommendations.csv",
        mime="text/csv",
    )
    st.markdown(
        '<div class="small-note">Download the AI-recommended nitrogen rates by yield class '
        'for use in your agronomic planning.</div>',
        unsafe_allow_html=True,
    )

    # ---------------------------------
    # Field map viewer
    # ---------------------------------
    if "geometry" in merged.columns and GEOPANDAS_AVAILABLE:
        st.divider()
        st.subheader("Field Map Viewer")
        try:
            gmap = gpd.GeoDataFrame(merged.copy(), geometry="geometry")
            if gmap.crs is None:
                gmap = gmap.set_crs(epsg=4326, allow_override=True)
            gmap = gmap.to_crs(epsg=4326)

            # Use centroid so polygon geometries work correctly
            gmap["lon"] = gmap.geometry.centroid.x
            gmap["lat"] = gmap.geometry.centroid.y

            ai_rate_lookup = dict(zip(ai_table["Yield Class"], ai_table["AI N Rate (lb/ac)"]))
            gmap["AI_N_Rate"] = gmap["YieldClass"].map(ai_rate_lookup)

            gmap["Yield"]        = pd.to_numeric(gmap["Yield"],        errors="coerce")
            gmap["NitrogenRate"] = pd.to_numeric(gmap["NitrogenRate"], errors="coerce")
            gmap["AI_N_Rate"]    = pd.to_numeric(gmap["AI_N_Rate"],    errors="coerce")

            gmap["DisplayYield"]     = gmap["Yield"].round(1)
            gmap["DisplayOriginalN"] = gmap["NitrogenRate"].round(1)
            gmap["DisplayAIN"]       = gmap["AI_N_Rate"].round(1)
            gmap["DisplayClass"]     = gmap["YieldClass"].astype(str)

            map_choice = st.selectbox(
                "Map Selection",
                ["Original Nitrogen Applied", "AI Recommended Nitrogen Rate"],
            )

            # Yield-class colour palette (red → green = very low → very high)
            YIELD_CLASS_ORDER   = ["Very Low", "Low", "Medium", "High", "Very High"]
            YIELD_CLASS_PALETTE = {
                "Very Low":  "#dc2626",
                "Low":       "#f97316",
                "Medium":    "#eab308",
                "High":      "#84cc16",
                "Very High": "#16a34a",
            }

            if map_choice == "Original Nitrogen Applied":
                # Original map: colour by binned N rate (red = low, green = high)
                gmap["LegendRange"], range_order = make_rate_range_labels(
                    gmap["NitrogenRate"], bins=6, decimals=1
                )
                gmap    = gmap.dropna(subset=["LegendRange"])
                range_order = [r for r in range_order if r and str(r).lower() not in ("nan", "")]
                map_note         = "Each dot shows the nitrogen rate originally applied at that location. Red = lower rates, green = higher rates."
                hover_rate_label = "N Applied"
                custom_cols      = ["DisplayOriginalN", "DisplayYield", "DisplayClass"]

                if len(range_order) == 0:
                    st.warning("Map legend ranges could not be created from the available data.")
                else:
                    palette   = ["#dc2626", "#f97316", "#eab308", "#84cc16", "#4fd000", "#16a34a"]
                    color_map = {label: palette[min(i, len(palette) - 1)] for i, label in enumerate(range_order)}
                    st.markdown(map_note)
                    fig_map = px.scatter_map(
                        gmap, lat="lat", lon="lon",
                        color="LegendRange",
                        category_orders={"LegendRange": range_order},
                        color_discrete_map=color_map,
                        zoom=12, height=650,
                        custom_data=custom_cols,
                    )
                    fig_map.update_traces(
                        marker=dict(size=6, opacity=0.88),
                        hovertemplate=(
                            f"<b>{hover_rate_label}:</b> %{{customdata[0]}} lb/ac<br>"
                            "<b>Yield:</b> %{customdata[1]} bu/ac<br>"
                            "<b>Class:</b> %{customdata[2]}"
                            "<extra></extra>"
                        ),
                    )
                    fig_map.update_layout(
                        margin=dict(l=0, r=0, t=0, b=0),
                        legend_title_text="N Rate",
                        legend=dict(orientation="v", yanchor="top", y=0.98, xanchor="left", x=1.01),
                    )
                    st.plotly_chart(fig_map, use_container_width=True, config={"displayModeBar": False})

            else:
                # AI map: colour by yield class (NUE performance)
                # Red = very low NUE → most nitrogen cut; Green = very high NUE → N maintained/increased
                gmap["YieldClassStr"] = gmap["YieldClass"].astype(str)
                gmap = gmap.dropna(subset=["YieldClassStr", "AI_N_Rate"])
                map_note = (
                    "Each dot is coloured by its yield class. "
                    "**Red = Very Low NUE** zones where nitrogen was reduced the most (−10%). "
                    "**Green = Very High NUE** zones where nitrogen was maintained or slightly increased (+5%)."
                )
                custom_cols = ["DisplayAIN", "DisplayYield", "DisplayClass"]

                st.markdown(map_note)
                fig_map = px.scatter_map(
                    gmap, lat="lat", lon="lon",
                    color="YieldClassStr",
                    category_orders={"YieldClassStr": YIELD_CLASS_ORDER},
                    color_discrete_map=YIELD_CLASS_PALETTE,
                    zoom=12, height=650,
                    custom_data=custom_cols,
                )
                fig_map.update_traces(
                    marker=dict(size=6, opacity=0.88),
                    hovertemplate=(
                        "<b>AI Rate:</b> %{customdata[0]} lb/ac<br>"
                        "<b>Yield:</b> %{customdata[1]} bu/ac<br>"
                        "<b>Class:</b> %{customdata[2]}"
                        "<extra></extra>"
                    ),
                )
                fig_map.update_layout(
                    margin=dict(l=0, r=0, t=0, b=0),
                    legend_title_text="Yield Class (NUE)",
                    legend=dict(orientation="v", yanchor="top", y=0.98, xanchor="left", x=1.01),
                )
                st.plotly_chart(fig_map, use_container_width=True, config={"displayModeBar": False})

        except Exception as e:
            st.warning(f"Field map could not be generated: {e}")
