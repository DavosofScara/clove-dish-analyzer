# Clove Dish Analyzer

A Streamlit web application for analyzing food & beverage dishes for profitability and carbon footprint analysis.

## Features

- 📊 Dish profitability analysis with margin calculations
- 🌍 Carbon footprint estimation per dish
- 💰 Ingredient cost tracking
- 📈 Interactive charts and visualizations
- 📄 PDF report generation
- 📥 Excel export functionality

## Quick Deploy to Streamlit Cloud

1. **Fork/Clone this repository to your GitHub account**

2. **Deploy to Streamlit Cloud**:
   - Go to [share.streamlit.io](https://share.streamlit.io)
   - Sign in with GitHub
   - Click "New app"
   - Select your repository
   - Set the path to: `clove_dish_analyzer.py`
   - Click "Deploy!"

3. **Your app will be live at**: `https://your-app-name.streamlit.app`

## Embed in Your Website

Once deployed, you can embed the app in your website using an iframe:

```html
<iframe 
  src="https://your-streamlit-app-url.streamlit.app" 
  width="100%" 
  height="800px" 
  frameborder="0"
  style="border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
</iframe>
```

## Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the app:
   ```bash
   streamlit run clove_dish_analyzer.py
   ```

## File Structure

- `clove_dish_analyzer.py` - Main Streamlit application
- `Clove_Dish_Template_Extended.xlsx` - Template for dish data
- `Clove_Ingredient_Prices.xlsx` - Ingredient price reference
- `.streamlit/config.toml` - Streamlit configuration and theming 