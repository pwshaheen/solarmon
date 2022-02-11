import requests, json
import time
import os
from datetime import datetime
import logging

from configparser import RawConfigParser
settings = RawConfigParser()
settings.read(os.path.dirname(os.path.realpath(__file__)) + '/solarmon.cfg')

token = settings.get('influxCloud', 'token')
org = settings.get('influxCloud', 'org')
bucket = settings.get('influxCloud', 'bucket')
cloudEnabled = settings.get('influxCloud', 'enabled')
cloudHost = settings.get('influxCloud', 'host')

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
with InfluxDBClient(url=cloudHost, token=token, org=org) as influxc:
    #influxc.create_database(db_name)
    write_api = influxc.write_api(write_options=SYNCHRONOUS)

from requests.structures import CaseInsensitiveDict
headers = CaseInsensitiveDict()
headers["Accept"] = "application/json"

logging.basicConfig(filename='solarforecast.log', encoding='utf-8', level=logging.INFO,format='%(asctime)s %(levelname)-8s %(message)s',datefmt='%Y-%m-%d %H:%M:%S')
try:

    url = requests.get("https://api.weather.gov/gridpoints/FFC/48,106/forecast",headers=headers)
    text = url.text
    data = json.loads(text)

    for key in data["properties"]["periods"]:
        info = [{
            'time': key["startTime"],
            'tag': 'Weather_Forecast',
            'measurement':'Weather_Forecast',
            "fields": {
                'name':key["name"],
                'temperature':key["temperature"],
                'windspeed':key["windSpeed"],
                'icon':key["icon"],
                'shortForecast':key["shortForecast"],
                'detailedForecast':key["detailedForecast"],
                'lastUpdated':data["properties"]["updated"]
            }
        }]

        write_api.write(bucket, org, info)
except Exception as err:
    logging.info('error with Weather API')
    logging.error(err)

url = requests.get("https://api.solcast.com.au/rooftop_sites/cc16-ed74-c2fa-627b/forecasts?format=json​&api_key=DfpNm1oxIUWhghz5Ja9C1ae7UmvXIhS4",headers=headers)
text = url.text
data = json.loads(text)


for key in data["forecasts"]:
    info = {                                    
            'SolarEstimate_watts': float(key["pv_estimate"])*1000,
            'SolarEstimate_kW': float(key["pv_estimate"])}  
    points = [{
    'time': key["period_end"],
    'tag': 'Solar_Forecast',
    'measurement':'Solar_Forecast',
    "fields": info
    }]
    write_api.write(bucket, org, points)