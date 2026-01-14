import streamlit as st
import pandas as pd
import altair as alt
from eurostat import get_data_df
import json

##########################################################
#           HELPER FUNCTIONS
##########################################################

europe_url = "https://raw.githubusercontent.com/leakyMirror/map-of-europe/master/GeoJSON/europe.geojson"
europe_geo = alt.Data(url=europe_url, format=alt.DataFormat(property='features', type='json'))

code_to_country = {
    'BE': 'Belgium', 'BG': 'Bulgaria', 'CZ': 'Czechia',
    'DK': 'Denmark', 'DE': 'Germany', 'EE': 'Estonia',
    'IE': 'Ireland', 'GR': 'Greece', 'ES': 'Spain',
    'FR': 'France', 'HR': 'Croatia', 'IT': 'Italy',
    'CY': 'Cyprus', 'LV': 'Latvia', 'LT': 'Lithuania',
    'LU': 'Luxembourg', 'HU': 'Hungary', 'MT': 'Malta',
    'NL': 'Netherlands', 'AT': 'Austria', 'PL': 'Poland',
    'PT': 'Portugal', 'RO': 'Romania', 'SI': 'Slovenia',
    'SK': 'Slovakia', 'FI': 'Finland', 'SE': 'Sweden',
    'IS': 'Iceland', 'NO': 'Norway', 'CH': 'Switzerland',
    'GB': 'United Kingdom', 'BA': 'Bosnia and Herzegovina', 'ME': 'Montenegro',
    'MK': 'North Macedonia', 'RS': 'Serbia', 'TR': 'Türkiye'
}

# download data from Eurostat 
@st.cache_data(ttl=1000)
def download_data():
    df = get_data_df('tps00071')
    if df is None:
        st.error("Couldn't load Eurostat data right now.")
        raise RuntimeError("Eurostat returned no data")
    df = df.drop(columns=['freq', 'isco08', 'wstatus', 'worktime', 'age', 'unit', 'sex'])
    df.rename(columns = {'geo\TIME_PERIOD': 'ISO2'}, inplace=True)
    return df


# Read data offline (in case Eurostat fails)
@st.cache_data(ttl=1000)
def read_data(path='data/hours_worked.xlsx'):
    df = pd.read_excel(path, sheet_name='Sheet 1', skiprows=16, skipfooter=3, header=None, na_values=":")
    df.columns = ['country', '2015', '2016', '2017', '2018', '2019', '2020', '2021', '2022', '2023', '2024']
    return df


# map countries
def rename_countries(df, data_local=False):
    if not data_local:
        df['country'] = df['ISO2'].map(code_to_country)
        df = df.dropna(subset=['country'])
    else:
        # reverse the dictionary mapping
        new_dict = {}
        for k, v in code_to_country.items():
            new_dict[v] = k
        df['ISO2'] = df['country'].map(new_dict)
    return df


# wide to long data
@st.cache_data(ttl=100)
def pivot_data(df: pd.DataFrame) -> pd.DataFrame:
    df_long = pd.melt(df, id_vars=['country', 'ISO2'],
                      var_name='year',
                      value_name='hours')

    df_long['year'] = df_long['year'].astype(int)
    return df_long

# return the clicked country in the map
def extract_selected_country(event, selection_name='country_click'):
    sel = (event or {}).get("selection", {}).get(selection_name)
    # case 1: list of records
    if isinstance(sel, list) and sel:
        return sel[0].get('country')
    # case 2: dictionary 
    elif isinstance(sel, dict):
        if "country" in sel:
            v = sel['country']
            return v[0] if isinstance(v, list) and v else v
        if "values" in sel and sel['values']:
            return sel['values'][0].get("country")
    return None

# ------------------------------ UI components --------------------

# Create a map with the annual data
bins = [10, 20, 30, 35, 40, 45, 60]
labels = ["10-20", "21-30", "31-35", "36-40", "41-45", "46-60"]
bin_colors = ['#fef0d9', '#fdd49e', '#fdbb84', '#fc8d59', '#e34a33', '#b30000']

no_data_color = "#d9d9d9" # gray for no data
color_domain = ['No data'] + labels
color_range = [no_data_color] + bin_colors

color_scale= alt.Scale(domain = color_domain, range=color_range)

def test():
    map_chart = (
        alt.Chart(europe_geo)
        .mark_geoshape(stroke='black', strokeWidth=0.3)
    )
    return map_chart    

# Show a map
def plot_map_value(df, year):
    source_data = df.loc[df['year'] == year, ['ISO2', 'country', 'hours', 'year']]
    source_data = source_data.copy()
    source_data['hours_bin'] = pd.cut(
        source_data['hours'],
        bins=bins,
        labels=labels,
        include_lowest=True,
        right=True
    )
    
    # click selection
    country_click = alt.selection_point(name='country_click', fields=['country'], on='click', empty='none')  # type: ignore
    
    map_chart = (
        alt.Chart(europe_geo)
        .mark_geoshape(stroke='black')
        .transform_lookup(
            lookup='properties.ISO2',
            from_=alt.LookupData(source_data, 'ISO2', ['hours', 'hours_bin', 'country', 'year'])
        )
        .transform_calculate(
            hours_bin_display="isValid(datum.hours_bin) ? datum.hours_bin : 'No data'"
        )
        .encode(
            color=alt.Color(
                'hours_bin_display:N',
                legend=alt.Legend(
                    title='Hours/week (bins)',
                    symbolType='square',
                    symbolStrokeWidth=0.1,
                    symbolSize=250,
                    labelFontSize=12,
                    titleFontSize=13
                ),
                # Put No Data first in the legend
                sort=color_domain,
                scale=color_scale
            ),
            tooltip=[
                alt.Tooltip('country:N'),
                alt.Tooltip('hours:Q'),
                alt.Tooltip('year:O'),
                alt.Tooltip('hours_bin_display:N', title='Class')
            ],
            opacity=alt.condition(country_click, alt.value(1), alt.value(0.6))  # visual feedback for selection
        )
        .add_params(country_click)
        .project(
            type='transverseMercator',
            rotate=[-10, -52, 0]
        )
        .properties(
            width=700,
            height=500,
            title=f'Average weekly hours worked in Europe in {str(year)}. Click on a country to see more data',
        )
    )
    
    event = st.altair_chart(map_chart, key='eu_map', on_select='rerun')
    selected_country = extract_selected_country(event, "country_click")
    return selected_country

# plot annual evolution
def show_history(df:pd.DataFrame, country:str):
    data_source = df.loc[df['country'] == country]
    fig = alt.Chart(data_source, title=f'Annual average of worked weekly hours in {country} ').mark_bar().encode(
        x = alt.X('year:O', title='year'),
        y = alt.Y('hours:Q', title='hours/week')
    ).interactive()
    return st.altair_chart(fig)


# create a barplot
def bar_plot(df_long: pd.DataFrame, year: int):
    df = df_long.loc[df_long['year'] == year].sort_values(by=['hours'])
    fig = alt.Chart(df, title=f'Average worked hours per week in {year}').mark_bar().encode(
        x=alt.X('hours:Q', title='hours/week'),
        y=alt.Y('country:N', title='country')
    )
    return st.altair_chart(fig, width='stretch')


##########################################################
#           LAYOUT DEFINITION 
##########################################################
def main():
    st.set_page_config(page_title='Average worked hours in EU', 
                       layout='wide',
                       initial_sidebar_state='expanded')
    st.title("Average usual weekly hours worked in the main job in EU")
    st.subheader('Annual data (copyright: Eurostat)')
    
    st.write("""Corresponds to the number of hours the person normally works. 
                 Covers all hours including extra hours, both paid and unpaid. 
                 Excludes the travel time between the home and the place of work as well as the main meal breaks (definition from Eurostat).""")
    url = 'https://ec.europa.eu/eurostat/cache/metadata/en/lfsa_esms.htm'
    st.markdown('Please check this [url](%s) for more information.' %url)
    col1, col2 = st.columns(2)
    used_fallback = False
    
    try:
        df = download_data()
        df = rename_countries(df)
    except Exception:
        used_fallback = True
        df = read_data()
        df = rename_countries(df, data_local=True)
        
    if used_fallback:
        st.warning("Eurostat is offline — using local cached Excel data.")

    df_long = pivot_data(df)
    
    with col1:
        years = sorted(df_long["year"].unique())
        year_selected = st.selectbox("Year", years, index=len(years)-1, key = 'year') or 2024
        bar_plot(df_long, year_selected)
        
    with col2:
        test()
        clicked_country = plot_map_value(df_long, year_selected)
        # fallback to France untill user clicks on a selection
        country_to_show = clicked_country or "France"
        st.divider(width='stretch')
        show_history(df_long, country_to_show) # type: ignore

    st.markdown('In 2024, Türkiye had the highest average weekly working hours at 44.2, while the Netherlands ranked lowest with roughly 31.6 hours.')

if __name__ == "__main__":
    main()

