import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from shiny import App, render, ui, reactive
from faicons import icon_svg
from pathlib import Path
from shinywidgets import output_widget, render_widget

# --- DATA LAYER (SQL) ---
# This section simulates a production SQL layer.
# In a real Posit Connect deployment, you would use environment variables
# for credentials and connect to a production DB (Postgres, Snowflake, etc.)

DB_PATH = Path(__file__).parent / "complaints.db"

def get_filtered_data(date_range, countries, channels, categories, statuses):
    conn = sqlite3.connect(DB_PATH)
    
    # Base query with filters
    query = """
    SELECT * FROM complaints 
    WHERE date BETWEEN ? AND ?
    """
    params = [date_range[0], date_range[1]]
    
    if countries:
        query += f" AND country IN ({','.join(['?']*len(countries))})"
        params.extend(countries)
    if channels:
        query += f" AND channel IN ({','.join(['?']*len(channels))})"
        params.extend(channels)
    if categories:
        query += f" AND category IN ({','.join(['?']*len(categories))})"
        params.extend(categories)
    if statuses:
        query += f" AND status IN ({','.join(['?']*len(statuses))})"
        params.extend(statuses)
        
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

def get_complex_sql_metrics():
    """
    Example of a non-trivial SQL query using CTE and Window Functions.
    This query calculates the cumulative amount of complaints over time 
    and the rank of each category by volume within its country.
    """
    conn = sqlite3.connect(DB_PATH)
    query = """
    WITH DailyStats AS (
        SELECT 
            date,
            category,
            country,
            COUNT(*) as daily_count,
            SUM(amount) as daily_amount
        FROM complaints
        GROUP BY date, category, country
    ),
    RankedCategories AS (
        SELECT 
            *,
            -- Window Function: Rank categories by volume within each country
            RANK() OVER (PARTITION BY country ORDER BY daily_count DESC) as category_rank,
            -- Window Function: Cumulative sum of amount over time
            SUM(daily_amount) OVER (ORDER BY date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as cumulative_amount
        FROM DailyStats
    )
    SELECT * FROM RankedCategories
    LIMIT 100
    """
    # This query serves as a 'performance layer' by pre-aggregating complex metrics
    # that would be expensive to compute in-memory for very large datasets.
    df = pd.read_sql(query, conn)
    conn.close()
    return df

# --- UI DEFINITION ---

app_ui = ui.page_navbar(
    ui.nav_panel(
        "Overview",
        ui.layout_sidebar(
            ui.sidebar(
                ui.div(
                    ui.div("CX", class_="logo-box"),
                    ui.h4("Insights", style="margin:0;"),
                    class_="sidebar-header"
                ),
                ui.input_date_range("date_range", "Date Range", start="2025-01-01", end="2025-12-31"),
                ui.input_selectize("country", "Country", choices=[], multiple=True),
                ui.input_selectize("channel", "Channel", choices=[], multiple=True),
                ui.input_selectize("category", "Category", choices=[], multiple=True),
                ui.input_selectize("status", "Status", choices=[], multiple=True),
                ui.hr(),
                ui.markdown("""
                **CX Complaints Insights**  
                This dashboard provides a comprehensive view of customer complaints, 
                helping teams monitor SLAs, escalation rates, and volume trends.
                """),
                width=300
            ),
            # KPI Cards
            ui.layout_columns(
                ui.div(
                    ui.div("Total Complaints", class_="kpi-title"),
                    ui.output_ui("total_complaints", inline=True),
                    class_="kpi-card blue"
                ),
                ui.div(
                    ui.div("Escalation Rate", class_="kpi-title"),
                    ui.output_ui("escalation_rate", inline=True),
                    class_="kpi-card red"
                ),
                ui.div(
                    ui.div("Avg SLA (Hours)", class_="kpi-title"),
                    ui.output_ui("avg_sla", inline=True),
                    class_="kpi-card teal"
                ),
                ui.div(
                    ui.div("Total Value", class_="kpi-title"),
                    ui.output_ui("total_amount", inline=True),
                    class_="kpi-card green"
                ),
                fill=False
            ),
            # Visualizations
            ui.layout_columns(
                ui.card(
                    ui.card_header("Complaints Over Time"),
                    output_widget("time_series_plot")
                ),
                ui.card(
                    ui.card_header("Complaints by Category"),
                    output_widget("category_bar_plot")
                ),
                col_widths=[8, 4]
            ),
            ui.card(
                ui.card_header("Detailed Complaints Data"),
                ui.output_data_frame("complaints_table")
            )
        )
    ),
    ui.nav_panel(
        "Drill-down",
        ui.layout_columns(
            ui.card(
                ui.card_header("Top Countries by Volume"),
                output_widget("country_rank_plot")
            ),
            ui.card(
                ui.card_header("Channel Performance"),
                output_widget("channel_bar_plot")
            )
        )
    ),
    title="CX Complaints Insights",
    id="main_navbar",
    header=ui.include_css(Path(__file__).parent / "styles.css"),
    fillable=True
)

# --- SERVER LOGIC ---

def server(input, output, session):
    
    # Initialize filter choices
    @reactive.Effect
    def _():
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql("SELECT DISTINCT country, channel, category, status FROM complaints", conn)
        conn.close()
        
        ui.update_selectize("country", choices=sorted(df['country'].unique().tolist()))
        ui.update_selectize("channel", choices=sorted(df['channel'].unique().tolist()))
        ui.update_selectize("category", choices=sorted(df['category'].unique().tolist()))
        ui.update_selectize("status", choices=sorted(df['status'].unique().tolist()))

    # Reactive data subset
    @reactive.calc
    def filtered_df():
        return get_filtered_data(
            input.date_range(),
            input.country(),
            input.channel(),
            input.category(),
            input.status()
        )

    # KPI Calculations
    @render.ui
    def total_complaints():
        return ui.span(f"{len(filtered_df()):,}", class_="kpi-value")

    @render.ui
    def escalation_rate():
        df = filtered_df()
        if len(df) == 0: return ui.span("0.0%", class_="kpi-value")
        rate = (df['is_escalated'].sum() / len(df)) * 100
        return ui.span(f"{rate:.1f}%", class_="kpi-value")

    @render.ui
    def avg_sla():
        df = filtered_df()
        if len(df) == 0: return ui.span("0.0", class_="kpi-value")
        return ui.span(f"{df['sla_hours'].mean():.1f}", class_="kpi-value")

    @render.ui
    def total_amount():
        df = filtered_df()
        if len(df) == 0: return ui.span("$0", class_="kpi-value")
        return ui.span(f"${df['amount'].sum():,.0f}", class_="kpi-value")

    # Visualizations
    @render_widget
    def time_series_plot():
        df = filtered_df().copy()
        if df.empty: 
            return ui.div("No data available for selected filters.")
        
        # Convert to datetime and aggregate by date
        df['date'] = pd.to_datetime(df['date'])
        df_daily = df.groupby('date').size().reset_index(name='count')
        df_daily = df_daily.sort_values('date')
        
        # Create the figure manually with go.Scatter for better control
        fig = go.Figure()
        
        # Add the area trace
        fig.add_trace(go.Scatter(
            x=df_daily['date'],
            y=df_daily['count'],
            mode='lines',
            name='Complaints',
            line=dict(
                color='#3b82f6',
                width=3,
                shape='spline',
                smoothing=1.3
            ),
            fill='tozeroy',
            fillcolor='rgba(59, 130, 246, 0.15)',
            hovertemplate='<b>Date</b>: %{x|%b %d, %Y}<br><b>Complaints</b>: %{y}<extra></extra>'
        ))
        
        fig.update_layout(
            template="plotly_white",
            margin=dict(l=50, r=20, t=20, b=50),
            height=350,
            showlegend=False,
            xaxis=dict(
                title=None,
                tickformat="%b",
                dtick="M1",
                showgrid=False,
                zeroline=False
            ),
            yaxis=dict(
                title="Complaints",
                showgrid=True,
                gridcolor='#f1f5f9',
                zeroline=False
            ),
            hovermode="x unified",
            plot_bgcolor='white'
        )
        
        return fig

    @render_widget
    def category_bar_plot():
        df = filtered_df()
        if df.empty: return ui.div("No data available.")
        
        df_cat = df.groupby('category').size().reset_index(name='count').sort_values('count', ascending=True)
        fig = px.bar(df_cat, x='count', y='category', orientation='h', template="plotly_white")
        fig.update_traces(marker_color='#3498db')
        fig.update_layout(margin=dict(l=150, r=20, t=20, b=20), height=350, yaxis_title=None)
        return fig

    @render.data_frame
    def complaints_table():
        return render.DataTable(filtered_df())

    # Drill-down Visuals
    @render_widget
    def country_rank_plot():
        df = filtered_df()
        if df.empty: return ui.div("No data.")
        
        df_country = df.groupby('country').size().reset_index(name='count').sort_values('count', ascending=False)
        fig = px.pie(df_country, values='count', names='country', hole=.4, template="plotly_white")
        fig.update_layout(margin=dict(l=0, r=0, t=20, b=0), height=400)
        return fig

    @render_widget
    def channel_bar_plot():
        df = filtered_df()
        if df.empty: return ui.div("No data.")
        
        df_chan = df.groupby(['channel', 'status']).size().reset_index(name='count')
        fig = px.bar(df_chan, x='channel', y='count', color='status', barmode='group', template="plotly_white")
        fig.update_layout(margin=dict(l=0, r=0, t=20, b=0), height=400)
        return fig

app = App(app_ui, server)
