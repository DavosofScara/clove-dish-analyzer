import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from io import BytesIO
from PIL import Image
import base64
from fpdf import FPDF
from datetime import date
import tempfile
import os

st.set_page_config(page_title="Clove Dish Analyzer", layout="wide")

# Custom CSS for better typography and spacing
st.markdown("""
<style>
    .main-header {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        font-weight: 600;
        letter-spacing: -0.025em;
        margin-bottom: 2rem;
    }
    .sub-header {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        font-weight: 500;
        letter-spacing: -0.01em;
        margin-bottom: 1.5rem;
        margin-top: 2rem;
    }
    .body-text {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        line-height: 1.6;
        margin-bottom: 1rem;
    }
    .section-spacing {
        margin-top: 3rem;
        margin-bottom: 2rem;
    }
    .card-style {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 1.5rem;
        border: 1px solid rgba(255, 255, 255, 0.1);
        margin-bottom: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)

# Load image and encode as base64
def get_base64_image(image_path):
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()

# Convert logo
encoded_logo = get_base64_image("clove_logo.png")

# Inject into page with improved styling
st.markdown(f"""
<div style='text-align: center; margin-bottom: 3rem; padding: 2rem 0;'>
    <img src="data:image/png;base64,{encoded_logo}" style='width:280px; margin-bottom: 1rem; filter: drop-shadow(0 4px 8px rgba(0,0,0,0.3));' />
    <h1 class="main-header" style='margin-bottom: 0.5rem; font-size: 2.5rem; color: #F0F0F0;'>Clove Dish Analyzer</h1>
    <p style='font-style: italic; color: #A9DFBF; font-size: 1.2rem; margin: 0; font-weight: 300;'>Forensic Profits in Food & Beverage</p>
</div>
""", unsafe_allow_html=True)

# --- File Uploads ---
st.markdown('<h2 class="sub-header">📁 Upload Your Files</h2>', unsafe_allow_html=True)

# Create a card-style container for uploads
st.markdown('<div class="card-style">', unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    st.markdown('<p class="body-text">Upload your dish spreadsheet to begin analysis:</p>', unsafe_allow_html=True)
    dish_file = st.file_uploader("🧾 Dish Spreadsheet", type=["xlsx"], help="Upload an Excel file with your dish data")
with col2:
    st.markdown('<p class="body-text">Optional: Add ingredient price reference:</p>', unsafe_allow_html=True)
    price_file = st.file_uploader("💰 Ingredient Prices (optional)", type=["xlsx"], help="Upload ingredient price data for cost calculations")

st.markdown('</div>', unsafe_allow_html=True)


# Load static carbon footprint reference table
@st.cache_data
def load_carbon_data():
    return {
        "Pasta": 1.1, "Beef Mince": 27.0, "Tomato Sauce": 2.5,
        "Chicken Breast": 6.9, "Lettuce": 0.8, "Cucumber": 0.4,
        "Chickpeas": 0.9, "Tomato": 1.4, "Coconut Milk": 2.9,
        "White Fish": 5.5, "Bun": 1.2, "Tortilla": 1.0, "Cheese": 13.5,
        "Arborio Rice": 1.8, "Mushrooms": 1.2, "Parmesan": 10.0,
        "Yogurt": 2.1, "Quinoa": 1.5, "Avocado": 2.2, "Couscous": 1.7,
        "Tofu": 1.9, "Broccoli": 0.6, "Soy Sauce": 3.2
    }

carbon_data = load_carbon_data()

# --- Process Price File ---
ingredient_price_map = {}
if price_file:
    try:
        price_df = pd.read_excel(price_file)
        ingredient_price_map = dict(zip(price_df["Ingredient"], price_df["Price per g (€)"]))
        st.success("✅ Price reference file loaded")
    except Exception as e:
        st.error(f"❌ Could not read price file: {e}")

# --- PDF Generation Function ---
from fpdf import FPDF
from datetime import date
import tempfile

def to_latin1(s):
    try:
        return s.encode("latin-1", "ignore").decode("latin-1")
    except:
        return ""

def generate_pdf(df):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Logo and header
    pdf.image("clove_logo.png", x=80, w=50)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, to_latin1("Clove Dish Analysis Report"), ln=True, align="C")
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 10, to_latin1(f"Date: {date.today().strftime('%B %d, %Y')}"), ln=True, align="C")
    pdf.ln(10)

    # Summary Table
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, to_latin1("Dish Summary"), ln=True)
    pdf.set_font("Helvetica", "", 10)

    for _, row in df.iterrows():
        flag_raw = row.get("Flag", "")
        flag_clean = str(flag_raw).replace("⚠️", "Warning").replace("🌍", "High CO2")
        line = (
            f"{row['Dish Name']} | Cost: €{row['Total Cost (€)']:.2f} | "
            f"Margin: {row['Margin (%)']}% | CO2e: {row['Estimated CO₂e (kg)']}kg | {flag_clean}"
        )
        try:
            safe_line = to_latin1(str(line))
            if safe_line.strip():
                pdf.multi_cell(0, 7, safe_line)
        except Exception:
            pdf.multi_cell(0, 7, "⚠️ Line could not be displayed.")

    # Key Observations
    low_margin = df[df["Margin (%)"] < 60].shape[0]
    high_co2 = df[df["Estimated CO₂e (kg)"] > 3].shape[0]
    observations = (
        f"{low_margin} dish(es) have a margin below 60%.\n"
        f"{high_co2} dish(es) exceed 3kg CO₂e emissions."
    )
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, to_latin1("Key Observations"), ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 6, to_latin1(observations))

    # --- Chart 1: CO₂e Footprint per Dish ---
    fig1, ax1 = plt.subplots(figsize=(6, 4))
    sns.barplot(data=df.sort_values("Estimated CO₂e (kg)", ascending=False),
                x="Estimated CO₂e (kg)", y="Dish Name", palette="Reds_r", ax=ax1)
    ax1.set_title("CO₂e Footprint per Dish")
    chart1_path = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
    fig1.tight_layout()
    fig1.savefig(chart1_path)
    plt.close(fig1)

    # --- Chart 2: Top Dishes by Margin ---
    fig2, ax2 = plt.subplots(figsize=(6, 4))
    sns.barplot(data=df.sort_values("Margin (%)", ascending=False),
                x="Margin (%)", y="Dish Name", palette="Greens_r", ax=ax2)
    ax2.set_title("Top Dishes by Margin")
    chart2_path = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
    fig2.tight_layout()
    fig2.savefig(chart2_path)
    plt.close(fig2)

    # Insert both charts side by side
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(90, 6, to_latin1("CO₂e per Dish"), ln=0)
    pdf.cell(90, 6, to_latin1("Top Dishes by Margin"), ln=1)

    y = pdf.get_y()
    pdf.image(chart1_path, x=10, y=y, w=90)
    pdf.image(chart2_path, x=110, y=y, w=90)
    pdf.ln(60)

    # Cleanup temp chart files
    os.remove(chart1_path)
    os.remove(chart2_path)

    # Save to temporary file
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(tmp_file.name)
    return tmp_file.name

# --- Load Dish File ---
if dish_file:
    df = pd.read_excel(dish_file)
    st.success("✅ Dish file loaded")
    st.write("Preview:", df.head())

    # --- Processing ---
    def estimate(row):
        total_emission = 0.0
        total_cost = 0.0
        for i in range(1, 4):
                ing = row.get(f"Ingredient {i}")
                qty = row.get(f"Qty {i} (g)")
                cost_per_g = row.get(f"Cost per g {i} (€)")
                if pd.notna(ing) and pd.notna(qty):
                    # CO₂ lookup
                    co2 = carbon_data.get(ing.strip(), 0)
                    total_emission += (qty / 1000) * co2
                    # Cost fallback
                    if pd.isna(cost_per_g) and ing.strip() in ingredient_price_map:
                        cost_per_g = ingredient_price_map[ing.strip()]
                    if pd.notna(cost_per_g):
                        total_cost += qty * cost_per_g
        return round(total_emission, 2), round(total_cost, 2)

    results = df.apply(estimate, axis=1)
    df["Estimated CO₂e (kg)"] = results.apply(lambda x: x[0])
    df["Total Cost (€)"] = results.apply(lambda x: x[1])
    df["Margin (%)"] = ((df["Selling Price (€)"] - df["Total Cost (€)"]) / df["Selling Price (€)"] * 100).round(2)
    df["Profit (€)"] = (df["Selling Price (€)"] - df["Total Cost (€)"]).round(2)
    df["CO₂e per € profit"] = (df["Estimated CO₂e (kg)"] / df["Profit (€)"]).round(2)
    df["Flag"] = ""
    df.loc[df["Margin (%)"] < 60, "Flag"] += "⚠️ Low margin  "
    df.loc[df["Estimated CO₂e (kg)"] > 3, "Flag"] += "🌍 High CO₂"

    # --- Show Results Table ---
    st.markdown('<h2 class="sub-header">📊 Dish Summary with Flags</h2>', unsafe_allow_html=True)
    
    # Create a card-style container for results
    st.markdown('<div class="card-style">', unsafe_allow_html=True)
    st.dataframe(df[["Dish Name", "Selling Price (€)", "Total Cost (€)", "Margin (%)", "Estimated CO₂e (kg)", "Flag"]], use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- Charts ---
    sns.set(style="whitegrid")
    
    st.markdown('<h2 class="sub-header">📈 Analysis Charts</h2>', unsafe_allow_html=True)

    # Margin Chart
    st.markdown('<div class="card-style">', unsafe_allow_html=True)
    fig1, ax1 = plt.subplots(figsize=(10, 6))
    sns.barplot(data=df.sort_values("Margin (%)", ascending=False), x="Margin (%)", y="Dish Name", ax=ax1, palette="Greens_r")
    ax1.set_title("Top Dishes by Margin", fontsize=16, fontweight=600, pad=20)
    ax1.set_xlabel("Margin (%)", fontsize=12, fontweight=500)
    ax1.set_ylabel("Dish Name", fontsize=12, fontweight=500)
    plt.tight_layout()
    st.pyplot(fig1)
    st.markdown('</div>', unsafe_allow_html=True)

    # Profit Contribution Pie
    st.markdown('<div class="card-style">', unsafe_allow_html=True)
    fig2, ax2 = plt.subplots(figsize=(8, 8))
    ax2.pie(df["Profit (€)"], labels=df["Dish Name"], autopct='%1.1f%%', startangle=140, textprops={'fontsize': 10})
    ax2.set_title("Dish Contribution to Total Profit", fontsize=16, fontweight=600, pad=20)
    plt.tight_layout()
    st.pyplot(fig2)
    st.markdown('</div>', unsafe_allow_html=True)

    # Carbon Impact Chart
    st.markdown('<div class="card-style">', unsafe_allow_html=True)
    fig3, ax3 = plt.subplots(figsize=(10, 6))
    sns.barplot(data=df.sort_values("Estimated CO₂e (kg)", ascending=False), x="Estimated CO₂e (kg)", y="Dish Name", ax=ax3, palette="Reds_r")
    ax3.set_title("CO₂e Footprint per Dish", fontsize=16, fontweight=600, pad=20)
    ax3.set_xlabel("CO₂e (kg)", fontsize=12, fontweight=500)
    ax3.set_ylabel("Dish Name", fontsize=12, fontweight=500)
    plt.tight_layout()
    st.pyplot(fig3)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- Download Excel ---
    st.markdown('<h2 class="sub-header">📥 Download Reports</h2>', unsafe_allow_html=True)
    
    st.markdown('<div class="card-style">', unsafe_allow_html=True)
    
    def to_excel(dataframe):
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            dataframe.to_excel(writer, index=False, sheet_name='Dish Analysis')
        return output.getvalue()

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="📥 Download Full Excel Report",
            data=to_excel(df),
            file_name="Clove_Dish_Analysis.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    
    with col2:
        if st.button("📄 Generate PDF Report", use_container_width=True):
            pdf_path = generate_pdf(df)
            with open(pdf_path, "rb") as f:
                st.download_button(
                    label="📥 Download PDF",
                    data=f,
                    file_name="Clove_Dish_Report.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
    
    st.markdown('</div>', unsafe_allow_html=True)

    # --- Booking CTA ---
    st.markdown('<div class="card-style" style="background: linear-gradient(135deg, rgba(169, 223, 191, 0.1), rgba(169, 223, 191, 0.05)); border: 1px solid rgba(169, 223, 191, 0.3);">', unsafe_allow_html=True)
    st.markdown('<h3 style="color: #A9DFBF; margin-bottom: 1rem;">💬 Need help interpreting your results?</h3>', unsafe_allow_html=True)
    st.markdown('<p class="body-text">Book a consultation to dive deeper into your analysis and optimize your menu profitability.</p>', unsafe_allow_html=True)
    st.markdown('<a href="https://your-calendly-link.com" target="_blank" style="background: #A9DFBF; color: #111111; padding: 0.75rem 1.5rem; text-decoration: none; border-radius: 8px; font-weight: 600; display: inline-block; margin-top: 1rem;">📅 Book Consultation</a>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- New Visuals Section ---
    st.markdown('<h2 class="sub-header">📍 Advanced Visuals</h2>', unsafe_allow_html=True)

    # 1. Cost vs CO₂e Scatterplot
    st.markdown('<div class="card-style">', unsafe_allow_html=True)
    fig, ax = plt.subplots(figsize=(10, 7))

    sns.scatterplot(
        data=df,
        x="Total Cost (€)",
        y="Estimated CO₂e (kg)",
        hue="Dish Name",
        s=150,
        alpha=0.85,
        edgecolor="black",
        linewidth=0.8,
        ax=ax
    )

    # Crosshair lines for reference
    avg_cost = df["Total Cost (€)"].mean()
    avg_co2 = df["Estimated CO₂e (kg)"].mean()
    ax.axhline(avg_co2, color='grey', linestyle='--', lw=0.7)
    ax.axvline(avg_cost, color='grey', linestyle='--', lw=0.7)

    # Annotate top-right quadrant (high cost + high CO₂)
    ax.text(avg_cost + 0.2, avg_co2 + 0.2, "⚠️ High Impact", fontsize=10, color='red')

    ax.set_title("Cost vs CO₂e per Dish", fontsize=16, fontweight=600, pad=20)
    ax.set_xlabel("Total Cost (€)", fontsize=12, fontweight=500)
    ax.set_ylabel("Estimated CO₂e (kg)", fontsize=12, fontweight=500)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    plt.tight_layout()
    st.pyplot(fig)
    st.markdown('</div>', unsafe_allow_html=True)

    # 2. Profit per Dish (€)
    st.markdown('<div class="card-style">', unsafe_allow_html=True)
    fig5, ax5 = plt.subplots(figsize=(8, 5))
    sns.barplot(data=df.sort_values("Profit (€)", ascending=True), x="Profit (€)", y="Dish Name", palette="Blues_d", ax=ax5)
    ax5.set_title("Profit per Dish (€)", fontsize=16, fontweight=600, pad=20)
    ax5.set_xlabel("Profit (€)", fontsize=12, fontweight=500)
    ax5.set_ylabel("Dish Name", fontsize=12, fontweight=500)
    plt.tight_layout()
    st.pyplot(fig5)
    st.markdown('</div>', unsafe_allow_html=True)

    # 3. CO₂e per € Profit
    st.markdown('<div class="card-style">', unsafe_allow_html=True)
    fig6, ax6 = plt.subplots(figsize=(8, 5))
    sns.barplot(data=df.sort_values("CO₂e per € profit", ascending=False), x="CO₂e per € profit", y="Dish Name", palette="Oranges_r", ax=ax6)
    ax6.set_title("CO₂e per € Profit", fontsize=16, fontweight=600, pad=20)
    ax6.set_xlabel("CO₂e per € Profit", fontsize=12, fontweight=500)
    ax6.set_ylabel("Dish Name", fontsize=12, fontweight=500)
    plt.tight_layout()
    st.pyplot(fig6)
    st.markdown('</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="card-style" style="background: rgba(255, 193, 7, 0.1); border: 1px solid rgba(255, 193, 7, 0.3);">', unsafe_allow_html=True)
    st.warning("📁 Upload an Excel file to begin your analysis. You can use the template below if needed.")
    st.markdown('<a href="Clove_Dish_Template_Extended.xlsx" download style="background: #A9DFBF; color: #111111; padding: 0.75rem 1.5rem; text-decoration: none; border-radius: 8px; font-weight: 600; display: inline-block; margin-top: 1rem;">📄 Download Template</a>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
