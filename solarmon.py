
#!/usr/bin/env python3

import time
import os
from datetime import datetime
import urllib.request
import logging

from configparser import RawConfigParser

from influxdb import InfluxDBClient
from pymodbus.client.sync import ModbusSerialClient as ModbusClient
from growatt import Growatt

setupSleep = 120

logging.basicConfig(filename='log.log', encoding='utf-8', level=logging.INFO,format='%(asctime)s %(levelname)-8s %(message)s',datefmt='%Y-%m-%d %H:%M:%S')
logging.info('Waiting 60 seconds for internet connection and influxDB to establish')
time.sleep(setupSleep)

settings = RawConfigParser()
settings.read(os.path.dirname(os.path.realpath(__file__)) + '/solarmon.cfg')

interval = settings.getint('query', 'interval', fallback=1)
offline_interval = settings.getint('query', 'offline_interval', fallback=60)
error_interval = settings.getint('query', 'error_interval', fallback=60)
rebootEnabled = settings.getint('query', 'rebootEnabled', fallback=0)
rebootCount = settings.getint('query', 'rebootErrorCount', fallback=30)

localEnabled = settings.get('influx', 'enabled')
db_name = settings.get('influx', 'db_name', fallback='inverter')
measurement = settings.get('influx', 'measurement', fallback='inverter')



# Clients
logging.info('Setup InfluxDB Client... ')
influx = InfluxDBClient(host=settings.get('influx', 'host', fallback='localhost'),
                        port=settings.getint('influx', 'port', fallback=8086),
                        username=settings.get('influx', 'username', fallback=None),
                        password=settings.get('influx', 'password', fallback=None),
                        database=db_name)
influx.create_database(db_name)



# You can generate an API token from the "API Tokens Tab" in the UI
token = settings.get('influxCloud', 'token')
org = settings.get('influxCloud', 'org')
bucket = settings.get('influxCloud', 'bucket')
cloudEnabled = settings.get('influxCloud', 'enabled')
cloudHost = settings.get('influxCloud', 'host')

cloudError = 0
setupError = 1

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
with InfluxDBClient(url=cloudHost, token=token, org=org) as influxc:
    #influxc.create_database(db_name)
    #Cloud Influx Client which differs from Local One
    write_api = influxc.write_api(write_options=SYNCHRONOUS)
port = settings.get('solarmon', 'port', fallback='/dev/ttyUSB0')
#check if connected to internet

try:
    urllib.request.urlopen('http://google.com') 
    logging.info('Internet Connection Found...Enabling Cloud Write if Set.')
except:
    cloudEnabled = "0"
    logging.error('Internet Connection NOT Found...Disabling Cloud Write.')

while setupError > 0:
    try:
        client = ModbusClient(method='rtu', port=port, baudrate=9600, stopbits=1, parity='N', bytesize=8, timeout=5, strict=False)
        client.connect()
        logging.info('Loading inverters... ')
        inverters = []
        for section in settings.sections():
            if "inverters" in section:
                name = section[10:]
                unit = int(settings.get(section, 'unit'))
                measurement = settings.get(section, 'measurement')
                growatt = Growatt(client, name, unit)
                #growatt.print_info()
                inverters.append({
                    'error_sleep': 0,
                    'growatt': growatt,
                    'measurement': measurement
                })
        setupError = 0    
    except Exception as err:
        logging.error(err)
        logging.error('Error Loading Inverter Info.  Error Count ' + str(setupError))
        setupError = setupError + 1
        time.sleep(offline_interval)
        if setupError > rebootCount:
            logging.info('reached max error tolerance.  Rebooting Pi.')
            if rebootEnabled == 1:
                os.system('sudo reboot')
            else: 
                logging.info('reboot has been disabled.  Only resetting error counter.')
                setupError = 1

        continue
logging.info('Starting Monitoring Loop')
while True:
    try:

        online = False
        for inverter in inverters:
        # If this inverter errored then we wait a bit before trying again
            if inverter['error_sleep'] > 0:
                inverter['error_sleep'] -= interval
                continue

            growatt = inverter['growatt']
    except Exception as err:
        logging.error('Error loading Inverters ' + err)
    try:
        #logging.info('read')
        now = datetime.utcnow()
        info = growatt.read()
            #print(info)

        if info is None:
            continue

            # Mark that at least one inverter is online so we should continue collecting data
        online = True

        points = [{
            'time': now,
            'tag': inverter['measurement'],
            'measurement':'Growatt_Inverter',
            "fields": info
         }]
           

        if cloudEnabled == "1" and cloudError == 0:
            try:
                write_api.write(bucket, org, points)
            except Exception as err:
                cloudError=1
                logging.error('error writing to cloud ' + err)
                #print('writing to cloud')
            if localEnabled == "1":
                try:
                    influx.write_points(points, time_precision='s')
                except Exception as err:
                    logging.error('error writing to local card ' + err)
                
    except Exception as err:
        logging.error(growatt.name)
        logging.error(str(err))
        logging.error('there was an exception')
        #inverter['error_sleep'] = error_interval
        logging.info('Captured Error and increasing error count to ' + str(setupError))
        if rebootEnabled == 1 and setupError > rebootCount:
            logging.info('Rebooting')
            os.system('sudo reboot')
        else:
            logging.info('reboot not enabled.  Continuing')
            online=False    
        continue
    if online:
        time.sleep(interval)
    else:
        # If all the inverters are not online because no power is being generated then we sleep for 1 min
        time.sleep(offline_interval)
