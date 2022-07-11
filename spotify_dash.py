from logging import PlaceHolder
from sqlite3.dbapi2 import connect
from _plotly_utils.importers import relative_import
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import sqlite3
import requests
import datetime
import plotly.express as px
from requests.sessions import default_headers
from spotipy import cache_handler
import sqlalchemy
from dataclasses import dataclass
import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import spotipy.util as util
import time
from statistics import multimode
from pytz import utc, timezone
import streamlit as st
from streamlit.type_util import is_namedtuple
from dateutil.relativedelta import relativedelta
#import bar_chart_race as bcr

#----------------------------------------- TO ADD ------------------------------------------------------#
# make variable that gets current df len. call it start_len then every 120 min check len and store in variable
# called new_len if new_len > start_len +40 then initialize start_len = new_len and refresh df/rerun page so appends
# new songs to df


#------------------------------------------------------------------------------------------------------------------#


#----------------------------------------- TAB LAYOUT ------------------------------------------------------#
st.set_page_config(page_title='SpotifyInReview', page_icon='🎧',
layout="wide", initial_sidebar_state="auto")
#------------------------------------------------------------------------------------------------------------------#

# IF YOU WANT HISTORICAL DATA PREDATING THE BEGINNING OF YOUR USE OF THIS APP WHICH IS CREATED AND APPENDED
# TO ONCE THE FIRST API HIT IS RECEIVED THEN GET THAT DATA HERE: https://www.spotify.com/ca-en/account/privacy/

#---------------------------------- CODE TO CREATE A JPEG BACKGROUND --------------------------------------------#
#code from https://discuss.streamlit.io/t/how-do-i-use-a-background-image-on-streamlit/5067/6
import base64

@st.cache(allow_output_mutation=True)
def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

def set_png_as_page_bg(png_file):
    bin_str = get_base64_of_bin_file(png_file)
    page_bg_img = '''
    <style>
    .stApp {
    background-image: url("data:image/png;base64,%s");
    background-repeat: no-repeat;
    background-attachment: scroll;  
    height: auto; width: auto;
    background-size: contain;
    background-position: center center;
    /*background-size: cover;*/
    }
    </style>
    ''' % bin_str
    
    st.markdown(page_bg_img, unsafe_allow_html=True)
    return

#set_png_as_page_bg('/Users/tmarianchuk/Downloads/background.png')

#----------------------------------- LOAD IN DATA FROM SPOTIPY API ------------------------------------------------#
def connect_to_api(userid):
    # set constant needed to access api
    #USER_ID = '12150191372'
    TOKEN = util.prompt_for_user_token(USER_ID,'user-read-recently-played')

    # create client connection to api/ store in .bash_profile, get from spotify developers page
    auth_manager = SpotifyClientCredentials()
    sp = spotipy.client.Spotify(auth=TOKEN,auth_manager=auth_manager)
    
    # define timeframe from which we want to extract data from api
    today = datetime.datetime.now()
    yesterday = today - datetime.timedelta(days=1)
    yesterday_unix_timestamp = int(yesterday.timestamp())*1000
    
    # get json data from api
    played_past_24_hrs = sp.current_user_recently_played(limit=50, after=yesterday_unix_timestamp, before=None)
    return(played_past_24_hrs)


def create_song_df(json_file):
    # create array to hold df column values
    song_names = []
    artist_names = []
    played_at_times = []
    timestamps = []
    
    for song in json_file['items']:
        song_names.append(song['track']['name'])
        artist_names.append(song['track']['album']['artists'][0]['name'])
        played_at_times.append(song['played_at'])
        timestamps.append(song['played_at'][0:10])
        
    song_dict={
            "song_name" : song_names,
            "artist_name" : artist_names,
            "played_at" : played_at_times,
            "timestamp" : timestamps
            }
    
    song_df = pd.DataFrame(song_dict, columns=['song_name','artist_name','played_at','timestamp'])
    return(song_df)

def check_if_data_valid(df: pd.DataFrame) -> bool:
    # check if data frame is empty
    if df.empty:
        print('no songs found. finishing execution...')
        return False
    
    # identify your primary key (unique identifier). primary key constraints ensure no duplicate rows in df
    if pd.Series(df['played_at']).is_unique:
        pass
    else:
        raise Exception('primary key check is violated')
        
    # checking for nulls
    if df.isnull().values.any():
        nulls = df.isnull().sum()
        raise Exception('there are {} null value(s) found'.format(nulls))
        
    # only want data from the past 24 hours
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    yesterday = yesterday.replace(hour=0,minute=0,second=0,microsecond=0)
    timestamps = df['timestamp'].tolist()
    for timestamp in timestamps:
        if datetime.datetime.strptime(timestamp, '%Y-%m-%d') < yesterday:
            raise Exception('one or more songs listened to over 24 hours ago')
    return True

#DATABASE_LOC = "sqlite:///my_played_tracks"
def load_to_database():
    # create database
    engine = sqlalchemy.create_engine(DATABASE_LOC)
    # initiate connection to database
    conn = sqlite3.connect('my_played_tracks.sqlite')
    # create cursor to interact with database
    cursor = conn.cursor()
    
    sql_query="""
    CREATE TABLE IF NOT EXISTS my_played_tracks(
        song_name VARCHAR(200),
        artist_name VARCHAR(200),
        played_at VARCHAR(200),
        timestamp VARCHAR(200),
        CONSTRAINT primary_key_constraint PRIMARY KEY (played_at)
    )
    """
    
    cursor.execute(sql_query)
    print('opened database successfully')
    
    try:
        song_df.to_sql('my_played_tracks',engine,index=False,if_exists='append')#'replace')#'append')
    except:
        print('data already exists')
        
    conn.close()
    print('closed database connection successfully')

#------------------------------------------------------------------------------------------------------------------#
# FUNC TO CONVERT UTC TO LOCAL TIME TAKEN FROM https://stackoverflow.com/questions/4770297/convert-utc-datetime-string-to-local-datetime #
def utc2local(utc):
    epoch = time.mktime(utc.timetuple())
    offset = datetime.datetime.fromtimestamp(epoch) - datetime.datetime.utcfromtimestamp(epoch)
    return(utc + offset)

#----------------------------------- CONNECT BACK TO DB AND EXTRACT AS DF -----------------------------------------#
def connect_back(query):
    df = pd.read_sql(query, DATABASE_LOC)
    return(df)

#-------------------------------------- FUNCS CREATING PLOTS ------------------------------------------#
def pie_chart(df:pd.DataFrame):
    artist_count_df = df.groupby(['artist_name','song_name']).count()
    fig = px.pie(artist_count_df, values='played_at', names=artist_count_df.index.get_level_values(0),
                 title='artist breakdown', labels={'label':'artist', 'played_at':'song counts'},
                 color_discrete_sequence=px.colors.sequential.Viridis)
    fig.update_layout(legend={'font_size':20}, title={'font_size':25}, hoverlabel={'font_size':16})
    fig.update_traces(textposition='inside', textinfo='percent', textfont_size=20)#+label')
    st.plotly_chart(fig, use_container_width=True)

def timeseries_hist(df:pd.DataFrame): #nov 7th is messed up because my sql query did not account for daylight savings
    df.set_index('played_at', inplace=True)
    song_counts = df.song_name.resample('s').count()
    time_component_count = pd.DataFrame({'time': song_counts.index, 'song_count': song_counts.values})
    #st.write(time_component_count[time_component_count.song_count == 1])
    fig = px.histogram(time_component_count, x='time', y='song_count', histfunc='sum', color_discrete_sequence=['cyan'],
                       title='active listening time')
    fig.update_layout(title={'font_size':25}, 
                      hoverlabel={'font_size':16,'bgcolor':'white'},
                      yaxis={'title':'song count'})
    # below 3 lines allows me to make hist go from midnight of day input to midnight next day
    tz = timezone('America/Chicago')
    midnight_wo_tzinfo = datetime.datetime.combine(df.date.min(), datetime.time())
    midnight_w_tzinfo = utc2local(tz.localize(midnight_wo_tzinfo).astimezone(utc))#tz.localize(midnight_wo_tzinfo).astimezone(tz)
    fig.update_xaxes(title_font={'size':18},
                     range=[midnight_w_tzinfo,midnight_w_tzinfo + datetime.timedelta(days=1)])
    #st.write(midnight_w_tzinfo,midnight_w_tzinfo + datetime.timedelta(days=1))
    fig.update_yaxes(title_font={'size':18})
    fig.update_traces(hovertemplate='Time: %{x} <br>Song Count: %{y}',
                      xbins=dict( # bins used for histogram
                                start=midnight_w_tzinfo,
                                end=midnight_w_tzinfo + datetime.timedelta(days=1),
                                size= 1800000)) #size value is in milliseconds so this set 30 min bin interval
    st.plotly_chart(fig, use_container_width=True) 

def find_mode(df:pd.DataFrame, col:int):
    if len(multimode(df.iloc[:,col])) == 1:
        mode = multimode(df.iloc[:,col])[0]
        st.metric(label=f"{df.iloc[:,col].name.split('_', 1)[0].capitalize()} of the day",value=mode)
    elif len(multimode(df.iloc[:,col])) == len(df.iloc[:,1]):
        st.metric(label=f"{df.iloc[:,col].name.split('_', 1)[0].capitalize()} of the Day", value='No repeats today!')
    else:# len(multimode(df.iloc[:,col])) > 1:
        modes = multimode(df.iloc[:,col])
        modes_str = ", ".join(multimode(modes))
        st.metric(label=f"{df.iloc[:,col].name.split('_', 1)[0].capitalize()}s of the day",value=modes_str)
#------------------------------------------ PAGE  LAYOUT ----------------------------------------------------------#
USER_ID = st.sidebar.text_input('11 digit USER ID here','12150191372',max_chars=11)
#st.write(USER_ID)
option = st.sidebar.selectbox('Choose a page',('Dailies','Monthlies','Year wrapped'))

DATABASE_LOC = "sqlite:///my_played_tracks"
sql_query = '''SELECT DISTINCT(played_at), song_name, artist_name 
                FROM my_played_tracks mpt ORDER BY 1 DESC'''

if __name__ == "__main__":
        # connect to api
        played_past_24hr = connect_to_api(USER_ID)
        
        # extract
        song_df = create_song_df(played_past_24hr)
        
        # transform
        if check_if_data_valid(song_df):
            print('data valid, proceed to load stage')
            
        # load
        load_to_database()

        # connect back to database to extract as df
        df = connect_back(sql_query)

if option == 'Dailies':
    today = datetime.date.today() 
    #tmw = datetime.date.today() + datetime.timedelta(days=1)
    d = st.date_input("Choose a date", today )
    #st.write(d)
    st.title("My Spotify stats for {}".format(d.strftime("%B %d, %Y")))#format(TODAY.strftime("%B %d, %Y")))
    title_alignment= """<style>#the-title {text-align: center}</style>"""
    st.markdown(title_alignment, unsafe_allow_html=True)
    
    pie, hist = st.columns(2)
    #----------------------- DF MANIPULATION. REFORMATTING TIME COMPONENTS -----------------------------------#
    df['played_at'] = pd.to_datetime(df.played_at)
    df['played_at'] = [utc2local(df.played_at[x]) for x in range(len(df.played_at))] #convert UTC to local #[df.played_at[x].astimezone(timezone('America/Chicago')) for x in range(len(df.played_at))]#
    df['date'] = df['played_at'].dt.date
    # creating the daily df from the full df
    dt_input_reformatted = datetime.datetime.strptime(d.strftime("%Y-%m-%d"),"%Y-%m-%d").date()
    df_daily = df[df.date == dt_input_reformatted].copy()
    #----------------------------------------------------------------------------------------------------------#
    
    #-------------------- CREATING DF CONTAINING INFO FROM JUST THE USER SPECIFIED DATE ---------------------#
    #if d < df.date.min():
    #    st.write('# I don\'t have any data for this day, sorry!')
    try:
        if d < df.date.min():
            st.write('# I don\'t have any data for this day, sorry!')
        elif (d <= datetime.date.today()) and (d >= df.date.min()):
            #st.write(df.date.min(),d,datetime.date.today())
            if df_daily.empty:
                st.write('# You didn\'t listen to anything on this day...not by my count anyways!')
            else:
                with pie:
                    pie_chart(df_daily)#(artist_count_df)

                with hist:
                    timeseries_hist(df_daily)#(time_component_count)

                col1, col2, col3= st.columns([4,2,1])
                with col1:
                    find_mode(df_daily,0)
                with col2:
                    find_mode(df_daily,1)
                #with col3:
                #    st.metric(label="Minutes listened",value=f"{14} min")
                with col3:
                    tot_songs=df_daily.song_name.count()
                    st.metric(label="Total Songs",value=f"{tot_songs} songs") #write if statement so that if 1 song instead of songs
        else:
                st.write('# I can\'t see the future...can you?') #this one writes to page
    except:
        st.write('# I can\'t see the future...can you?') #this one doesn't write out cause u don't know how to use exception
#------------------------------------------------------------------------------------------------------------------#

#-------------------- CREATED A SECOND SQL DATABASE THAT INCLUDE MORE INFO BUT -------------------------------------#
#-------------------- IS NOT SIZE COMPATIBLE WITH DB1 SO KEEPING BOTH FOR NOW --------------------------------------#
spotify = spotipy.Spotify(auth_manager=SpotifyClientCredentials())

#@st.cache(allow_output_mutation=True)
def load_data_v2_from_api(userid,database_loc):
    TOKEN = util.prompt_for_user_token(userid,'user-read-recently-played')

    # create client connection to api
    auth_manager = SpotifyClientCredentials()
    sp = spotipy.client.Spotify(auth=TOKEN,auth_manager=auth_manager)
    
    # define timeframe from which we want to extract data from api
    today = datetime.datetime.now()
    yesterday = today - datetime.timedelta(days=1)
    yesterday_unix_timestamp = int(yesterday.timestamp())*1000
    
    # get json data from api
    played_past_24_hrs = sp.current_user_recently_played(limit=50, after=yesterday_unix_timestamp, before=None)

    # create array to hold df column values
    song_names = []
    artist_names = []
    artist_uris = []
    album_names = []
    album_uris = []
    played_at_times = []
    timestamps = []
    durations_in_secs = []
    
    for song in played_past_24_hrs['items']:
        song_names.append(song['track']['name'])
        artist_names.append(song['track']['album']['artists'][0]['name'])
        artist_uris.append(song['track']['album']['artists'][0]['uri'])
        album_names.append(song['track']['album']['name'])
        album_uris.append(song['track']['album']['uri'])
        played_at_times.append(song['played_at'])
        timestamps.append(song['played_at'][0:10])
        durations_in_secs.append(song['track']['duration_ms']/1000)
        
    song_dict={
            "song_name" : song_names,
            "artist_name" : artist_names,
            "artist_uri" : artist_uris,
            "album_name" : album_names,
            "album_uri" : album_uris,
            "played_at" : played_at_times,
            "timestamp" : timestamps,
            "duration_s" : durations_in_secs
            }
    
    song_df = pd.DataFrame(song_dict, columns=['song_name','artist_name','artist_uri','album_name','album_uri','played_at','timestamp','duration_s'])

    # create database
    engine = sqlalchemy.create_engine(database_loc)
    # initiate connection to database
    conn = sqlite3.connect('my_played_tracks_v2.sqlite')
    # create cursor to interact with database
    cursor = conn.cursor()
    
    sql_query="""
    CREATE TABLE IF NOT EXISTS my_played_tracks_v2(
        song_name VARCHAR(200),
        artist_name VARCHAR(200),
        artist_uri VARCHAR(200),
        album_name VARCHAR(200),
        album_uri VARVHAR(200),
        played_at VARCHAR(200),
        timestamp VARCHAR(200),
        duration_s VARCHAR(200),
        CONSTRAINT primary_key_constraint PRIMARY KEY (played_at)
    )
    """
    
    cursor.execute(sql_query)
    print('opened database successfully')
    
    try:
        song_df.to_sql('my_played_tracks_v2',engine,index=False,if_exists='append')#'replace')#
    except:
        print('data already exists')
        
    conn.close()
    print('closed database connection successfully')
#------------------------------------------------------------------------------------------------------------------#


#---------------------------- CREATE DF VERSION 2 AND MONTHLIES DF SUBSETS -----------------------------------------#
DATABASE_LOC = "sqlite:///my_played_tracks_v2"
load_data_v2_from_api(USER_ID,DATABASE_LOC)
sql_query = '''SELECT DISTINCT(played_at) as played_at, song_name, artist_name, artist_uri, album_name, album_uri, duration_s 
            FROM my_played_tracks_v2 mpt ORDER BY 1 DESC'''

# connect back to database to extract as df
df_v2 = connect_back(sql_query) 

def secs_2_hr_min(secs):
    hours = secs // 3600 #the floor division // rounds the result down to the nearest whole number
    minutes = secs // 60 - hours * 60
    hr_min_str = "%d hr. %02d min." % (hours, minutes)
    return(hr_min_str)

def monthly_subset(df:pd.DataFrame,mo:str,yr:str):
    tmp = pd.to_datetime(df.played_at)
    df['month'] = tmp.dt.date.apply(lambda x: x.strftime('%b').lower())
    df['year'] = tmp.dt.date.apply(lambda x: x.strftime('%Y'))
    df_monthly = df[(df.month == mo) & (df.year == yr)].copy()
    return(df_monthly)

def artist_podium(df:pd.DataFrame):
    top3_df = df.groupby('artist_name').count().sort_values('played_at',ascending=False)[:3].reset_index().rename(columns={'played_at':'song_counts'}).iloc[['1','0','2']]
    mx = top3_df.song_counts.max()
    top3_artists = list(top3_df.artist_name)
    uris = list((df[df.artist_name == top3_artists[0]].artist_uri.iloc[0],
                df[df.artist_name == top3_artists[1]].artist_uri.iloc[0],
                df[df.artist_name == top3_artists[2]].artist_uri.iloc[0]))
    sources = [spotify.artist(uris[0])['images'][0]['url'],
               spotify.artist(uris[1])['images'][0]['url'],
               spotify.artist(uris[2])['images'][0]['url']]
    xpos = [0.15,0.5,0.85]
    ypos = [top3_df.song_counts.iloc[0]/mx,
            top3_df.song_counts.iloc[1]/mx,
            top3_df.song_counts.iloc[2]/mx]
    fig = px.bar(top3_df,x='artist_name', y='song_counts',text='song_counts',
                title='The Artist Podium')
    colors = ['rgb(192,192,192)', #silver
              'rgb(212,175,55)', #gold
              'rgb(207,127,50)'] #bronze
    fig.update_traces(marker=dict(color=colors,
                                  line=dict(width=2,
                                            color='black'),
                                  opacity=0.75))
    fig.update_layout(bargap=0,plot_bgcolor='rgba(0,0,0,0)',
                      yaxis={'visible':False,'showgrid':False},
                      xaxis={'visible':False,'showgrid':True},
                      title={'font_size':30,
                             'y':0.1,
                             'x':0.5,
                             'xanchor': 'center',
                             'yanchor': 'bottom'})
    for i,src in enumerate(sources):
        fig.add_layout_image(
                source=src,
                xref="paper",
                yref="paper",
                x=xpos[i],
                y=ypos[i],
                xanchor="center",
                yanchor="bottom",
                sizex=1,
                sizey=0.35,
            )
    st.plotly_chart(fig, use_container_width=True)

def month_dat(mo: str, yr:str):
    df_monthly = monthly_subset(df_v2, mo, yr)
    if len(df_monthly) > 0:
        st.metric('Total time listened',secs_2_hr_min(df_monthly.duration_s.sum()))
        #need to fix this for if there are multiple modes, need to generalize the find_mode() function
        som = multimode(df_monthly['song_name'])[0]
        st.metric('Song of the month',f"{som} by {df_monthly[df_monthly.song_name == som].artist_name.iloc[0]}")

        albom = multimode(df_monthly['album_name'])[0]
        st.metric('Album of the Month',albom)
        # album_uri = df_v2[df_v2.album_name == albom].artist_uri.iloc[0]
        # album = spotify.artist_albums(album_uri, album_type='album')
        # st.image(album["items"][0]["images"][0]["url"],width=200)
        
        #pie_chart(df_v2)
        if len(df_monthly.artist_name.unique()) > 2:
            artist_podium(df_monthly)
        elif len(df_monthly.artist_name.unique()) == 2:
            st.metric("Your artists of the month", df_monthly.artist_name.unique()[0] +' & '+ df_monthly.artist_name.unique()[1])
        else:
            st.metric("Your one and only artist of the month", df_monthly.artist_name.unique()[0])
        # create 2 pie charts with top 5 or 10 or 20 songs/genres
        # st.write('### Your top 10 songs and genres this month')
    else:
        st.write("## nothing yet...")
        pass
#------------------------------------------------------------------------------------------------------------------#
if option == 'Monthlies':
    #st.write(df_v2)
    #st.write(df)
    today = datetime.datetime.now()
    year = today.year
    year_of_interest = st.sidebar.text_input(label='Year here',value=str(year))
    st.write(f'# Your Spotify Seasonal Summaries for {year_of_interest}')
    winter,spring = st.columns(2)
    with winter:
        st.image("./images/winter.jpg",caption='Click below for a breakdown of your Winter listens',use_column_width='auto')
        dec = st.expander(label='December')
        with dec:
            month_dat('dec',year_of_interest)
        jan = st.expander(label='January')
        with jan:
            month_dat('jan',year_of_interest)
        feb = st.expander(label='February')
        with feb:
            month_dat('feb',year_of_interest)
        winter_playlist = st.expander(label='My Winter Mixtape')

    with spring:
        st.image("./images/spring.jpg",caption='Click below for a breakdown of your Spring listens',use_column_width='auto')
        mar = st.expander(label='March')
        with mar:
            #st.write('it march!')
            #st.write(monthly_subset(df_v2, 'mar', year_of_interest))
            month_dat('mar',year_of_interest)
        apr = st.expander(label='April')
        with apr:
            month_dat('apr',year_of_interest)
        may = st.expander(label='May')
        with may:
            month_dat('may',year_of_interest)
        spring_playlist = st.expander(label='My Spring Mixtape')

    summer,fall = st.columns(2)
    with summer:
        st.image("./images/summer.jpg",caption='Click below for a breakdown of your Summer listens',use_column_width='auto')
        jun = st.expander(label='June')
        with jun:
            month_dat('jun',year_of_interest)
        jul = st.expander(label='July')
        with jul:
            month_dat('jul',year_of_interest)
        aug = st.expander(label='August')
        with aug:
            month_dat('aug',year_of_interest)
        summer_playlist = st.expander(label='My Summer Mixtape')

    with fall:
        st.image("./images/fall.jpg",caption='Click below for a breakdown of your Fall listens',use_column_width='auto')
        sep = st.expander(label='September')
        with sep:
            month_dat('sep',year_of_interest)
        oct = st.expander(label='October')
        with oct:
            month_dat('oct',year_of_interest) 
        nov = st.expander(label='November')
        with nov:
            month_dat('nov',year_of_interest)
        fall_playlist = st.expander(label='My Fall Mixtape')

    
#------------------------------------------------------------------------------------------------------------------#
import altair as alt
# make it so use has to place their bet on an artist/song and at conclusion of race "award"/notify if correct!

# df_dados = pd.DataFrame(data=data, columns=['week_title','full_name','ranking_points','rank_number'])

# week_list = df_dados['week_title'].unique()

# bars = alt.Chart(df_dados).mark_bar().encode(
#   x=alt.X('1:Q',axis=alt.Axis(title='ATP Ranking Points')),
#   y=alt.Y('0:N',axis=alt.Axis(title='The Big Four'))
#   ).properties(
#       width=750,
#       height=400
#   )

# bar_plot = st.altair_chart(bars)

# def plot_bar_animated_altair(df, week):
#   bars = alt.Chart(df, title="Ranking as of week: "+week).mark_bar().encode(
#     x=alt.X('ranking_points:Q', axis=alt.Axis(title='ATP Ranking Points')),
#     y=alt.Y('full_name:N',axis=alt.Axis(title='The Big Four'),sort='-x'),
#     color=alt.Color('full_name:N', title='Players',  legend=alt.Legend(orient="left")), 
#     ).properties(
#         width=750, 
#         height=400
#     )
#   text = bars.mark_text(
#     align='left',
#     baseline='middle',
#     dx=0, # Nudges text to right so it doesn't appear on top of the bar
#     fontSize=20,
#     color='black'
#   ).encode(
#         text='ranking_points:Q'
#   )


#   return bars + text


# if st.button('Let\'s race!'):
#   for week in week_list:
#     weekly_df = df_dados[df_dados['week_title']==week]       
#     bars = plot_bar_animated_altair(weekly_df, week)
#     time.sleep(0.5) 
#     bar_plot.altair_chart(bars)

#------------------------------------------------------------------------------------------------------------------#
# bar chart race, time machine (where did your music transport you this year? (capture genre as well as time period) ex: 'this year you were livin your best 80's rockstar life','you were living in your own musical','nothing like the present, you caught all the newest tunes and lived in the music moment')
if option == 'Year wrapped':
    today = datetime.datetime.now()
    year = today.year
    woohoo = st.expander(f'Happy end of {year}! Let\'s unwrap your spotify year of music 🎁 [click me]')
    #st.write(f'{today.month, today.day}')
    if today.month == 12 and today.day == 31:
        add_sb = st.sidebar.selectbox('what would you like to see?', ('stuff','more stuff','other stuff','surprise me'))
        with woohoo:
            st.balloons()
            st.write('# Cheers to a year of great music! 🥂')
            # bcr.bar_chart_race(df = df, 
            #        n_bars = 6, 
            #        sort='desc',
            #        title='Top artist')
            if add_sb == 'surprise me':
                my_bar = st.progress(0)
                for percent_complete in range(100):
                    time.sleep(0.1)
                    my_bar.progress(percent_complete + 1)

            c1,c2,c3 = st.columns(3)
            with c1:
                st.write('can i put this column here plz?')
            with c2:
                st.write('col no. 2 yes pls')
            with c3:
                st.write('what\'s we gonn put here..')
    elif today.month == 12 and today.day != 31:
        with woohoo:
            st.write(f'# End of {year} coming soon...')
            # historicals = st.button('Click me for a peek into the past')
            # if historicals:
            #     st.write('which year?')
    elif today.month == 1:
        with woohoo:
            st.write('# The new year has just begun!')
    elif 1 < today.month <= 4:
        with woohoo:
            st.write('# Patience...it\'s only spring!')
    elif 4 < today.month <= 8:
        with woohoo:
            st.write('# Patience...it\'s still summer!')
    else:
        with woohoo:
            st.write('# Not through the year just yet, hang in there!')

    # writedf, writedf_v2, merged_dfs= st.columns(3)
    # with writedf:
    #     st.write(df[['played_at','artist_name']])
    # with writedf_v2:
    #     st.write(df_v2)#[['played_at','artist_name']])
    # with merged_dfs:
    #     mergeddf = pd.concat([df[['played_at','artist_name']],df_v2[['played_at','artist_name']]],ignore_index=True)
    #     st.write(mergeddf)
    #     st.write(monthly_subset(mergeddf,'nov'))
#------------------------------------------------------------------------------------------------------------------#
