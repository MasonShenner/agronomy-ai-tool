import streamlit as st
import pandas as pd
import zipfile
import tempfile
import os
import plotly.express as px
import plotly.graph_objects as go
import json

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
    page_title="Agronomy AI Tool",
    layout="wide",
    page_icon="🌾"
)

# ---------------------------------
# Custom styling
# ---------------------------------
st.markdown(
    """
    <style>
    .main {
        padding-top: 1.2rem;
    }

    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }

    .hero-box {
        background: linear-gradient(135deg, #10233d 0%, #16385c 100%);
        padding: 1.4rem 1.6rem;
        border-radius: 18px;
        border: 1px solid rgba(255,255,255,0.08);
        margin-bottom: 1rem;
    }

    .hero-title {
        font-size: 2rem;
        font-weight: 700;
        color: white;
        margin-bottom: 0.4rem;
    }

    .hero-subtitle {
        font-size: 1rem;
        color: #d7e7f7;
        margin-bottom: 0.2rem;
    }

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

    .kpi-label {
        font-size: 0.9rem;
        color: #9ca3af;
        margin-bottom: 0.35rem;
    }

    .kpi-value {
        font-size: 1.65rem;
        font-weight: 700;
        color: #f9fafb;
    }

    .section-card {
        background: #0f172a;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 18px;
        padding: 1rem 1rem 0.75rem 1rem;
        margin-bottom: 1rem;
    }

    .summary-box {
        background: linear-gradient(135deg, #13304d 0%, #1d4c73 100%);
        padding: 1.15rem 1.2rem;
        border-radius: 18px;
        border: 1px solid rgba(255,255,255,0.08);
        color: white;
        margin-bottom: 1rem;
    }

    .summary-title {
        font-size: 1.25rem;
        font-weight: 700;
        margin-bottom: 0.6rem;
    }

    .small-note {
        color: #9ca3af;
        font-size: 0.88rem;
        margin-top: 0.2rem;
    }
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
        <div class="hero-title">Agronomy AI Decision Support Tool</div>
        <div class="hero-subtitle">
            Upload nitrogen prescription and yield data to compare original agronomist decisions
            with AI-assisted nitrogen recommendations.
        </div>
        <div class="crop-tag">Crop Type: CWRS (Canada Western Red Spring Wheat)</div>
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
        df = clean_columns(df)
        return df, "CSV file loaded successfully."

    if file_name.endswith(".xlsx") or file_name.endswith(".xls"):
        df = pd.read_excel(uploaded_file)
        df = clean_columns(df)
        return df, "Excel file loaded successfully."

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
                    csv_path = os.path.join(tmpdir, inner_file)
                    df = pd.read_csv(csv_path)
                    df = clean_columns(df)
                    return df, f"ZIP file loaded. Found CSV: {inner_file}"

            for inner_file in extracted_files:
                if inner_file.lower().endswith(".xlsx") or inner_file.lower().endswith(".xls"):
                    excel_path = os.path.join(tmpdir, inner_file)
                    df = pd.read_excel(excel_path)
                    df = clean_columns(df)
                    return df, f"ZIP file loaded. Found Excel file: {inner_file}"

            shp_files = [f for f in extracted_files if f.lower().endswith(".shp")]

            if shp_files:
                if not GEOPANDAS_AVAILABLE:
                    return None, "ZIP contains a shapefile, but geopandas is not installed."

                shp_path = os.path.join(tmpdir, shp_files[0])

                try:
                    try:
                        gdf = gpd.read_file(shp_path, engine="pyogrio")
                    except Exception:
                        gdf = gpd.read_file(shp_path)

                    gdf = clean_columns(gdf)
                    return gdf, f"ZIP file loaded. Found shapefile: {shp_files[0]}"
                except Exception as e:
                    return None, f"Found shapefile but could not read it: {e}"

            return None, "ZIP file was read, but no CSV, Excel, or shapefile was found."

    return None, "Unsupported file type."

def add_kpi(label, value, color="#f9fafb"):
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value" style="color:{color};">{value}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

def prepare_point_map_data(gdf):
    """
    Converts shapefile geometry into lat/lon for point-based plotting.
    Supports Point and MultiPoint. Falls back to centroid if needed.
    Also forces numeric plotting fields to avoid dtype/category issues.
    """
    plot_gdf = gdf.copy()

    if plot_gdf.crs is None:
        plot_gdf = plot_gdf.set_crs(epsg=4326, allow_override=True)
    else:
        plot_gdf = plot_gdf.to_crs(epsg=4326)

    geom_types = plot_gdf.geometry.geom_type.astype(str).str.lower()

    if geom_types.isin(["point"]).all():
        plot_gdf["lon"] = plot_gdf.geometry.x
        plot_gdf["lat"] = plot_gdf.geometry.y
    elif geom_types.isin(["multipoint"]).all():
        plot_gdf["lon"] = plot_gdf.geometry.centroid.x
        plot_gdf["lat"] = plot_gdf.geometry.centroid.y
    else:
        plot_gdf["lon"] = plot_gdf.geometry.centroid.x
        plot_gdf["lat"] = plot_gdf.geometry.centroid.y

    # force numeric map columns
    numeric_cols = ["lat", "lon", "Yield", "NitrogenRate", "AI_N_Rate", "N_Change"]
    for col in numeric_cols:
        if col in plot_gdf.columns:
            plot_gdf[col] = pd.to_numeric(plot_gdf[col], errors="coerce")

    plot_gdf = plot_gdf.dropna(subset=["lat", "lon"]).copy()
    return plot_gdf

def get_field_center_and_zoom(df):
    """
    Auto-center and auto-zoom based on point spread.
    """
    center_lat = df["lat"].median()
    center_lon = df["lon"].median()

    lat_range = df["lat"].max() - df["lat"].min()
    lon_range = df["lon"].max() - df["lon"].min()
    max_range = max(lat_range, lon_range)

    if max_range < 0.002:
        zoom = 16
    elif max_range < 0.005:
        zoom = 15
    elif max_range < 0.01:
        zoom = 14
    elif max_range < 0.03:
        zoom = 13
    else:
        zoom = 12

    return center_lat, center_lon, zoom

def build_point_map(
    df,
    value_column,
    color_scale,
    color_label,
    hover_columns,
    range_color=None
):
    """
    Build a clean point-based field map using Plotly.
    """
    plot_df = df.copy()

    # make sure mapped values are numeric
    for col in ["lat", "lon", value_column, "Yield", "NitrogenRate", "AI_N_Rate", "N_Change"]:
        if col in plot_df.columns:
            plot_df[col] = pd.to_numeric(plot_df[col], errors="coerce")

    plot_df = plot_df.dropna(subset=["lat", "lon", value_column"]).copy()

    if plot_df.empty:
        return None

    center_lat, center_lon, zoom = get_field_center_and_zoom(plot_df)

    point_size = 8
    if len(plot_df) > 10000:
        point_size = 4
    elif len(plot_df) > 5000:
        point_size = 5
    elif len(plot_df) > 2500:
        point_size = 6

    hover_data = {}
    for col in hover_columns:
        if col in plot_df.columns:
            hover_data[col] = True

    fig = px.scatter_mapbox(
        plot_df,
        lat="lat",
        lon="lon",
        color=value_column,
        color_continuous_scale=color_scale,
        range_color=range_color,
        hover_data=hover_data,
        zoom=zoom,
        center={"lat": center_lat, "lon": center_lon},
        height=600
    )

    fig.update_traces(
        marker=dict(size=point_size, opacity=0.82)
    )

    fig.update_layout(
        mapbox_style="open-street-map",
        margin=dict(l=0, r=0, t=0, b=0),
        coloraxis_colorbar_title=color_label,
        uirevision=f"{value_column}_point_map"
    )

    return fig

# ---------------------------------
# Upload section
# ---------------------------------
st.markdown('<div class="section-card">', unsafe_allow_html=True)
st.subheader("Upload Field Data")

upload_col1, upload_col2 = st.columns(2)

with upload_col1:
    n_file = st.file_uploader(
        "Upload Nitrogen Prescription File",
        type=["csv", "xlsx", "xls", "zip"]
    )

with upload_col2:
    y_file = st.file_uploader(
        "Upload Yield Data File",
        type=["csv", "xlsx", "xls", "zip"]
    )

st.markdown(
    '<div class="small-note">Accepted file types: CSV, Excel, and ZIP exports including shapefiles.</div>',
    unsafe_allow_html=True
)
st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------
# Main processing
# ---------------------------------
if n_file is not None and y_file is not None:
    n_df, n_message = read_uploaded_file(n_file)
    y_df, y_message = read_uploaded_file(y_file)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("File Processing Status")

    status_col1, status_col2 = st.columns(2)
    with status_col1:
        st.write(f"**Nitrogen file:** {n_message}")
    with status_col2:
        st.write(f"**Yield file:** {y_message}")

    if n_df is None or y_df is None:
        st.error("One or both files could not be read.")
        st.stop()
    else:
        st.success("Both files were loaded successfully.")
    st.markdown('</div>', unsafe_allow_html=True)

    # ---------------------------------
    # Preview data
    # ---------------------------------
    preview_col1, preview_col2 = st.columns(2)

    with preview_col1:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("Nitrogen Prescription Data Preview")
        preview_n = pd.DataFrame(n_df).drop(columns=["geometry"], errors="ignore")
        st.dataframe(preview_n.head(), width="stretch")
        st.markdown('</div>', unsafe_allow_html=True)

    with preview_col2:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("Yield Data Preview")
        preview_y = pd.DataFrame(y_df).drop(columns=["geometry"], errors="ignore")
        st.dataframe(preview_y.head(), width="stretch")
        st.markdown('</div>', unsafe_allow_html=True)

    # ---------------------------------
    # Agronomy calculations
    # ---------------------------------
    n = n_df.copy()
    y = y_df.copy()

    SQFT_TO_ACRES = 1 / 43560

    if "DISTANCE" in n.columns and "SWATHWIDTH" in n.columns:
        n["Area_ac"] = n["DISTANCE"] * n["SWATHWIDTH"] * SQFT_TO_ACRES

    if "DISTANCE" in y.columns and "SWATHWIDTH" in y.columns:
        y["Area_ac"] = y["DISTANCE"] * y["SWATHWIDTH"] * SQFT_TO_ACRES

    if "VRYIELDVOL" in y.columns:
        y["Yield"] = y["VRYIELDVOL"]

    min_len = min(len(n), len(y))
    merged = pd.DataFrame()

    if "Area_ac" in y.columns:
        merged["Area_ac"] = y["Area_ac"].iloc[:min_len].values

    if "Yield" in y.columns:
        merged["Yield"] = y["Yield"].iloc[:min_len].values

    if "AppliedRate" in n.columns:
        merged["NitrogenRate"] = n["AppliedRate"].iloc[:min_len].values

    if "Yield" in merged.columns and "NitrogenRate" in merged.columns:
        merged["N_Efficiency"] = merged["Yield"] / merged["NitrogenRate"]

    # Keep geometry from yield if available, otherwise nitrogen
    if "geometry" in y.columns:
        merged["geometry"] = y["geometry"].iloc[:min_len].values
    elif "geometry" in n.columns:
        merged["geometry"] = n["geometry"].iloc[:min_len].values

    merged = merged.replace([float("inf"), -float("inf")], pd.NA)
    merged = merged.dropna(subset=["Area_ac", "Yield", "NitrogenRate", "N_Efficiency"])

    if merged.empty:
        st.error("The uploaded files were read, but the processed dataset is empty after cleaning.")
        st.stop()

    merged["YieldClass"] = pd.qcut(
        merged["Yield"],
        5,
        labels=["Very Low", "Low", "Medium", "High", "Very High"]
    )

    summary = merged.groupby("YieldClass", observed=False).agg({
        "Area_ac": "sum",
        "Yield": "mean",
        "NitrogenRate": "mean",
        "N_Efficiency": "mean"
    }).reset_index()

    summary = summary.rename(columns={
        "YieldClass": "Yield Class",
        "Area_ac": "Area (ac)",
        "Yield": "Yield (bu/ac)",
        "NitrogenRate": "N Rate (lb/ac)",
        "N_Efficiency": "N Efficiency"
    })

    # ---------------------------------
    # AI recommendation model
    # ---------------------------------
    ai_table = summary.copy()

    def adjust_n_rate(row):
        efficiency = row["N Efficiency"]
        current_n = row["N Rate (lb/ac)"]

        if efficiency < 0.4:
            return current_n * 0.90
        elif efficiency < 0.6:
            return current_n * 0.95
        elif efficiency < 0.75:
            return current_n
        else:
            return current_n * 1.05

    ai_table["AI N Rate (lb/ac)"] = ai_table.apply(adjust_n_rate, axis=1)
    ai_table["N Change (lb/ac)"] = ai_table["AI N Rate (lb/ac)"] - ai_table["N Rate (lb/ac)"]

    # ---------------------------------
    # Map AI values back to points
    # ---------------------------------
    ai_rate_lookup = dict(zip(ai_table["Yield Class"], ai_table["AI N Rate (lb/ac)"]))
    ai_change_lookup = dict(zip(ai_table["Yield Class"], ai_table["N Change (lb/ac)"]))

    merged["AI_N_Rate"] = merged["YieldClass"].map(ai_rate_lookup)
    merged["N_Change"] = merged["YieldClass"].map(ai_change_lookup)
    # Force mapped recommendation fields to numeric
merged["AI_N_Rate"] = pd.to_numeric(merged["AI_N_Rate"], errors="coerce")
merged["N_Change"] = pd.to_numeric(merged["N_Change"], errors="coerce")
merged["Yield"] = pd.to_numeric(merged["Yield"], errors="coerce")
merged["NitrogenRate"] = pd.to_numeric(merged["NitrogenRate"], errors="coerce")

    # ---------------------------------
    # Rounded display
    # ---------------------------------
    summary_display = summary.copy()
    ai_display = ai_table.copy()

    for col in ["Area (ac)", "Yield (bu/ac)", "N Rate (lb/ac)", "N Efficiency"]:
        summary_display[col] = summary_display[col].round(2)

    for col in [
        "Area (ac)", "Yield (bu/ac)", "N Rate (lb/ac)",
        "N Efficiency", "AI N Rate (lb/ac)", "N Change (lb/ac)"
    ]:
        ai_display[col] = ai_display[col].round(2)

    # ---------------------------------
    # KPI cards
    # ---------------------------------
    total_area = summary["Area (ac)"].sum()
    avg_original_n = ai_table["N Rate (lb/ac)"].mean()
    avg_ai_n = ai_table["AI N Rate (lb/ac)"].mean()
    avg_n_change = ai_table["N Change (lb/ac)"].mean()

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        add_kpi("Estimated Field Area", f"{total_area:.1f} ac")
    with kpi2:
        add_kpi("Average Original N Rate", f"{avg_original_n:.1f} lb/ac")
    with kpi3:
        add_kpi("Average AI N Rate", f"{avg_ai_n:.1f} lb/ac")
    with kpi4:
        change_color = "#22c55e" if avg_n_change >= 0 else "#f97316"
        add_kpi("Average N Change", f"{avg_n_change:.1f} lb/ac", color=change_color)

    # ---------------------------------
    # Summary box
    # ---------------------------------
    lowest_eff_class = ai_table.loc[ai_table["N Efficiency"].idxmin(), "Yield Class"]
    highest_eff_class = ai_table.loc[ai_table["N Efficiency"].idxmax(), "Yield Class"]

    st.markdown(
        f"""
        <div class="summary-box">
            <div class="summary-title">AI Recommendation Summary</div>
            <div>
                The field was divided into yield zones to compare how nitrogen performed across different areas.
                Lower-yield areas showed weaker efficiency, which means nitrogen was not being used as effectively.
                Higher-yield areas showed stronger efficiency and a better response to nitrogen.
                <br><br>
                Based on this pattern, the model recommends slightly reducing nitrogen in lower-performing areas
                and maintaining or slightly increasing it in stronger-performing zones.
                <br><br>
                The weakest nitrogen performance was found in the <b>{lowest_eff_class}</b> zone, while the strongest
                performance was found in the <b>{highest_eff_class}</b> zone.
                <br><br>
                On average, the original nitrogen rate was <b>{avg_original_n:.1f} lb/ac</b>, and the AI-recommended
                rate is <b>{avg_ai_n:.1f} lb/ac</b>. This represents an average change of
                <b>{avg_n_change:.1f} lb/ac</b> across the field.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ---------------------------------
    # Nitrogen rate chart
    # ---------------------------------
    with st.expander("View Nitrogen Rate by Yield Class", expanded=False):
        st.markdown("Compare the original nitrogen rate with the AI-recommended rate for each yield class.")

        fig_n = go.Figure()

        fig_n.add_trace(
            go.Bar(
                x=summary_display["Yield Class"],
                y=summary_display["N Rate (lb/ac)"],
                name="Original N Rate",
                text=summary_display["N Rate (lb/ac)"],
                textposition="outside"
            )
        )

        fig_n.add_trace(
            go.Bar(
                x=ai_display["Yield Class"],
                y=ai_display["AI N Rate (lb/ac)"],
                name="AI N Rate",
                text=ai_display["AI N Rate (lb/ac)"],
                textposition="outside"
            )
        )

        fig_n.update_layout(
            barmode="group",
            height=430,
            xaxis_title="Yield Class",
            yaxis_title="Nitrogen Rate (lb/ac)",
            margin=dict(l=20, r=20, t=20, b=20)
        )

        st.plotly_chart(
            fig_n,
            width="stretch",
            config={"displayModeBar": False}
        )

    # ---------------------------------
    # Side-by-side tables
    # ---------------------------------
    st.subheader("Comparison: Agronomist vs AI Recommendation")

    table_col1, table_col2 = st.columns(2)

    with table_col1:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### Original Agronomist")
        st.dataframe(summary_display, width="stretch", hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with table_col2:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### AI Recommendation")
        st.dataframe(ai_display, width="stretch", hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ---------------------------------
# Point field maps
# ---------------------------------
if "geometry" in merged.columns and GEOPANDAS_AVAILABLE:
    st.subheader("Field Maps")

    try:
        gmap = gpd.GeoDataFrame(merged.copy(), geometry="geometry")
        gmap = prepare_point_map_data(gmap)

        if gmap.empty:
            st.warning("No valid point geometry was available for mapping.")
        else:
            map_tab1, map_tab2 = st.tabs(["Yield Map", "AI Nitrogen Adjustment Map"])

            with map_tab1:
                st.markdown('<div class="section-card">', unsafe_allow_html=True)
                st.markdown("### Yield Map")
                st.markdown("This point-based map shows yield variation across the field.")

                yield_df = gmap.dropna(subset=["Yield"]).copy()

                fig_yield = build_point_map(
                    df=yield_df,
                    value_column="Yield",
                    color_scale="YlGn",
                    color_label="Yield",
                    hover_columns=["Yield", "NitrogenRate", "AI_N_Rate", "N_Change", "YieldClass"]
                )

                if fig_yield is None:
                    st.info("Yield map could not be displayed because no valid mapped yield points were found.")
                else:
                    st.plotly_chart(
                        fig_yield,
                        width="stretch",
                        config={"displayModeBar": False, "scrollZoom": True}
                    )

                st.markdown('</div>', unsafe_allow_html=True)

            with map_tab2:
                st.markdown('<div class="section-card">', unsafe_allow_html=True)
                st.markdown("### AI Nitrogen Adjustment Map")
                st.markdown("Orange-red points suggest reducing nitrogen. Green points suggest maintaining or increasing nitrogen.")

                adj_df = gmap.dropna(subset=["N_Change"]).copy()
                adj_df["N_Change"] = pd.to_numeric(adj_df["N_Change"], errors="coerce")
                adj_df = adj_df.dropna(subset=["N_Change"]).copy()

                if adj_df.empty:
                    st.info("AI adjustment map could not be displayed because no valid nitrogen adjustment points were found.")
                else:
                    max_abs_change = float(adj_df["N_Change"].abs().max())
                    if pd.isna(max_abs_change) or max_abs_change == 0:
                        max_abs_change = 1.0

                    fig_adj = build_point_map(
                        df=adj_df,
                        value_column="N_Change",
                        color_scale="RdYlGn",
                        color_label="N Change (lb/ac)",
                        hover_columns=["Yield", "NitrogenRate", "AI_N_Rate", "N_Change", "YieldClass"],
                        range_color=[-max_abs_change, max_abs_change]
                    )

                    if fig_adj is None:
                        st.info("AI adjustment map could not be displayed after cleaning the mapped values.")
                    else:
                        st.plotly_chart(
                            fig_adj,
                            width="stretch",
                            config={"displayModeBar": False, "scrollZoom": True}
                        )

                st.markdown('</div>', unsafe_allow_html=True)

    except Exception as e:
        st.warning(f"Point field map could not be generated: {e}")

elif "geometry" in merged.columns and not GEOPANDAS_AVAILABLE:
    st.warning("Geometry was found, but geopandas is not installed, so the field map cannot be displayed.")
